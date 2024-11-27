#!/bin/bash

# If no path is provided, use the directory of this script
if [ -z "$1" ]; then
    SCRIPT_DIR=$(dirname "$(readlink -f "$0")")
else
    SCRIPT_DIR="$1"
fi

# Navigate to the determined directory
cd "$SCRIPT_DIR" || {
    echo "Directory $SCRIPT_DIR does not exist. Exiting."
    exit 1
}

# Set the DISPLAY environment variable and run the program
export DISPLAY=:0
./Magmotor
