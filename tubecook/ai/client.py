"""Клиент существующего ИИ-прокси (antigravity-claude-proxy).

Протокол: Anthropic Messages API (/v1/messages), бэкенд: Google Gemini (Pro/Flash).
"""
from __future__ import annotations

import json
import logging
import urllib.error
import urllib.request
from typing import Any

logger = logging.getLogger(__name__)


class AIProxyError(Exception):
    """Ошибка обращения к ИИ-прокси (таймаут, сетевой сбой, невалидный ответ)."""
    pass


class AIClient:
    def __init__(self, endpoint: str = "http://127.0.0.1:18080/v1/messages",
                 api_key: str = "test",
                 model: str = "gemini-3.8-flash-tiered",
                 timeout: float = 45.0):
        self.endpoint = endpoint
        self.api_key = api_key
        self.model = model
        self.timeout = timeout

    def generate(self, prompt: str, system: str = "",
                 max_tokens: int = 4000,
                 temperature: float = 0.3) -> str:
        """Синхронный вызов прокси через urllib.request."""
        payload: dict[str, Any] = {
            "model": self.model,
            "max_tokens": max_tokens,
            "temperature": temperature,
            "messages": [{"role": "user", "content": prompt}],
        }
        if system:
            payload["system"] = system

        data = json.dumps(payload).encode("utf-8")
        headers = {
            "Content-Type": "application/json",
            "x-api-key": self.api_key,
            "User-Agent": "Tubecook/4.0",
        }
        req = urllib.request.Request(self.endpoint, data=data, headers=headers, method="POST")

        try:
            with urllib.request.urlopen(req, timeout=self.timeout) as resp:
                resp_bytes = resp.read()
        except urllib.error.HTTPError as exc:
            err_body = exc.read().decode("utf-8", errors="ignore")
            logger.warning("AI proxy HTTP error %s: %s", exc.code, err_body)
            raise AIProxyError(f"AI proxy HTTP {exc.code}: {err_body}") from exc
        except Exception as exc:
            logger.warning("AI proxy network error: %s", exc)
            raise AIProxyError(f"AI proxy connection failed: {exc}") from exc

        try:
            resp_json = json.loads(resp_bytes.decode("utf-8"))
        except Exception as exc:
            raise AIProxyError(f"Malformed JSON from AI proxy: {exc}") from exc

        # Anthropic Messages API format: content: [{"type": "text", "text": "..."}]
        content = resp_json.get("content", [])
        if not isinstance(content, list):
            raise AIProxyError(f"Unexpected response structure: {resp_json}")

        text = ""
        for block in content:
            if isinstance(block, dict) and block.get("type") == "text":
                text = block.get("text", "").strip()
                break

        if not text:
            raise AIProxyError("AI proxy returned empty text")

        # Защита от системных инъекций прокси Antigravity
        if any(bad in text for bad in ("is no longer available", "switch to Gemini", "Antigravity")):
            logger.warning("AI proxy injected system notice in text: %s", text[:100])
            raise AIProxyError("System injection detected in AI response")

        if text.upper().startswith("FALLBACK") and len(text) < 30:
            raise AIProxyError("Model signaled FALLBACK")

        return text
