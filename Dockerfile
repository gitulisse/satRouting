# Multi-stage build for Satellite Routing Simulator
# Optimized for memory-intensive simulations

# ============================================
# Stage 1: Builder (install dependencies)
# ============================================
FROM python:3.11-slim as builder

WORKDIR /build

# Install build dependencies
RUN apt-get update && apt-get install -y --no-install-recommends \
    gcc \
    g++ \
    libgeos-dev \
    libproj-dev \
    proj-data \
    proj-bin \
    && rm -rf /var/lib/apt/lists/*

# Copy and install Python dependencies
COPY simulator/requirements.txt .
RUN pip install --no-cache-dir --user -r requirements.txt

# ============================================
# Stage 2: Runtime (minimal image)
# ============================================
FROM python:3.11-slim

# Labels for container metadata
LABEL maintainer="satellite-routing-simulator"
LABEL version="1.0"
LABEL description="LEO Satellite Network Routing Simulator"

# Set environment variables
ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    PIP_NO_CACHE_DIR=1 \
    PIP_DISABLE_PIP_VERSION_CHECK=1 \
    # Memory optimization for large constellations
    PYTHONMALLOC=malloc \
    # Set default simulation parameters
    SIM_STRATEGY=9 \
    SIM_DURATION=60 \
    SIM_TRAFFIC=10 \
    SIM_INPUT=1

# Install runtime dependencies
RUN apt-get update && apt-get install -y --no-install-recommends \
          libgeos-c1v5 \
          libproj25 \
          proj-bin \
          proj-data \
          curl \
          && rm -rf /var/lib/apt/lists/* \
          && apt-get clean


# Create non-root user for security
RUN useradd --create-home --shell /bin/bash simuser

WORKDIR /satRouting
RUN mkdir -p /satRouting/simulator/output_resumed && \
    chown -R simuser:simuser /satRouting

# Copy installed packages from builder
COPY --from=builder /root/.local /home/simuser/.local

# Copy application code
COPY --chown=simuser:simuser data/ /satRouting/data/
COPY --chown=simuser:simuser secrets/ /satRouting/secrets/
COPY --chown=simuser:simuser simulator/ /satRouting/simulator/
COPY --chown=simuser:simuser traffic_matrix_generator/ /satRouting/traffic_matrix_generator/
COPY --chown=simuser:simuser scripts/ /satRouting/scripts/

# Make bootstrap scripts executable
RUN chmod +x /satRouting/scripts/*.sh

# Set PATH to include user-installed packages
ENV PATH=/home/simuser/.local/bin:$PATH

# Switch to non-root user
USER simuser

# Expose Flask port
EXPOSE 8001

# Health check for Flask service
HEALTHCHECK --interval=30s --timeout=10s --start-period=5s --retries=3 \
    CMD curl -f http://localhost:8001/traffic_matrix?cities=Tokyo\&total_volume_of_traffic=1 || exit 1

# Resource hints (for Docker Compose / Kubernetes)
# Note: Actual limits should be set in docker-compose.yml or k8s manifests
# Memory: 4GB recommended minimum, 8GB for Starlink simulations
# CPU: 2 cores minimum, 4+ recommended

# Default command
CMD ["/satRouting/scripts/bootstrapperDocker.sh"]
