# Test-only derived world; only the exported package and fixed vendor are copied.
FROM chi-agent-a-world:py312-review-20261025-01
COPY bundle/ /opt/chi-go/
COPY vendor/ /opt/chi-go/vendor/chi-bench/
COPY model/ /test/model/
COPY pdf/ /pdf-deps/
COPY harbor_synthetic_python.py /test/harbor_synthetic_python.py
RUN ln -s /usr/local/bin/python3 /workspace/.venv/bin/python-real && rm /workspace/.venv/bin/python && printf '%s\n' '#!/bin/sh' 'case "$1" in /opt/chi-go/scripts/go_chi_entry.py) exec /usr/local/bin/python3 /test/harbor_synthetic_python.py "$@" ;; *) exec /workspace/.venv/bin/python-real "$@" ;; esac' > /workspace/.venv/bin/python \
 && chmod 755 /workspace/.venv/bin/python \
 && mkdir -p /logs/artifacts/workspaces /test/state \
 && git config --global --add safe.directory /opt/chi-go/vendor/chi-bench
