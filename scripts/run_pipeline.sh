#!/usr/bin/env bash
# run pipeline.sh

# End-to-end pipeline runner for the LEO tracker.
# Sets up the environment, runs the Python pipeline, and opens the report.

# Usage:
#	source scripts/run_pipeline.sh				# defaults: html, 100 objects
#	source scripts/run_pipeline.sh --limit 500		# fetch 500 objects
#	source scripts/run_pipeline.sh --no-report		# skip report generation

# Any arguments passed to this script are forwarded directly to main.py, so
# all main.py CLI flags work here too.

set -euo pipefail

# Resolve project root ----------
PROJECT_ROOT="$(pwd)"

# Verify wer're being run from the project root by checking for a known file.
# Prevents confusing errors it someone sources script from wrong directory.
if [ ! -f "$PROJECT_ROOT/main.py" ]; then
	echo "ERROR: run_pipeline.sh must be sourced from the project root."
	echo "		cd to leo-tracker/ first, then run: source scripts/run_pipeline.sh"
	return 1 # 'return' instead of 'exit' so terminal session is not closed
fi

# Activate virtual environment ----------
VENV_DIR="$PROJECT_ROOT/venv"

if [ ! -d "$VENV_DIR" ]; then
	echo "Virtual environment not found. Running full setup first..."
	source "$PROJECT_ROOT/scripts/setup_env.sh"
else
	# If venv already exists, activate it.
	# shellcheck disable=SC1091
	source "$VENV_DIR/bin/activate"
fi

# Load environment variables ----------
ENV_FILE="$PROJECT_ROOT/.env"

if [ ! -f "$ENV_FILE" ]; then
	echo "ERROR: .env file not found. Copy .env.example and fill in credentials."
	return 1
fi

# Export variables from .env into the current shell session.
# split lines into key value
while IFS='=' read -r key value; do
	# skip empty keys and comment lines
	[[ -z "$key" || "$key" =~ ^# ]] && continue
	# remove trailing and leading "
	value="${value%\"}"
	value="${value#\"}"
	# set environment value
	export "$key=$value"
done < "$ENV_FILE"

# Run the pipeline ----------
echo ""
echo "~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~"
echo " LEO Tracker - Starting pipeline"
echo " $(date -u '+%Y-%m-%d %H:%M:%S UTC')"
echo "~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~"
echo ""

# "$@" passes all arguments/flags given to this script straight to main.py
python "$PROJECT_ROOT/main.py" "$@"

# Open the report ----------
# Only open report if --no-report was not passed.
# grep checks argument list for that flag
if [[ ! "$*" =~ "--no-report" ]]; then
	# assign latest .html file to variable; sort by modification time, suppress errors, and select first result
	LATEST_REPORT=$(ls -t "$PROJECT_ROOT/reports/"*.html 2>/dev/null | head -1)

	if [ -n "$LATEST_REPORT" ]; then
		echo ""
		echo "Opening report: $LATEST_REPORT"
		
		# Detect OS and use appropriate command to open report.
		# WSL exposes a WSLENV variable and has /proc/version containing
		# "microsoft" - most reliable way to detect WSL.
		if grep -qi "microsoft" /proc/version 2>/dev/null; then
			# Convert Linux path to Windows UNC path that explorer.exe understands.
			# wslpath -w coverts /home/name/... to \\wsl$\Ubuntu\home\name\...
			WIN_PATH=$(wslpath -w "$LATEST_REPORT")
			explorer.exe "$WIN_PATH"
		elif [[ "$OSTYPE" == "darwin"* ]]; then
			# macOS - 'open' is native command
			open "$LATEST_REPORT"
		else
			# Native Linux - xdg-open delegates to desktop env's default browser
			# (works on Ubuntu, Fedora, etc.)
			xdg-open "$LATEST_REPORT"
		fi
	fi
fi

echo ""
echo "~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~"
echo " Pipeline complete."
echo "~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~"
