"""Модуль юридического анализа статьи и генерации видеосценария."""
from __future__ import annotations

import json
import logging
import re
from typing import Any

from tubecook.ai.client import AIClient, AIProxyError
from tubecook.ai.prompts import SYSTEM_PROMPT, build_analysis_prompt
from tubecook.ai.regex_utils import (
    extract_article_body,
    extract_article_image,
    extract_case_numbers,
    extract_youtube_link,
)

logger = logging.getLogger(__name__)


class ScriptAnalyzer:
    def __init__(self, client: AIClient | None = None):
        self.client = client or AIClient()

    def analyze_article(self, title: str, link: str, guid: str,
                        published: str, html_content: str) -> dict[str, Any]:
        """Анализирует HTML статьи и возвращает структурированный payload для Job."""
        body = extract_article_body(html_content)
        if len(body) < 150:
            raise AIProxyError(f"Статья слишком коротка для анализа ({len(body)} знаков)")

        case_numbers = extract_case_numbers(body)
        lead_image = extract_article_image(html_content)
        yt_link = extract_youtube_link(html_content)

        prompt = build_analysis_prompt(title, body, case_numbers)

        raw_response = self.client.generate(prompt=prompt, system=SYSTEM_PROMPT)

        # Очистка markdown блоков json, если модель их вставила
        cleaned = raw_response.strip()
        if cleaned.startswith("```"):
            cleaned = re.sub(r"^```(?:json)?\n?", "", cleaned)
            cleaned = re.sub(r"\n?```$", "", cleaned)
        cleaned = cleaned.strip()

        try:
            parsed = json.loads(cleaned)
        except json.JSONDecodeError as exc:
            logger.warning("Не удалось разобрать JSON от ИИ: %s", exc)
            raise AIProxyError(f"ИИ вернул невалидный JSON: {exc}") from exc

        # Валидация базовых полей
        topic = str(parsed.get("topic") or title).strip()
        hook = str(parsed.get("hook") or topic).strip()
        script = str(parsed.get("script") or "").strip()
        scenes = parsed.get("scenes") or []
        facts = parsed.get("facts") or []
        tags = parsed.get("tags") or ["право", "суд", "домдара"]

        if not script and scenes:
            script = " ".join(s.get("text", "") for s in scenes)

        if not script:
            raise AIProxyError("ИИ не сгенерировал текст озвучки (script)")

        # Проверка номера дела: если в источнике были номера дел, убедимся, что хотя бы один попал
        if case_numbers:
            has_case = any(num in script for num in case_numbers) or any(
                num in str(s) for s in scenes for num in case_numbers
            )
            if not has_case:
                logger.info("ИИ пропустил номер дела, добавляем в факты: %s", case_numbers)
                facts.append({"text": f"Номер дела: № {case_numbers[0]}", "attribution": "Материалы суда"})

        # Собираем visual_plan
        visual_plan = []
        for i, s in enumerate(scenes):
            v_desc = s.get("visual", "")
            # Если есть главное фото статьи, используем его для сцен спора/фактов
            bg_image = lead_image if (i in (1, 2) and lead_image) else None
            visual_plan.append({
                "scene": i,
                "kind": s.get("kind", "auto"),
                "text": s.get("text", ""),
                "description": v_desc,
                "image_url": bg_image,
            })

        sources = [{
            "url": link,
            "published": published,
            "checked_at": published,
            "note": "domdara.org RSS feed",
        }]
        if yt_link:
            sources.append({"url": yt_link, "note": "Embedded YouTube clip"})

        return {
            "topic": topic,
            "hook": hook,
            "script": script,
            "visual_plan": visual_plan,
            "facts": facts,
            "sources": sources,
            "tags": tags,
            "meta": {
                "domdara_guid": guid,
                "lead_image": lead_image,
                "case_numbers": case_numbers,
                "youtube_link": yt_link,
            }
        }
