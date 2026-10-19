#!/usr/bin/env bash
# ============================================================================
# hp_bench.sh — БЕНЧМАРК НА ЦЕЛЕВОЙ МАШИНЕ (HP ProBook 440 G3).
# Проверяет VA-API, рендерит ДЕМО-сюжет профилями base/extended на CPU и VA-API,
# замеряет время и пиковую RAM, пишет bench_report_<дата>.json.
# Замеры песочницы Z.ai НЕ подставляются за замеры HP — только для сравнения.
# ============================================================================
set -euo pipefail
cd "$(dirname "$0")/.."

PY="./venv/bin/python"; [ -x "$PY" ] || PY="python3"

echo "=== 1. Окружение ==="
uname -a
nproc; free -m | head -2
echo "VA-API устройство:"; ls -l /dev/dri/renderD128 2>/dev/null || echo "  нет (/dev/dri/renderD128)"
command -v vainfo >/dev/null && vainfo 2>/dev/null | head -12 || echo "  vainfo не установлен (apt install vainfo)"

echo; echo "=== 2. Тесты (быстрая проверка целостности) ==="
"$PY" -m pytest tests/ -q || true

run_profile () {  # $1=profile $2=hw $3=outfile
  echo; echo "=== 3. Рендер: profile=$1 hw=$2 ==="
  mkdir -p build
  T0=$(date +%s.%N)
  /usr/bin/time -v env TUBECOOK_HW="$2" "$PY" -m tubecook.cli demo \
      --profile "$1" --out "build/bench_$1_$2" 2> "build/time_$1_$2.txt" \
      || { echo "рендер failed, см. build/time_$1_$2.txt"; return 1; }
  T1=$(date +%s.%N)
  RAM=$(grep "Maximum resident set size" "build/time_$1_$2.txt" | grep -o -E "[0-9]+" || echo "?")
  echo "время: $(echo "$T1 $T0" | awk '{printf "%.1f", $1-$2}') c; пиковая RAM: ${RAM:-?} КБ"
}

run_profile base  cpu
run_profile base  vaapi || echo "VA-API недоступен — CPU fallback (это нормально)"
run_profile extended cpu

echo; echo "=== 4. Отчёт ==="
"$PY" - <<'EOF'
import json, glob, os, datetime
rep = {"machine": os.uname().nodename, "ts": datetime.datetime.now().astimezone().isoformat(),
       "profiles": {}}
for d in sorted(glob.glob("build/bench_*")):
    rp = os.path.join(d, "render_report.json")
    if os.path.exists(rp):
        r = json.load(open(rp))
        rep["profiles"][os.path.basename(d)] = {
            k: r.get(k) for k in ("profile", "hw", "wall_s", "stages_s",
                                  "total_s", "master_mb", "env")}
name = f"bench_report_{datetime.datetime.now():%Y%m%d_%H%M}.json"
json.dump(rep, open(name, "w"), ensure_ascii=False, indent=2)
print("сохранено:", name)
print(json.dumps(rep["profiles"], ensure_ascii=False, indent=1))
EOF
echo
echo "Сравните wall_s с песочницей Z.ai (base CPU: ~101 c на 2 ядрах) и решите,"
echo "оставлять VA-API (TUBECOOK_HW=vaapi) или CPU (TUBECOOK_HW=cpu) в .env."
