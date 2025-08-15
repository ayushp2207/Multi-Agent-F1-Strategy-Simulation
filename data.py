# data.py
import streamlit as st
import fastf1 as ff1
import os
import pandas as pd

@st.cache_data(ttl=3600)
def load_session_data(year, race, session_type):
    """Loads session data, ensuring telemetry is included."""
    cache_dir = 'fastf1_cache'
    if not os.path.exists(cache_dir):
        os.makedirs(cache_dir)
    ff1.Cache.enable_cache(cache_dir)
    
    session = ff1.get_session(year, race, session_type)
    
    # CORRECT: This loads the data needed for session.car_data
    session.load(telemetry=True) 
    
    laps = session.laps
    drivers_info = session.results[['DriverNumber', 'Abbreviation', 'TeamName', 'TeamColor']].rename(columns={'Abbreviation': 'Driver'})
    laps = pd.merge(laps, drivers_info, on=['DriverNumber', 'Driver'])
    
    return session, laps