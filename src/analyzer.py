"""
analyzer.py

Performs catalog health analysis on TLE and state vector data.
Three responsibilities:
    1. TLE age and staleness analysis
    2. Orbital regime classification
    3. Basic conjunction screening via pairwise distance computation

Module is purely analytical - it receives DataFrames and returns DataFrames.
It does not fetch data or propagate orbits itself.
"""

import logging
import numpy as np
import pandas as pd
from datetime import datetime, timezone

logger = logging.getLogger(__name__)

# Constants ----------
# These are set here so they are easy to change for testing.
STALE_TLE_DAYS = 7.0
CONJUNCTION_THRESHOLD_KM = 50
EARTH_RADIUS_KM = 6371.0

# 1. TLE AGE ANALYSIS ----------

def compute_tle_age(df: pd.DataFrame) -> pd.DataFrame:
    """
    Compute the age of each TLE in days relative to the current UTC time.

    TLE age is the primary indicator of catalog health. A fresh TLE (age < 1 day)
    gives positional uncertainty of roughly 1-3 km. A week-old TLE may have
    uncertainty of 10-20+ km depending on the object's altitude and drag profile.
    Lower altitude satellites will experience more drag and therefore have
    larger uncertainties.

    Args:
        df: DataFrame containing an EPOCH column (datetime64).

    Returns:
        DataFrame with added columns:
            tle_age_days: float, age of TLE in days
            is_stale: bool, True if age exceeds STALE_TLE_DAYS threshold
    """
    df = df.copy()

    now = pd.Timestamp.now(tz=timezone.utc)

    # EPOCH column may not be timezone-aware. If not, localize it to UTC.
    # Timezone-naive datetimes compared to timezone-aware ones raise an error -
    # this helps us avoid mixing timezones.
    if df["EPOCH"].dt.tz is None:
        df["EPOCH"] = df["EPOCH"].dt.tz_localize("UTC")

    # Vectorized subtraction - computes timedelta for all rows simultaneously.
    # .dt.total_seconds() extracts the total seconds from each timedelta,
    # then we convert to days. This is more precise than .dt.days which
    # truncates to whole days.
    df["tle_age_days"] = (now - df["EPOCH"]).dt.total_seconds() / 86400.0

    # Boolean column - True where age exceeds our staleness threshold.
    df["is_stale"] = df["tle_age_days"] > STALE_TLE_DAYS

    stale_count = df["is_stale"].sum()
    logger.info(
        f"TLE age computed: {stale_count}/{len(df)} objects have stale TLEs "
        f"(>{STALE_TLE_DAYS} days)" 
    )

    return df

def summarize_tle_age(df: pd.DataFrame) -> None:
    """
    Print a readable staleness report to the logger.

    In a production system this could write to a monitoring dashboard
    or trigger alerts. For this case, it logs to the console.
    """
    stale = df[df["is_stale"]]
    fresh = df[~df["is_stale"]]

    logger.info("--- TLE Staleness Report ----------")
    logger.info(f" Total objects: {len(df)}")
    logger.info(f" Fresh (<={STALE_TLE_DAYS} days): {len(fresh)}")
    logger.info(f" Stale (>{STALE_TLE_DAYS} days): {len(stale)}")

    if not stale.empty:
        logger.info(" 5 Stalest objects:")
        stalest = df.nlargest(5, "tle_age_days")[
            ["OBJECT_NAME", "tle_age_days", "EPOCH"]
        ]
        for _, row in stalest.iterrows():
            logger.info(
                f"{row['OBJECT_NAME']:<25}"
                f"{row['tle_age_days']:>8.1f} days old"
                f"(epoch: {row['EPOCH'].strftime('%Y-%m-%d')})"
            )

# 2. Orbital Regime Classification ----------

