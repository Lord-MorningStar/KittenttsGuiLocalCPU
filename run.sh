#!/usr/bin/env bash
set -euo pipefail
ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
cd "$ROOT"
if [ ! -x "$ROOT/.venv-cpp/bin/python" ]; then
    echo "KittenTTS Local no está instalado. Ejecuta ./setup.sh primero." >&2
    exit 1
fi
export PYTHONUTF8=1
export GRADIO_ANALYTICS_ENABLED=False
exec "$ROOT/.venv-cpp/bin/python" app.py "$@"
