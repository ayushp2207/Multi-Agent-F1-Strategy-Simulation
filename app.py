# app.py
import streamlit as st
import time
import pandas as pd
import plotly.express as px
from data import load_session_data
from ui import generate_leaderboard_html_broadcast, format_lap_time, generate_f1_car_tire_display
from agents import RaceEngineerAgent # Import the agent
from agents import llm_config
from agents import (
    RaceEngineerAgent, WeatherForecasterAgent, TireExpertAgent,
    RivalAnalystAgent, ChiefStrategistAgent, DecisionAnalystAgent, is_termination_msg
)
import os
from PIL import Image
import autogen
import base64
from helpers import (
    analyze_user_decision, run_agent_discussions_with_interruption, initialize_session_state, display_agent_message_with_typing,
    initialize_session_state, check_strategy_triggers, run_agent_discussions, display_radio_conversation, get_radio_message_for_lap, set_page_background )

def generate_simulated_temp(tire_position):
    """Generate realistic simulated tire temperatures"""
    # Get current compound to base temperature on
    try:
        current_lap_data = laps.loc[(laps['LapNumber'] == st.session_state.current_lap) & (laps['Driver'] == st.session_state.managed_driver)]
        if not current_lap_data.empty:
            compound = current_lap_data.iloc[0]['Compound']
            tire_life = current_lap_data.iloc[0]['TyreLife']
            
            # Base temperature by compound
            if 'SOFT' in str(compound):
                base_temp = 95
            elif 'MEDIUM' in str(compound):
                base_temp = 90
            else:  # HARD
                base_temp = 85
            
            # Temperature variations by position
            position_offset = {'FL': 2, 'FR': 4, 'RL': -1, 'RR': 3}
            
            # Tire life effect (older tires run hotter)
            age_effect = int(tire_life) * 0.5 if pd.notna(tire_life) else 0
            
            # Lap-based variation
            lap_variation = (st.session_state.current_lap % 7) * 2
            
            return int(base_temp + position_offset[tire_position] + age_effect + lap_variation)
    except:
        pass
    
    # Ultimate fallback
    base_temps = {'FL': 88, 'FR': 92, 'RL': 85, 'RR': 90}
    return base_temps[tire_position] + (st.session_state.current_lap % 5)

def update_tire_temperatures():
    """Updates tire temps using session.car_data with proper error handling."""
    try:
        # Get the driver number for the managed driver
        driver_abbr = st.session_state.managed_driver
        driver_info = session.results.loc[session.results['Abbreviation'] == driver_abbr].iloc[0]
        driver_number = str(driver_info['DriverNumber'])

        # Access the telemetry for that specific car from the car_data dictionary
        if driver_number in session.car_data:
            car_telemetry = session.car_data[driver_number]
            
            # Filter the telemetry data for the current lap
            lap_telemetry = car_telemetry.loc[car_telemetry['LapNumber'] == st.session_state.current_lap]

            if not lap_telemetry.empty:
                # Get the last reading of the lap and update the state
                latest_temps = lap_telemetry.iloc[-1]
                
                # Extract temperatures with fallback
                fl_temp = latest_temps.get('TyreTempFL', 0)
                fr_temp = latest_temps.get('TyreTempFR', 0)
                rl_temp = latest_temps.get('TyreTempRL', 0)
                rr_temp = latest_temps.get('TyreTempRR', 0)
                
                st.session_state.tire_temperatures = {
                    'FL': int(fl_temp) if pd.notna(fl_temp) and fl_temp > 0 else generate_simulated_temp('FL'),
                    'FR': int(fr_temp) if pd.notna(fr_temp) and fr_temp > 0 else generate_simulated_temp('FR'),
                    'RL': int(rl_temp) if pd.notna(rl_temp) and rl_temp > 0 else generate_simulated_temp('RL'),
                    'RR': int(rr_temp) if pd.notna(rr_temp) and rr_temp > 0 else generate_simulated_temp('RR')
                }
                return
        
        # Fallback to simulation if no telemetry data
        st.session_state.tire_temperatures = {
            'FL': generate_simulated_temp('FL'),
            'FR': generate_simulated_temp('FR'),
            'RL': generate_simulated_temp('RL'),
            'RR': generate_simulated_temp('RR')
        }

    except Exception as e:
        # Generate simulated temperatures if everything fails
        st.session_state.tire_temperatures = {
            'FL': generate_simulated_temp('FL'),
            'FR': generate_simulated_temp('FR'),
            'RL': generate_simulated_temp('RL'),
            'RR': generate_simulated_temp('RR')
        }

