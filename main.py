"""
main.py

Entry point for the LEO tracker pipeline.
Fetches live TLE data, propagates orbits, analyzes catalog health,
and produces an operational report.

Usage:
    python main.py
    python main.py --format html
    python main.py --format html --limit 200
"""

import argparse
import logging
import pandas as pd
from datetime import datetime, timezone

from src.fetcher import create_session, fetch_tle_dataframe, close_session
from src.propagator import build_satrec_list, propagate_to_time, compute_orbital_radius
from src.analyzer import compute_tle_age, summarize_tle_age, classify_orbits, screen_conjunctions
from src.reporter import generate_report_data, render_html, save_report

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s %(name)s: %(message)s]"
)
logger = logging.getLogger(__name__)

def parse_args():
    """
    Define and parse command-line arguments.

    argparse is used for building CLIs in Python. Automatically Generates 
    --help output and validates argument types.
    """
    parser = argparse.ArgumentParser(
        description="LEO Satellite Catalog Health Monitor",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
Examples:
    python main.py                          # Run with defaults (html, 100 objects)
    python main.py --format html            # Explicit HTML output
    python main.py --limit 500              # Fetch 500 objects
    python main.py --no-report              # Print summary only, no file output
        """
    )

    parser.add_argument(
        "--format",
        choices=["html"],
        default="html",
        help="Output report format (default: html)."
    )

    parser.add_argument(
        "--limit",
        type=int,
        default=None,
        help="Number of objects to fetch (default: 100)."
    )

    parser.add_argument(
        "--no-report",
        action="store_true",
        help="Skip report file generation, print summary to terminal only."
    )

    return parser.parse_args()


def main():
    args = parse_args()
    generated_at = datetime.now(timezone.utc)

    session = create_session()

    try:
        # Phase 2: Fetch ----------
        # Fetch the satellites.
        # If --limit was passes on the CLI, it overrides the .env value.
        from config import FETCH_LIMIT
        fetch_limit = args.limit if args.limit is not None else FETCH_LIMIT

        df = fetch_tle_dataframe(session, limit=fetch_limit)


        # Phase 3: Propagate ----------
        # Propagate all satellites to right now.
        satellites = build_satrec_list(df)
        now = datetime.now(timezone.utc)
        df_states = propagate_to_time(satellites, now)
        df_states = compute_orbital_radius(df_states)


        # Phase 4: Analyze ----------
        # Perform conjunction calculations.
        df = compute_tle_age(df)
        summarize_tle_age(df)
        df = classify_orbits(df)
        df_conjunctions = screen_conjunctions(df_states)


        # Phase 5: Report ----------
        if not args.no_report:
            report_data = generate_report_data(
                df_tle=df,
                df_states=df_states,
                df_conjunctions=df_conjunctions,
                generated_at=generated_at,
                fetch_limit=fetch_limit
            )

            if args.format == "html":
                content = render_html(report_data)
                filepath = save_report(content, fmt="html")
                print(f"\nReport generated: {filepath}")
                print("Open it in your browser to view the full report.")

    finally:
        # The finally block runs whether or not an exception occurred.
        # Guarantees the session is always closed cleanly, even if an error is raised.
        close_session(session)

if __name__=="__main__":
    # Block only runs when you execute this file directly with
    # 'python main.py'. It does NOT run if another module imports main.py.
    main()