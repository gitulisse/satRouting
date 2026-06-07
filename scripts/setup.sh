 1 #!/bin/bash
# Ensure we are in the project root
cd "$(dirname "$0")/.." || exit

echo "Setting up Satellite Simulator..."
python3 -m venv venv
source venv/bin/activate
pip install -r simulator/requirements.txt

# Download satellite data if missing
if [ ! -f "simulator/oneweb_satellites.json" ]; then
    curl -o simulator/oneweb_satellites.json "https://celestrak.org/NORAD/elements/gp.php?GROUP=oneweb&FORMAT=JSON"
fi

chmod +x scripts/*.sh
echo "Setup complete! Run 'bash scripts/bootstrapperCustomInput.sh'"