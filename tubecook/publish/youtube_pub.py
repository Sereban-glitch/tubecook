"""Загрузка на YouTube Shorts: resumable upload, локальный OAuth, честные квоты.

- OAuth делается ВЛАДЕЛЬЦЕМ локально (google-auth-oauthlib, run_local_server);
  client_secret.json/token.json остаются на ноутбуке и не попадают в чат/репо;
- квоты: НЕ считаем старое «1600 units из 10000» истиной по умолчанию —
  фактическая квота проекта проверяется в Cloud Console (см. docs/CLOUD_RESEARCH.md);
  при 4 выпусках/сутки запас обычно велик;
- disclosure: status.containsSyntheticMedia=true по умолчанию (ИИ-озвучка
  и синтетический видеоряд реалистичны — правила YouTube требуют метку);
  selfDeclaredMadeForKids=false по умолчанию и настраивается.
  hasCustomThumbnail НЕ является disclosure-флагом и здесь не используется;
- таймаут/обрыв после старта загрузки -> UNCERTAIN: сверка videos.list по id,
  без слепого повторного постинга.

Live-режим требует google-клиентов и token.json; их отсутствие блокирует
только реальный upload, но не разработку и dry-run (ТЗ).
"""
from __future__ import annotations

import json
from pathlib import Path

from tubecook.models import TargetState
from tubecook.publish.base import Publisher, TargetResult

SCOPES = ["https://www.googleapis.com/auth/youtube.upload"]


def build_video_metadata(job: dict, cfg) -> dict:
    p = job
    title = (p.get("topic", "")[:95]) or "Tubecook"
    desc_lines = [p.get("hook", ""), "", p.get("script", "")[:1500], "",
                  "Источники:"]
    for s in p.get("sources", [])[:5]:
        desc_lines.append(f"— {s.get('url', '')}")
    if p.get("demo"):
        desc_lines = (["ДЕМО-СЮЖЕТ (не новость): тест нового рендера Tubecook v4."]
                      + desc_lines)
    if cfg.yt_out.disclose_synthetic:
        desc_lines += ["", "Озвучка и монтаж выполнены автоматически "
                           "(синтетические медиа раскрыты по политике YouTube)."]
    desc_lines += ["", "#shorts"]
    body = {
        "snippet": {
            "title": title,
            "description": "\n".join(desc_lines)[:4900],
            "tags": [t for t in p.get("tags", []) if t][:15],
            "categoryId": str(cfg.yt_out.category_id),
        },
        "status": {
            "privacyStatus": cfg.yt_out.privacy,
            "selfDeclaredMadeForKids": cfg.yt_out.made_for_kids,
            "containsSyntheticMedia": cfg.yt_out.disclose_synthetic,
            "embeddable": True,
        },
    }
    return body


