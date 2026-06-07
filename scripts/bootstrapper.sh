#!/bin/bash
# SatRoute - Standard Brumana Analysis
# Performs the full Dijkstra-based comparison for Iridium or OneWeb.

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

# 3. Run the Brumana Analysis
echo "Starting full Dijkstra analysis (1,800 steps, 20 Gbps)..."
cd simulator
# Defaulting to OneWeb (input 1) for the modern constellation analysis
python3 main.py --analyze dijkstra -d 1800 -t 20 --input 1 || true

# Notification
curl -d "Simulation finished on $(hostname)!" ntfy.sh/Satellite_Simulation_Attempt || echo "Notification failed."

echo "Workflow finished."
