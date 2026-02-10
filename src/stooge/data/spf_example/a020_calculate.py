"""
This script simply adds a column to the dataframe.
"""
import local
import pandas as pd


def add_summary_string(df):
    """Add a column to the df which is useful for displaying."""

    def _get_summary_str(ser):
        time_str = str(ser["time"])[:19]
        depth_str = f"Depth={ser['depth']/1_000}km"
        mag_str = f"ML={ser['magnitude']:02f}"
        out = f"{time_str}  {depth_str}  {mag_str}"
        return out

    df["summary_string"] = df.apply(_get_summary_str, axis=1)
    return df


if __name__ == "__main__":
    df = pd.read_csv(local.cleaned_csv)
    out = add_summary_string(df)
    out.to_csv(local.calc_csv)
