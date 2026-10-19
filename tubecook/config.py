"""Конфигурация Tubecook v4.

Все секреты читаются ТОЛЬКО из окружения/.env (см. env.example).
В коде и в этом файле секретов нет и быть не должно.
"""
from __future__ import annotations

import os
from dataclasses import dataclass, field
from pathlib import Path
from zoneinfo import ZoneInfo

APP = "tubecook"

# Категории фоновой музыки: нейтральные подложки вместо мрачного legacy-трека.
# TUBECOOK_BGM принимает: имя категории (news|legal|tech|legacy), путь к файлу
# или none/off (без музыки). Файлы: assets/bgm/<cat>_loop.mp3 (scripts/make_bgm.py).
BGM_CATEGORIES = {
    "news": "assets/bgm/news_loop.mp3",
    "legal": "assets/bgm/legal_loop.mp3",
    "tech": "assets/bgm/tech_loop.mp3",
    "legacy": "assets/bgm/soft_loop.mp3",   # старый трек, оставлен для сравнения
}
BGM_OFF = ("none", "off", "no", "")


def _env(key: str, default: str | None = None) -> str | None:
    v = os.environ.get(key)
    return v if v not in (None, "") else default


def _env_int(key: str, default: int) -> int:
    try:
        return int(_env(key, str(default)))
    except (TypeError, ValueError):
        return default


def _env_bool(key: str, default: bool) -> bool:
    v = _env(key)
    if v is None:
        return default
    return v.strip().lower() in ("1", "true", "yes", "on", "да")


def _env_set(key: str) -> set[int]:
    """'12345,67890' -> {12345, 67890}; пусто -> пустое множество."""
    raw = _env(key, "") or ""
    out: set[int] = set()
    for part in raw.replace(";", ",").split(","):
        part = part.strip()
        if not part:
            continue
        try:
            out.add(int(part))
        except ValueError:
            continue
    return out


def _env_float(key: str, default: float) -> float:
    try:
        return float(_env(key, str(default)))
    except (TypeError, ValueError):
        return default


def _clamp(v: float, lo: float, hi: float) -> float:
    return max(lo, min(hi, v))


def _resolve_bgm(raw: str | None, root: Path) -> tuple:
    """TUBECOOK_BGM -> (Path|None, category|path|none).

    Принимает: категорию (news|legal|tech|legacy), путь к файлу или
    none/off. Возвращает (bgm_path_abs_or_None, описание выбора) —
    описание попадает в отчёт рендера, чтобы выбор музыки был прозрачным.
    """
    val = (raw or "").strip()
    low = val.lower()
    if low in BGM_OFF:
        return None, "none"
    if low in BGM_CATEGORIES:
        return (root / BGM_CATEGORIES[low]).resolve(), low
    p = Path(val)
    if not p.is_absolute():
        p = (root / p).resolve()
    return p, str(p)


@dataclass
class RenderConfig:
    # Мастер-канон: 1080x1920@30. 60 fps не используется по умолчанию:
    # на i5-6200U выигрыш незаметен, а время рендера удваивается.
    w: int = 1080
    h: int = 1920
    fps: int = 30
    preset: str = "veryfast"
    crf: int = 21
    hw: str = "auto"            # auto | vaapi | cpu
    vaapi_device: str = "/dev/dri/renderD128"
    tail_s: float = 0.9         # хвост после последнего слова озвучки (ТЗ: 0.6-1.0 c)
    transition_s: float = 0.35  # кроссфейд между сценами (базовый профиль)
    profile: str = "base"       # base | extended

    # профиль extended: больше движения (сдвиги, дрейф акцентов, быстрые переходы)
    extended_transition_s: float = 0.5

    def encoder(self) -> list[str]:
        """Аппаратный или CPU-энкодер. VA-API включается, только если устройство есть."""
        want_vaapi = self.hw == "vaapi" or (self.hw == "auto" and Path(self.vaapi_device).exists())
        if want_vaapi and Path(self.vaapi_device).exists():
            return ["-vaapi_device", self.vaapi_device, "-c:v", "h264_vaapi",
                    "-b:v", "6M", "-maxrate", "8M", "-bufsize", "12M"]
        return ["-c:v", "libx264", "-preset", self.preset, "-crf", str(self.crf)]


@dataclass
class TelegramOutConfig:
    channel_id: str = ""        # @svobodnye_ludi_zp или -100...
    budget_mb: int = 15         # продуктовый бюджет из ТЗ
    crf_ladder: tuple = (23, 26, 28)
    audio_k_ladder: tuple = (128, 96, 80)