# --- Control Functions ---
def start_simulation():
    st.session_state.simulation_running = True
    st.session_state.current_lap = 1
    st.session_state.simulation_phase = 'normal'
    st.session_state.strategy_chat_history = {}
    st.session_state.strategy_choice = None

def stop_simulation():
    st.session_state.simulation_running = False
    st.session_state.current_lap = 0
    st.session_state.simulation_phase = 'normal'

def advance_lap():
    if st.session_state.current_lap < total_laps:
        st.session_state.current_lap += 1
        st.session_state.simulation_phase = 'normal'
        st.session_state.choice_processed = False
        st.session_state.discussion_completed = False  # Reset for next lap
    else:
        stop_simulation()
        st.success("Race Finished!")

# --- Page Configuration ---
st.set_page_config(page_title="Project Pit Wall | F1 Strategy", layout="wide")

# Initialize session state
initialize_session_state()

if st.session_state.show_guide:
    set_page_background('F1.avif')

    # CSS for the container and text styling
    st.markdown("""
        <style>
        .guide-container {
            background-color: rgba(10, 10, 10, 0.75);
            backdrop-filter: blur(15px);
            border-radius: 25px;
            padding: 2rem 3rem;
            border: 1px solid rgba(255, 255, 255, 0.1);
            color: #FFFFFF !important; /* Force all text inside to be white */
        }
        .guide-container h2 {
            font-size: 2.5rem; /* Larger headers */
            font-weight: 700;
            text-shadow: 0px 0px 10px rgba(0,0,0,0.5);
            text-align: center;
        }
        .guide-container p {
            font-size: 1.1rem;
            font-weight: 400;
            text-align: left; /* Left-align paragraphs for readability */
        }
        .guide-container b {
            color: #1ED760; /* A cool accent color for bolded text */
        }
        </style>
    """, unsafe_allow_html=True)

    # Use columns to center the guide box on the page
    _, center_col, _ = st.columns([1, 2, 1])
    with center_col:
        
        html_content = ""

        # Page 1: Introduction
        if st.session_state.guide_page == 1:
            html_content = """
                <h2>Welcome to the Pit Wall 🏎️</h2>
                <p>You're not just a spectator anymore. You are the <b>Team Principal</b>.
                This simulator drops you into the hot seat of F1 strategy. Your calls, your pressure, your victory. This isn't just a simulation; it's a real-time test of your strategic nerve against historical race data.</p>
            """

        # Page 2: How to Start
        elif st.session_state.guide_page == 2:
            html_content = """
                <h2>Step 1: The Pre-Race Briefing 📋</h2>
                <p>Configure your simulation in the sidebar. Choose the <b>Year</b>, <b>Race</b>, and your chosen <b>Driver</b>.
                When you're ready, hit <b>▶️ Start Simulation</b> and go lights out.</p>
            """
        
        # Page 3: The Dashboard Explained
        elif st.session_state.guide_page == 3:
            html_content = """
                <h2>Step 2: Reading the Race 📊</h2>
                <p>Your live dashboard is your eyes on the track. Monitor the <b>Timing Tower</b>, your driver's <b>Tire Status</b>, and gaps to <b>Rivals</b>. Every piece of data is a clue.</p>
            """

        # Page 4: Strategy Decisions
        elif st.session_state.guide_page == 4:
            html_content = """
                <h2>Step 3: It's Your Call ⚔️</h2>
                <p>When the race pauses, your AI Pit Wall will report in. Your <b>Chief Strategist</b> will present two paths: <b>Plan A</b> and <b>Plan B</b>. There's no right answer, only consequences. Make the call.</p>
            """

        # Render the entire guide box with all its text content in one go
        st.markdown(f'<div class="guide-container">{html_content}</div>', unsafe_allow_html=True)

        
        st.write("") # Spacer
        nav_col1, nav_col2, nav_col3 = st.columns([1, 1, 1])
        with nav_col1:
            if st.session_state.guide_page > 1:
                if st.button("⬅️ Back", use_container_width=True):
                    st.session_state.guide_page -= 1
                    st.rerun()
        with nav_col3:
            if st.session_state.guide_page < 4:
                if st.button("Next ➡️", type="primary", use_container_width=True):
                    st.session_state.guide_page += 1
                    st.rerun()
            elif st.session_state.guide_page == 4:
                if st.button("Engage 🏁", type="primary", use_container_width=True):
                    st.session_state.show_guide = False
                    st.rerun()

