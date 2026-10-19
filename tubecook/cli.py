"""CLI Tubecook v4: все операции доступны без Telegram (питание тестов/бенча).

python -m tubecook.cli <команда> --help
"""
from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

from tubecook import db as dbm, __version__
from tubecook.bot.core import BotCore, DEMO_JOB
from tubecook.config import Config, load_env_file
from tubecook.pipeline import Pipeline
from tubecook.publish.telegram_pub import TelegramPublisher
from tubecook.publish.youtube_pub import YouTubePublisher
from tubecook.queue import Queue
from tubecook.scheduler import Scheduler
from tubecook.security import SenderRole


def _ctx(root: str = "."):
    load_env_file(Path(root) / ".env")
    cfg = Config.from_env(root)
    conn = dbm.connect(cfg.db_path)
    dbm.migrate(conn)
    return cfg, conn, Queue(conn, cfg)


def cmd_ingest(args) -> int:
    cfg, conn, queue = _ctx()
    raw = Path(args.file).read_text(encoding="utf-8")
    from tubecook.protocol import parse_message
    parsed = parse_message(raw) if "#TUBECOOK" in raw.upper() else _parse_json_job(raw)
    if not parsed.ok:
        print("ОШИБКА ФОРМАТА: " + "; ".join(parsed.errors[:6]))
        return 2
    role = SenderRole.ADMIN if args.role == "admin" else SenderRole.SENDER
    r = queue.submit(parsed.job, sender_id=args.sender, role=role)
    print(r.render_text())
    return 0


def _parse_json_job(raw: str):
    from tubecook.protocol import ParseResult, validate_payload, content_hash, dedupe_key_for
    try:
        data = json.loads(raw)
    except json.JSONDecodeError as e:
        res = ParseResult()
        res.errors = [f"битый JSON: {e}"]
        return res
    res = ParseResult()
    res.errors = validate_payload(data)
    if not res.errors:
        res.ok = True
        res.job = data
        res.job_id = data.get("job_id", "")
        res.content_hash = content_hash(data)
        res.dedupe_key = dedupe_key_for(data)
    return res


def cmd_status(_args) -> int:
    cfg, conn, queue = _ctx()
    s = queue.status_summary()
    print(json.dumps(s, ensure_ascii=False, indent=2))
    return 0


def cmd_run_once(args) -> int:
    cfg, conn, queue = _ctx()
    publishers = {"telegram": TelegramPublisher(cfg), "youtube": YouTubePublisher(cfg)}
    pipeline = Pipeline(cfg, queue, publishers=publishers)
    jid = pipeline.process_next(owner="cli")
    print("обработано:", jid or "(очередь пуста)")
    return 0


def cmd_publish(args) -> int:
    cfg, conn, queue = _ctx()
    if args.live:
        print("ВНИМАНИЕ: live-режим. Реальные API будут вызваны.")
        cfg.dry_run_publish = False
    publishers = {"telegram": TelegramPublisher(cfg), "youtube": YouTubePublisher(cfg)}
    pipeline = Pipeline(cfg, queue, publishers=publishers)
    res = pipeline.publish_job(args.job_id, owner="cli")
    print(json.dumps(res, ensure_ascii=False, indent=2))
    return 0


def cmd_render(args) -> int:
    """Прямой рендер JSON-задания без БД (демо/бенч)."""
    load_env_file(".env")
    cfg = Config.from_env(".")
    payload = json.loads(Path(args.job).read_text(encoding="utf-8"))
    from tubecook.media import deliver, render
    out = Path(args.out) if args.out else cfg.jobs_dir / payload["job_id"]
    res = render.render_episode(payload, cfg, out, profile=args.profile,
                                engine=args.engine)
    tg = deliver.encode_telegram(res["master"], out / "telegram.mp4", cfg)
    deliver.extract_thumbnail(res["master"], out / "thumb.jpg")
    print(json.dumps({"master": str(res["master"]),
                      "telegram": str(tg["path"]), "tg_mb": tg["size_mb"],
                      "report": str(out / "render_report.json")},
                     ensure_ascii=False, indent=2))
    return 0


def cmd_demo(args) -> int:
    """Демо-ролик (помечен 'НЕ НОВОСТЬ'): base/extended профили."""
    args.job = str(Path(__file__).parent.parent / "examples" / "demo_job.json")
    args.out = args.out or f"build/demo_{args.profile}"
    return cmd_render(args)


def cmd_bot(args) -> int:
    from tubecook.service import main as service_main
    cfg, conn, queue = _ctx()
    service_main(cfg, console=True)
    return 0


def cmd_service(_args) -> int:
    from tubecook.service import main as service_main
    cfg, _conn, _queue = _ctx()
    service_main(cfg, console=False)
    return 0


def cmd_approve(args) -> int:
    cfg, conn, queue = _ctx()
    admin = next(iter(cfg.admin_ids), 0)
    r = queue.approve(args.job_id, admin_id=admin)
    print(r.detail or r.render_text())
    return 0


def cmd_cancel(args) -> int:
    cfg, conn, queue = _ctx()
    admin = next(iter(cfg.admin_ids), 0)
    r = queue.cancel(args.job_id, by=admin, reason=args.reason or "")
    print(r.detail or r.render_text())
    return 0


