#!/usr/bin/env bash
set -e
cd "$(dirname "$0")"

echo "============================================================"
echo "  Starting Antigravity DataFlow (Visual ETL Engine)"
echo "============================================================"

PY_CMD=""

if [ -f ".venv/bin/python" ]; then
    PY_CMD=".venv/bin/python"
elif [ -f "venv/bin/python" ]; then
    PY_CMD="venv/bin/python"
elif command -v python3 &>/dev/null; then
    PY_CMD="python3"
elif command -v python &>/dev/null; then
    PY_CMD="python"
fi

if [ -z "$PY_CMD" ]; then
    echo "[ERROR] Python 3 was not found. Please install Python 3.10+."
    exit 1
fi

if ! "$PY_CMD" -c "import flask, pandas, waitress" &>/dev/null; then
    echo "[INFO] Installing required dependencies from requirements.txt..."
    "$PY_CMD" -m pip install -r requirements.txt
fi

echo "[OK] Using Python: $PY_CMD"
echo "[INFO] Starting application server and opening browser..."
exec "$PY_CMD" run.py
