#!/bin/sh
set -eu

# Run inside chi-agent-dev:latest. The target is a separately mounted Docker
# volume, keeping the base /opt/venv and requirements.lock unchanged.
TARGET=${1:-/model-deps}
uv pip install --target "$TARGET" --require-hashes -r /workspace/requirements-model.lock
PYTHONPATH="$TARGET" /opt/venv/bin/python -c 'import importlib.metadata as m; assert m.version("openai-agents") == "0.13.6"; assert m.version("openai") == "2.36.0"'
