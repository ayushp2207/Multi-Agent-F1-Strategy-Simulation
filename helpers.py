import streamlit as st
import time
import pandas as pd
import plotly.express as px
from data import load_session_data
from ui import generate_leaderboard_html_broadcast, format_lap_time, generate_f1_car_tire_display
from agents import RaceEngineerAgent # Import the agent
from agents import llm_config
from agents import (
    RaceEngineerAgent, WeatherForecasterAgent, TireExpertAgent, DecisionAnalystAgent,
    RivalAnalystAgent, ChiefStrategistAgent, is_termination_msg
)
import autogen
import re


def typewriter_generator_single(text: str, delay: float = 0.05):
    """A generator function that yields words from a single text with a delay."""
    # Handle if the item is a dict from an agent message
    if isinstance(text, dict) and 'content' in text:
        content = text['content']
    else:
        content = str(text)
        
    # Yield word by word
    for word in content.split(" "):
        yield word + " "
        time.sleep(delay)

def display_agent_message_with_typing(container, agent_name, icon, message_content, delay=0.02):
    """Display agent message with typewriter effect"""
    placeholder = container.empty()
    
    # Show "thinking" state
    placeholder.markdown(
        f"""
        <div style="
            background-color: #2d2d2d;
            color: #FFFFFF;
            padding: 10px;
            border-radius: 8px;
            border-left: 4px solid #ff6b6b;
            margin: 5px 0;
            font-size: 12px;
            min-height: 140px;
        ">
            <div style="font-weight: bold; margin-bottom: 8px; padding-bottom: 5px; border-bottom: 1px solid #444;">
                {icon} {agent_name}
            </div>
            <div>
                <span style="opacity: 0.5;">Analyzing data...</span>
            </div>
        </div>
        """, 
        unsafe_allow_html=True
    )
    
    time.sleep(0.5)
    
    # Type out the message
    typed_text = ""
    words = message_content.split()
    for i, word in enumerate(words):
        typed_text += word + " "
        placeholder.markdown(
            f"""
            <div style="
                background-color: #2d2d2d;
                color: #FFFFFF;
                padding: 10px;
                border-radius: 8px;
                border-left: 4px solid #ff6b6b;
                margin: 5px 0;
                font-size: 12px;
                min-height: 140px;
            ">
                <div style="font-weight: bold; margin-bottom: 8px; padding-bottom: 5px; border-bottom: 1px solid #444;">
                    {icon} {agent_name}
                </div>
                <div>
                    {typed_text}{"▌" if i < len(words)-1 else ""}
                </div>
            </div>
            """, 
            unsafe_allow_html=True
        )
        time.sleep(delay)

def build_strategy_prompts(laps_df, session_obj, current_lap, driver_abbr):
    """Gathers data and builds a dictionary of targeted prompts for each agent."""
    driver_lap_data = laps_df.loc[(laps_df['LapNumber'] == current_lap) & (laps_df['Driver'] == driver_abbr)].iloc[0]
    position = driver_lap_data['Position']
    tyre_life = int(driver_lap_data['TyreLife']) if pd.notna(driver_lap_data['TyreLife']) else 0
    compound = driver_lap_data['Compound']
    
    next_lap_data = laps_df.loc[(laps_df['LapNumber'] == current_lap + 1) & (laps_df['Driver'] == driver_abbr)]
    historic_pit_stop = "No"
    if not next_lap_data.empty and pd.notna(next_lap_data.iloc[0]['PitInTime']):
        historic_pit_stop = f"Yes, pitted for {next_lap_data.iloc[0]['Compound']} tires."

    lap_start_time = driver_lap_data['LapStartTime']
    future_weather_df = session_obj.weather_data[session_obj.weather_data['Time'] > lap_start_time]
    rain_msg = "No rain expected in the next few laps."
    if not future_weather_df.empty and future_weather_df['Rainfall'].any():
        rain_time = future_weather_df[future_weather_df['Rainfall']].iloc[0]['Time']
        rain_lap_df = laps_df[laps_df['LapStartTime'] >= rain_time]
        if not rain_lap_df.empty:
            rain_lap = int(rain_lap_df.iloc[0]['LapNumber'])
            rain_msg = f"Rain is possible around lap {rain_lap}."

    leaderboard = laps_df.loc[laps_df['LapNumber'] == current_lap].sort_values(by='Position')
    rivals_df = leaderboard[
        (leaderboard['Position'].between(position - 5, position + 5)) & (leaderboard['Position'] != position)
    ]
    rivals_df = rivals_df.dropna(subset=['Position', 'TyreLife'])
    rival_intel_lines = [f"- P{int(r['Position'])} {r['Driver']} on {r['Compound']} ({int(r['TyreLife'])} laps old)." for _, r in rivals_df.iterrows()]
    rival_intel = "\n".join(rival_intel_lines)
    
    # Create a dictionary of prompts
    prompts = {
        "RaceEngineerAgent": f"Driver: {driver_abbr}, Position: P{int(position)}, Lap: {current_lap}. Give your standard technical update.",
        "TireExpertAgent": f"Driver: {driver_abbr} is on {compound} tires that are {tyre_life} laps old. Report on wear, degradation, and temperature.",
        "WeatherForecasterAgent": f"Current forecast is: {rain_msg}. Confirm the outlook.",
        "RivalAnalystAgent": f"Our driver {driver_abbr} is P{int(position)}. Nearby rivals:\n{rival_intel}\nAnalyze the immediate threats.",
        "ChiefStrategistAgent": {
            "briefing": f"You have received reports from your team. Your driver {driver_abbr} is P{int(position)} on {int(tyre_life)}-lap-old {compound} tires. The weather is clear.",
            "historical_fact": f"CRITICAL INFO: In the real race, did {driver_abbr} pit at the end of this lap? **{historic_pit_stop}**"
        }
    }
    return prompts