class YouTubePublisher(Publisher):
    name = "youtube"

    def publish(self, job: dict, artifacts: dict) -> TargetResult:
        video = artifacts.get("master")
        meta = build_video_metadata(job, self.cfg)

        if self.cfg.dry_run_publish:
            body = ("канал: %s\nвидео: %s\n\n--- metadata videos.insert ---\n%s\n"
                    "(status.containsSyntheticMedia=%s, "
                    "selfDeclaredMadeForKids=%s — disclosure-поля YouTube API)"
                    % (self.cfg.yt_out.channel_id or "(не задан)", video,
                       json.dumps(meta, ensure_ascii=False, indent=2),
                       meta["status"]["containsSyntheticMedia"],
                       meta["status"]["selfDeclaredMadeForKids"]))
            path = self.write_dry_run(job, artifacts, body)
            return TargetResult(self.name, TargetState.DRY_RUN, ref=str(path),
                                dry_run=True)

        # live без OAuth-токена — явный сбой с инструкцией (токен делается
        # локально владельцем, в чат не присылается)
        if not _has_credentials():
            return TargetResult(
                self.name, TargetState.FAILED,
                error="live-режим без token.json: выполните локально "
                      "`python -m tubecook.cli oauth-youtube` "
                      "(client_secret.json + OAuth Desktop-клиент)")

        if not video or not Path(video).exists():
            return TargetResult(self.name, TargetState.FAILED,
                                error=f"мастер-видео не найдено: {video}")

        try:
            return self._upload(video, meta)
        except TimeoutError:
            return TargetResult(self.name, TargetState.UNCERTAIN,
                                error="таймаут загрузки: видео могло быть "
                                      "опубликовано; сверка — /check")
        except Exception as e:
            return TargetResult(self.name, TargetState.FAILED, error=str(e)[:500])

    def _upload(self, video: str, meta: dict) -> TargetResult:
        from google.oauth2.credentials import Credentials
        from google.auth.transport.requests import Request
        from googleapiclient.discovery import build
        from googleapiclient.http import MediaFileUpload
        from googleapiclient.errors import HttpError

        token_file = Path("token.json")
        creds = Credentials.from_authorized_user_file(str(token_file), SCOPES)
        if not creds.valid:
            creds.refresh(Request())
            token_file.write_text(creds.to_json(), encoding="utf-8")
        yt = build("youtube", "v3", credentials=creds)

        media = MediaFileUpload(video, chunksize=8 * 1024 * 1024,
                                resumable=True, mimetype="video/mp4")
        req = yt.videos().insert(part="snippet,status", body=meta,
                                 media_body=media)
        resp, retries = None, 0
        while resp is None:
            try:
                status, resp = req.next_chunk()
            except HttpError as e:
                if e.resp.status in (500, 502, 503, 504) and retries < 10:
                    retries += 1
                    import time
                    time.sleep(2 ** retries)
                else:
                    raise
        vid = resp["id"]
        return TargetResult(self.name, TargetState.SENT,
                            ref=f"https://youtu.be/{vid}")

    def verify(self, job_id: str, ref: str) -> TargetResult:
        """Сверка uncertain: videos.list по videoId (дешёвая, 1 unit)."""
        vid = ref.rsplit("/", 1)[-1].strip()
        if not vid or not _has_credentials():
            return TargetResult(self.name, TargetState.UNCERTAIN, ref=ref,
                                error="verify недоступен (нет token.json); "
                                      "сверьте канал вручную")
        try:
            from google.oauth2.credentials import Credentials
            from google.auth.transport.requests import Request
            from googleapiclient.discovery import build
            creds = Credentials.from_authorized_user_file("token.json", SCOPES)
            if not creds.valid:
                creds.refresh(Request())
            yt = build("youtube", "v3", credentials=creds)
            r = yt.videos().list(part="status", id=vid).execute()
            items = r.get("items", [])
            if items:
                return TargetResult(self.name, TargetState.SENT, ref=ref)
            return TargetResult(self.name, TargetState.FAILED, ref=ref,
                                error="videos.list: видео не найдено — "
                                      "загрузка не завершилась")
        except Exception as e:
            return TargetResult(self.name, TargetState.UNCERTAIN, ref=ref,
                                error=f"verify сбой: {e}")


def _has_credentials() -> bool:
    return Path("token.json").exists()


def run_local_oauth() -> str:
    """Разовая локальная авторизация (запускает браузер на ноутбуке владельца)."""
    try:
        from google_auth_oauthlib.flow import InstalledAppFlow
    except ImportError as e:
        return ("нет google-клиентов: pip install google-api-python-client "
                f"google-auth-oauthlib ({e})")
    if not Path("client_secret.json").exists():
        return ("нет client_secret.json: создайте OAuth-клиент 'Desktop app' в "
                "console.cloud.google.com (YouTube Data API v3) и положите файл "
                "рядом с проектом. НЕ присылайте его в чат.")
    flow = InstalledAppFlow.from_client_secrets_file("client_secret.json", SCOPES)
    creds = flow.run_local_server(port=0)
    Path("token.json").write_text(creds.to_json(), encoding="utf-8")
    return ("token.json сохранён локально. Проверьте в Cloud Console фактическую "
            "квоту videos.insert вашего проекта — не полагайтесь на старые "
            "дефолтные цифры.")
