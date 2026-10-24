FROM python:3.13-slim

# Install system dependencies including docker-cli for environment inspections
RUN apt-get update && apt-get install -y --no-install-recommends \
    git \
    curl \
    ca-certificates \
    docker-cli \
    && rm -rf /var/lib/apt/lists/*

# Install uv via pip
RUN pip install --no-cache-dir uv

# Set up isolated container environment for dependencies in /opt/venv
ENV UV_PROJECT_ENVIRONMENT=/opt/venv
ENV PATH="/opt/venv/bin:$PATH"
ENV PYTHONDONTWRITEBYTECODE=1
ENV PYTHONUNBUFFERED=1

WORKDIR /workspace

# Copy dependency definition and pre-install packages in /opt/venv
COPY pyproject.toml /workspace/
RUN uv venv /opt/venv && uv pip install -e ".[dev]"

# Default command runs offline tests
CMD ["python3", "-m", "unittest", "discover", "-s", "tests", "-v"]
