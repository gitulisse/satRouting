#!/bin/bash

set -e  # Ferma tutto se c'è un errore

cleanup() {
    echo "Chiudo Flask..."
    kill $FLASK_PID 2>/dev/null || true
}
trap cleanup EXIT

echo "Entro in cartella venv"
cd ../venv

echo "Attivo virtualenv..."
source ./bin/activate

echo "Avvio servizio Flask..."
cd ../traffic_matrix_generator

export FLASK_RUN_PORT=8001
export FLASK_APP=traffic_matrix_generator_svc.py

flask run &
FLASK_PID=$!

echo "Flask avviato con PID $FLASK_PID"

# Torna alla cartella principale (adatta se serve)
cd ../simulator

# =====================================================
# SATELLITE DATA CONFIGURATION
# =====================================================
# Choose ONE of the following options:

# Option A: Use local cached JSON file (RECOMMENDED - avoids API rate limiting)
# Download once from: https://celestrak.org/NORAD/elements/gp.php?GROUP=oneweb&FORMAT=JSON
USE_LOCAL_FILE=true
LOCAL_SATELLITE_FILE="oneweb_satellites.json"

# Option B: Fetch from Celestrak API (may trigger rate limiting)
# Set USE_LOCAL_FILE=false to use API
# =====================================================

echo ""
echo "========================================="
echo "Satellite Data Configuration"
echo "========================================="

if [ "$USE_LOCAL_FILE" = true ]; then
    if [ -f "$LOCAL_SATELLITE_FILE" ]; then
        echo "✓ Using local satellite data: $LOCAL_SATELLITE_FILE"
        echo "  (File size: $(du -h "$LOCAL_SATELLITE_FILE" | cut -f1))"
        echo "  (Satellites: $(grep -o '"NORAD_CAT_ID"' "$LOCAL_SATELLITE_FILE" | wc -l))"
    else
        echo "✗ ERROR: Local file not found: $LOCAL_SATELLITE_FILE"
        echo ""
        echo "Please download the satellite data:"
        echo "  curl -o $LOCAL_SATELLITE_FILE 'https://celestrak.org/NORAD/elements/gp.php?GROUP=oneweb&FORMAT=JSON'"
        echo ""
        echo "Or set USE_LOCAL_FILE=false in bootstrapperOMM.sh to fetch from API"
        echo ""
        exit 1
    fi
else
    echo "⚠ Fetching satellite data from Celestrak API"
    echo "  (Warning: May trigger rate limiting with multiple runs)"
fi

echo ""

# =====================================================
# OUTPUT DIRECTORY SETUP
# =====================================================

# Create output directories if they don't exist
OUTPUT_DIR="output"
LOGS_DIR="$OUTPUT_DIR/logs"
RESULTS_DIR="$OUTPUT_DIR/results"

mkdir -p "$LOGS_DIR"
mkdir -p "$RESULTS_DIR"

echo "Output directories ready: $OUTPUT_DIR/"

# =====================================================
# EXECUTION TIME TRACKING
# =====================================================

# Create execution time log file
EXEC_TIME_LOG="$LOGS_DIR/execution_times.log"
echo "=== Execution Time Log ===" > "$EXEC_TIME_LOG"
echo "Date: $(date)" >> "$EXEC_TIME_LOG"
echo "Constellation: OneWeb" >> "$EXEC_TIME_LOG"
echo "Duration: 60 seconds (simulated)" >> "$EXEC_TIME_LOG"
echo "Traffic: 20 Gbps" >> "$EXEC_TIME_LOG"
if [ "$USE_LOCAL_FILE" = true ]; then
    echo "Satellite Data: Local file ($LOCAL_SATELLITE_FILE)" >> "$EXEC_TIME_LOG"
else
    echo "Satellite Data: Celestrak API" >> "$EXEC_TIME_LOG"
fi
echo "=========================" >> "$EXEC_TIME_LOG"
echo "" >> "$EXEC_TIME_LOG"

# Track total execution time
TOTAL_START=$(date +%s)

echo "Avvio simulazione principale..."

