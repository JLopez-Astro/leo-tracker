import os
from dotenv import load_dotenv

# load_dotenv() reads .env file and loads variables into os.environ.
# This means config.py works whether you sourced setup_env.sh OR
# just run the Python script directly - it finds variables either way.
load_dotenv()

# os.environ.get() reads an environment variable by name.
# The second argument is a default value if the variable isn't set.
# For credentials, we raise an error rather than silently use a bad default.
SPACETRACK_USERNAME = os.environ.get("SPACETRACK_USERNAME")
SPACETRACK_PASSWORD = os.environ.get("SPACETRACK_PASSWORD")
FETCH_LIMIT = int(os.environ.get("FETCH_LIMIT", 100))

# Validate at startup - fail if credentials are missing.
if not SPACETRACK_USERNAME or not SPACETRACK_PASSWORD:
    raise EnvironmentError(
        "Missing credentials. Ensure SPACETRACK_USERNAME and "
        "SPACETRACK_PASSWORD are set in your .env file."
    )