# --- Initialize Session State (Consolidated and Clean) ---
def initialize_session_state():
    """Initialize all session state variables in one place"""
    defaults = {
        'simulation_running': False,
        'current_lap': 0,
        'simulation_phase': 'normal',  # 'normal', 'strategy_discussion', 'awaiting_choice', 'showing_outcome'
        'strategy_chat_history': {},  # Changed to dict to store individual agent messages
        'strategy_choice': None,
        'strategy_log': [],
        'last_strategy_lap': 0,
        'predicted_rain_lap': None,
        'decision_mode': False,
        'decision_timer_start': 0,
        'pit_approved': None,
        'outcome_text': "",
        'choice_processed': False,
        'discussion_completed': False,  # NEW: Track if discussion is done for this lap
        'tire_temperatures': {'FL': 85, 'FR': 88, 'RL': 82, 'RR': 86},  # Mock tire temperatures
        'last_radio_lap': 0,
        'radio_conversation_active': False,
        'radio_messages_shown': [],  # Track which messages we've used
    }
    
    for key, default_value in defaults.items():
        if key not in st.session_state:
            st.session_state[key] = default_value

def check_strategy_triggers(lap_num, current_lap_data, session, laps, lap_start_time):
    """Check if any strategy triggers are active for this lap"""
    trigger_reasons = []
    
    # 1) 10-lap interval
    if lap_num > 1 and lap_num % 10 == 0:
        trigger_reasons.append(f"lap_interval({lap_num})")

    # 2) Safety Car / Red Flag
    if not current_lap_data.empty:
        status = current_lap_data['TrackStatus'].iloc[0]
        if status in ['4', '5']:
            trigger_reasons.append(f"track_status({status})")

    # 3) Rain forecast: only two laps before
    if pd.notna(lap_start_time):
        weather_slice = session.weather_data[session.weather_data['Time'] <= lap_start_time]
        if st.session_state.predicted_rain_lap is None and not weather_slice.empty and weather_slice['Rainfall'].any():
            rain_time = weather_slice[weather_slice['Rainfall']].iloc[0]['Time']
            rain_lap_df = laps[laps['LapStartTime'] >= rain_time]
            if not rain_lap_df.empty:
                rain_lap = int(rain_lap_df.iloc[0]['LapNumber'])
                st.session_state.predicted_rain_lap = rain_lap

        prl = st.session_state.predicted_rain_lap
        if prl and lap_num in [prl - 2, prl - 1]:
            trigger_reasons.append(f"rain_warning(lap {prl})")
    
    return trigger_reasons

