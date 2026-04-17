"""
main.py

Entry point for the LEO tracker pipeline.
Run this directly to test each building phase.
"""

import pandas as pd
from datetime import datetime, timezone
from src.fetcher import create_session, fetch_tle_dataframe, close_session
from src.propagator import build_satrec_list, propagate_to_time, compute_orbital_radius
from src.analyzer import compute_tle_age, summarize_tle_age, classify_orbits, screen_conjunctions

def main():
    session = create_session()

    try:
        # Phase 2: Fetch ----------
        # Fetch the satellites.
        df = fetch_tle_dataframe(session)

        ## .head() shows the first 5 rows, a quick way to sanity-check a
        ## DataFrame without printing thousands of rows to terminal.
        # print("\nFirst 5 records:")
        # print(df[["OBJECT_NAME", "EPOCH", "INCLINATION", "PERIOD", "APOAPSIS", "PERIAPSIS"]].head())

        # Phase 3: Propagate ----------
        # Propagate all satellites to right now.
        satellites = build_satrec_list(df)
        now = datetime.now(timezone.utc)
        df_states = propagate_to_time(satellites, now)
        df_states = compute_orbital_radius(df_states)

        # print("\nPropagated state vectors (first 5):")
        # print(df_states.head())

        ## .describe() gives summary statistics for all numeric columns.
        # print("\nAltitude summary (km):")
        # print(df_states["altitude_km"].describe())

        # Phase 4: Analyze ----------
        # Perform conjunction calculations.
        df = compute_tle_age(df)
        summarize_tle_age(df)

        df = classify_orbits(df)

        df_conjunctions = screen_conjunctions(df_states)

        if not df_conjunctions.empty:
            proint("\nConjunction alerts:")
            print(df_conjunctions)
        else:
            print("\nNo conjunction alerts at this time.")

        # # Sanity check - flag anything outside expected LEO altitude range
        # suspicious = df_states[
        #     (df_states["altitude_km"] < 130) |
        #     (df_states["altitude_km"] > 2000)
        # ]
        # if not suspicious.empty:
        #     print(f"\nSuspicious objects outside expected LEO range: {len(suspicious)}")
        #     print(suspicious[["name", "altitude_km", "error"]])

        # # Find the suspicious objects in the original TLE data
        # suspicious_names = suspicious["name"].tolist()
        # print(df[df["OBJECT_NAME"].isin(suspicious_names)][
        #     ["OBJECT_NAME", "INCLINATION", "APOAPSIS", "PERIAPSIS", "PERIOD"]
        # ])

        # .info() prints column names, data types, and non-null counts.
        # Ran on DataFrames to understand its structure.
        # print("\nDataFrame info:")
        # print(df.info())

        # print("\nNumeric summary:")
        #print(df.describe())
        # Describe only true numeric columns, excluding EPOCH
        # print(df.select_dtypes(include='float64').describe())

    finally:
        # The finally block runs whether or not an exception occurred.
        # Guarantees the session is always closed cleanly, even if an error is raised.
        close_session(session)

if __name__=="__main__":
    # Block only runs when you execute this file directly with
    # 'python main.py'. It does NOT run if another module imports main.py.
    main()