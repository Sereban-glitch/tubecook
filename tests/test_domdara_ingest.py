"""Тесты модуля сбора новостей Домдары и ИИ-анализа."""
import json
from datetime import datetime, timezone, timedelta
from unittest.mock import MagicMock

import pytest

from tubecook import db as dbm
from tubecook.ai.analyzer import ScriptAnalyzer
from tubecook.ai.client import AIProxyError
from tubecook.ai.regex_utils import (
    extract_article_body,
    extract_article_image,
    extract_case_numbers,
    extract_youtube_link,
)
from tubecook.ingest.domdara import DomdaraIngest, parse_rss_xml
from tubecook.models import Priority, JobState
from tubecook.queue import Queue


SAMPLE_RSS_XML = b"""<?xml version="1.0" encoding="UTF-8"?>
<rss version="2.0" xmlns:content="http://purl.org/rss/1.0/modules/content/">
<channel>
    <title>\xd0\x9d\xd0\xb0\xd1\x80\xd0\xbe\xd0\xb4\xd0\xbd\xd1\x8b\xd0\xb9 \xd0\xba\xd0\xbe\xd0\xbe\xd0\xbf\xd0\xb5\xd1\x80\xd0\xb0\xd1\x82\xd0\xb8\xd0\xb2 \xd0\xa3\xd0\xba\xd1\x80\xd0\xb0\xd0\xb8\xd0\xbd\xd1\x8b</title>
    <link>http://domdara.org</link>
    <item>
        <title>\xd0\x9a \xd1\x87\xd0\xb5\xd0\xbb\xd0\xbe\xd0\xb2\xd0\xb5\xd0\xba\xd1\x83 \xd0\xb8\xd0\xb7 \xd0\xbe\xd0\xb1\xd1\x89\xd0\xb8\xd0\xbd\xd1\x8b \xd0\xbf\xd1\x80\xd0\xb8\xd0\xbb\xd0\xb5\xd1\x82\xd0\xb5\xd0\xbb\xd0\xb0 \xd0\xbf\xd1\x82\xd0\xb8\xd1\x87\xd0\xba\xd0\xb0</title>
        <link>http://domdara.org/k-cheloveku-iz-obshhiny-priletela-ptichka/</link>
        <pubDate>Sun, 18 Oct 2026 17:28:43 +0000</pubDate>
        <guid isPermaLink="false">http://domdara.org/?p=5787</guid>
        <description><![CDATA[https://www.youtube.com/shorts/uNvXfn8zK5Q]]></description>
        <content:encoded><![CDATA[<p><a href="https://www.youtube.com/shorts/uNvXfn8zK5Q">https://www.youtube.com/shorts/uNvXfn8zK5Q</a></p>]]></content:encoded>
    </item>
    <item>
        <title>\xd0\x97\xd0\xb0\xd0\xbf\xd0\xbe\xd1\x80\xd0\xbe\xd0\xb6\xd1\x81\xd0\xba\xd0\xb0\xd1\x8f \xd0\xbe\xd0\xb1\xd1\x89\xd0\xb8\xd0\xbd\xd0\xb0 \xd0\xbd\xd0\xb0\xd1\x82\xd1\x8f\xd0\xbd\xd1\x83\xd0\xbb\xd0\xb0 \xd0\x92\xd0\xbe\xd0\xb4\xd0\xbe\xd0\xba\xd0\xb0\xd0\xbd\xd0\xb0\xd0\xbb \xd0\xb2 \xd1\x81\xd1\x83\xd0\xb4\xd0\xb5</title>
        <link>http://domdara.org/zaporozhskaja-obshhina-natjanula-vodokanal-v-sude/</link>
        <pubDate>Thu, 15 Oct 2026 21:14:01 +0000</pubDate>
        <guid isPermaLink="false">http://domdara.org/?p=5786</guid>
        <description><![CDATA[\xd0\x94\xd0\xb5\xd0\xbb\xd0\xbe \xe2\x84\x96 280/8165/23 \xd0\xa0\xd0\x95\xd0\xa8\xd0\x95\xd0\x9d\xd0\x98\xd0\x95 \xd0\x98\xd0\x9c\xd0\x95\xd0\x9d\xd0\x95\xd0\x9c \xd0\xa3\xd0\x9a\xd0\xa1\xd0\x90\xd0\x98\xd0\x9d\xd0\xab]]></description>
        <content:encoded><![CDATA[<div class="content-inner"><p>\xd0\x94\xd0\xb5\xd0\xbb\xd0\xbe \xe2\x84\x96 280/8165/23. \xd0\xa1\xd1\x83\xd0\xb4 \xd1\x80\xd0\xb5\xd1\x88\xd0\xb8\xd0\xbb \xd1\x83\xd0\xb4\xd0\xbe\xd0\xb2\xd0\xbb\xd0\xb5\xd1\x82\xd0\xb2\xd0\xbe\xd1\x80\xd0\xb8\xd1\x82\xd1\x8c \xd0\xb8\xd1\x81\xd0\xba.</p></div>]]></content:encoded>
    </item>
</channel>
</rss>
"""


