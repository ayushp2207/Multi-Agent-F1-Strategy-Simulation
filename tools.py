# tools.py
import pandas as pd

# This function will act as a tool for our agents.
# In a real scenario, this would fetch live data. Here, it gets data for a specific lap.
def get_current_lap_data(laps_data: pd.DataFrame, lap_number: int) -> pd.DataFrame:
    """
    Fetches all race data for a specific lap number.

    Args:
        laps_data (pd.DataFrame): The DataFrame containing all lap data for the race.
        lap_number (int): The current lap number to get data for.

    Returns:
        pd.DataFrame: A DataFrame containing all data for the specified lap.
    """
    return laps_data.loc[laps_data['LapNumber'] == lap_number]