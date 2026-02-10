"""
Script to create simple visualizations of earthquake data.
"""
import local
import matplotlib.pyplot as plt
import pandas as pd
from local import magnitude_time_plot


def plot_magnitude_histogram(df):
    """Plot a histogram of magnitudes, return mpl figure."""
    fig, ax = plt.subplots(1, 1)
    ax.hist(df["magnitude"])
    ax.set_xlabel("Local Magnitude")
    ax.set_ylabel("Count")
    plt.tight_layout()
    return fig


def time_mag_dot_plot(df):
    """Create a dot plot of magnitude and time."""
    time = pd.to_datetime(df["time"])
    fig, ax = plt.subplots(1, 1)
    ax.plot(time, df["magnitude"], ".")
    ax.set_xlabel("Time")
    ax.set_ylabel("Local Magnitude")
    plt.tight_layout()
    return fig


if __name__ == "__main__":
    df = pd.read_csv(local.calc_csv)
    # plot magnitude histogram
    fig = plot_magnitude_histogram(df)
    fig.savefig(local.magnitude_histogram)
    # plot magnitude vs time
    fig = time_mag_dot_plot(df)
    fig.savefig(magnitude_time_plot)