SAMPLE_ARTICLE_HTML = """
<!DOCTYPE html>
<html>
<head>
    <title>Запорожская община натянула Водоканал в суде</title>
    <meta property="og:image" content="http://domdara.org/wp-content/uploads/2021/03/vodokanal.jpg" />
</head>
<body>
    <article class="entry-content">
        <h1>Запорожская община натянула Водоканал в суде</h1>
        <p>18 августа 2026 г. Запорожский окружной административный суд рассмотрел дело № 280/8165/23.</p>
        <p>Истица обжаловала незаконные начисления и непредоставление первичных бухгалтерских документов.</p>
        <p>Ранее по связанным делам № 335/13534/17 и № 335/2083/18 коммунальщики требовали долги без подтверждения.</p>
        <p>Суд постановил: иск удовлетворить частично, признать действия КП Водоканал противоправными.</p>
        <p><a href="https://www.youtube.com/shorts/uNvXfn8zK5Q">Смотрите видео</a></p>
    </article>
</body>
</html>
"""


def test_parse_rss_xml():
    items = parse_rss_xml(SAMPLE_RSS_XML)
    assert len(items) == 2
    assert items[0]["guid"] == "http://domdara.org/?p=5787"
    assert "птичка" in items[0]["title"]
    assert items[1]["guid"] == "http://domdara.org/?p=5786"
    assert "Водоканал" in items[1]["title"]
    assert items[1]["pub_dt"] < items[0]["pub_dt"]


def test_regex_case_numbers():
    text = "В деле № 280/8165/23 и по справі № 335/13534/17 было вынесено решение. Производство № 753/19985/25."
    cases = extract_case_numbers(text)
    assert "280/8165/23" in cases
    assert "335/13534/17" in cases
    assert "753/19985/25" in cases


def test_extract_html_metadata():
    body = extract_article_body(SAMPLE_ARTICLE_HTML)
    assert "280/8165/23" in body
    img = extract_article_image(SAMPLE_ARTICLE_HTML)
    assert img == "http://domdara.org/wp-content/uploads/2021/03/vodokanal.jpg"
    yt = extract_youtube_link(SAMPLE_ARTICLE_HTML)
    assert yt == "https://www.youtube.com/shorts/uNvXfn8zK5Q"


def test_cold_start_lookback(cfg, q):
    ingest = DomdaraIngest(cfg, q)
    now = datetime(2026, 10, 19, 12, 0, 0, tzinfo=timezone.utc)
    items = parse_rss_xml(SAMPLE_RSS_XML)

    cfg.domdara_initial_lookback_days = 3
    # 18 Oct is within 3 days, 15 Oct is 4 days ago
    unseen = ingest.get_unseen_items(items, now=now)
    assert len(unseen) == 1
    assert unseen[0]["guid"] == "http://domdara.org/?p=5787"


def test_cold_start_latest_only(cfg, q):
    cfg.domdara_seed_mode = "latest_only"
    ingest = DomdaraIngest(cfg, q)
    items = parse_rss_xml(SAMPLE_RSS_XML)

    unseen = ingest.get_unseen_items(items)
    assert unseen == []

    # Курсор должен быть выставлен на самую свежую статью (18 Oct)
    last_guid = dbm.get_meta(q.conn, "domdara_last_seen_guid")
    assert last_guid == "http://domdara.org/?p=5787"


