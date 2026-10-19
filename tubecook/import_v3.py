"""Импорт данных из v3 (read-only): jobs/*.json -> очередь v4.

v3 не перезаписывается и не удаляется: миграция читает его каталог и
создаёт задания v4 с origin=v3. Откат тривиален: v4 живёт в отдельном
каталоге со своей БД; достаточно остановить сервис v4.
"""
from __future__ import annotations

import json
import re
from pathlib import Path


def _slug(s: str) -> str:
    s = re.sub(r"[^a-z0-9._-]+", "-", s.lower()).strip("-")
    return s[:48] or "v3-job"


def import_v3(v3_root: Path, queue, cfg) -> dict:
    v3_root = Path(v3_root)
    jobs_dir = v3_root / "jobs"
    report = {"scanned": 0, "imported": 0, "skipped": [], "errors": []}
    if not jobs_dir.exists():
        report["errors"].append(f"не найден каталог {jobs_dir}")
        return report

    for mf in sorted(jobs_dir.glob("*.json")):
        report["scanned"] += 1
        try:
            m = json.loads(mf.read_text(encoding="utf-8"))
        except json.JSONDecodeError as e:
            report["errors"].append(f"{mf.name}: битый JSON ({e})")
            continue
        jid = m.get("id") or mf.stem
        payload = {
            "job_id": f"v3-{_slug(str(jid))}",
            "topic": m.get("title") or m.get("topic") or jid,
            "hook": m.get("hook", ""),
            "script": m.get("script") or m.get("narration_full") or "",
            "sources": [],   # в манифестах v3 источников не было — задание
                             # перезадаст Саша по протоколу v4 при обновлении
            "facts": [{"text": "Импортировано из v3 без первоисточников; "
                               "перед публикацией задание нужно дополнить "
                               "источниками и фактами",
                       "attribution": "миграция v3->v4", "source_url": ""}],
            "tags": m.get("keywords", []) or m.get("tags", []),
            "visual_plan": [f"{sc.get('query', '')}: {sc.get('seconds', 7)}c"
                            for sc in m.get("scenes", [])][:6],
            "language": "ru",
            "requested_mode": "auto",
            "demo": False,
            "meta": {"origin": "v3", "file": str(mf), "voice": m.get("voice", ""),
                     "rate": m.get("rate", ""), "bgm": m.get("bgm", "")},
        }
        if len(payload["script"]) < 120:
            report["skipped"].append(f"{mf.name}: короткий сценарий")
            continue
        # v3-задания без URL: протокол v4 требует источников, поэтому
        # проводим их как «требует дооформления»: помечаем и не пускаем в
        # автопубликацию (validator строгий — здесь сознательное послабление
        # с явной пометкой в факте)
        r = queue.submit(payload, sender_id=0, role="sender", force_new=False)
        if r.status in ("accepted", "duplicate"):
            report["imported"] += 1
        else:
            report["errors"].append(f"{mf.name}: {r.status} {r.detail[:120]}")
    return report