for i in $(seq 1 15)
do
    if [ "$i" -ne 9 ]
    then
        echo ""
        echo "========================================="
        echo "Starting Strategy $i..."
        echo "========================================="

        # Record start time for this strategy
        STRATEGY_START=$(date +%s.%N)
        STRATEGY_START_HR=$(date +"%Y-%m-%d %H:%M:%S")

        # Run simulation with satellite data source
        if [ "$USE_LOCAL_FILE" = true ]; then
            # Use local file
            python3 main.py --strategy "$i" --duration 60 --traffic 20 --input 2 --sat-file "$LOCAL_SATELLITE_FILE" > "$LOGS_DIR/OneWeb_${i}.txt" 2>&1 || true
        else
            # Use API
            python3 main.py --strategy "$i" --duration 60 --traffic 20 --input 1 > "$LOGS_DIR/OneWeb_${i}.txt" 2>&1 || true
        fi

        # Check if simulation succeeded
        if [ $? -eq 0 ]; then
            # Record end time and calculate duration
            STRATEGY_END=$(date +%s.%N)
            STRATEGY_END_HR=$(date +"%Y-%m-%d %H:%M:%S")
            STRATEGY_DURATION=$(echo "$STRATEGY_END - $STRATEGY_START" | bc)

            # Format duration as MM:SS
            STRATEGY_DURATION_INT=$(echo "$STRATEGY_DURATION" | cut -d'.' -f1)
            MINUTES=$((STRATEGY_DURATION_INT / 60))
            SECONDS=$((STRATEGY_DURATION_INT % 60))
            FORMATTED_DURATION=$(printf "%02d:%02d" $MINUTES $SECONDS)

            echo "Strategy $i completed in ${FORMATTED_DURATION} (wall clock time)"

            # Log to file
            echo "Strategy $i:" >> "$EXEC_TIME_LOG"
            echo "  Start: $STRATEGY_START_HR" >> "$EXEC_TIME_LOG"
            echo "  End: $STRATEGY_END_HR" >> "$EXEC_TIME_LOG"
            echo "  Duration: ${FORMATTED_DURATION} (${STRATEGY_DURATION} seconds)" >> "$EXEC_TIME_LOG"
            echo "  Output: $LOGS_DIR/OneWeb_${i}.txt" >> "$EXEC_TIME_LOG"
            echo "" >> "$EXEC_TIME_LOG"
        else
            STRATEGY_END=$(date +%s.%N)
            STRATEGY_END_HR=$(date +"%Y-%m-%d %H:%M:%S")
            echo "Strategy $i FAILED - check $LOGS_DIR/OneWeb_${i}.txt for errors"
            echo "Strategy $i: FAILED" >> "$EXEC_TIME_LOG"
            echo "  Start: $STRATEGY_START_HR" >> "$EXEC_TIME_LOG"
            echo "  End: $STRATEGY_END_HR" >> "$EXEC_TIME_LOG"
            echo "" >> "$EXEC_TIME_LOG"
        fi
    else
        echo ""
        echo "========================================="
        echo "Skipping Strategy 9 (Baseline Dijkstra)"
        echo "========================================="
        echo "Strategy 9:" >> "$EXEC_TIME_LOG"
        echo "  Status: SKIPPED (memory intensive)" >> "$EXEC_TIME_LOG"
        echo "" >> "$EXEC_TIME_LOG"
    fi
done

# Calculate total execution time
TOTAL_END=$(date +%s)
TOTAL_DURATION=$((TOTAL_END - TOTAL_START))
TOTAL_MINUTES=$((TOTAL_DURATION / 60))
TOTAL_SECONDS=$((TOTAL_DURATION % 60))
TOTAL_FORMATTED=$(printf "%02d:%02d" $TOTAL_MINUTES $TOTAL_SECONDS)

echo ""
echo "========================================="
echo "All simulations completed!"
echo "Total execution time: ${TOTAL_FORMATTED}"
echo "========================================="

# Add total to log
echo "=========================" >> "$EXEC_TIME_LOG"
echo "TOTAL EXECUTION TIME: ${TOTAL_FORMATTED} (${TOTAL_DURATION} seconds)" >> "$EXEC_TIME_LOG"
echo "Completed: $(date)" >> "$EXEC_TIME_LOG"

echo "Simulazione terminata, chiudo Flask..."
kill $FLASK_PID

deactivate
echo "Fatto."
echo ""
echo "========================================="
echo "Output Files Summary"
echo "========================================="
echo "Logs: $LOGS_DIR/"
echo "  - execution_times.log"
echo "  - OneWeb_1.txt through OneWeb_15.txt"
echo ""
echo "Results: $RESULTS_DIR/"
echo "  (Analysis results will be saved here)"
echo ""
echo "Execution times saved to: $EXEC_TIME_LOG"
