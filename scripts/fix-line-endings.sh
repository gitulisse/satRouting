#!/bin/bash
# fix-line-endings.sh
# Converts all text files to Unix (LF) line endings for Docker compatibility
# Run this if you suspect CRLF contamination (e.g., after receiving files from Windows)

# Ensure we are in the project root
cd "$(dirname "$0")/.." || exit

echo "=== Fixing Line Endings for Docker ==="
echo

# Check if dos2unix is available
if ! command -v dos2unix &> /dev/null; then
    echo "[ERROR] dos2unix not found!"
    echo
    echo "Install it with:"
    echo "  Ubuntu/Debian: sudo apt install dos2unix"
    echo "  Fedora: sudo dnf install dos2unix"
    echo "  macOS: brew install dos2unix"
    echo
    exit 1
fi

echo "Converting shell scripts..."
find . -name "*.sh" -exec dos2unix -q {} \;

echo "Converting Python files..."
find . -name "*.py" -exec dos2unix -q {} \;

echo "Converting YAML files..."
find . -name "*.yml" -o -name "*.yaml" -exec dos2unix -q {} \;

echo "Converting Dockerfile..."
dos2unix -q Dockerfile

echo "Converting Docker Compose..."
dos2unix -q docker-compose.yml

echo
echo "=== Line Endings Fixed ==="
echo "Files are now ready for Docker"