def run_agent_discussions(laps, session, lap_num, managed_driver):
    """Run the agent discussions and return individual agent responses"""
    prompts = build_strategy_prompts(laps, session, lap_num, managed_driver)
    
    agent_responses = {}
    
    # Use a dictionary to explicitly link prompt keys to agents and their display names
    agent_map = {
        "RaceEngineerAgent": (RaceEngineerAgent, "Race Engineer"),
        "TireExpertAgent": (TireExpertAgent, "Tire Expert"),
        "WeatherForecasterAgent": (WeatherForecasterAgent, "Weather Forecaster"),
        "RivalAnalystAgent": (RivalAnalystAgent, "Rival Analyst")
    }
    
    # Get specialist reports by iterating through the map
    for prompt_key, (agent, display_name) in agent_map.items():
        ephemeral_proxy = autogen.UserProxyAgent(
            "EphemeralProxy", 
            human_input_mode="NEVER", 
            code_execution_config=False
        )
        # Use the reliable 'prompt_key' to get the message
        ephemeral_proxy.initiate_chat(recipient=agent, message=prompts[prompt_key], max_turns=1)
        report = ephemeral_proxy.last_message()
        agent_responses[display_name] = report['content']

    # Get Chief Strategist final decision
    reports_text = "\n".join([f"**{name} Report:**\n{content}\n" for name, content in agent_responses.items()])
    
    user_proxy = autogen.UserProxyAgent(
        name="TeamPrincipal",
        human_input_mode="NEVER",
        code_execution_config=False,
        is_termination_msg=is_termination_msg
    )
    
    chief_briefing = (
        f"{prompts['ChiefStrategistAgent']['briefing']}\n\n"
        f"{prompts['ChiefStrategistAgent']['historical_fact']}\n\n"
        f"---**CONSOLIDATED TEAM REPORTS**---\n{reports_text}"
        f"---**END OF REPORTS**---\n\n"
        "Chief Strategist, using all the above information, provide Plan A and Plan B."
    )

    user_proxy.initiate_chat(recipient=ChiefStrategistAgent, message=chief_briefing, max_turns=1)
    final_plan = user_proxy.last_message()
    agent_responses["Chief Strategist"] = final_plan['content']
    
    return agent_responses


def get_radio_messages():
    """Returns radio message templates for different lap ranges"""
    return {
        "early_race": [
            {"engineer": "How are the tires feeling?", "driver": "Good grip, car feels balanced."},
            {"engineer": "Keep pushing, you're doing great.", "driver": "Copy that, staying focused."},
            {"engineer": "Traffic ahead in sector 2.", "driver": "Understood, I see them."},
            {"engineer": "DRS available next lap.", "driver": "Perfect, I'll use it on the main straight."},
            {"engineer": "Your sector times are strong.", "driver": "The car is responding well today."}
        ],
        "mid_race": [
            {"engineer": "Tire degradation looking normal.", "driver": "Starting to feel some sliding in the rear."},
            {"engineer": "Gap to car behind is 3.2 seconds.", "driver": "Roger, keeping an eye on mirrors."},
            {"engineer": "Weather radar shows clear skies.", "driver": "Good, let's stick to the plan."},
            {"engineer": "Your lap times are consistent.", "driver": "Yeah, finding a good rhythm here."},
            {"engineer": "Pit window opens in 8 laps.", "driver": "Copy, let me know when to push."}
        ],
        "late_race": [
            {"engineer": "15 laps remaining, stay focused.", "driver": "Understood, giving it everything."},
            {"engineer": "Tires are holding up well.", "driver": "Still got some grip left."},
            {"engineer": "P{} car is 2 seconds behind.", "driver": "I can see him, defending position."},
            {"engineer": "Great job managing the tires.", "driver": "Thanks, let's bring it home."},
            {"engineer": "Final 10 laps, keep it clean.", "driver": "Copy that, staying concentrated."}
        ]
    }

def get_radio_message_for_lap(lap_num, total_laps, driver_position):
    """Get appropriate radio message based on race phase"""
    messages = get_radio_messages()
    
    # Determine race phase
    race_progress = lap_num / total_laps
    if race_progress < 0.33:
        phase_messages = messages["early_race"]
    elif race_progress < 0.66:
        phase_messages = messages["mid_race"]
    else:
        phase_messages = messages["late_race"]
    
    # Pick a random message and customize if needed
    import random
    message = random.choice(phase_messages)
    
    # Replace position placeholders
    if "{}" in message.get("engineer", ""):
        message["engineer"] = message["engineer"].format(driver_position + 1)
    
    return message