@dataclass
class YouTubeOutConfig:
    channel_id: str = ""        # проверяется перед live-режимом
    privacy: str = "public"     # public | unlisted | private
    made_for_kids: bool = False
    disclose_synthetic: bool = True
    category_id: int = 28       # Science & Technology


@dataclass
class Config:
    root: Path = Path(".")
    data_dir: Path = Path("data")
    db_path: Path = Path("data/tubecook.db")
    jobs_dir: Path = Path("data/jobs")       # артефакты рендера по job_id
    outbox_dir: Path = Path("data/outbox")   # dry-run "публикации" и превью
    bgm_path: Path | None = Path(BGM_CATEGORIES["news"])
    bgm_category: str = "news"      # news | legal | tech | legacy | none | <путь>
    # Громкость подложки до даккинга (треки нормализованы к пику -12 dBFS;
    # 0.5 -> легкий фон ~ -26..-30 dB RMS, голос остаётся кристально чистым).
    bgm_volume: float = 0.5
    font_bold: str = "/usr/share/fonts/truetype/dejavu/DejaVuSans-Bold.ttf"
    font_regular: str = "/usr/share/fonts/truetype/dejavu/DejaVuSans.ttf"
    sub_font: str = "DejaVu Sans"
    log_file: Path = Path("data/tubecook.log")

    tz: ZoneInfo = field(default_factory=lambda: ZoneInfo("Europe/Kyiv"))
    slots: tuple = (0, 6, 12, 18)             # Europe/Kyiv, ТЗ

    # --- доступ (ID Telegram, не токены) ---
    admin_ids: set = field(default_factory=set)
    allowed_sender_ids: set = field(default_factory=set)

    # --- голос ---
    voice: str = "ru-RU-DmitryNeural"
    rate: str = "+0%"

    # --- режимы ---
    require_approval: bool = True     # HITL по умолчанию: превью Сергею перед публикацией
    autonomous_mode: bool = False     # 4/сутки без подтверждений; включается владельцем отдельно
    dry_run_publish: bool = True      # публикация отключена, пока владелец явно не включит live

    # --- очередь / политика ---
    lease_s: int = 900
    max_attempts: int = 4
    backoff_s: tuple = (300, 1800, 7200, 21600)
    news_ttl_h: int = 36
    catchup_max: int = 1              # после сна: не более 1 пропущенного выпуска залпом
    empty_notify_cooldown_h: int = 12

    render: RenderConfig = field(default_factory=RenderConfig)
    tg_out: TelegramOutConfig = field(default_factory=TelegramOutConfig)
    yt_out: YouTubeOutConfig = field(default_factory=YouTubeOutConfig)

    # --- Домдара (сбор новостей) ---
    domdara_enabled: bool = True
    domdara_feed_url: str = "http://domdara.org/feed/"
    domdara_poll_interval_minutes: int = 30
    domdara_initial_lookback_days: int = 3
    domdara_seed_mode: str = "lookback"  # lookback | latest_only
    domdara_article_ttl_days: int = 14
    domdara_user_agent: str = "Mozilla/5.0 Codex Bridge"

    # --- ИИ-прокси (анализ статей и генерация сценариев) ---
    ai_proxy_url: str = "http://127.0.0.1:18080/v1/messages"
    ai_proxy_key: str = "test"
    ai_model: str = "gemini-3.8-flash-tiered"

    # --- секреты (только окружение; в БД/коде не хранятся) ---
    telegram_bot_token: str = ""

    def resolve(self) -> "Config":
        """Переводит пути в абсолютные относительно root."""
        self.data_dir = (self.root / self.data_dir).resolve()
        self.db_path = (self.root / self.db_path).resolve()
        self.jobs_dir = (self.root / self.jobs_dir).resolve()
        self.outbox_dir = (self.root / self.outbox_dir).resolve()
        self.log_file = (self.root / self.log_file).resolve()
        if self.bgm_path is not None and not Path(self.bgm_path).is_absolute():
            self.bgm_path = (self.root / self.bgm_path).resolve()
        for d in (self.data_dir, self.jobs_dir, self.outbox_dir):
            d.mkdir(parents=True, exist_ok=True)
        return self

    @classmethod
    def from_env(cls, root: str | Path = ".") -> "Config":
        cfg = cls(root=Path(root))
        cfg.db_path = Path(_env("TUBECOOK_DB", "data/tubecook.db"))
        cfg.data_dir = Path(_env("TUBECOOK_DATA", "data"))
        cfg.jobs_dir = Path(_env("TUBECOOK_JOBS_DIR", "data/jobs"))
        cfg.outbox_dir = Path(_env("TUBECOOK_OUTBOX", "data/outbox"))
        cfg.log_file = Path(_env("TUBECOOK_LOG", "data/tubecook.log"))
        cfg.bgm_path, cfg.bgm_category = _resolve_bgm(_env("TUBECOOK_BGM", "news"), root=Path(root))
        cfg.bgm_volume = _clamp(_env_float("TUBECOOK_BGM_VOLUME", 0.5), 0.0, 1.5)
        cfg.tz = ZoneInfo(_env("TUBECOOK_TZ", "Europe/Kyiv"))
        cfg.admin_ids = _env_set("TUBECOOK_ADMINS")
        cfg.allowed_sender_ids = _env_set("TUBECOOK_SENDERS")
        cfg.voice = _env("TUBECOOK_VOICE", "ru-RU-DmitryNeural")
        cfg.rate = _env("TUBECOOK_RATE", "+0%")
        cfg.require_approval = _env_bool("TUBECOOK_REQUIRE_APPROVAL", True)
        cfg.autonomous_mode = _env_bool("TUBECOOK_AUTONOMOUS", False)
        cfg.dry_run_publish = _env_bool("TUBECOOK_PUBLISH_LIVE", False) is False
        # TUBECOOK_PUBLISH_LIVE=true -> live (отключает dry-run); по умолчанию dry-run.
        cfg.news_ttl_h = _env_int("TUBECOOK_NEWS_TTL_H", 36)
        cfg.lease_s = _env_int("TUBECOOK_LEASE_S", 900)
        cfg.max_attempts = _env_int("TUBECOOK_MAX_ATTEMPTS", 4)
        cfg.sub_font = _env("TUBECOOK_SUB_FONT", "DejaVu Sans")
        cfg.font_bold = _env("TUBECOOK_FONT_BOLD", cfg.font_bold)
        cfg.font_regular = _env("TUBECOOK_FONT_REGULAR", cfg.font_regular)

        r = cfg.render
        r.hw = _env("TUBECOOK_HW", "auto")
        r.profile = _env("TUBECOOK_RENDER_PROFILE", "base")
        r.crf = _env_int("TUBECOOK_CRF", 21)
        r.tail_s = float(_env("TUBECOOK_TAIL_S", "0.9"))

        cfg.tg_out.channel_id = _env("TELEGRAM_CHANNEL_ID", "")
        cfg.tg_out.budget_mb = _env_int("TELEGRAM_BUDGET_MB", 15)
        cfg.yt_out.channel_id = _env("YOUTUBE_CHANNEL_ID", "")
        cfg.yt_out.privacy = _env("YOUTUBE_PRIVACY", "public")
        cfg.yt_out.made_for_kids = _env_bool("YOUTUBE_MADE_FOR_KIDS", False)
        cfg.yt_out.disclose_synthetic = _env_bool("YOUTUBE_DISCLOSE_SYNTHETIC", True)

        # домдара
        cfg.domdara_enabled = _env_bool("TUBECOOK_DOMDARA_ENABLED", True)
        cfg.domdara_feed_url = _env("TUBECOOK_DOMDARA_FEED_URL", "http://domdara.org/feed/")
        cfg.domdara_poll_interval_minutes = _env_int("TUBECOOK_DOMDARA_POLL_INTERVAL", 30)
        cfg.domdara_initial_lookback_days = _env_int("TUBECOOK_DOMDARA_LOOKBACK_DAYS", 3)
        cfg.domdara_seed_mode = _env("TUBECOOK_DOMDARA_SEED_MODE", "lookback")
        cfg.domdara_article_ttl_days = _env_int("TUBECOOK_DOMDARA_TTL_DAYS", 14)
        cfg.domdara_user_agent = _env("TUBECOOK_DOMDARA_USER_AGENT", "Mozilla/5.0 Codex Bridge")

        # ии-прокси
        cfg.ai_proxy_url = _env("AI_PROXY_URL", "http://127.0.0.1:18080/v1/messages")
        cfg.ai_proxy_key = _env("AI_PROXY_KEY", "test")
        cfg.ai_model = _env("REPORT_AI_MODEL", _env("AI_MODEL", "gemini-3.8-flash-tiered"))

        # секреты
        cfg.telegram_bot_token = _env("TUBECOOK_TOKEN", "") or _env("TELEGRAM_BOT_TOKEN", "")
        return cfg.resolve()


def load_env_file(path: str | Path = ".env") -> None:
    """Читает .env (KEY=VALUE) в os.environ, не перезаписывая уже заданные переменные."""
    p = Path(path)
    if not p.exists():
        return
    for line in p.read_text(encoding="utf-8").splitlines():
        line = line.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        k, _, v = line.partition("=")
        k, v = k.strip(), v.strip().strip('"').strip("'")
        if k and k not in os.environ:
            os.environ[k] = v
