"""Секреты: env.example без значений, .gitignore, отсутствие токенов в коде."""
import re
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
TOKEN_RE = re.compile(r"\d{8,10}:AA[\w-]{30,}")
SECRET_FILE_KEYS = ("TUBECOOK_TOKEN", "TELEGRAM_BOT_TOKEN", "GOOGLE_CLIENT_SECRET",
                    "PEXELS_API_KEY")


def test_env_example_has_no_values():
    env = (ROOT / "env.example").read_text(encoding="utf-8")
    for line in env.splitlines():
        line = line.strip()
        if "=" in line and not line.startswith("#"):
            key, _, val = line.partition("=")
            assert val.strip() == "", f"env.example: {key} содержит значение"


def test_gitignore_protects_secrets():
    gi = (ROOT / ".gitignore").read_text(encoding="utf-8")
    for must in (".env", "token.json", "client_secret.json", "data/"):
        assert must in gi, f".gitignore не содержит {must}"


def test_no_tokens_in_repo():
    for p in ROOT.rglob("*"):
        if p.suffix in (".py", ".md", ".sh", ".example", ".toml", ".txt", ".service",
                        ".timer") and p.is_file() and "node_modules" not in str(p):
            text = p.read_text(encoding="utf-8", errors="ignore")
            assert not TOKEN_RE.search(text), f"похоже на токен в {p}"


def test_admin_ids_are_config_not_secrets(cfg):
    # ID администратора — настройка доступа, не токен: живёт в env
    assert cfg.admin_ids == {111}
    assert cfg.telegram_bot_token == ""
