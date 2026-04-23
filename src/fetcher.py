"""
fetcher.py

Responsible for authenticating with the Space-Track API and retrieving
Two-Line Element (TLE) data for LEO objects. Returns data as a Pandas
DataFrame for downstream processing.

Space-Track API docs: https://www.space-track.org/documentation
"""

import time
import logging
import requests
import pandas as pd

from config import SPACETRACK_USERNAME, SPACETRACK_PASSWORD, FETCH_LIMIT


# Logging setup ----------
# The logging module is preferred alternative to print() for status
# messages. Allows control verbosity (DEBUG, INFO, WARNING, ERROR) and
# can redirect output to a file without changing code.
# __name__ provides logger name of this module ('src.fetcher'), making
# it easier to trace which module produced which log message.
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(name)s: %(message)s"
)
logger = logging.getLogger(__name__)

# Constants ----------
# Set Space-Track URL to variable for easy edit if URL changes.
BASE_URL = "https://www.space-track.org"
# "/ajaxauth/login" is used since page does not need to be reloaded, making
# for faster interactions.
LOGIN_URL = f"{BASE_URL}/ajaxauth/login"

# Space-Track REST query URL structure.
# It requests latest TLE for each object (order by epoch desc, limit 1 per object)
# filtered to LEO objects (period < 128 minutes) in JSON format.
# FETCH_LIMIT controls number of objects pulled.

def create_session():
    """
    Create and return an authenticated requests.Session.

    A Session object persists certain parameters (cookies/headers) across
    multiple requests. This is more efficient than authenticating on every
    request. Authenticate once at startup, then make many data requests.

    Returns:
        requests.Session: An authenticated session with cookies set.

    Raises:
        RuntimeError: If authentication fails.
    """
    session = requests.Session()

    # Login endpoint expects credentials as form-encoded POST data.
    # 'identity' and 'password' are the exact field names Space-Track expects.
    credentials = {
        "identity": SPACETRACK_USERNAME,
        "password": SPACETRACK_PASSWORD
    }

    logger.info("Authenticating with Space-Track API...")

    # A try/except block to catch network-level errors (no internet, timeout)
    # separately from API-level errors (bad credentials, server error).
    try:
        response = session.post(LOGIN_URL, data=credentials, timeout=30)
    except requests.exceptions.RequestException as e:
        raise RuntimeError(f"Network error during authentication: {e}") from e

    # HTTP status codes state the issue:
    # 200 = OK, 401 = Unauthorized, 403 = Forbidden, 500 = Server error
    # raise_for_status() raises an exception for any 4xx or 5xx code,
    # so you don't continue with a failed request without knowing.
    response.raise_for_status()

    # Space-Track returns the string "Failed" in the body on bad credentials
    # even with a 200 status code. We can use this to check for bad credentials.
    if "Failed" in response.text:
        raise RuntimeError(
            "Authentication failed. Check your SPACETRACK_USERNAME "
            "and SPACETRACK_PASSWORD in .env."
        )

    logger.info("Authentication successful.")
    return session

def fetch_tle_dataframe(session, limit):
    """
    Fetch TLE data for LEO objects and return as a Pandas DataFrame.

    Each row in the DataFrame represents one tracked object. Columns include
    orbital parameters, TLE strings, epoch, and object metadata.

    Args:
        session: An authenticated requests.Session from create_session().

    Returns:
        pd.DataFrame: One row per object, columns are Space-Track API fields.

    Raises:
        RuntimeError: If the data request fails or returns empty data.
    """
    actual_limit = limit if limit is not None else FETCH_LIMIT

    TLE_QUERY_URL = (
        f"{BASE_URL}/basicspacedata/query/class/gp"
        f"/MEAN_MOTION/>11.25" # >11.25 revs/day = orbital period < ~128 min = LEO
        f"/DECAY_DATE/null-val" # exclude objects that have already re-entered
        f"/orderby/NORAD_CAT_ID asc"
        f"/limit/{actual_limit}"
        f"/format/json"
    )

    logger.info(f"Fetching TLE data (limit: {actual_limit} objects)...")

    try:
        response = session.get(TLE_QUERY_URL, timeout=60)
    except requests.exceptions.RequestException as e:
        raise RuntimeError(f"Network error fetching TLE data: {e}") from e

    response.raise_for_status()

    # response.json() parses the JSON response body into a Python list of dicts.
    # Each dict is one satellite record with all its orbital parameters.
    data = response.json()

    if not data:
        raise RuntimeError("API returned empty dataset. Check your query parameters.")

    logger.info(f"Received {len(data)} records from Space-Track.")

    # pd.DataFrame(list_of_dicts) is a common pattern.
    # Each dict becomes a row and dict keys become column names.
    df = pd.DataFrame(data)

    # Parse the EPOCH column as a proper datetime type.
    # It first comes as a string, ex: "2025-001.12345". Converting it
    # to a datetime object allows time-based filtering and math later.
    df["EPOCH"] = pd.to_datetime(df["EPOCH"])

    # Convert numeric columns from strings (JSON delivers everything as strings)
    # to proper numeric types to make math possible.
    numeric_cols = [
        "MEAN_MOTION", "ECCENTRICITY", "INCLINATION",
        "RA_OF_ASC_NODE", "ARG_OF_PERICENTER", "MEAN_ANOMALY",
        "BSTAR", "MEAN_MOTION_DOT", "MEAN_MOTION_DDOT",
        "SEMIMAJOR_AXIS", "PERIOD", "APOAPSIS", "PERIAPSIS"
    ]

    # errors='coerce' means if a value can't be converted to a number,
    # it becomes NaN rather than crashing.
    for col in numeric_cols:
        if col in df.columns:
            df[col] = pd.to_numeric(df[col], errors="coerce")

    logger.info(f"DataFrame built: {df.shape[0]} rows x {df.shape[1]} columns")
    return df

def close_session(session):
    """
    Close the authenticated session. Logs out of Space-Track.

    Args:
        session: An authenticated requests.Session from create_session().

    Returns:
        None.

    """
    session.close()
    logger.info("Session closed.")