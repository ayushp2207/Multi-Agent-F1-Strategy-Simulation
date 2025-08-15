# ui.py
import pandas as pd

def get_tire_info(compound):
    """Returns a single letter and color for a tire compound."""
    if 'SOFT' in str(compound):
        return 'S', '#FF3131'
    if 'MEDIUM' in str(compound):
        return 'M', '#FFF500'
    if 'HARD' in str(compound):
        return 'H', '#F0F0F0'
    if 'INTERMEDIATE' in str(compound):
        return 'I', '#43B02A'
    if 'WET' in str(compound):
        return 'W', '#0067A1'
    return 'U', '#808080' # Unknown

def format_interval(interval_td):
    """Formats a timedelta interval into a +S.ms string or 'Interval'."""
    if pd.isna(interval_td):
        return "Interval"
    
    seconds = interval_td.total_seconds()
    
    if seconds == 0.0:
        return "Interval"
    
    return f"+{seconds:.3f}"

def get_contrast_color(hex_color):
    """
    Calculates the best contrasting text color (black or white) for a given hex background.
    """
    hex_color = hex_color.lstrip('#')
    # Convert hex to RGB integers
    r, g, b = tuple(int(hex_color[i:i+2], 16) for i in (0, 2, 4))
    # Calculate the perceived brightness of the color
    luminance = (0.299 * r + 0.587 * g + 0.114 * b)
    # Return black for bright backgrounds, white for dark backgrounds
    return '#000000' if luminance > 140 else '#FFFFFF'

