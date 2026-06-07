#!/bin/bash
# SatRoute - Quick Test Run
# Used to verify that the environment, Flask service, and simulator 
# are working correctly before starting long simulations.

set -e

# Ensure we are in the project root
cd "$(dirname "$0")/.." || exit

cleanup() {
    echo "Stopping Flask service..."
    if [ ! -z "$FLASK_PID" ]; then
        kill $FLASK_PID 2>/dev/null || true
    fi
}
trap cleanup EXIT

# 1. Activate Virtual Environment
if [ -d "venv" ]; then
    echo "Activating virtualenv..."
    source venv/bin/activate
else
    echo "Virtualenv not found, skipping activation."
fi

# 2. Start Traffic Matrix Service (Flask)
echo "Starting Flask service..."
cd traffic_matrix_generator
export FLASK_RUN_PORT=8001
export FLASK_APP=traffic_matrix_generator_svc.py
flask run &
FLASK_PID=$!
cd ..

# Wait for API to stabilize
sleep 2

# 3. Run a minimal simulation
echo "Running a 10-second test simulation (Strategy 4, OneWeb)..."
cd simulator
python3 main.py --duration 10 --traffic 10 --strategy 4 --input 1

echo "Simulation completed. Stopping Flask service..."
