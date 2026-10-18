#!/usr/bin/env python3
# ============================================================================
# 07_upload_youtube.py — Resumable Upload в YouTube Data API v3.
# Квоты (Глава 3.3): videos.insert = 1600 units; дневной лимит проекта
# 10000 units → максимум 6 загрузок/день через API (без расширенной квоты).
#
# ГЛАВНАЯ ловушка OAuth (Глава 5.5): пока приложение в статусе «Testing»,
# refresh-токен живёт 7 СУТОК. Переведите OAuth-консент на Production —
# область youtube.upload не является sensitive, верификация лёгкая.
#
# Использование:
#   python3 07_upload_youtube.py --video build/task-001/out/final_1080x1920.mp4 \
#       --title "Парадокс Банаха-Тарского" --tags "наука,математика,shorts" \
#       --privacy public          # public | unlisted | private
# ============================================================================
import argparse
import os
import sys
import time

try:
    from google.auth.transport.requests import Request
    from google.oauth2.credentials import Credentials
    from google_auth_oauthlib.flow import InstalledAppFlow
    from googleapiclient.discovery import build
    from googleapiclient.errors import HttpError
    from googleapiclient.http import MediaFileUpload
except ImportError:
    print("ОШИБКА: поставьте google-клиентов:\n"
          "  pip install google-api-python-client google-auth-oauthlib",
          file=sys.stderr)
    sys.exit(2)

SCOPES = ["https://www.googleapis.com/auth/youtube.upload"]
CLIENT_SECRET = os.environ.get("GOOGLE_CLIENT_SECRET", "client_secret.json")
TOKEN = "token.json"
RETRIABLE = [500, 502, 503, 504]  # коды, при которых повторяем чанк


def get_service():
    """OAuth + сборка клиента. Токен кэшируется в token.json."""
    creds = None
    if os.path.exists(TOKEN):
        creds = Credentials.from_authorized_user_file(TOKEN, SCOPES)
    if not creds or not creds.valid:
        if creds and creds.expired and creds.refresh_token:
            creds.refresh(Request())  # продление — работает в Production-режиме
        else:
            flow = InstalledAppFlow.from_client_secrets_file(CLIENT_SECRET, SCOPES)
            creds = flow.run_local_server(port=0)
        with open(TOKEN, "w") as f:
            f.write(creds.to_json())
    return build("youtube", "v3", credentials=creds)


def upload(video_path: str, title: str, description: str, tags: list,
           category: str, privacy: str, kids: bool = False) -> dict:
    yt = get_service()
    body = {
        "snippet": {
            "title": title[:100],
            "description": description[:5000],
            "tags": tags[:30],
            "categoryId": category,
        },
        "status": {
            "privacyStatus": privacy,
            "selfDeclaredMadeForKids": kids,
            # раскрытие синтетики: политика 2025+ требует помечать изменённый/ИИ-контент
            "embeddable": True,
        },
    }
    media = MediaFileUpload(
        video_path, chunksize=8 * 1024 * 1024,  # 8 МиБ — оптимум для 2-ядерного
        resumable=True, mimetype="video/mp4")
    req = yt.videos().insert(part="snippet,status", body=body, media_body=media)

    t0, retries = time.time(), 0
    resp = None
    while resp is None:
        try:
            status, resp = req.next_chunk()
            if status:
                print(f"\r[upload] {int(status.progress() * 100)}%", end="", flush=True)
        except HttpError as e:
            if e.resp.status in RETRIABLE and retries < 10:
                retries += 1
                wait = 2 ** retries
                print(f"\n[upload] {e.resp.status}, повтор {retries}/10 через {wait} c")
                time.sleep(wait)
            else:
                raise
    print()
    return {"id": resp["id"], "wall_s": round(time.time() - t0, 1),
            "url": f"https://youtu.be/{resp['id']}"}


def main() -> int:
    ap = argparse.ArgumentParser(description="Resumable upload на YouTube")
    ap.add_argument("--manifest", help="JSON-манифест задачи (берёт оттуда title, description, tags, video)")
    ap.add_argument("--video", help="путь к mp4 (если не задан --manifest)")
    ap.add_argument("--title", help="заголовок ролика")
    ap.add_argument("--description", default="")
    ap.add_argument("--tags", default="наука,shorts")
    ap.add_argument("--category", default="27",
                    help="28=Science&Tech, 27=Education, 24=Entertainment")
    ap.add_argument("--privacy", default="public",
                    choices=["public", "unlisted", "private"],
                    help="прогрев нового канала — используйте unlisted (Глава 2.1)")
    args = ap.parse_args()

    title = args.title
    description = args.description
    tags = args.tags
    category = args.category
    privacy = args.privacy
    video = args.video

    if args.manifest:
        import json
        from pathlib import Path
        m_path = Path(args.manifest)
        if not m_path.exists():
            print(f"ОШИБКА: манифест {args.manifest} не найден", file=sys.stderr)
            return 1
        m = json.loads(m_path.read_text(encoding="utf-8"))
        title = title or m.get("title")
        description = description or m.get("description", "")
        if not description and m.get("script"):
            description = f"{m.get('hook', '')}\n\n{m.get('script', '')}"
        if m.get("tags"):
            tags = ",".join(m["tags"]) if isinstance(m["tags"], list) else m["tags"]
        elif m.get("keywords"):
            tags = ",".join(m["keywords"])
        category = m.get("category", category)
        privacy = m.get("privacy", privacy)
        if not video:
            # Ищем итоговое видео в build/<id>/out/
            work = m_path.parent.parent / "build" / m["id"] / "out"
            cand = [work / "short_quality.mp4", work / "short_fast.mp4", work / "final_1080x1920.mp4"]
            for c in cand:
                if c.exists():
                    video = str(c)
                    break

    if not video or not os.path.exists(video):
        print(f"ОШИБКА: видеофайл не найден: {video}", file=sys.stderr)
        return 1
    if not title:
        print("ОШИБКА: укажите --title или задайте 'title' в манифесте", file=sys.stderr)
        return 1

    if not os.path.exists(CLIENT_SECRET):
        print(f"ОШИБКА: нет {CLIENT_SECRET}. Создайте OAuth-клиент типа "
              "'Desktop app' в console.cloud.google.com и скачайте секрет.",
              file=sys.stderr)
        return 2

    disc = ("Озвучка и монтаж выполнены автоматически; раскрываю наличие "
            "синтетических элементов по политике YouTube.")
    desc = f"{description}\n\n{disc}\n\n#shorts"
    tag_list = [t.strip() for t in tags.split(",") if t.strip()]
    res = upload(video, title, desc, tag_list, category, privacy)
    print(f"[upload] готово за {res['wall_s']} c: {res['url']}")
    print("[upload] израсходовано 1600 квот units; остаток смотрите в консоли "
          "(IAM → Quotas → YouTube Data API v3)")
    return 0


if __name__ == "__main__":
    sys.exit(main())
