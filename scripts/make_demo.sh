#!/usr/bin/env bash
# Пересборка двух демо-роликов (base + extended) с одной озвучкой/сценарием.
# Пример того, как на HP получать «обычный» и «улучшенный» варианты для сравнения.
set -euo pipefail
cd "$(dirname "$0")/.."
PY="./venv/bin/python"; [ -x "$PY" ] || PY="python3"
exec "$PY" -m tubecook.cli demo --profile base