def classify_orbits(df: pd.DataFrame) -> pd.DataFrame:
    """
    Classify each object by orbit shape and regime.

    Shape classification uses eccentricity directly from the TLE data.
    Regime classification uses the PERIAPSIS column to determine the
    lowest point of the orbit - an object is in LEO if its perigee
    is below 2000 km regardless of where its apogee is.

    Args:
        df: DataFrame containing ECCENTRICITY and PERIAPSIS columns.

    Returns:
        DataFrame with added columns:
            orbit_shape: 'circular', 'mildly elliptical', or 'highly elliptical'
            orbit_regime: 'LEO', 'MEO', or 'GEO/HEO'
    """
    df = df.copy()

    # pd.cut() bins the continuous values into labeled categories.
    # bins defines the boundary points, labels names each interval.
    # This is cleaner than a chain of if/elif statements and works
    # on the entire column at once.
    df["orbit_shape"] = pd.cut(
        df["ECCENTRICITY"],
        bins=[0, 0.01, 0.1, 1.0],
        labels=["circular", "mildly elliptical", "highly elliptical"]
    )

    # Regime based on periapsis altitude (lowest point of orbit).
    df["orbit_regime"] = pd.cut(
        df["PERIAPSIS"],
        bins=[0, 2000, 35786, np.inf],
        labels=["LEO", "MEO", "GEO/HEO"]
    )

    logger.info("--- Orbit Classification ----------")
    logger.info(f"\n{df['orbit_shape'].value_counts().to_string()}")
    logger.info(f"\n{df['orbit_regime'].value_counts().to_string()}")

    return df

# 3. Confunction Screening ----------

def screen_conjunctions(df_states: pd.DataFrame) -> pd.DataFrame:
    """
    Screen all pairs of satellites for potential conjunctions.

    Computes pairwaise Euclidean distance between ECI position vectors
    and returns pairs whose separation falls below CONJUNCTION_THRESHOLD_KM.

    This is a brute-force O(n^2) approach appropriate for n=100 objects.
    
    Args:
        df_states: DataFrame from propagate_to_time() containing
                    x, y, z columns in km and name column.

    Returns:
        DataFrame of flagged pairs with columns:
            object_a, object_b: names of the two objects
            distance_km: separation in km at the propagation time
    """
    # Drop rows where propagation failed - NaN positions would give meaningless distances.
    # Use ~ to filter OUT rows with errors, .reset_index drops those rows, leaving valid states.
    valid = df_states[~df_states["error"]].reset_index(drop=True)

    # Extract position vectors as a numpy array for efficient computation.
    # Shape: (n_satellites, 3) where columns are x, y, z.
    # Working in numpy rather than pandas here because we need matrix
    # operations across all pairs simultaneously.
    positions = valid[["x", "y", "z"]].to_numpy()
    names = valid["name"].to_list()
    n = len(positions)

    conjunctions = []

    # Iterate over all unique pairs (i,j) where i < j.
    # range(n-1) and range(i+1, n) ensures we check each pair once, and
    # distance(A,B) == distance(B,A) so we don't need duplicate distances.
    for i in range(n - 1):
        for j in range(i + 1, n):
            # Euclidean distance -> distance between two satellites.
            delta = positions[i] - positions[j]
            distance = np.sqrt(np.dot(delta, delta))

            # np.dot(delta, delta) is equivalent to sum of squares.
            # Slightly faster than (delta**2).sum()

            if distance < CONJUNCTION_THRESHOLD_KM:
                conjunction.append({
                    "object_a": names[i],
                    "object_b": names[j],
                    "distance_km": round(distance, 3)
                })

    df_conj = pd.DataFrame(conjunctions)

    if df_conj.empty:
        logger.info(
            f"No conjunctions found below {CONJUNCTION_THRESHOLD_KM} km threshold."
        )
    else:
        logger.info(
            f"Found {len(df_conj)} potential conjunction(s) "
            f"below {CONJUNCTION_THRESHOLD_KM} km:"
        )
        for _, row in df_conj.iterrows():
            logger.info(
                f" {row['object_a']} <--> {row['object_b']}: "
                f"{row['distance_km']} km"
            )

    return df_conj