def format_lap_time(td):
    """Formats a timedelta object into a MM:SS.ms string."""
    if pd.isna(td):
        return "&nbsp;" # Use HTML non-breaking space for empty cells
    total_seconds = td.total_seconds()
    minutes = int(total_seconds // 60)
    seconds = int(total_seconds % 60)
    milliseconds = int((total_seconds - (minutes * 60) - seconds) * 1000)
    return f"{minutes}:{seconds:02d}.{milliseconds:03d}"

def get_team_color_style(team_name):
    """Returns a hex color code for a given F1 team."""
    team_colors = {
        "Mercedes": "#6CD3BF", "Red Bull Racing": "#3671C6", "Ferrari": "#F91536",
        "McLaren": "#F58020", "Aston Martin": "#358C75", "Alpine": "#2293D1",
        "AlphaTauri": "#5E8FAA", "Alfa Romeo": "#C92D4B", "Haas F1 Team": "#B6BABD",
        "Williams": "#37BEDD"
    }
    return team_colors.get(team_name, "#FFFFFF") # Default to white

def get_tire_temperature_color(temperature):
    """Returns color based on tire temperature (similar to F1 broadcast graphics)."""
    if temperature < 70:
        return "#0066FF"  # Blue - Cold
    elif temperature < 80:
        return "#00FFFF"  # Cyan - Cool
    elif temperature < 90:
        return "#00FF00"  # Green - Optimal
    elif temperature < 100:
        return "#FFFF00"  # Yellow - Warm
    elif temperature < 110:
        return "#FF9900"  # Orange - Hot
    else:
        return "#FF0000"  # Red - Overheating

def generate_f1_car_tire_display(tire_temps, driver_name):
    """Generates an F1 car tire temperature display similar to broadcast graphics."""
    fl_color = get_tire_temperature_color(tire_temps['FL'])
    fr_color = get_tire_temperature_color(tire_temps['FR'])
    rl_color = get_tire_temperature_color(tire_temps['RL'])
    rr_color = get_tire_temperature_color(tire_temps['RR'])
    
    html = f"""
    <style>
        .car-container {{
            display: flex;
            flex-direction: column;
            align-items: center;
            background-color: #1a1a1a;
            padding: 20px;
            border-radius: 15px;
            font-family: 'Roboto', sans-serif;
            color: white;
            margin: 10px 0;
        }}
        .car-title {{
            font-size: 18px;
            font-weight: bold;
            margin-bottom: 15px;
            text-align: center;
        }}
        .car-body {{
            position: relative;
            width: 200px;
            height: 120px;
            background: linear-gradient(135deg, #2a2a2a, #404040);
            border-radius: 20px 20px 10px 10px;
            border: 2px solid #555;
            margin: 10px 0;
        }}
        .car-front {{
            position: absolute;
            top: -5px;
            left: 50%;
            transform: translateX(-50%);
            width: 60px;
            height: 10px;
            background-color: #666;
            border-radius: 5px 5px 0 0;
        }}
        .car-rear {{
            position: absolute;
            bottom: -5px;
            left: 50%;
            transform: translateX(-50%);
            width: 80px;
            height: 10px;
            background-color: #666;
            border-radius: 0 0 5px 5px;
        }}
        .tire {{
            position: absolute;
            width: 25px;
            height: 40px;
            border-radius: 5px;
            border: 2px solid #333;
            display: flex;
            align-items: center;
            justify-content: center;
            font-size: 10px;
            font-weight: bold;
            color: #000;
            text-shadow: 1px 1px 1px rgba(255,255,255,0.5);
        }}
        .tire-fl {{
            top: 10px;
            left: -15px;
            background-color: {fl_color};
        }}
        .tire-fr {{
            top: 10px;
            right: -15px;
            background-color: {fr_color};
        }}
        .tire-rl {{
            bottom: 10px;
            left: -15px;
            background-color: {rl_color};
        }}
        .tire-rr {{
            bottom: 10px;
            right: -15px;
            background-color: {rr_color};
        }}
        .temp-display {{
            display: grid;
            grid-template-columns: 1fr 1fr;
            gap: 10px;
            margin-top: 15px;
            width: 100%;
            max-width: 200px;
        }}
        .temp-item {{
            background-color: #2a2a2a;
            padding: 8px;
            border-radius: 8px;
            text-align: center;
            font-size: 12px;
        }}
        .temp-value {{
            font-size: 14px;
            font-weight: bold;
            margin-bottom: 2px;
        }}
        .temp-label {{
            font-size: 10px;
            color: #aaa;
        }}
        .legend {{
            display: flex;
            justify-content: space-between;
            margin-top: 15px;
            font-size: 10px;
            width: 100%;
            max-width: 200px;
        }}
        .legend-item {{
            display: flex;
            align-items: center;
            gap: 3px;
        }}
        .legend-color {{
            width: 8px;
            height: 8px;
            border-radius: 50%;
        }}
    </style>
    
    <div class="car-container">
        <div class="car-title">{driver_name} - Tire Temperatures</div>
        
        <div class="car-body">
            <div class="car-front"></div>
            <div class="car-rear"></div>
            
            <div class="tire tire-fl">{tire_temps['FL']}°</div>
            <div class="tire tire-fr">{tire_temps['FR']}°</div>
            <div class="tire tire-rl">{tire_temps['RL']}°</div>
            <div class="tire tire-rr">{tire_temps['RR']}°</div>
        </div>
        
        <div class="temp-display">
            <div class="temp-item">
                <div class="temp-value" style="color: {fl_color};">{tire_temps['FL']}°C</div>
                <div class="temp-label">Front Left</div>
            </div>
            <div class="temp-item">
                <div class="temp-value" style="color: {fr_color};">{tire_temps['FR']}°C</div>
                <div class="temp-label">Front Right</div>
            </div>
            <div class="temp-item">
                <div class="temp-value" style="color: {rl_color};">{tire_temps['RL']}°C</div>
                <div class="temp-label">Rear Left</div>
            </div>
            <div class="temp-item">
                <div class="temp-value" style="color: {rr_color};">{tire_temps['RR']}°C</div>
                <div class="temp-label">Rear Right</div>
            </div>
        </div>
        
        <div class="legend">
            <div class="legend-item">
                <div class="legend-color" style="background-color: #0066FF;"></div>
                <span>Cold</span>
            </div>
            <div class="legend-item">
                <div class="legend-color" style="background-color: #00FF00;"></div>
                <span>Optimal</span>
            </div>
            <div class="legend-item">
                <div class="legend-color" style="background-color: #FFFF00;"></div>
                <span>Warm</span>
            </div>
            <div class="legend-item">
                <div class="legend-color" style="background-color: #FF0000;"></div>
                <span>Hot</span>
            </div>
        </div>
    </div>
    """
    
    return html

def generate_leaderboard_html_broadcast(leaderboard_data):
    """Generates a broadcast-style animated HTML leaderboard."""
    html = """
    <style>
        .tower-container {
            display: flex;
            flex-direction: column;
            gap: 3px;
            font-family: 'Roboto', sans-serif;
            background-color: #1E1E1E;
            padding: 10px;
            border-radius: 10px;
        }
        .driver-row {
            display: grid;
            grid-template-columns: 25px 90px 1fr 30px; /* Pos, Driver, Interval, Tire */
            align-items: center;
            padding: 5px 10px;
            background-color: #383838;
            border-left: 5px solid transparent;
            color: #EFEFEF;
            transition: all 0.7s ease-in-out;
            order: var(--order);
        }
        .pos { font-weight: 700; font-size: 14px; }
        .driver-name { font-weight: 900; font-size: 18px; }
        .interval {
            justify-self: right;
            font-family: 'monospace';
            font-size: 16px;
            font-weight: 500;
            color: #B0B0B0;
        }
        .tire {
            display: flex;
            justify-content: center;
            align-items: center;
            width: 22px;
            height: 22px;
            border-radius: 50%;
            font-weight: 700;
            font-size: 14px;
            justify-self: right;
        }
    </style>
    <div class="tower-container">
    """
    
    for _, row in leaderboard_data.iterrows():
        position = int(row['Position'])
        driver_name = row['Driver']
        interval_str = format_interval(row['Interval'])
        tire_letter, tire_color = get_tire_info(row['Compound'])
        team_color = row['TeamColor'] # Assumes 'TeamColor' is passed in
        
        html += f"""
        <div class="driver-row" style="--order: {position}; border-left-color: #{team_color};">
            <div class="pos">{position}</div>
            <div class="driver-name">{driver_name}</div>
            <div class="interval">{interval_str}</div>
            <div class="tire" style="background-color: {tire_color}; color: black;">{tire_letter}</div>
        </div>
        """
        
    html += "</div>"
    return html