else:
    set_page_background('F1.avif')

    st.markdown("""
    <style>
    /* Target ONLY the main page container, not the sidebar */
    div[data-testid="stAppViewContainer"] {
        color: white;
    }

    /* Target headers ONLY inside the main page container */
    div[data-testid="stAppViewContainer"] h1,
    div[data-testid="stAppViewContainer"] h2,
    div[data-testid="stAppViewContainer"] h3,
    div[data-testid="stAppViewContainer"] h4,
    div[data-testid="stAppViewContainer"] h5,
    div[data-testid="stAppViewContainer"] h6 {
        color: white !important;
    }

    /* Metric widgets are only on the main page, so this is fine */
    div[data-testid="stMetricLabel"], div[data-testid="stMetricValue"] {
        color: white !important;
    }

    /* --- ADD THIS NEW RULE --- */
    /* Force sidebar headers back to black */
    div[data-testid="stSidebarUserContent"] h1,
    div[data-testid="stSidebarUserContent"] h2,
    div[data-testid="stSidebarUserContent"] h3,
    div[data-testid="stSidebarUserContent"] h4,
    div[data-testid="stSidebarUserContent"] h5,
    div[data-testid="stSidebarUserContent"] h6 {
        color: black !important;
    }
    </style>
    """, unsafe_allow_html=True)
    
    # --- Main Application ---
    st.title("Project Pit Wall 🏎️")
    st.markdown("### Live Race Simulation Dashboard")

    # --- Sidebar for Session Selection ---
    st.sidebar.header("Race Selection")
    year = st.sidebar.selectbox("Select Year", [2023, 2022, 2021], index=0)
    races = ["Bahrain", "Jeddah", "Monaco", "Silverstone", "Monza", "Suzuka", "Las Vegas"]
    race_name = st.sidebar.selectbox("Select Race", races, index=0)

    # --- Load Data ---
    try:
        session, laps = load_session_data(year, race_name, 'R')
        total_laps = int(laps['LapNumber'].max())
        driver_list = session.results['Abbreviation'].unique().tolist()
        default_driver_index = driver_list.index('HAM') if 'HAM' in driver_list else 0
        managed_driver = st.sidebar.selectbox("Select Driver to Manage", driver_list, index=default_driver_index)
    except Exception as e:
        st.error(f"Could not load data for {year} {race_name}. Error: {e}")
        st.stop()

    st.session_state.managed_driver = managed_driver


    # --- Sidebar Controls ---
    st.sidebar.header("Simulation Control")

    if st.session_state.simulation_running:
        if st.sidebar.button("⏹️ Stop Simulation"):
            stop_simulation()
            st.rerun()
    else:
        if st.sidebar.button("▶️ Start Simulation"):
            start_simulation()
            st.rerun()

    # --- Main Dashboard Placeholders ---
    header_placeholder = st.empty()
    event_placeholder = st.empty()

    # Create main layout
    col1, col2, col3 = st.columns([2, 1, 2])
    with col1:
        leaderboard_placeholder = st.empty()
    with col2:
        driver_panel_placeholder = st.empty()
    with col3:
        plot_placeholder = st.empty()

    # Strategy phase placeholders - separate for each phase
    strategy_discussion_placeholder = st.empty()
    outcome_placeholder = st.empty()

    # Sidebar elements
    st.sidebar.header("Team Radio 📻")
    radio_placeholder = st.sidebar.empty()
    dialog_placeholder = st.sidebar.empty()

    # --- MAIN SIMULATION LOGIC ---
    if st.session_state.simulation_running:
        lap_num = st.session_state.current_lap
        
        # Pre-calculate Tire Degradation Model
        degradation_model = {}
        for compound in laps['Compound'].unique():
            compound_laps = laps[laps['Compound'] == compound]
            if not compound_laps.empty:
                degradation_model[compound] = round(compound_laps['LapTime'].dt.total_seconds().std() * 0.1, 3)

        # Get current lap data
        current_lap_data = laps.loc[laps['LapNumber'] == lap_num]
        lap_start_time = current_lap_data['LapStartTime'].min() if not current_lap_data.empty else None

        # --- PHASE CONTROL LOGIC ---
        if st.session_state.simulation_phase == 'normal':
            # Check for strategy triggers
            trigger_reasons = check_strategy_triggers(lap_num, current_lap_data, session, laps, lap_start_time)
            # --- NEW: Detect interruption context (SC / VSC / Rain) and store it BEFORE running agent discussions ---
            interruption = None
            try:
                if not current_lap_data.empty and 'TrackStatus' in current_lap_data.columns:
                    track_status = str(current_lap_data['TrackStatus'].iloc[0])
                    if track_status in ['4', '5']:
                        interruption = "Safety Car / Red Flag"
                    elif track_status in ['6', '7']:
                        interruption = "Virtual Safety Car"

                # Rain detection (reuse existing weather logic)
                if pd.notna(lap_start_time) and hasattr(session, 'weather_data'):
                    try:
                        weather_data = session.weather_data.loc[session.weather_data['Time'] <= lap_start_time]
                        if (not weather_data.empty) and weather_data.iloc[-1].get('Rainfall'):
                            interruption = "Rainfall / Wet Track"
                    except Exception:
                        # ignore weather parsing errors
                        pass
            except Exception:
                interruption = None

            # Store interruption to session_state so downstream code (run_agent_discussions wrapper) can use it
            st.session_state['current_interruption'] = interruption

            # Store interruption in session state so downstream functions can access it
            if interruption:
                st.session_state['current_interruption'] = interruption
                # Add it to trigger reasons only if it's not a generic periodic trigger
                if interruption not in trigger_reasons:
                    trigger_reasons.append(interruption)
            else:
                # clear previous interruption if none currently detected
                st.session_state['current_interruption'] = None

            update_tire_temperatures()

            if (lap_num % 10 == 0 or lap_num % 10 == 3 or lap_num % 10 == 7) and st.session_state.last_radio_lap != lap_num:
                # Get driver position for context
                driver_lap_data_df = laps.loc[(laps['LapNumber'] == lap_num) & (laps['Driver'] == managed_driver)]
                if not driver_lap_data_df.empty:
                    driver_position = int(driver_lap_data_df.iloc[0]['Position']) if pd.notna(driver_lap_data_df.iloc[0]['Position']) else 10
                    
                    # Get radio message
                    radio_msg = get_radio_message_for_lap(lap_num, total_laps, driver_position)
                    
                    # Display radio conversation
                    with radio_placeholder.container():
                        display_radio_conversation(
                            radio_placeholder, 
                            radio_msg["engineer"], 
                            radio_msg["driver"], 
                            managed_driver
                        )
                    
                    st.session_state.last_radio_lap = lap_num
            else:
                # Show empty radio when no conversation
                with radio_placeholder.container():
                    st.markdown(
                        """
                        <div style="
                            background-color: #1a1a1a;
                            padding: 15px;
                            border-radius: 8px;
                            text-align: center;
                            color: #666;
                            font-style: italic;
                        ">
                            📻 Team Radio - Standby
                        </div>
                        """, 
                        unsafe_allow_html=True
                    )

            # Display trigger info in sidebar
            if trigger_reasons:
                st.sidebar.write("🛑 Triggered by:", ", ".join(trigger_reasons))
            else:
                st.sidebar.write("✅ No trigger this lap")
            
            if st.session_state.get('current_interruption'):
                st.sidebar.warning(f"Interruption detected: {st.session_state['current_interruption']}")
            
            # If triggers found and we haven't processed this lap yet
            if trigger_reasons and st.session_state.last_strategy_lap != lap_num:
                st.session_state.last_strategy_lap = lap_num
                st.session_state.simulation_phase = 'strategy_discussion'
                st.session_state.discussion_completed = False  # Reset discussion flag
                st.rerun()
        
        elif st.session_state.simulation_phase == 'strategy_discussion':
            # Only run agent discussions if not already completed
            if not st.session_state.discussion_completed:
                with st.spinner("Pit wall is deliberating..."):
                    agent_responses = run_agent_discussions(laps, session, lap_num, managed_driver)

                    # Use the wrapper to ensure interruption context is attached
                    interruption = st.session_state.get('current_interruption', None)
                    agent_responses = run_agent_discussions_with_interruption(laps, session, lap_num, managed_driver, interruption=interruption)
                    st.session_state.strategy_chat_history = agent_responses
                    st.session_state.discussion_completed = True  # Mark as completed
                    
                    # Update tire temperatures for the car display
                    update_tire_temperatures()
                
            # Move to awaiting choice phase
            st.session_state.simulation_phase = 'awaiting_choice'
            st.rerun()
        
        elif st.session_state.simulation_phase == 'awaiting_choice' or st.session_state.simulation_phase == 'chosen':

            st.markdown("""
        <style>
        /* Find the specific columns where the buttons are placed */
        div[data-testid="stHorizontalBlock"] button {
            /* Initial State: White button, black text */
            background-color: #FFFFFF !important;
            color: #000000 !important;
            border: 2px solid #FFFFFF !important;
            border-radius: 10px;
            font-weight: bold;
            transition: all 0.3s ease-in-out; /* Smooth transition effect */
        }
        
        /* Hover State: Transparent button, white text */
        div[data-testid="stHorizontalBlock"] button:hover {
            background-color: transparent !important;
            color: #FFFFFF !important;
            border-color: #FFFFFF !important;
        }
        </style>
        """, unsafe_allow_html=True)

            if st.session_state.simulation_phase == 'awaiting_choice':
                with strategy_discussion_placeholder.container():
                    st.markdown("---")
                    st.title("⚔️ PIT WALL STRATEGY REVIEW")
                    st.markdown("---")

                    # Create two main columns: Left for agent boxes, Right for leaderboard and car
                    left_col, right_col = st.columns([3, 2])
                    
                    with left_col:
                        st.markdown("### Team Communications")
                        
                        # Create 2x2 grid for agent messages
                        agent_row1_col1, agent_row1_col2 = st.columns(2)
                        agent_row2_col1, agent_row2_col2 = st.columns(2)

                        agent_containers = [
                            (agent_row1_col1, "Race Engineer", "🔧"),
                            (agent_row1_col2, "Tire Expert", "🏎️"),
                            (agent_row2_col1, "Weather Forecaster", "🌤️"),
                            (agent_row2_col2, "Rival Analyst", "🎯")
                        ]

                        # Display agent messages with typewriter effect sequentially
                        for container, agent_name, icon in agent_containers:
                            if agent_name in st.session_state.strategy_chat_history:
                                message_content = st.session_state.strategy_chat_history[agent_name]
                                display_agent_message_with_typing(container, agent_name, icon, message_content)

                        # Chief Strategist with typewriter effect
                        st.markdown("---")
                        st.markdown("**👑 Chief Strategist - Strategic Options**")
                        if "Chief Strategist" in st.session_state.strategy_chat_history:
                            chief_placeholder = st.empty()
                            chief_content = st.session_state.strategy_chat_history["Chief Strategist"]
                            
                            # Typewriter for Chief Strategist
                            typed_text = ""
                            for word in chief_content.split(" "):
                                typed_text += word + " "
                                chief_placeholder.markdown(
                                    f"""
                                    <div style="
                                        background-color: #1a472a;
                                        color: #FFFFFF;
                                        padding: 15px;
                                        border-radius: 8px;
                                        border-left: 4px solid #4CAF50;
                                        margin: 10px 0;
                                        font-size: 14px;
                                    ">
                                        {typed_text}<span style="opacity: 0.7;">|</span>
                                    </div>
                                    """, 
                                    unsafe_allow_html=True
                                )
                                time.sleep(0.03)
                            
                            # Final version
                            chief_placeholder.markdown(
                                f"""
                                <div style="
                                    background-color: #1a472a;
                                    color: #FFFFFF;
                                    padding: 15px;
                                    border-radius: 8px;
                                    border-left: 4px solid #4CAF50;
                                    margin: 10px 0;
                                    font-size: 14px;
                                ">
                                    {typed_text.strip()}
                                </div>
                                """, 
                                unsafe_allow_html=True
                            )
                        
                        st.markdown("---")
                        st.subheader("Your Decision, Team Principal")

                        colA, colB = st.columns(2)
                        if colA.button("Execute Plan A", use_container_width=True, key=f"plan_a_{lap_num}"):
                            st.session_state.strategy_choice = 'A'
                            st.session_state.simulation_phase = 'showing_outcome'
                            strategy_discussion_placeholder.empty()
                            st.rerun()
                        if colB.button("Execute Plan B", use_container_width=True, key=f"plan_b_{lap_num}"):
                            st.session_state.strategy_choice = 'B'
                            st.session_state.simulation_phase = 'showing_outcome'
                            strategy_discussion_placeholder.empty()
                            st.rerun()

                    with right_col:
                        st.markdown("### Current Race Situation")
                        
                        # Show current leaderboard (paused at this lap)
                        leaderboard_data = laps.loc[laps['LapNumber'] == lap_num][['Driver', 'Position', 'Time', 'Compound', 'TeamColor']]
                        valid_leaderboard = leaderboard_data.dropna(subset=['Position']).sort_values(by='Position')
                        
                        if not valid_leaderboard.empty:
                            valid_leaderboard['Time'] = pd.to_timedelta(valid_leaderboard['Time'])
                            valid_leaderboard['Interval'] = valid_leaderboard['Time'].diff()
                            leaderboard_html = generate_leaderboard_html_broadcast(valid_leaderboard)
                            st.html(leaderboard_html)
                        
                        st.markdown("---")
                        st.markdown(f"### {managed_driver} - Car Status")
                        
                        # Show F1 car tire temperature display
                        car_html = generate_f1_car_tire_display(st.session_state.tire_temperatures, managed_driver)
                        st.html(car_html)

                # Don't render normal dashboard when in this phase
                st.session_state.simulation_phase = 'chosen'
                st.stop()
            else:
                colA, colB = st.columns(2)
                if colA.button("Execute Plan A", use_container_width=True, key=f"plan_a_{lap_num}"):
                            st.session_state.strategy_choice = 'A'
                            st.session_state.simulation_phase = 'showing_outcome'
                            strategy_discussion_placeholder.empty()
                            st.rerun()
                if colB.button("Execute Plan B", use_container_width=True, key=f"plan_b_{lap_num}"):
                            st.session_state.strategy_choice = 'B'
                            st.session_state.simulation_phase = 'showing_outcome'
                            strategy_discussion_placeholder.empty()
                            st.rerun()
        
        elif st.session_state.simulation_phase == 'showing_outcome' or st.session_state.simulation_phase == 'shown':

            plan_a_image_path = os.path.join("plana.gif")   # image to show when decision is correct (Plan A)
            plan_b_image_path = os.path.join("planb.gif")   # image to show when decision is incorrect (Plan B)

            if st.session_state.simulation_phase == 'showing_outcome':
                # First time entering this phase: produce paragraphs via the LLM
                if not st.session_state.choice_processed:
                    st.session_state.strategy_log.append((lap_num, st.session_state.strategy_choice))

                    with st.spinner("Analyzing your strategic decision with the Decision Analyst..."):
                        try:
                            paragraphs = analyze_user_decision(
                                laps, session, lap_num, managed_driver,
                                st.session_state.strategy_choice,
                                st.session_state.strategy_chat_history
                            )
                        except Exception as e:
                            paragraphs = [f"Analysis failed to run: {e}"]

                        if not isinstance(paragraphs, (list, tuple)):
                            paragraphs = [str(paragraphs)]

                        st.session_state.outcome_paragraphs = paragraphs
                        st.session_state.choice_processed = True

                # Now render the result + image
                with outcome_placeholder.container():
                    st.markdown("---")
                    st.title("📊 DECISION IMPACT ANALYSIS")
                    st.markdown("---")

                    paragraphs = st.session_state.get('outcome_paragraphs', [])

                    # Decide which image to show (Plan A is treated as historical/correct)
                    user_choice = st.session_state.get('strategy_choice', None)

                    def _show_image(path):
                        """
                        Show image resizing it to half the original width.
                        For GIFs: determine original width via PIL, then stream raw bytes to st.image
                        with a width parameter so the animation is preserved and scaled.
                        For static images: resize via PIL to maintain quality.
                        """
                        if not os.path.exists(path):
                            return False
                        lower = path.lower()
                        try:
                            if lower.endswith('.gif'):
                                # Read raw bytes and embed as base64 <img> so GIF animation is preserved.
                                # Use CSS to display the GIF at ~50% width (adjust style as needed).
                                try:
                                    with open(path, "rb") as f:
                                        b64 = base64.b64encode(f.read()).decode("utf-8")
                                    html = f'<img src="data:image/gif;base64,{b64}" style="width:75%; height:auto; display:block; margin:auto;" />'
                                    st.markdown(html, unsafe_allow_html=True)
                                    return True
                                except Exception:
                                    # fallback to direct st.image as a last resort
                                    with open(path, "rb") as f:
                                        st.image(f.read(), use_column_width=False)
                                    return True
                            else:
                                # Static image: open and resize via PIL preserving aspect ratio
                                img = Image.open(path)
                                orig_w, orig_h = img.size
                                half_w = max(100, int(orig_w // 2))
                                new_h = max(1, int(orig_h * (half_w / orig_w)))
                                resized = img.resize((half_w, new_h), Image.LANCZOS)
                                st.image(resized, use_container_width =False)
                            return True
                        except Exception:
                            # fallback to default st.image behavior
                            try:
                                st.image(path, use_container_width =False)
                                return True
                            except Exception:
                                return False

                    # Show image (if available) above the analysis
                    if user_choice == 'A':
                        candidate = os.path.join("plana.gif")
                        if not os.path.exists(candidate):
                            candidate = os.path.join("plana.jpg")
                        _show_image(candidate)
                    else:
                        candidate = os.path.join("planb.gif")
                        if not os.path.exists(candidate):
                            candidate = os.path.join("planb.jpg")
                        _show_image(candidate)

                    full_text = "\n\n".join(paragraphs) if paragraphs else "No analysis available."
                    block_placeholder = st.empty()
                    typed = ""
                    # Typewriter per character for the full message
                    for ch in full_text:
                        typed += ch
                        # convert newlines to <br> for HTML display
                        html_text = typed.replace("\n", "<br>")
                        block_placeholder.markdown(
                            f"""
                            <div style="
                                background-color: #0b1220;
                                color: #eaf2fb;
                                padding: 16px;
                                border-radius: 10px;
                                margin: 8px 0;
                                font-size: 14px;
                                line-height:1.5;
                            ">
                                {html_text}<span style="opacity:0.6">|</span>
                            </div>
                            """,
                            unsafe_allow_html=True
                        )
                        # you can tune speed here (increase to slow down)
                        time.sleep(0.008)

                    # Replace with final text without caret
                    final_html = full_text.replace("\n", "<br>")
                    block_placeholder.markdown(
                        f"""
                        <div style="
                            background-color: #0b1220;
                            color: #eaf2fb;
                            padding: 16px;
                            border-radius: 10px;
                            margin: 8px 0;
                            font-size: 14px;
                            line-height:1.5;
                        ">
                            {final_html}
                        </div>
                        """,
                        unsafe_allow_html=True
                    )

                    # Continue button
                    if st.button("Continue Race", type="primary", use_container_width=True, key=f"continue_{lap_num}"):
                        # Clear placeholders/state and advance
                        st.session_state.outcome_paragraphs = []
                        st.session_state.outcome_text = ""
                        st.session_state.choice_processed = False
                        strategy_discussion_placeholder.empty()
                        outcome_placeholder.empty()
                        advance_lap()
                        st.rerun()

                # After first render mark the phase as 'shown' so a refresh doesn't re-run analysis
                st.session_state.simulation_phase = 'shown'
                st.stop()

            else:
                # If we're already in 'shown' (user refreshed / re-entered), just advance when Continue pressed
                st.session_state.outcome_paragraphs = []
                st.session_state.outcome_text = ""
                st.session_state.choice_processed = False
                strategy_discussion_placeholder.empty()
                outcome_placeholder.empty()
                advance_lap()
                st.rerun()
                
        # --- NORMAL DASHBOARD RENDERING (only in 'normal' phase) ---
        if st.session_state.simulation_phase == 'normal':
            # Event Detection
            with event_placeholder.container():
                if not current_lap_data.empty:
                    track_status = current_lap_data['TrackStatus'].iloc[0]
                    if track_status in ['4', '5']: 
                        st.error("⚠️ SAFETY CAR / RED FLAG", icon="🚨")
                    elif track_status in ['6', '7']: 
                        st.warning("🟡 VIRTUAL SAFETY CAR", icon="⚠️")
                    
                    if pd.notna(lap_start_time):
                        weather_data = session.weather_data.loc[session.weather_data['Time'] <= lap_start_time]
                        if not weather_data.empty and weather_data.iloc[-1]['Rainfall']: 
                            st.info("🌧️ RAIN DETECTED", icon="💧")

            # Header
            with header_placeholder.container():
                st.subheader(f"Lap {lap_num}/{total_laps}")

            # Leaderboard
            with leaderboard_placeholder.container():
                st.markdown("##### Timing Tower")
                
                leaderboard_data = laps.loc[laps['LapNumber'] == lap_num][['Driver', 'Position', 'Time', 'Compound', 'TeamColor']]
                valid_leaderboard = leaderboard_data.dropna(subset=['Position']).sort_values(by='Position')

                if not valid_leaderboard.empty:
                    valid_leaderboard['Time'] = pd.to_timedelta(valid_leaderboard['Time'])
                    valid_leaderboard['Interval'] = valid_leaderboard['Time'].diff()
                    leaderboard_html = generate_leaderboard_html_broadcast(valid_leaderboard)
                    st.html(leaderboard_html)

            # Driver Panel
            with driver_panel_placeholder.container():
                driver_lap_data_df = laps.loc[(laps['LapNumber'] == lap_num) & (laps['Driver'] == managed_driver)]
                if not driver_lap_data_df.empty:
                    driver_lap_data = driver_lap_data_df.iloc[0]
                    driver_pos = driver_lap_data['Position']
                    st.subheader(f"Managing: {managed_driver}")
                    status = "IN PIT" if pd.isna(driver_pos) else "Racing"
                    st.metric("Status", status)
                    if status == "Racing":
                        st.metric("Position", int(driver_pos))
                    
                    st.markdown("---")
                    
                    # Tire Expert Panel
                    st.subheader("Tire Expert Intel")
                    current_compound = driver_lap_data['Compound']
                    
                    if pd.notna(driver_lap_data['TyreLife']):
                        tyre_age = int(driver_lap_data['TyreLife'])
                        degradation = degradation_model.get(current_compound, 0.150)
                        predicted_lifespan = max(0, 25 - tyre_age) if 'SOFT' in str(current_compound) else max(0, 35 - tyre_age)
                        
                        st.metric(f"{current_compound} Tire Status", f"{tyre_age} Laps Old")
                        st.write(f"Predicted Remaining Laps: **{predicted_lifespan}**")
                        st.write(f"Est. Time Loss/Lap: **{degradation}s**")
                    else:
                        st.metric(f"{current_compound} Tire Status", "Data Unavailable")

                    st.markdown("---")

                    # Rival Analyst Panel
                    st.subheader("Rival Analyst Intel")
                    if status == "Racing" and not valid_leaderboard.empty:
                        car_ahead = valid_leaderboard[valid_leaderboard['Position'] == driver_pos - 1]
                        car_behind = valid_leaderboard[valid_leaderboard['Position'] == driver_pos + 1]
                        
                        gap_ahead_str = "Clear Track"
                        if not car_ahead.empty:
                            gap_ahead_str = f"{car_ahead.iloc[0]['Driver']} (+{round(2.5 + (lap_num % 4) * 0.1, 1)}s)"

                        gap_behind_str = "Clear Track"
                        if not car_behind.empty:
                            gap_behind_str = f"{car_behind.iloc[0]['Driver']} (-{round(1.5 + (lap_num % 3) * 0.1, 1)}s)"
                        
                        st.metric("Car Ahead", gap_ahead_str)
                        st.metric("Car Behind", gap_behind_str)

                    st.markdown("---")

                    # Strategy Simulation Panel
                    st.subheader("Strategy Simulation")
                    pit_stop_time_loss = 23
                    predicted_rejoin_pos = int(driver_pos + 5) if status == "Racing" else "N/A"
                    
                    st.metric("Pit Stop Time Loss", f"~{pit_stop_time_loss} seconds")
                    st.metric("Predicted Re-join Position", f"P{predicted_rejoin_pos}")

                    

            # Plot
            with plot_placeholder.container():
                if not valid_leaderboard.empty:
                    top_5_drivers = valid_leaderboard.head(5)['Driver'].tolist()
                    plot_data = laps[laps['Driver'].isin(top_5_drivers) & (laps['LapNumber'] <= lap_num)][['Driver', 'LapNumber', 'LapTime']]
                    if not plot_data.empty:
                        plot_data['LapTimeSeconds'] = plot_data['LapTime'].dt.total_seconds()
                        fig = px.line(plot_data, x='LapNumber', y='LapTimeSeconds', color='Driver', 
                                    labels={'LapNumber': 'Lap', 'LapTimeSeconds': 'Lap Time (s)'})
                        st.plotly_chart(fig, use_container_width=True)
                    
                    st.markdown("---")
                    car_html = generate_f1_car_tire_display(st.session_state.tire_temperatures, managed_driver)
                    st.html(car_html)

            # Advance lap after a delay (only in normal phase)
            time.sleep(2)
            advance_lap()
            st.rerun()