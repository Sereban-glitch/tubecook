#!/usr/bin/env bash
# Запуск полного набора тестов Tubecook v4 (без сети, ~2 мин).
set -euo pipefail
cd "$(dirname "$0")/.."
PY="./venv/bin/python"; [ -x "$PY" ] || PY="python3"
exec "$PY" -m pytest tests/ -q --color=yes