def test_backlog_recovery_chronological_order(cfg, q):
    """Проверка требования ТЗ: пропущенные статьи ставятся строго от старых к новым."""
    ingest = DomdaraIngest(cfg, q)
    dbm.set_meta(q.conn, "domdara_last_seen_guid", "old_marker")

    item1 = {"guid": "g1", "title": "Новость 1", "pub_dt": datetime(2026, 10, 10, tzinfo=timezone.utc)}
    item2 = {"guid": "g2", "title": "Новость 2", "pub_dt": datetime(2026, 10, 14, tzinfo=timezone.utc)}
    item3 = {"guid": "g3", "title": "Новость 3", "pub_dt": datetime(2026, 10, 12, tzinfo=timezone.utc)}

    # В RSS статьи идут от новых к старым (item2, item3, item1)
    unseen = ingest.get_unseen_items([item2, item3, item1])

    # Конвейер обязан отсортировать от старых к новым: item1 (10-е) -> item3 (12-е) -> item2 (14-е)
    assert [x["guid"] for x in unseen] == ["g1", "g3", "g2"]


def test_priority_queue_ordering(cfg, q):
    """Проверка весовой очереди: manual (Сергей) > ai_news (Саша) > domdara."""
    p_domdara = {
        "job_id": "job-domdara", "topic": "Домдара", "hook": "Хук",
        "script": "Текст", "requested_priority": "domdara"
    }
    p_ai = {
        "job_id": "job-ai", "topic": "ИИ Саша", "hook": "Хук",
        "script": "Текст", "requested_priority": "ai_news"
    }
    p_manual = {
        "job_id": "job-manual", "topic": "Тема Сергея", "hook": "Хук",
        "script": "Текст", "requested_priority": "manual"
    }

    # Подаем в порядке domdara -> ai -> manual
    q.submit(p_domdara, sender_id=-100, role="domdara")
    q.submit(p_ai, sender_id=222, role="sender")
    q.submit(p_manual, sender_id=111, role="admin")

    # Claim должен вернуть СНАЧАЛА manual
    c1 = q.claim(owner="worker")
    assert c1["job_id"] == "job-manual"
    assert c1["priority"] == "manual"

    # Затем ai_news
    c2 = q.claim(owner="worker")
    assert c2["job_id"] == "job-ai"
    assert c2["priority"] == "ai_news"

    # Затем domdara
    c3 = q.claim(owner="worker")
    assert c3["job_id"] == "job-domdara"
    assert c3["priority"] == "domdara"


def test_ai_analyzer_structure():
    mock_client = MagicMock()
    mock_client.generate.return_value = json.dumps({
        "topic": "Суд против Водоканала",
        "hook": "Как община выиграла суд!",
        "script": "Запорожский суд рассмотрел дело 280/8165/23 и признал действия Водоканала незаконными.",
        "scenes": [
            {"kind": "hook", "text": "Суд против Водоканала!", "visual": "Весы правосудия"},
            {"kind": "fact_card", "text": "Дело номер 280/8165/23.", "visual": "Карточка дела"}
        ],
        "facts": [{"text": "Дело № 280/8165/23"}],
        "tags": ["суд", "водоканал"]
    })

    analyzer = ScriptAnalyzer(client=mock_client)
    res = analyzer.analyze_article(
        title="Запорожская община",
        link="http://domdara.org/test/",
        guid="test-guid",
        published="2026-10-18T10:00:00Z",
        html_content=SAMPLE_ARTICLE_HTML
    )

    assert res["topic"] == "Суд против Водоканала"
    assert "280/8165/23" in res["script"]
    assert len(res["visual_plan"]) == 2
    assert res["meta"]["lead_image"] == "http://domdara.org/wp-content/uploads/2021/03/vodokanal.jpg"


def test_ai_proxy_error_does_not_enqueue(cfg, q, monkeypatch):
    mock_client = MagicMock()
    mock_client.generate.side_effect = AIProxyError("Proxy offline")
    analyzer = ScriptAnalyzer(client=mock_client)
    ingest = DomdaraIngest(cfg, q, analyzer=analyzer)

    # Мокаем poll_feed и fetch_url
    monkeypatch.setattr(ingest, "poll_feed", lambda **k: parse_rss_xml(SAMPLE_RSS_XML))
    monkeypatch.setattr("tubecook.ingest.domdara.fetch_url", lambda *a, **kw: SAMPLE_ARTICLE_HTML.encode("utf-8"))

    # Запуск ингеста
    enqueued = ingest.ingest_once()
    # Ни одно сырое задание не должно попасть в очередь!
    assert enqueued == []
    count = q.conn.execute("SELECT COUNT(*) FROM jobs").fetchone()[0]
    assert count == 0
