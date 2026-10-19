#!/usr/bin/env bash
# ============================================================================
# install.sh — установка Tubecook v4 РЯДОМ с v3 (v3 не трогаем!).
# Запуск: bash install.sh [каталог_установки]   (по умолчанию ~/projects/tubecook_v4)
# ============================================================================
set -euo pipefail

DEST="${1:-$HOME/projects/tubecook_v4}"
SRC="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"

echo "Источник:  $SRC"
echo "Установка: $DEST"

if [ -d "$DEST/data/tubecook.db" ] || [ -f "$DEST/data/tubecook.db" ]; then
  echo "ВНИМАНИЕ: в $DEST уже есть БД v4 — это обновление, данные сохраняются."
fi

mkdir -p "$DEST"
# копируем пакет/доки/скрипты (артефакты и data/ не трогаем)
rsync -a --exclude 'data/' --exclude 'build/' --exclude 'venv/' \
      --exclude '__pycache__/' --exclude '.pytest_cache/' "$SRC/" "$DEST/" 2>/dev/null \
  || cp -r "$SRC/tubecook" "$SRC/tests" "$SRC/docs" "$SRC/scripts" "$SRC/examples" \
           "$SRC/deploy" "$SRC/assets" "$SRC/env.example" "$SRC/README.md" \
           "$SRC/PROJECT_STATE.md" "$SRC/SPEC_PROTOCOL.md" "$SRC/requirements.txt" \
           "$SRC/pyproject.toml" "$DEST/"

cd "$DEST"
if [ ! -d venv ]; then
  python3 -m venv venv
fi
./venv/bin/pip install --quiet -r requirements.txt
echo "Готово. Дальше:"
echo "  cp env.example .env && \$EDITOR .env      # ID и токены — ТОЛЬКО локально"
echo "  ./venv/bin/python -m pytest tests/ -q     # тесты"
echo "  ./venv/bin/python -m tubecook.cli demo --profile base   # демо-ролик"
echo "  bash scripts/hp_bench.sh                  # замеры VA-API/CPU на этой машине"
