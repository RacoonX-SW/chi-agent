FROM python:3.13-slim@sha256:57b29a7c050c4e679e4bea572e14b3965cf4b5839de2da49d55e49ffc4024f39

# Install system dependencies
RUN apt-get update && apt-get install -y --no-install-recommends \
    git \
    curl \
    ca-certificates \
    && rm -rf /var/lib/apt/lists/*

# Install pinned uv
RUN pip install --no-cache-dir uv==0.6.14

# Set up isolated container environment for dependencies in /opt/venv
ENV UV_PROJECT_ENVIRONMENT=/opt/venv
ENV PATH="/opt/venv/bin:$PATH"
ENV PYTHONDONTWRITEBYTECODE=1
ENV PYTHONUNBUFFERED=1

WORKDIR /workspace

# Copy dependency definition and install locked dependencies in /opt/venv
COPY pyproject.toml requirements.lock /workspace/
RUN uv venv /opt/venv && uv pip install --no-cache -r requirements.lock && uv pip install --no-deps -e .

# Default command runs offline tests
CMD ["python3", "-m", "unittest", "discover", "-s", "tests", "-v"]
