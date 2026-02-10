"""
The first script to run
"""

import pandas as pd
from local import cleaned_csv, earthquake_csv


def clean_earthquake_df(df):
    """Clean the earthquake dataframe."""
    # drop any rows with lat/long out of range or invalid event_id
    bad_lat = abs(df["longitude"]) > 180
    bad_long = abs(df["latitude"]) > 90
    out = df[~(bad_long | bad_lat)].dropna(axis="rows", subset=["event_id"])
    return out


if __name__ == "__main__":
    df = pd.read_csv(earthquake_csv)
    out = clean_earthquake_df(df)
    out.to_csv(cleaned_csv, index=False)
