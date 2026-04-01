#!/bin/bash
# Bootstrap script for Docker deployment
# Starts Flask traffic matrix service and runs simulation

set -e  # Exit on error

echo "=== Satellite Routing Simulator - Docker Bootstrap ==="
echo "Date: $(date)"
echo "Working directory: $(pwd)"

# Function to cleanup on exit
cleanup() {
    echo "Cleaning up..."
    if [ ! -z "$FLASK_PID" ]; then
        echo "Stopping Flask service (PID: $FLASK_PID)..."
        kill $FLASK_PID 2>/dev/null || true
    fi
}
trap cleanup EXIT

# Check if running in Docker
if [ -f /.dockerenv ]; then
    echo "Running in Docker container"
    DOCKER_MODE=true
else
    echo "Running outside Docker"
    DOCKER_MODE=false
fi

# Start Flask traffic matrix service (if enabled)
if [ "$SKIP_FLASK" != "true" ]; then
    echo "Starting Flask traffic matrix service on port 8001..."
    cd /satRouting/traffic_matrix_generator
    export FLASK_RUN_PORT=8001
    export FLASK_APP=traffic_matrix_generator_svc.py
    
    # Check if required environment variables are set
    if [ -z "$BASE_CITY_API_URL" ] || [ -z "$CITY_SVC_API_KEY_FILE" ]; then
        echo "WARNING: BASE_CITY_API_URL or CITY_SVC_API_KEY_FILE not set"
        echo "Traffic matrix generation may fail. Set SKIP_FLASK=true to skip."
    fi
    
    flask run --host=0.0.0.0 &
    FLASK_PID=$!
    echo "Flask started with PID: $FLASK_PID"
    
    # Wait for Flask to be ready
    sleep 3
    
    # Health check
    if curl -s http://localhost:8001/traffic_matrix\?cities\=Tokyo\&total_volume_of_traffic\=1 > /dev/null 2>&1; then
        echo "✓ Flask service is healthy"
    else
        echo "⚠ Flask service may not be fully ready (continuing anyway)"
    fi
    
    cd /satRouting/simulator
else
    echo "Skipping Flask service (SKIP_FLASK=true)"
fi

# Parse command line arguments or use defaults
STRATEGY=${SIM_STRATEGY:-5}
DURATION=${SIM_DURATION:-60}
TRAFFIC=${SIM_TRAFFIC:-10}
INPUT=${SIM_INPUT:-1}

echo ""
echo "=== Starting Simulation ==="
echo "Strategy: $STRATEGY"
echo "Duration: $DURATION seconds"
echo "Traffic: $TRAFFIC Gbps"
echo "Input format: $INPUT (0=Iridium, 1=OneWeb, 2=Custom OMM)"
echo ""

# Run the main simulation
python3 main.py \
    --strategy "$STRATEGY" \
    --duration "$DURATION" \
    --traffic "$TRAFFIC" \
    --input "$INPUT"

echo ""
echo "=== Simulation Complete ==="
echo "Results saved to simulator/ directory"
