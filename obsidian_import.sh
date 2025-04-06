#!/bin/bash

# Set the path to the Python script in the current directory
PYTHON_SCRIPT="$(dirname "$0")/obsidian_import.py"

# Check if the Python script exists
if [ ! -f "$PYTHON_SCRIPT" ]; then
    echo "Error: Python script not found at $PYTHON_SCRIPT"
    exit 1
fi

# Activate the virtual environment
echo "Activating Python virtual environment..."
source ~/.venv/obsidian_import/bin/activate || {
    echo "Error: Failed to activate virtual environment"
    exit 1
}

# Determine which Python command to use
if command -v python &> /dev/null; then
    PYTHON_CMD="python"
elif command -v python3 &> /dev/null; then
    PYTHON_CMD="python3"
else
    echo "Error: No Python interpreter found"
    deactivate
    exit 1
fi

# Add default arguments for logging and configuration
DEFAULT_ARGS="--log=DBG --reset-log --config=config.yaml"

# Pass all arguments along with the default arguments to the Python script
$PYTHON_CMD "$PYTHON_SCRIPT" $DEFAULT_ARGS "$@"

# Deactivate the virtual environment after execution
echo "Deactivating Python virtual environment..."
deactivate
