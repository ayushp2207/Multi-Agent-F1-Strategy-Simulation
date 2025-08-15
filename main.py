import streamlit as st
import fastf1 as ff1
import pandas as pd
import os
import time
import plotly.express as px

# --- Page Configuration ---
st.set_page_config(
    page_title="Project Pit Wall | F1 Live Strategy",
    layout="wide",
    initial_sidebar_state="expanded",
)

# --- Helper Function for Precise Lap Time Formatting ---
def format_lap_time(td):
    """Formats a timedelta object into a MM:SS.ms string."""
    if pd.isna(td):
        return "N/A"
    # total_seconds() gives a float, e.g., 96.543
    total_seconds = td.total_seconds()
    minutes = int(total_seconds // 60)
    seconds = int(total_seconds % 60)
    milliseconds = int((total_seconds - (minutes * 60) - seconds) * 1000)
    return f"{minutes}:{seconds:02d}.{milliseconds:03d}"

# --- Caching Functions ---
@st.cache_data
def load_session_data(year, race, session_type):
    """Loads and returns the session data, with caching."""
    cache_dir = 'fastf1_cache'
    if not os.path.exists(cache_dir):
        os.makedirs(cache_dir)
    ff1.Cache.enable_cache(cache_dir)
    
    print(f"Loading data for {year} {race} {session_type}...")
    session = ff1.get_session(year, race, session_type)
    session.load()
    print("Data loaded.")
    return session

# --- Main Application ---
st.title("Project Pit Wall 🏎️")
st.markdown("A Live Multi-Agent F1 Strategy Simulation")

# --- Sidebar ---
st.sidebar.header("Race Selection")
year = st.sidebar.selectbox("Select Year", [2024, 2023, 2022], index=1)
# A more extensive list of races for better selection
races = ["Bahrain", "Jeddah", "Melbourne", "Baku", "Miami", "Monaco", "Barcelona", "Montreal", "Spielberg", "Silverstone", "Budapest", "Spa-Francorchamps", "Zandvoort", "Monza", "Singapore", "Suzuka", "Lusail", "Austin", "Mexico City", "São Paulo", "Las Vegas", "Yas Marina"]
race_name = st.sidebar.selectbox("Select Race", races, index=0)


# --- Load Data ---
try:
    session = load_session_data(year, race_name, 'R')
    laps = session.laps
    total_laps = int(laps['LapNumber'].max())
except Exception as e:
    st.error(f"Error loading data for {year} {race_name}. Please choose another race. Details: {e}")
    st.stop()

# --- Main Dashboard Placeholders ---
header_placeholder = st.empty()
leaderboard_placeholder = st.empty()
plot_placeholder = st.empty()

# --- Main Replay Loop ---
st.sidebar.header("Simulation Control")
start_button = st.sidebar.button("Start Race Simulation")

if start_button:
    for lap_num in range(1, total_laps + 1):
        with header_placeholder.container():
            current_lap_data_header = laps.loc[laps['LapNumber'] == lap_num]
            lap_start_time = current_lap_data_header['LapStartTime'].min()
            weather_data = session.weather_data.loc[session.weather_data['Time'] <= lap_start_time].iloc[-1]
            sc_status = "No Safety Car"
            if 'SC' in str(current_lap_data_header['TrackStatus'].unique()):
                sc_status = "⚠️ SAFETY CAR DEPLOYED"
            
            col1, col2, col3, col4 = st.columns(4)
            col1.metric("Lap", f"{lap_num}/{total_laps}")
            col2.metric("Track Status", sc_status)
            col3.metric("Air Temp", f"{weather_data['AirTemp']} °C")
            col4.metric("Track Temp", f"{weather_data['TrackTemp']} °C")

        with leaderboard_placeholder.container():
            st.subheader("Leaderboard")
            leaderboard_data = laps.loc[laps['LapNumber'] == lap_num][['Driver', 'Position', 'LapTime', 'Compound', 'TyreLife']].sort_values(by='Position')
            
            # *** THIS IS THE KEY CHANGE ***
            # Apply our custom formatting function to the 'LapTime' column
            leaderboard_data['LapTime'] = leaderboard_data['LapTime'].apply(format_lap_time)
            
            leaderboard_data = leaderboard_data.rename(columns={'TyreLife': 'Tire Age (Laps)'})
            st.dataframe(leaderboard_data.set_index('Position'), height=385)

        with plot_placeholder.container():
            st.subheader("Lap Time Comparison")
            top_5_drivers = laps.loc[laps['LapNumber'] == lap_num].nsmallest(5, 'Position')['Driver'].tolist()
            lap_time_data = laps[laps['Driver'].isin(top_5_drivers) & (laps['LapNumber'] <= lap_num)][['Driver', 'LapNumber', 'LapTime']]
            lap_time_data['LapTimeSeconds'] = lap_time_data['LapTime'].dt.total_seconds()
            
            fig = px.line(lap_time_data, x='LapNumber', y='LapTimeSeconds', color='Driver',
                          title="Lap Times for Top 5 Drivers", labels={'LapNumber': 'Lap', 'LapTimeSeconds': 'Lap Time (s)'})
            st.plotly_chart(fig, use_container_width=True)

        time.sleep(3)

    st.success("Race Simulation Finished!")