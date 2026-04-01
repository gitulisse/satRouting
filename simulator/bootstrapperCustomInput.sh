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

echo "Avvio simulazione principale..."
python3 main.py --strategy 10 --duration 60 --traffic 20 --input 2

echo "Simulazione terminata, chiudo Flask..."
kill $FLASK_PID

deactivate
echo "Fatto."
