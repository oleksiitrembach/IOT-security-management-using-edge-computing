#!/usr/bin/env bash
# PB4 / S6 — kontrola dostepu (TLS + ACL). Cienki delegat do run.py:
# generuje certy w kontenerze, podnosi overlay TLS i sprawdza odrzucenie
# dostepu anonimowego (auth) oraz odczytu spoza ACL (autoryzacja).
#   ./scripts/test_access_control.sh
set -e
PYTHON="${PYTHON:-python}"; command -v "$PYTHON" >/dev/null 2>&1 || PYTHON=python3
"$PYTHON" run.py access-control