def display_radio_conversation(radio_placeholder, engineer_msg, driver_msg, driver_abbr):
    """Display radio conversation with typing effect"""
    
    # Clear and show engineer message first
    radio_placeholder.markdown(
        f"""
        <div style="
            background-color: #1a1a1a;
            padding: 10px;
            border-radius: 8px;
            margin: 5px 0;
            border-left: 3px solid #00ff00;
        ">
            <div style="color: #00ff00; font-size: 12px; margin-bottom: 5px;">
                📻 RACE ENGINEER
            </div>
            <div style="color: white; font-size: 14px;">
                Connecting...
            </div>
        </div>
        """, 
        unsafe_allow_html=True
    )
    
    time.sleep(0.5)
    
    # Type engineer message
    typed_engineer = ""
    for word in engineer_msg.split():
        typed_engineer += word + " "
        radio_placeholder.markdown(
            f"""
            <div style="
                background-color: #1a1a1a;
                padding: 10px;
                border-radius: 8px;
                margin: 5px 0;
                border-left: 3px solid #00ff00;
            ">
                <div style="color: #00ff00; font-size: 12px; margin-bottom: 5px;">
                    📻 RACE ENGINEER
                </div>
                <div style="color: white; font-size: 14px;">
                    {typed_engineer}▌
                </div>
            </div>
            """, 
            unsafe_allow_html=True
        )
        time.sleep(0.03)
    
    # Complete engineer message
    radio_placeholder.markdown(
        f"""
        <div style="
            background-color: #1a1a1a;
            padding: 10px;
            border-radius: 8px;
            margin: 5px 0;
            border-left: 3px solid #00ff00;
        ">
            <div style="color: #00ff00; font-size: 12px; margin-bottom: 5px;">
                📻 RACE ENGINEER
            </div>
            <div style="color: white; font-size: 14px;">
                {typed_engineer.strip()}
            </div>
        </div>
        """, 
        unsafe_allow_html=True
    )
    
    time.sleep(1.0)
    
    # Add driver response
    radio_placeholder.markdown(
        f"""
        <div style="
            background-color: #1a1a1a;
            padding: 10px;
            border-radius: 8px;
            margin: 5px 0;
            border-left: 3px solid #00ff00;
        ">
            <div style="color: #00ff00; font-size: 12px; margin-bottom: 5px;">
                📻 RACE ENGINEER
            </div>
            <div style="color: white; font-size: 14px;">
                {typed_engineer.strip()}
            </div>
        </div>
        <div style="
            background-color: #1a1a1a;
            padding: 10px;
            border-radius: 8px;
            margin: 5px 0;
            border-left: 3px solid #ff6b35;
        ">
            <div style="color: #ff6b35; font-size: 12px; margin-bottom: 5px;">
                🏎️ {driver_abbr}
            </div>
            <div style="color: white; font-size: 14px;">
                Responding...
            </div>
        </div>
        """, 
        unsafe_allow_html=True
    )
    
    time.sleep(0.5)
    
    # Type driver response
    typed_driver = ""
    for word in driver_msg.split():
        typed_driver += word + " "
        radio_placeholder.markdown(
            f"""
            <div style="
                background-color: #1a1a1a;
                padding: 10px;
                border-radius: 8px;
                margin: 5px 0;
                border-left: 3px solid #00ff00;
            ">
                <div style="color: #00ff00; font-size: 12px; margin-bottom: 5px;">
                    📻 RACE ENGINEER
                </div>
                <div style="color: white; font-size: 14px;">
                    {typed_engineer.strip()}
                </div>
            </div>
            <div style="
                background-color: #1a1a1a;
                padding: 10px;
                border-radius: 8px;
                margin: 5px 0;
                border-left: 3px solid #ff6b35;
            ">
                <div style="color: #ff6b35; font-size: 12px; margin-bottom: 5px;">
                    🏎️ {driver_abbr}
                </div>
                <div style="color: white; font-size: 14px;">
                    {typed_driver}▌
                </div>
            </div>
            """, 
            unsafe_allow_html=True
        )
        time.sleep(0.03)
    
    # Final complete conversation
    radio_placeholder.markdown(
        f"""
        <div style="
            background-color: #1a1a1a;
            padding: 10px;
            border-radius: 8px;
            margin: 5px 0;
            border-left: 3px solid #00ff00;
        ">
            <div style="color: #00ff00; font-size: 12px; margin-bottom: 5px;">
                📻 RACE ENGINEER
            </div>
            <div style="color: white; font-size: 14px;">
                {typed_engineer.strip()}
            </div>
        </div>
        <div style="
            background-color: #1a1a1a;
            padding: 10px;
            border-radius: 8px;
            margin: 5px 0;
            border-left: 3px solid #ff6b35;
        ">
            <div style="color: #ff6b35; font-size: 12px; margin-bottom: 5px;">
                🏎️ {driver_abbr}
            </div>
            <div style="color: white; font-size: 14px;">
                {typed_driver.strip()}
            </div>
        </div>
        """, 
        unsafe_allow_html=True
    )

