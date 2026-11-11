# A-stage controller only. It uses the existing D0 development image and adds
# pinned clients for the local Docker Engine API and the Hugging Face Hub.
FROM chi-agent-dev:latest

COPY docker/a/requirements.lock /tmp/a-requirements.lock
RUN uv venv /opt/a-venv --python 3.12 \
    && uv pip install --python /opt/a-venv/bin/python --no-cache -r /tmp/a-requirements.lock

WORKDIR /workspace
ENV PATH="/opt/a-venv/bin:${PATH}" PYTHONDONTWRITEBYTECODE=1 PYTHONUNBUFFERED=1 DOCKER_HOST=unix:///var/run/docker.sock
CMD ["sleep", "infinity"]
