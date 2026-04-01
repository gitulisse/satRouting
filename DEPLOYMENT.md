# Satellite Routing Simulator - Deployment Guide

## Quick Start

### Option 1: Docker (Recommended)

#### Linux/macOS

```bash
# Build and run with default settings
docker-compose up --build

# Run with custom parameters
docker-compose up --build --abort-on-container-exit

# Run specific simulation (OneWeb, Strategy 9, 30s, 5 Gbps)
SIM_STRATEGY=9 SIM_DURATION=30 SIM_TRAFFIC=5 SIM_INPUT=1 docker-compose up
```

#### Windows

**Prerequisites:**
1. Install [Docker Desktop for Windows](https://www.docker.com/products/docker-desktop/)
2. Enable WSL 2 backend (recommended)
3. Install Git for Windows (handles line endings automatically)

```powershell
# Clone repository (Git handles line endings)
git clone <repository-url>
cd satellite-routing-simulator

# If files were copied (not cloned), fix line endings:
# Option A: Using included script
.\fix-line-endings.bat

# Option B: Using Git Bash
bash fix-line-endings.sh

# Build and run
docker-compose up --build
```

### Option 2: Local Python Environment

```bash
# Create virtual environment
cd simulator
python3 -m venv venv
source venv/bin/activate

# Install dependencies
pip install -r requirements.txt

# Run simulation
python3 main.py --strategy 5 --duration 60 --traffic 10 --input 1
```

---

## System Requirements

### Minimum Requirements

| Constellation | RAM | CPU | Storage |
|---------------|-----|-----|---------|
| Iridium (66 sats) | 2 GB | 1 core | 1 GB |
| OneWeb (634 sats) | 4 GB | 2 cores | 2 GB |
| Starlink (partial) | 8 GB | 4 cores | 5 GB |

### Recommended Requirements

| Constellation | RAM | CPU | Storage |
|---------------|-----|-----|---------|
| Iridium (66 sats) | 4 GB | 2 cores | 2 GB |
| OneWeb (634 sats) | 8 GB | 4 cores | 5 GB |
| Starlink (full) | 32 GB | 8 cores | 10 GB |

---

## Configuration Options

### Environment Variables

| Variable | Default | Description |
|----------|---------|-------------|
| `SIM_STRATEGY` | 5 | Routing strategy (1-15) |
| `SIM_DURATION` | 60 | Simulation duration (seconds) |
| `SIM_TRAFFIC` | 10 | Traffic volume (Gbps) |
| `SIM_INPUT` | 1 | Satellite format (0=Iridium, 1=OneWeb, 2=Custom) |
| `SKIP_FLASK` | false | Skip traffic matrix service |

### Routing Strategies

| ID | Name | Paradigm | Memory Usage |
|----|------|----------|--------------|
| 1-3 | Position Guessing | Distributed | Low |
| 4-6 | Position Sharing | Distributed | Low-Medium |
| 7-8 | Adaptive Load Balancing | Distributed | Medium |
| 9 | Baseline Dijkstra | Centralized | **High** ⚠️ |
| 10-11 | Source Routing | Centralized | Medium |
| 12-15 | K-Disjoint Paths | Centralized | High |

**⚠️ Warning for Strategy 9 (Dijkstra):** On low-spec machines:
- Use Iridium constellation (`--input 0`)
- Reduce traffic volume (`--traffic 3`)
- Shorten duration (`--duration 30`)

---

## Docker Deployment

### Build Image

```bash
docker build -t satellite-simulator:latest .
```

### Run Container

```bash
# Basic run
docker run --rm -it \
  -e SIM_STRATEGY=5 \
  -e SIM_DURATION=60 \
  -e SIM_TRAFFIC=10 \
  -v $(pwd)/simulator:/satRouting/simulator \
  satellite-simulator:latest

# With resource limits
docker run --rm -it \
  --memory=8g \
  --cpus=4.0 \
  -e SIM_STRATEGY=9 \
  -e SIM_INPUT=1 \
  satellite-simulator:latest
```

### Docker Compose Profiles

```bash
# Run main simulator
docker-compose up

# Run only traffic matrix service
docker-compose --profile standalone up traffic-matrix-svc

# Run with custom resources
docker-compose up --build \
  --abort-on-container-exit \
  --exit-code-from satellite-simulator
```

---

## Kubernetes Deployment (Optional)

### Resource Quota Example

```yaml
apiVersion: v1
kind: ResourceQuota
metadata:
  name: simulator-quota
spec:
  hard:
    requests.cpu: "4"
    requests.memory: 8Gi
    limits.cpu: "8"
    limits.memory: 16Gi
```

### Pod Example

```yaml
apiVersion: v1
kind: Pod
metadata:
  name: satellite-simulator
spec:
  containers:
  - name: simulator
    image: satellite-simulator:latest
    resources:
      requests:
        memory: "4Gi"
        cpu: "2"
      limits:
        memory: "8Gi"
        cpu: "4"
    env:
    - name: SIM_STRATEGY
      value: "5"
    - name: SIM_DURATION
      value: "60"
```

---

## Cross-Platform Transfer Guide

### Ubuntu → Windows Transfer

**Method 1: Git (Recommended - Handles Line Endings Automatically)**

```bash
# On Ubuntu (ensure .gitattributes exists)
git add .gitattributes
git commit -m "Add line ending configuration"
git push

# On Windows
git clone <repository-url>
# Git automatically converts to CRLF on checkout (if configured)
# Docker build will work correctly
```

**Method 2: Direct Copy (USB/Network)**

```bash
# On Ubuntu, before copying:
cd satellite-routing-simulator

# Convert all files to Unix line endings (ensure consistency)
bash fix-line-endings.sh

# Copy to USB/network drive
# Files will work on Windows Docker (build context normalizes)
```

**Method 3: Archive (ZIP/TAR)**

```bash
# On Ubuntu, create archive:
tar -czf sat-routing.tar.gz --transform='s,^,satellite-routing-simulator/,' \
    --exclude='venv' \
    --exclude='__pycache__' \
    --exclude='*.pyc' \
    .

# On Windows:
# 1. Extract archive
# 2. Run: .\fix-line-endings.bat
# 3. Build: docker-compose up --build
```

### Windows → Ubuntu Transfer

**Method 1: Git (Recommended)**
```bash
# On Windows
git clone <repository-url>
git push

# On Ubuntu
git clone <repository-url>
# Git preserves LF endings
```

**Method 2: Direct Copy**
```bash
# On Windows, before copying:
.\fix-line-endings.bat

# Copy to USB/network drive
# Files will work on Ubuntu Docker
```

### Line Ending Configuration

**`.gitattributes`** (already included) ensures:
- Shell scripts (`.sh`) always use LF
- Python files (`.py`) always use LF
- YAML files (`.yml`) always use LF
- Git handles conversion automatically on checkout

**Git Configuration:**
```bash
# On Windows (optional - Git handles this via .gitattributes)
git config --global core.autocrlf true

# On Linux/macOS
git config --global core.autocrlf input
```

---

## Troubleshooting

### Line Ending Issues (Windows → Linux)

**Symptoms:**
```
standard_init_linux.go:211: exec user process caused "exec format error"
/bin/bash^M: bad interpreter: No such file or directory
```

**Cause:** Files have Windows line endings (CRLF) instead of Unix (LF)

**Solutions:**

**Option 1: Use Git (Automatic)**
```bash
# Git automatically handles line endings with .gitattributes
git clone <repository-url>
```

**Option 2: Run conversion script**
```bash
# On Windows (PowerShell)
.\fix-line-endings.bat

# On Linux/macOS
bash fix-line-endings.sh
```

**Option 3: Manual conversion (WSL/Linux)**
```bash
sudo apt install dos2unix
dos2unix bootstrapperDocker.sh
dos2unix simulator/*.py
```

**Option 4: VS Code Settings**
Add to `.vscode/settings.json`:
```json
{
  "files.eol": "\n"
}
```

### Memory Issues (OOM Killer)

**Symptoms:** Container killed unexpectedly, "Killed" message

**Solutions:**
1. Increase memory limit in docker-compose.yml
2. Reduce constellation size (use Iridium instead of Starlink)
3. Reduce traffic volume
4. Use Strategy 1-8 instead of 9-15

```bash
# Example: Low-memory configuration
docker run --memory=4g --cpus=2.0 \
  -e SIM_STRATEGY=5 \
  -e SIM_DURATION=30 \
  -e SIM_TRAFFIC=3 \
  -e SIM_INPUT=0 \
  satellite-simulator:latest
```

### Flask Service Fails

**Symptoms:** Traffic matrix generation fails

**Solutions:**
1. Check API key in `secrets/city_api_key.txt`
2. Set `SKIP_FLASK=true` to bypass
3. Verify network connectivity

```bash
# Test Flask health
curl http://localhost:8001/traffic_matrix?cities=Tokyo&total_volume_of_traffic=1
```

### Slow Performance

**Symptoms:** Simulation takes hours

**Solutions:**
1. Reduce simulation duration
2. Use fewer satellites (Iridium vs Starlink)
3. Increase CPU allocation
4. Disable unnecessary metrics collection

---

## Output Files

Simulation results are saved in `simulator/` directory:

| File | Description |
|------|-------------|
| `*_results.json` | Analysis results |
| `dijkstra_table*.json` | Path comparison data |
| `control_traffic_comparison.json` | Control overhead metrics |
| `time_passing_simulation.json` | Time-series data |

---

## Security Considerations

1. **API Keys:** Store in Docker secrets or environment variables
2. **Non-root User:** Container runs as `simuser` (not root)
3. **Resource Limits:** Always set memory/CPU limits in production
4. **Network:** Expose only necessary ports (8001 for Flask)

---

## Performance Tuning

### For Low-Spec Machines (< 8GB RAM)

```bash
# Use Iridium constellation
SIM_INPUT=0

# Use lightweight strategies
SIM_STRATEGY=5  # Position Sharing LB

# Reduce load
SIM_DURATION=30
SIM_TRAFFIC=3
```

### For High-Spec Machines (> 16GB RAM)

```bash
# Use full Starlink constellation
SIM_INPUT=2
# Enter: https://celestrak.org/NORAD/elements/gp.php?GROUP=starlink&FORMAT=json

# Use advanced strategies
SIM_STRATEGY=15  # Edge Disjoint Cost Balancing

# Full simulation
SIM_DURATION=120
SIM_TRAFFIC=20
```

---

## Support

For issues or questions:
1. Check `simulator/DOCUMENTATION.md` for detailed architecture
2. Review `simulator/REQUIREMENTS.md` for class dependencies
3. Enable debug mode: Add `DEBUG=True` in `constants.py`
