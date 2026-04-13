# shebang - Tells OS which interpreter to use when script is run. Finds bash.
#!/usr/bin/env bash

# -e: exit immediately if command fails
# -u: treat unset variables as an error
# -o pipefail: if any command in a pipe fails, whole pipe fails
set -euo pipefail

# Resolve Paths ----------
# When sourcing from the project root, can rely on pwd directly.
# Use pwd -P to resolve any symlinks and get real physical path.
PROJECT_ROOT="$(pwd)"

echo "Setting up leo-tracker in: $PROJECT_ROOT"

# Virtual Environment ----------
VENV_DIR="$PROJECT_ROOT/venv"

if [ ! -d "$VENV_DIR" ]; then
	echo "Creating virtual environment..."
	python3 -m venv "$VENV_DIR"
else
	echo "Virtual environment already exists, skipping creation."
fi

# Activate the virtual environment
# Modifies PATH sp 'python' and 'pip' point to the venv versions.
# Tell ShellCheck to ignore stop complaining for this instance.
# shellcheck disable=SC1091
source "$VENV_DIR/bin/activate"
echo "Virtual environment activated: $VIRTUAL_ENV"

# Dependencies ----------
echo "Installing dependencies from requirements.txt..."
pip install --upgrade pip --quiet
pip install -r "$PROJECT_ROOT/requirements.txt"

# Environment Variables ----------
# Load variables from the .env file and export them into the shell environment.

ENV_FILE="$PROJECT_ROOT/.env"

# If $ENV_FILE exists...
if [ -f "$ENV_FILE" ]; then
	echo "Loading environment variables from .env..."
	# This loop reads each line, skips comments and blank lines, and exports variable.
	while IFS='=' read -r key value; do
		# Check for blank or commented lines and skip them
		[[ -z "$key" || "$key" =~ ^# ]] && continue
		# Strip surrounding quotes from value if present
		# Remove trailing "
		value="${value%\"}"
		# Remove leading "
		value="${value#\"}"
		export "$key=$value"
		echo "  Exported: $key"
	done < "$ENV_FILE"
else
	echo "WARNING: .env file not found at $ENV_FILE"
	echo "Copy .env.example to .env and fill in your credentials."
	exit 1
fi

echo ""
echo "Setup complete. You are now in the leo-tracker virtual environment."
echo "To deactivate, run: deactivate"
