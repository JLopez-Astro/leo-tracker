"""
reporter.py

Generates operational catalog health reports in multiple formats.
Architecture separates data assembly from presentation:
    - generate_report_data() builds a format-agnostic content dictionary
    - render_*() functions pass that dict to format-specific renderers
    - save_report() writes the output to a timestamped file

HTML rendering uses Jinja2 templates (templates/report.html).
Adding a new format means writing one new render function and one new template.

Supported formats: html (csv and txt planned)
"""

import logging
import os
from datetime import datetime, timezone
import pandas as pd
from jinja2 import Environment, FileSystemLoader, select_autoescape

logger = logging.getLogger(__name__)

EARTH_RADIUS_KM = 6371.0

# Jinja2 Environment ----------
# FileSystemLoader tells Jinja2 where to find template files.
# select_autoescape enables automatic HTML escaping for variables rendered
# into HTML context. This prevents HTML errors if a satellite name contains
# non-alphanumeric characters (< or &).
# Templates directory is resolved relative to this file's location so
# the path works regardless of where you run the script from.
TEMPLATES_DIR = os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", "templates")

jinja_env = Environment(
    loader=FileSystemLoader(TEMPLATES_DIR),
    autoescape=select_autoescape(["html"]),
    trim_blocks=True, # removes newline after block tags like {% if %}
    lstrip_blocks=True, # strips leading whitespace before block tags
)


# Data Assembly ----------

def generate_report_data(df_tle, df_states, df_conjunctions, generated_at, fetch_limit):
    """
    Assemble all report content into a format-agnostic dictionary.

    This function is the single source for report content. Every renderer
    (HTML, text, CSV) draws from this same dict, ensuring consistency across
    formats.

    Args:
        df_tle:     TLE DataFrame with age and classification columns added.
        df_states:      Propagated state vector DataFrame.
        df_conjunctions:     Conjunction screening results DataFrame.
        generated_at:       UTC datetime when the report was generated.
        fetch_limit:        Number of objects that were fetched from the API.

    Returns:
        dict containing all report sections as structured data.
    """
    stale = df_tle[df_tle["is_stale"]]
    fresh = df_tle[df_tle["is_stale"]]
    valid_states = df_states[~df_states["error"]]

    # Top 5 stalest objects for the health section
    stalest = df_tle.nlargest(5, "tle_age_days")[
        ["OBJECT_NAME", "tle_age_days", "EPOCH", "INCLINATION",
        "PERIAPSIS", "APOAPSIS"]
    ].copy()
    stalest["tle_age_days"] = stalest["tle_age_days"].round(1)
    stalest["EPOCH"] = stalest["EPOCH"].dt.strftime("%Y-%m-%d")
    stalest["is_stale"] = stalest["tle_age_days"] > 7.0

    # Orbit shape and regime breakdowns
    shape_counts = {
        str(k): int(v) for k, v in 
        df_tle["orbit_shape"].value_counts().items()
    }
    regime_counts = {
        str(k): int(v) for k, v in 
        df_tle["orbit_regime"].value_counts().items()
    }

    # Altitude statistics from propagated states
    alt_stats = valid_states["altitude_km"].describe().round(1).to_dict()

    # Conjunction rows with risk classification
    conj_rows = []
    if not df_conjunctions.empty:
        for _, row in df_conjunctions.iterrows():
            conj_rows.append({
                "object_a": row["object_a"],
                "object_b": row["object_b"],
                "distance_km": row["distance_km"],
                "risk_level": _conjunction_risk(row["distance_km"])
            })

    health_pct = round(len(fresh) / len(df_tle) * 100, 1)

    return {
        "generated_at": generated_at.strftime("%Y-%m-%d %H:%M:%S UTC"),
        "fetch_limit": fetch_limit,
        "total_objects": len(df_tle),
        "propagation_success": int((~df_states["error"]).sum()),
        "propagation_failures": int((df_states["error"]).sum()),
        "fresh_count": len(fresh),
        "stale_count": len(stale),
        "health_pct": health_pct,
        "stalest_objects": stalest.to_dict(orient="records"),
        "shape_counts": shape_counts,
        "regime_counts": regime_counts,
        "alt_stats": alt_stats,
        "conjunction_count": len(df_conjunctions),
        "conjunctions": conj_rows,
    }


def _conjunction_risk(distance_km):
    """
    Classify conjunction risk level by distance.

    Args:
        distance_km: Float, distance between two objects in km.

    Returns:
        String stating conjunction risk level.
    """
    if distance_km < 5:
        return "CRITICAL"
    elif distance_km < 20:
        return "HIGH"
    elif distance_km < 50:
        return "MEDIUM"
    return "LOW"


# Renderers ----------

def render_html(data):
    """
    Render report data as a self-contained HTML document via Jinja2.

    The template lives in templates/report.html. This function simply
    loads it and passes the data dictionary as template variables.
    All presentation logic lives in the template.

    Args:
        data: Report dictionary from generate_report_data().

    Returns:
        Rendered HTML string ready to write to disk.
    """
    template = jinja_env.get_template("report.html")
    return template.render(**data)


# Save ----------

def save_report(content, fmt, output_dir="reports"):
    """
    Write the rendered report to a timestamped file on disk.

    Timestamped filenames are never overwritten, automatically building
    an archive of every run.

    Args:
        content: Rendered report string.
        fmt: File extension ('html', 'txt', 'csv').
        output_dir: Directory to write into (created if absent).

    Returns:
        Full path of the written file.
    """
    os.makedirs(output_dir, exist_ok=True)

    timestamp = datetime.now(timezone.utc).strftime("%Y%m%d_%H%M%S")
    filename = f"leo_report_{timestamp}.{fmt}"
    filepath = os.path.join(output_dir, filename)

    with open(filepath, "w", encoding="utf-8") as f:
        f.write(content)

    logger.info(f"Report saved: {filepath}")
    return filepath