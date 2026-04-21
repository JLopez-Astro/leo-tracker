"""
propagator.py

Takes a DataFrame of TLE data and propagates each satellite's orbital state
forward in time using the SGP4 model. Returns position and velocity vectors
in the Earth-Centered Intertial (ECI) coordinate frame.

SGP4 reference: Vallado et al. 2006
"""

import logging
import numpy as np
import pandas as pd
from datetime import datetime, timezone
from sgp4.api import Satrec, jday

logger = logging.getLogger(__name__)


def build_satrec_list(df):
    """
    Parse TLE strings from the DataFrame into SGP4 Satrec objects.

    A Satrec (satellite record) is SGP4 library's internal representation of
    a satellite. It parses TLE strings and computes constants needed for
    propagation. All Satrec objects are built once upfront rather than
    rebuilding them on every propagation as this is more efficient than
    propagating to multiple future times.

    Args:
        df: DataFrame containing TLE_LINE1, TLE_LINE2, and OBJECT_NAME columns.

    Returns:
        List of (name, Satrec) tuples for successfully parsed satellites.
    """
    satellites = []
    failed = 0

    for _, row in df.iterrows():
        try:
            # Satrec.twoline2rv() parses two TLE lines into satellite
            # record object. Standard SGP4 initialization step.
            sat = Satrec.twoline2rv(row["TLE_LINE1"], row["TLE_LINE2"])
            satellites.append((row["OBJECT_NAME"], sat))
        except Exception as e:
            logger.warning(f"Failed to parse TLE for {row['OBJECT_NAME']}: {e}")
            failed += 1

    logger.info(f"Parsed {len(satellites)} satellites ({failed} failed)")
    return satellites


def propagate_to_time(satellites, target_time):
    """
    Propagate all satellites to a given time and return their ECI state vectors.

    ECI (Earth-Centered Inertial) is a coordinate frame with origin at Earth's
    center, x-axis pointing toward the sun at vernal equinox, z-axis
    toward the north pole. It does not rotate with Earth, making it
    preferrable for orbital mechanics. The y-axis direction completes the
    right-handed system.

    Position is returned in kilometers, velocity in km/s.

    Args:
        satellites: List of (name, Satrec) tuples from build_satrec_list().
        target_time: The UTC datetime to propagate to.

    Returns:
        DataFrame with columns: name, x, y, z (km), vx, vy, vz (km/s),
        and error flag for any satellites that failed propagation.
    """
    # SGP4 uses Julian Date (JD) internally for time representation, standard format in astrodynamics.
    # jday() converts a calendar datetime into JD split into two parts:
    # jd (whole days) and fr (fractional day) for numerical precision.
    jd, fr = jday(
        target_time.year,
        target_time.month,
        target_time.day,
        target_time.hour,
        target_time.minute,
        target_time.second + target_time.microsecond / 1e6
    )

    records = []

    for name, sat in satellites:
        # sat.sgp4(jd, fr) is the core propagation call.
        # It returns:
        #   e: error code (0 = success, non-zero = propagation failed)
        #   r: position vector [x, y, z] in km in ECI frame
        #   v: velocity vector [vx, vy, vz] in km/s in ECI frame
        e, r, v = sat.sgp4(jd, fr)

        if e != 0:
            # Error codes indicate physical impossibilities in the propagation
            # e.g. the satellite has decayed, or the TLE epoch is too old.
            # We record the failure rather than silently dropping the object.
            logger.debug(f"Propagation error for {name}: code {e}")
            records.append({
                "name": name,
                "x":np.nan, "y":np.nan, "z":np.nan,
                "vx":np.nan, "vy":np.nan, "vz":np.nan,
                "error":True, "error_code":e
            })
        else:
            records.append({
                "name":name,
                "x":r[0], "y":r[1], "z":r[2],
                "vx":v[0], "vy":v[1], "vz":v[2],
                "error":False,
                "error_code":0
            })

    df_states = pd.DataFrame(records)

    # Count number of successful propagated satellites.
    successful = (~df_states["error"]).sum()
    logger.info(
        f"Propagated {successful}/{len(satellites)} satellites successfully "
        f"to {target_time.strftime('%Y-%m-%d %H:%M:%S')}"
    )

    return df_states

def compute_orbital_radius(df_states):
    """
    Add an orbital radius column (distance from Earth's center) to the
    state vector DataFrame.

    Radius is r = sqrt(x^2 + y^2 + z^2)

    This is useful for sanity-checking. LEO objects should have radii
    between roughly 6500 and 8400 km (Earth radius ~6371 km + 130-2000 km altitude).
    Anything outside this range suggests a bad TLE or propagation failure.

    Args:
        df_states: DataFrame from propagate_to_time().

    Returns:
        Same DataFrame with added 'radius_km' and 'altitude_km' columns.
    """
    EARTH_RADIUS_KM = 6371.0 # Mean radius

    df_states = df_states.copy() # Avoid modifying input dataframe

    # Use np.sqrt and ** to operate element-wise on entire columns as once
    # (Vectorization). Quicker than looping row by row. Pandas the GOAT!
    df_states["radius_km"] = np.sqrt(
        df_states["x"]**2 +
        df_states["y"]**2 +
        df_states["z"]**2
    )

    df_states["altitude_km"] = df_states["radius_km"] - EARTH_RADIUS_KM

    return df_states

