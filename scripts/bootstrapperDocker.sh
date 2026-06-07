#!/bin/bash
# SatRoute - Master Docker Bootstrapper
# Works both inside Docker and as a standalone script.

set -e # Exit on error

# 1. Configuration & Default Values
# Fix permissions for volume mounts (if running as root inside container)
if [ "$(id -u)" = "0" ]; then
    echo "Fixing permissions for /satRouting..."
    chown -R simuser:simuser /satRouting
fi

# These environment variables can be set in docker-compose.yml
ANALYZE=${SIM_ANALYZE:-""}
PLOT=${SIM_PLOT:-""}
STRATEGY=${SIM_STRATEGY:-9}
DURATION=${SIM_DURATION:-60}
TRAFFIC=${SIM_TRAFFIC:-10}
INPUT_FORMAT=${SIM_INPUT:-1}
MACHINE_ID=${MACHINE_ID:-$(hostname)}

# 2. Environment Detection & Path Setup
if [ -f /.dockerenv ]; then
    echo "--- [ENV] DOCKER MODE DETECTED ---"
    PROJECT_ROOT="/satRouting"
    SIMULATOR_DIR="/satRouting/simulator"
    TRAFFIC_DIR="/satRouting/traffic_matrix_generator"
    API_KEY_PATH="/satRouting/secrets/city_api_key.txt"
else
    echo "--- [ENV] LOCAL MODE DETECTED ---"
    PROJECT_ROOT="$(cd "$(dirname "$0")/.." && pwd)"
    SIMULATOR_DIR="$PROJECT_ROOT/simulator"
    TRAFFIC_DIR="$PROJECT_ROOT/traffic_matrix_generator"
    API_KEY_PATH="$PROJECT_ROOT/secrets/city_api_key.txt"
    
    if [ -d "$PROJECT_ROOT/venv" ]; then
        echo "Activating local venv..."
        source "$PROJECT_ROOT/venv/bin/activate"
    fi
fi

# Cleanup logic for background processes
cleanup() {
    echo "Cleaning up Flask service..."
    if [ ! -z "$FLASK_PID" ]; then
        kill $FLASK_PID 2>/dev/null || true
    fi
}
trap cleanup EXIT

# 3. Start Traffic Matrix Service (Flask)
echo "Starting Flask API on port 8001..."
cd "$TRAFFIC_DIR"
export FLASK_RUN_PORT=8001
export FLASK_APP=traffic_matrix_generator_svc.py
export CITY_SVC_API_KEY_FILE="$API_KEY_PATH"

flask run --host=0.0.0.0 &
FLASK_PID=$!

sleep 3 # Wait for API

# 4. Run the Simulation
cd "$SIMULATOR_DIR"
echo "========================================================="
echo "STARTING SIMULATION"
echo "Machine:  $MACHINE_ID"
echo "Config:   Format $INPUT_FORMAT, Strategy $STRATEGY, $DURATION steps"
echo "========================================================="

# Assemble the command
CMD="python3 main.py --input $INPUT_FORMAT --strategy $STRATEGY --duration $DURATION --traffic $TRAFFIC"

if [ ! -z "$ANALYZE" ]; then
    CMD="$CMD --analyze $ANALYZE"
fi

if [ ! -z "$PLOT" ]; then
    CMD="$CMD --plot $PLOT"
fi

echo "Executing: $CMD $@"
$CMD "$@" || true

# 5. Send Notification
echo "Sending notification..."
curl -d "Simulation COMPLETE on $MACHINE_ID!" ntfy.sh/Satellite_Simulation_Attempt || echo "Notification failed."

echo "Workflow finished successfully."