def run_agent_discussions_with_interruption(laps, session, lap_num, managed_driver, interruption=None):
    """
    Wrapper around run_agent_discussions(...) that ensures the interruption context is attached
    to the returned agent messages. This keeps the original run_agent_discussions implementation
    intact while guaranteeing agents downstream (esp. DecisionAnalyst) receive the interruption.
    """
    # Call the existing function (assumes it exists in this module)
    try:
        agent_responses = run_agent_discussions(laps, session, lap_num, managed_driver)
    except Exception as e:
        # If the original fails, return a minimal fallback dict
        agent_responses = {"Race Engineer": "No response", "Tire Expert": "No response", "Weather Forecaster": "No response", "Rival Analyst": "No response", "Chief Strategist": "No response"}

    # Attach interruption context into the returned dict so analyze_user_decision can pick it up
    if interruption:
        agent_responses['InterruptionContext'] = interruption

    return agent_responses


def analyze_user_decision(laps, session, lap_num, managed_driver, user_choice, agent_context):
    """
    Use the DecisionAnalyst LLM to produce a paragraph-style analysis.
    Returns: list[str]  -> a list of paragraphs (strings) in order to be shown sequentially.
    """
    import pandas as pd
    import re
    from agents import DecisionAnalystAgent

    # helper normalizer (keeps/extends your earlier normalizer)
    def _normalize_agent_response_to_text(resp):
        import ast, re
        if resp is None:
            return ""
        # If list, take assistant message or first item
        if isinstance(resp, (list, tuple)):
            for item in resp:
                if isinstance(item, dict) and item.get("role") == "assistant" and item.get("content"):
                    resp = item
                    break
            else:
                resp = resp[0] if len(resp) > 0 else resp

        # extract content
        content = None
        if isinstance(resp, dict):
            content = resp.get("content") or resp.get("message") or resp.get("text") or str(resp)
        else:
            content = getattr(resp, "content", None) or getattr(resp, "text", None) or getattr(resp, "message", None) or str(resp)

        # if looks like dict-string, try parse
        if isinstance(content, str) and content.strip().startswith("{") and ("'content'" in content or '"content"' in content):
            try:
                parsed = ast.literal_eval(content)
                if isinstance(parsed, dict):
                    content = parsed.get("content") or parsed.get("message") or parsed.get("text") or str(parsed)
            except Exception:
                pass

        content = "" if content is None else str(content).strip()

        # Clean extraneous object wrappers (simple)
        content = re.sub(r"^\s*Assistant Response:\s*", "", content, flags=re.I)

        return content

    try:
        # --- Build contextual info (same as you did earlier) ---
        current_lap_data = laps.loc[laps['LapNumber'] == lap_num]
        driver_data = laps.loc[(laps['LapNumber'] == lap_num) & (laps['Driver'] == managed_driver)]

        if driver_data.empty:
            driver_position = "Unknown"
            tire_info = "Unknown"
            tire_age = "Unknown"
        else:
            driver_row = driver_data.iloc[0]
            driver_position = f"P{int(driver_row['Position'])}" if pd.notna(driver_row['Position']) else "Pit Lane"
            tire_info = str(driver_row['Compound']) if pd.notna(driver_row['Compound']) else "Unknown"
            tire_age = f"{int(driver_row['TyreLife'])} laps" if pd.notna(driver_row['TyreLife']) else "Unknown"

        total_laps = int(laps['LapNumber'].max()) if 'LapNumber' in laps.columns else 0
        race_progress = f"{lap_num}/{total_laps} ({round((lap_num/total_laps*100),1) if total_laps else 0}%)"

        # Compute a simple historical choice (you already mark A as historical)
        # We keep your original heuristic but force Plan A = historical by default if you'd prefer
        historical_choice = 'A'  # your convention: Plan A == historical
        interruption_note = ""
        try:
            interruption = None
            if isinstance(agent_context, dict):
                interruption = agent_context.get('InterruptionContext') or agent_context.get('interruption') or None

            if interruption:
                # Make a short, prominent section for the LLM prompt
                interruption_note = f"\nINTERRUPTION CONTEXT:\n- {interruption}\n\n"
        except Exception:
            interruption_note = ""
        
        # Build the team communications excerpt but exclude the interruption key so it doesn't duplicate
        communications_lines = []
        if isinstance(agent_context, dict):
            for agent, message in agent_context.items():
                if agent in ('InterruptionContext', 'interruption'):
                    continue
                try:
                    # truncate long messages for prompt brevity
                    if isinstance(message, str) and len(message) > 300:
                        communications_lines.append(f"- {agent}: {message[:300]}...")
                    else:
                        communications_lines.append(f"- {agent}: {message}")
                except Exception:
                    communications_lines.append(f"- {agent}: (unreadable message)")
        else:
            # Fallback: try to stringify
            try:
                communications_lines = [f"- {str(agent_context)[:400]}"]
            except:
                communications_lines = ["- No agent communications available"]

        communications_text = chr(10).join(communications_lines)

        # --- Build a detailed prompt for the DecisionAnalyst LLM ---
        # We ask the LLM to produce paragraph-format reasoning and to tailor responses
        analysis_prompt = f"""
You are an expert Formula 1 Decision Analyst. Use the following race context and team communications to produce a **clear, human-friendly, paragraph-based** explanation about the user's decision.

Important:
- Plan A is the historically executed plan for this race; Plan B is an alternative that was NOT taken.
- The user does NOT know which plan is historical. Determine whether the user's choice (Plan {user_choice}) **matches** the historical choice (Plan {historical_choice}) and explain accordingly.
- **If an INTERRUPTION CONTEXT is provided below, treat it as the highest-priority factor**: begin your response by stating how the interruption (Safety Car / VSC / Rain) changed the strategy options and why it influenced the historical decision. Then continue to explain the rest of the reasoning.
- If the user chose the historical plan, explain **why that plan was correct** in this context (use evidence from the race context and agent communications).
- If the user chose the non-historical plan, explain **why that choice was risky or suboptimal**, and under what circumstances it could be a valid alternative.
- Provide **3–4 concise paragraphs**, each paragraph focused (validation; strategic reasoning; choice analysis; practical lessons). Avoid long bullet lists. Keep language accessible to newcomers.
- Do NOT include extra meta-text at the end like "I'm done". Finish with the final paragraph.

RACE CONTEXT:
- Event: {session.event.get('EventName', 'Unknown')} {session.event.get('EventDate', '')}
- Lap: {race_progress}
- Driver: {managed_driver} — Position: {driver_position}
- Tyres: {tire_info} — Age: {tire_age}
- Track/Weather: determined from session data if available.

{interruption_note}TEAM COMMUNICATIONS (short excerpts):
{communications_text}

TASK:
Write 3–4 paragraphs that:
1) Start with a short validation sentence: whether Plan {user_choice} **is** or **is not** the historically-chosen plan. NOTE Plan B is NOT historical. Plan A is.
2) If an interruption context was provided, open with a short paragraph that explains *how* the interruption (e.g. Safety Car / Rain) affected the team's decision space and why it drove or removed certain options.
3) Explain the strategic reasons the historical team chose Plan {historical_choice}, citing tyre/track/position or communications.
4) If the user diverged, explain the concrete risks of that divergence and when it *could* be viable.
5) Conclude with a paragraph of practical lessons the user can take away about F1 strategy.

Return plain text only (no JSON or dict wrappers).
"""
        # Call the DecisionAnalyst LLM
        decision_analyst = DecisionAnalystAgent
        raw_response = decision_analyst.generate_reply([{"role": "user", "content": analysis_prompt}])

        # Normalize to text
        outcome_text = _normalize_agent_response_to_text(raw_response)

        # If the LLM returned nothing usable, fallback to raw string
        if not outcome_text:
            try:
                outcome_text = str(raw_response)
            except:
                outcome_text = f"Decision analysis returned no text for Plan {user_choice}."

        # Split into paragraphs (preserve order); remove empty fragments
        paragraphs = [p.strip() for p in re.split(r'\n{2,}', outcome_text) if p.strip()]

        # If only one long paragraph, try splitting by sentence groups to make display nicer
        if len(paragraphs) == 1:
            # split on periods followed by two spaces/newline or on newline
            sent_groups = re.split(r'(?<=\.)\s{2,}|\n', paragraphs[0])
            sent_groups = [s.strip() for s in sent_groups if s.strip()]
            # limit the groups to max 5 to avoid too many tiny paragraphs
            if 1 < len(sent_groups) <= 5:
                paragraphs = sent_groups

        return paragraphs

    except Exception as e:
        # Fallback: single paragraph error message
        return [f"Decision analysis failed to generate a response due to error: {e}"]