def cmd_import_v3(args) -> int:
    from tubecook.import_v3 import import_v3
    cfg, conn, queue = _ctx()
    report = import_v3(Path(args.path), queue, cfg)
    print(json.dumps(report, ensure_ascii=False, indent=2))
    return 0


def cmd_oauth(_args) -> int:
    from tubecook.publish.youtube_pub import run_local_oauth
    print(run_local_oauth())
    return 0


def cmd_check(args) -> int:
    cfg, conn, queue = _ctx()
    publishers = {"telegram": TelegramPublisher(cfg), "youtube": YouTubePublisher(cfg)}
    core = BotCore(cfg, queue, None, None, publishers)
    for r in core._check(args.job_id):
        print(r["text"])
    return 0


def build_parser() -> argparse.ArgumentParser:
    ap = argparse.ArgumentParser(prog="tubecook", description=f"Tubecook v{__version__}")
    sub = ap.add_subparsers(dest="cmd", required=True)

    p = sub.add_parser("ingest", help="принять задание из файла (текст протокола/JSON)")
    p.add_argument("file")
    p.add_argument("--role", default="sender", choices=["sender", "admin"])
    p.add_argument("--sender", type=int, default=0)
    p.set_defaults(fn=cmd_ingest)

    p = sub.add_parser("status", help="сводка очереди")
    p.set_defaults(fn=cmd_status)

    p = sub.add_parser("run-once", help="обработать одно задание (рендер)")
    p.set_defaults(fn=cmd_run_once)

    p = sub.add_parser("publish", help="публикация задания (по умолчанию dry-run)")
    p.add_argument("job_id")
    p.add_argument("--live", action="store_true",
                   help="реально вызывать API (требует токены и права)")
    p.set_defaults(fn=cmd_publish)

    p = sub.add_parser("render", help="прямой рендер JSON-задания (без очереди)")
    p.add_argument("job")
    p.add_argument("--profile", default="base", choices=["base", "extended"])
    p.add_argument("--engine", default="auto", choices=["auto", "edge", "mock"])
    p.add_argument("--out")
    p.set_defaults(fn=cmd_render)

    p = sub.add_parser("demo", help="демо-ролик (base/extended)")
    p.add_argument("--profile", default="base", choices=["base", "extended"])
    p.add_argument("--engine", default="auto", choices=["auto", "edge", "mock"])
    p.add_argument("--out")
    p.set_defaults(fn=cmd_demo)

    p = sub.add_parser("bot", help="консольная сессия бота (тот же протокол)")
    p.set_defaults(fn=cmd_bot)

    p = sub.add_parser("service", help="запуск демона (бот+планировщик+воркер)")
    p.set_defaults(fn=cmd_service)

    p = sub.add_parser("approve", help="одобрить выпуск")
    p.add_argument("job_id")
    p.set_defaults(fn=cmd_approve)

    p = sub.add_parser("cancel", help="отменить задание")
    p.add_argument("job_id")
    p.add_argument("--reason", default="")
    p.set_defaults(fn=cmd_cancel)

    p = sub.add_parser("import-v3", help="импорт заданий из каталога v3 (read-only)")
    p.add_argument("path")
    p.set_defaults(fn=cmd_import_v3)

    p = sub.add_parser("oauth-youtube", help="локальная OAuth-авторизация YouTube")
    p.set_defaults(fn=cmd_oauth)

    p = sub.add_parser("check", help="сверить uncertain-публикации")
    p.add_argument("job_id")
    p.set_defaults(fn=cmd_check)

    p = sub.add_parser("domdara-ingest", help="запуск сбора новостей Домдары")
    p.add_argument("--dry-run", action="store_true", help="только сбор и анализ без сохранения в очередь")
    p.add_argument("--limit", type=int, default=5, help="максимум статей за такт")
    p.set_defaults(fn=cmd_domdara_ingest)

    p = sub.add_parser("domdara-status", help="статус курсора сбора Домдары")
    p.set_defaults(fn=cmd_domdara_status)
    return ap


def cmd_domdara_ingest(args) -> int:
    cfg, conn, queue = _ctx()
    from tubecook.ingest.domdara import DomdaraIngest
    ingest = DomdaraIngest(cfg, queue)
    enqueued = ingest.ingest_once(dry_run=args.dry_run, limit=args.limit)
    if enqueued:
        print(f"Обработано заданий Domdara: {len(enqueued)}")
        for jid in enqueued:
            print(f"  + {jid}")
    else:
        print("Новых статей Domdara не обнаружено.")
    return 0


def cmd_domdara_status(args) -> int:
    cfg, conn, queue = _ctx()
    last_guid = dbm.get_meta(conn, "domdara_last_seen_guid", "не установлен")
    last_date = dbm.get_meta(conn, "domdara_last_pub_date", "не установлен")
    print("Статус ингеста Домдара:")
    print(f"  feed_url: {cfg.domdara_feed_url}")
    print(f"  enabled: {cfg.domdara_enabled}")
    print(f"  last_seen_guid: {last_guid}")
    print(f"  last_pub_date: {last_date}")
    print(f"  seed_mode: {cfg.domdara_seed_mode}")
    print(f"  lookback_days: {cfg.domdara_initial_lookback_days}")
    return 0


def main() -> int:
    ap = build_parser()
    args = ap.parse_args()
    try:
        return args.fn(args)
    except KeyboardInterrupt:
        return 130


if __name__ == "__main__":
    sys.exit(main())
