# Облачное исследование Tubecook v4 (Task R-1)

- Дата: 2026-10-18. Только исследование, без покупок/аккаунтов.
- Метод: web-search + чтение официальных страниц (2025–2026). Все ключевые цифры сверены с первоисточниками; где официальной цифры нет — помечено явно.
- Профиль нагрузки: 4 вертикальных ролика/день (45–60 с, 1080×1920, TTS + ASS-караоке), публикация Telegram-канал + YouTube Shorts, ~120 эпизодов/мес, ~120 000 символов TTS/мес, ~15–40 МБ готового MP4 на выпуск.

---

## 1. NotebookLM (Google) — API, Video Overviews, автоматизация

**Переименование.** С июля 2026 NotebookLM называется **Gemini Notebook** (notebook.google), ноутбуки сохранены — https://notebook.google/

**Публичный API — нет.** Публичного self-serve API для потребительского NotebookLM/Gemini Notebook не существует (статус на октябрь 2026):
- Официальная документация Enterprise: API для создания/управления ноутбуками есть только в продукте **Gemini Notebook Enterprise** (Google Cloud, платный корпоративный) — https://docs.cloud.google.com/gemini/enterprise/notebooklm-enterprise/docs/api-notebooks
- Форум Google для разработчиков: «There is currently not a public API for NotebookLM» — https://discuss.ai.google.dev/t/how-to-access-notebooklm-via-api/5084
- Сторонние обзоры подтверждают то же на 2026 — https://autocontentapi.com/blog/does-notebooklm-have-an-api , https://notebookclipper.com/blog/gemini-notebook-api
- Неофициальные обёртки существуют (REST-обёртка над веб-интерфейсом) — https://github.com/gnh1201/notebooklm-rest-api — это НЕ официальный API.

**Video Overviews.** Официальная справка: Video Overview можно **скачать (кнопка Download)** и «Share the downloaded video file»; при ограничениях издателя контента скачивание может быть недоступно — https://support.google.com/gemininotebook/answer/16454555 . Водяной знак/брендинг в официальной справке не описан (официальной цифры/факта о водяном знаке не нашёл), но существует целый рынок сторонних «watermark remover» для NotebookLM-видео (свидетельство, что метка на практике присутствует): https://www.reddit.com/r/notebooklm/comments/1mjx4uw/is_it_possible_to_remove_the_watermark_from_the , https://www.deckcleaner.xyz/en/blog/google-notebooklm-video-overview . Удаление водяного знака сторонними инструментами — вне рамок ToS Google (пользовательские обсуждения: https://www.skool.com/ai-marketing-insiders/content-usage-and-branding-for-notebooklm-videos ).

**ToS/автоматизация.** Общие условия Google запрещают «using automated means to access content from any of our services in violation of the machine-readable instructions on our web pages» и прочий misuse — https://policies.google.com/terms (см. раздел «When we suspend or terminate your account»: scraping, automated access). robots.txt notebook.google — `User-agent: * Allow: /` (https://notebook.google/robots.txt), т.е. прямого запрета краулинга нет, но это **не санкционирует API-доступ/браузерную автоматизацию** как «API». Браузерная автоматизация (Playwright/Selenium) интерфейса Gemini Notebook:
- технически возможна, но не поддерживается, ломается при изменениях UI;
- риск: капчи/флаги аккаунта, вплоть до блокировки Google-аккаунта (там же почта, YouTube-канал) — риск несоразмерный.
- Video Overviews нельзя запрограммировать по параметрам (нет шаблонов 9:16 с таймингом TTS/караоке — формат продукта фиксированный), т.е. для Tubecook это не замена рендер-конвейеру, максимум «генератор отдельного фрагмента» с ручным экспортом.

**Вывод по п.1:** официального API нет; экспорт Video Overview есть (ручной); автоматизация = против ToS-духа с риском аккаунта. Для конвейера на 4 выпуска/день неприменимо.

---

## 2. Облачные видео-API с «бесплатным уровнем»

| Сервис | Что реально бесплатно | Водяной знак / лимиты | Автоматизация | Источник |
|---|---|---|---|---|
| **Shotstack** | Бесплатный **sandbox** навсегда (не trial-кредиты), API-доступ | В sandbox: водяной знак, видео до 10 минут; AI-ассеты платные даже в sandbox; production-использование = платные планы от $39/мес (250 мин) или PAYG $10/50 мин | REST API, официально для автоматизации; но бесплатный sandbox = для разработки/теста | https://shotstack.io/pricing ; https://shotstack.io/learn/render-your-first-video-shotstack-api («Outputs are watermarked, and videos are limited to 10 minutes») |
| **JSON2Video** | **600 кредитов однократно** при регистрации (не возобновляются) | Водяной знак на free-плане; макс. 1080p; макс. длительность 60 с; «personal, educational, and evaluation use — not for commercial use» | API есть, но free = пробные кредиты, не постоянный тариф | https://json2video.com/docs/v2/reference/credits/plans ; https://json2video.com/get-api-key |
| **Creatomate** | 50 API-кредитов один раз (trial) | Trial без водяного знака, но кредиты разовые; постоянного free-плана нет | API/шаблоны, платно от $49/мес (сторонний обзор) | https://creatomate.com/pricing ; https://creatomate.com (обзор: https://www.plainlyvideos.com/blog/creatomate-review ) |
| **Remotion (+ Lambda / свой рендер)** | Библиотека/фреймворк **бесплатны для частных лиц и команд ≤3 чел** (source-available, лицензия Remotion); «облачного рендера Remotion» как сервиса НЕТ — Lambda рендерится **в вашем AWS-аккаунте** (платите AWS) | Без водяных знаков; ограничения диктует ваш compute | Полная программная автоматизация; Company License: Creators $25/мес/чел или Automators $0.01/рендер (мин. $100/мес) | https://www.remotion.dev/docs/license/faq ; https://www.remotion.dev/lambda ; https://www.remotion.dev/lambda/faq |
| **Bannerbear** | 30 API-кредитов один раз (trial, не возобновляется) | Постоянного free-тарифа нет | API + Zapier/Make; от ~$49/мес | https://www.bannerbear.com/pricing ; https://www.bannerbear.com/help/articles/60-how-does-the-free-trial-work |
| **Cloudinary** | Постоянный **Free-план: 25 кредитов/мес** (1 кредит = 1000 трансформаций ИЛИ 1 ГБ хранилища ИЛИ 1 ГБ bandwidth видео), скользящее 30-дневное окно, без карты | Макс. размер видеофайла 100 МБ; видео-трансформации (включая нарезку/сборку слайдшоу) считаются по кредитам — на 120 видео/мес НЕ хватит | URL-based API/SDK, официально поддерживается; но это скорее обработчик/доставка, не рендер сложных ASS-караоке | https://cloudinary.com/documentation/billing_and_plans ; https://cloudinary.com/pricing/compare-plans |
| **CloudConvert** | Постоянный free: **10 конверсий (кредитов) в день**, «personal use, testing and hobby projects», макс. файл 1 ГБ, низкий приоритет | Без водяного знака; но это конвертер, НЕ видеоредактор: сборку «клипы+субтитры+TTS» он не делает | API с ключом; лимит 10/день на аккаунт | https://cloudconvert.com/pricing |

**Итог по п.2:** ни один из «бесплатных уровней» видеогенерации не покрывает продакшн 4 ролика/день: либо разовые trial-кредиты (JSON2Video/Creatomate/Bannerbear), либо watermarked sandbox (Shotstack), либо слишком мал (Cloudinary 25 кредитов). **Remotion — единственный «бесплатный» путь к облачному рендеру, но бесплатно только само ПО; compute (AWS Lambda / Cloud Run / GitHub Actions) оплачивается отдельно** — или бесплатно на публичных GitHub Actions (см. п.4).

Прочие замеченные альтернативы: Plainly, HyperFrames, Orshot (платные, с trial) — обзор сравнения: https://www.wireflow.ai/blog/best-remotion-without-self-hosting-tools-in-2026

---

## 3. Бесплатный always-on compute для «мозга» (бот-поллинг, очередь, планировщик)

**Oracle Cloud Always Free:**
- ARM (VM.Standard.A1.Flex): «1,500 OCPU hours и 9,000 GB hours в месяц», для Always Free тенантий это **эквивалент 2 OCPU + 12 ГБ RAM** (1 VM или 2 VM), только в home region — официальные доки: https://docs.oracle.com/iaas/Content/FreeTier/freetier_topic-Always_Free_Resources.htm и https://www.oracle.com/cloud/free/
- ВАЖНО (сдвиг 2026): в середине 2026 Oracle сократил лимит ARM с 4 OCPU/24 ГБ до 2 OCPU/12 ГБ (тихо, без анонса): https://www.infoq.com/news/2026/07/oracle-cloud-free-tier-limits ; https://news.ycombinator.com/item?id=49183750 (дедлайн снижения — 18 августа 2026); https://terminalbytes.com/oracle-cloud-free-tier-changes-2026
- Плюс 2× AMD E2.1.Micro (1/8 OCPU, 1 ГБ) Always Free; 200 ГБ Block Volume; 20 ГБ Object Storage — https://www.oracle.com/cloud/free/
- Риски: «out of host capacity» в популярных регионах — официально признано в доках (https://docs.oracle.com/iaas/Content/FreeTier/freetier_topic-Always_Free_Resources.htm); **reclaim простаивающих инстансов**: за 7-дневное окно CPU (95-й перцентиль) <20%, сеть <20%, память <20% (для A1) → Oracle может изъять VM (там же). Для лёгкого ботового поллинга это реальный риск — нужна периодическая нагрузка. Практические отчёты о «out of capacity»: https://www.reddit.com/r/oraclecloud/comments/1oobbq1/ ; о reclaim: https://www.reddit.com/r/oraclecloud/comments/1ulme2e/
- Не требует карты (для бесплатного аккаунта), аккаунт «на всю жизнь», но Oracle оставляет за собой право менять условия — https://www.oracle.com/cloud/free/

**Fly.io:** для новых аккаунтов **постоянного free-VM-тарифа больше нет** (2026): новые организации — Pay As You Go без monthly fee; бесплатны после trial только 10 ГБ снапшотов, SSL, inbound-трафик; VM shared-cpu-1x 256 МБ ≈ $2.19/мес — https://docs.fly.io/about/pricing/ , https://fly.io/pricing/ . Сторонние обзоры 2026 подтверждают отмену free allowances для новых юзеров: https://expresstech.io/7-fly-io-alternatives-in-2026-real-pricing-after-the-free-tier-died ; https://www.budgetforge.dev/tools/fly-io-pricing-2026-2 . (Точный объём стартового trial для новых аккаунтов: по сторонним данным 2 VM-часа или 7 дней — квота неизвестна (официальной цифры не нашёл).)

**Google Cloud Run:**
- Free tier (постоянный, пересчитывается ежемесячно, **требует привязанный billing account/карту**): для сервисов — 2 млн запросов/мес, 180 000 vCPU-сек и 360 000 GiB-сек (requests-based billing, us-central1); для **Jobs — 240 000 vCPU-сек и 450 000 GiB-сек** в месяц — https://cloud.google.com/run/pricing
- Лимиты времени: HTTP-запрос сервиса — максимум **60 минут**; задача Cloud Run **Job — таймаут задачи до 168 часов (7 дней)** (без GPU) — https://cloud.google.com/run/quotas . Т.е. ffmpeg-джоба 10–30 мин спокойно проходит и по HTTP-сервису, и тем более Job.
- Требование billing: «To use products that have a Free Tier, you need a Google Cloud billing account» — https://cloud.google.com/free/docs/free-cloud-platform ; превышение лимитов = автосписание.
- Расчёт под Tubecook (4 джоба/день): Job 2 vCPU × 20 мин × 4/день × 30 = 288 000 vCPU-сек/мес — **выше бесплатных 240 000**; 1 vCPU × 20 мин — 144 000 vCPU-сек (влезает), но 1 vCPU для 1080×1920 рендера — медленно. RAM 2 ГБ × 1200 с × 120 = 288 000 GiB-сек (лимит 450 000 — влезает). Итог: **частично влезает, но «на грани» и с риском списаний при превышении**.

**HuggingFace Spaces:**
- Текущие правила (2026): **Static Spaces бесплатны всем; создание Gradio/Docker Spaces на compute требует платный план (PRO и т.п.)** — «Gradio and Docker Spaces run on compute and require a paid plan to create» — https://huggingface.co/docs/hub/en/spaces-overview . Лимиты окружения: 16 ГБ RAM / 2 CPU / 50 ГБ непостоянного диска; на free-железе Space «засыпает» после простоя (ранее задокументировано: cpu-basic засыпает через 48 часов — https://huggingface.co/docs/huggingface_hub/en/package_reference/space_runtime ). Претензии сообщества на «удаление бесплатного CPU Basic» (июль 2026): https://discuss.huggingface.co/t/official-community-complaint-revert-free-cpu-basic-spaces-and-remove-anti-developer-sdk-restrictions/177703
- Вывод: как always-on «мозг» в 2026 непригоден; как рендер-воркер — тоже (sleep + 2 CPU + ephemeral диск).

**GitHub Actions (кратко, детали в п.4):** бесплатный always-on «планировщик» возможен только как cron в публичном репо (нена­дёжен: задержки/пропуски, авто-отключение через 60 дней бездействия — см. п.4), поллинг Telegram-бота на Actions не организуешь (нет постоянного процесса).

---

## 4. GitHub Actions как рендер-воркер в public repo

**Что бесплатно (официально, статус на октябрь 2026):**
- «GitHub Actions usage is free for self-hosted runners and for **public repositories that use standard GitHub-hosted runners**» — https://docs.github.com/billing/managing-billing-for-github-actions/about-billing-for-github-actions
- Изменения цен 2025–2026: с 1 января 2026 hosted-раннеры подешевели до 39%, **standard usage (hosted и self-hosted) в публичных репозиториях остаётся бесплатным**; с 1 марта 2026 введён «cloud platform charge» $0.002/мин для self-hosted usage (считается в минуты плана; **public repo — по-прежнему бесплатно**) — https://github.com/resources/insights/2026-pricing-changes-for-github-actions ; https://github.blog/changelog/2025-12-16-coming-soon-simpler-pricing-and-a-better-experience-for-github-actions/
- Лимиты джоба: **6 часов на job**; матрица до 256 jobs; workflow run — до 35 дней — https://docs.github.com/en/actions/reference/limits
- Для private repo: GitHub Free = 2 000 мин/мес + 500 МБ artifact-хранилища (Linux 1×) — https://docs.github.com/billing/managing-billing-for-github-actions/about-billing-for-github-actions . Для 4×20 мин×30 = 2 400 мин/мес — **private-квоты не хватает** → нужен именно **public** репо.

**Реалистичность 4 видео/день:** да, по машинному времени. ubuntu-latest (4 vCPU) рендерит 45–60-сек 1080×1920 с libx264 за единицы минут (быстрее i5-6200U); даже с запасом 4×30 мин/день — 60 мин/день, публичный репо = $0. Ограничения:
- Артефакты: retention по умолчанию 90 дней (артефакты Actions); хранение артефактов квотится (Free 500 МБ — но в public репо Actions-использование бесплатно) — https://docs.github.com/billing/managing-billing-for-github-actions/about-billing-for-github-actions ; обсуждения: https://github.com/orgs/community/discussions/166576 , https://github.com/orgs/community/discussions/73875
- Cron-надёжность: официально «The schedule event can be delayed during periods of high loads... If the load is sufficiently high enough, some queued jobs may be dropped», запуск только на default branch, **в публичном репо scheduled workflow автоматически отключается при 60 днях без активности в репозитории** — https://docs.github.com/en/actions/reference/events-that-trigger-workflows (раздел schedule). Сторонние наблюдения: задержки до 8–14 часов — https://github.com/orgs/community/discussions/201738 ; мониторинг/обходы: https://dev.to/krissv/monitoring-github-actions-scheduled-workflows-a-practical-guide-31h7 . Вывод: cron годится как «вспомогательный» триггер; основной запуск лучше делать `workflow_dispatch`/`repository_dispatch` из always-on «мозга» (или держать в репо активность/keepalive-коммит раз в <60 дней).
- Риски бана: ToS GitHub для Actions прямо предупреждает о «misuse»: terminations of jobs, ограничения, отключение репо, в тяжёлых случаях аккаунта; запрещена деятельность, создающая непропорциональную нагрузку (примеры: CDN, serverless-приложения на Actions) — https://docs.github.com/en/site-policy/github-terms/github-terms-for-additional-products-and-features . Рендер 4×~15 мин/день — умеренная, легитимная CI-нагрузка; риск невысокий, но не нулевой (.quantitative-порог «злоупотребления» не опубликован — квота неизвестна (официальной цифры не нашёл)).
- Секреты: GitHub Actions Secrets (зашифрованы, не видны в логах), для чувствительных шагов — Environments с required reviewers; OIDC; «Encrypted secrets» — https://docs.github.com/en/actions/security-for-github-actions/security-guides/using-secrets-in-github-actions . В public репо секреты недоступны форкам/PR из форков (по умолчанию не передаются в pull_request из форков) — там же. Хранить там TG-токен и YT refresh-token можно (это штатная практика), с оговоркой: любой с write-доступом к репо может «вытекичь» секрет через `echo` — дисциплина кода обязательна.

---

## 5. TTS бесплатно (облако и локально)

Потребность Tubecook: ~120 000 символов/мес, русский язык, продакшн (публикация в TG/YouTube).

| Вариант | Бесплатная квота (официально) | Русский | Коммерческое использование | Источник |
|---|---|---|---|---|
| **Azure Speech F0** | Neural TTS: **0,5 млн символов/мес** (500 000, обновляется ежемесячно) | есть ru-RU | **НЕТ для free**: Microsoft Product Terms (MCA) дают права на коммерческое использование аудио-вывода prebuilt neural голосов только **paid tier**; F0 — allowance для оценки/тестирования. Подтверждено ответом модератора на Microsoft Q&A (март 2026): «Do not rely on Free (F0) for commercial output rights» | https://azure.microsoft.com/en-us/pricing/details/speech/ ; https://www.microsoft.com/licensing/terms/productoffering/MicrosoftAzure/MCA ; https://learn.microsoft.com/en-us/answers/questions/5805156/please-clarify-the-conflicting-information-regardi |
| **Google Cloud TTS** | Standard и WaveNet (legacy): **4 млн символов/мес**; Neural2/Polyglot/Studio/Chirp3-HD: **1 млн символов/мес**; после — $4–160/1M | ru-RU есть (список голосов — проверять при настройке) | Производственное использование разрешено (free tier = квота), **но нужно включить billing (карту)**: «You must enable billing to use Text-to-Speech» | https://cloud.google.com/text-to-speech/pricing |
| **ElevenLabs Free** | **10 000 кредитов/мес** (~10 мин Multilingual TTS), API доступен | русский поддерживается | **Free без commercial license** (Commercial License со Starter $5–6/мес). 10 мин/мес ≠ 120 мин/мес — квоты физически не хватает | https://elevenlabs.io/pricing |
| **Kokoro-82M (локально)** | Открытые веса, Apache-2.0; 82M параметров; ~5× реального времени на CPU (сторонний бенчмарк) | **русского НЕТ** (v1.0: 8 языков, 54 голоса — en, es, fr, hi, it, ja, pt, zh) | Да (Apache-2.0; проверить лицензии отдельных голосов) | https://github.com/hexgrad/kokoro ; https://huggingface.co/hexgrad/Kokoro-82M ; бенчмарк: https://www.reddit.com/r/TextToSpeech/comments/1sqkiuc/ |
| **Piper (локально)** | rhasspy/piper (Python) — **MIT**; поддерживаемый C++-движок piper1-gpl — **GPL-3.0**; очень быстр на CPU (позиционируется как «fast, local», работает на Raspberry Pi) | **есть ru_RU** (denis/irina/ruslan/dmitri medium) | Да (MIT-код; голоса под своими лицензиями, напр. CC0 у конверсий) | https://github.com/rhasspy/piper ; https://github.com/OHF-Voice/piper1-gpl ; список голосов: https://github.com/rhasspy/piper/blob/master/VOICES.md ; ru-голоса: https://huggingface.co/rhasspy/piper-voices/tree/v1.0.0/ru/ru_RU |
| **edge-tts (текущий движок v3)** | Бесплатен, без официально опубликованных квот | ru-RU (DmitriNeural и др.) | **Вне ToS**: это неофициальный доступ к сервису Edge Read-aloud; официального разрешения нет. На вопрос о легальности edge-tts на Microsoft Q&A **официального ответа нет** (вопрос без ответа, окт 2024). Сервис периодически ломается: 403 WSS-ошибки (issue янв 2026) — Microsoft добавил обязательный заголовок/токен (Sec-MS-GEC), не воспроизводимый браузерным WebSocket | https://pypi.org/project/edge-tts/ ; https://learn.microsoft.com/en-us/answers/questions/2392491/unofficial-edge-tts-api ; https://github.com/rany2/edge-tts/issues/458 ; https://www.reddit.com/r/ereader/comments/1muuxtr/ ; общий ToS: https://www.microsoft.com/en-us/servicesagreement |

**Вывод по п.5:** для честного бесплатного продакшена на русском — **локальный Piper (ru_RU, MIT)**; Google Cloud TTS (4M Standard-символов, нужна карта) — облачная альтернатива; Azure F0 и ElevenLabs Free формально не для коммерческого вывода; edge-tts — работает, но это серая зона с регулярными поломками и без ToS-покрытия: для регулярного продакшена честно считать риском (вплоть до мгновенной поломки пайплайна).

---

## 6. YouTube Data API v3 — квоты, Shorts, маркировка синтетики

**Квоты (актуальная модель «гранулярных» квот, действует с июня 2026):**
- Дефолт: **100 вызовов videos.insert/день (собственный бакет, 1 юнит/вызов), 100 вызовов search.list/день (собственный бакет), 10 000 юнитов/день суммарно на все остальные методы**; квота сбрасывается в полночь PT — https://developers.google.com/youtube/v3/determine_quota_cost
- История: 4 дек 2025 стоимость загрузки снижена с ~1600 юнитов до ~100 юнитов; с 1 июня 2026 — переход на гранулярные квоты (videos.insert/search.list в отдельных бакетах) — https://developers.google.com/youtube/v3/revision_history
- **videos.list = 1 юнит** (таблица Quota Calculator, там же). Для 4 загрузок/день хватает с огромным запасом (лимит 100 insert/день).
- Запросы на расширение квоты — через Quota Extension Form (аудит) — там же.

**Shorts:** вертикальные (square или выше) ролики **до 3 минут**, загруженные начиная с 15 октября 2024, автоматически классифицируются как Shorts — https://support.google.com/youtube/answer/15424877 ; анонс: https://blog.youtube/news-and-events/tall-updates-coming-to-shorts . Загрузка через API = обычный videos.insert (специального Shorts-API нет). 45–60 с вертикали = Shorts. (Общий файловый лимит загрузок YouTube в этом исследовании не проверял — для 15–40 МБ файлов не критичен.)

**Маркировка синтетического/изменённого контента (актуально):**
- Политика: создатели обязаны раскрывать **реалистичный** AI-контент (изменённые события, подмена реальных людей, реалистичные сцены и т.п.); в процессе загрузки — «Attributes → AI use → Yes»; на «фотореалистичный» и музыкальный AI-контент метка встроюится в плеер — https://support.google.com/youtube/answer/14328491 ; анонс: https://blog.youtube/news-and-events/disclosing-ai-generated-content
- API: поле **`status.containsSyntheticMedia`** (boolean) — устанавливается владельцем канала в videos.insert/videos.update для раскрытия A/S-контента; `status.selfDeclaredMadeForKids` — самостоятельная декларация «для детей» — https://developers.google.com/youtube/v3/docs/videos
- Для Tubecook: TTS-озвучка + стоковые клипы, как правило, НЕ «фотореалистичная синтетика» (нет подмены реальных людей/событий) — обязательной метки может не требоваться; но при использовании AI-видео/фотореалистичных вставок YouTube ждёт раскрытия. Поле в API есть — задавать `containsSyntheticMedia` при соответствии критериям. Требование атрибуции AI для аудио: Microsoft AI Code of Conduct упоминает раскрытие AI-аудио (https://learn.microsoft.com/en-us/legal/ai-code-of-conduct , из ответа Q&A п.5).
- OAuth-практика: проект с OAuth consent screen в статусе **Testing выдаёт refresh-токены, истекающие через 7 дней** — для серверной автоматизации нужно перевести приложение в production-режим (непроверенное sensitive-scope приложение работает с предупреждением; лимиты пользователей — квота неизвестна (официальную цифру в этом исследовании не проверял)) — https://developers.google.com/identity/protocols/oauth2

---

## 7. Telegram Bot API — лимиты

Официально (core.telegram.org):
- **sendVideo / загрузка файлов ботом: максимум 50 МБ** («Bots can currently send files of any type of up to 50 MB in size»); скачивание файлов через getFile — до 20 МБ; фото — до 10 МБ — https://core.telegram.org/bots/faq ; https://core.telegram.org/bots/api#sending-files
- **Локальный Bot API сервер**: бот сможет «Upload files up to 2000 MB», скачивать без лимита — https://core.telegram.org/bots/api#using-a-local-bot-api-server
- **Rate limits**: «When sending messages inside a particular chat, avoid sending more than one message per second... We may allow short bursts... eventually 429 errors. In a group, bots are not able to send more than 20 messages per minute. For bulk notifications, bots are not able to broadcast more than about 30 messages per second» (до 1000/с с платными paid broadcasts) — https://core.telegram.org/bots/faq#how-do-i-avoid-hitting-limits
- file_id персистентны (можно переотправлять без повторной загрузки) — там же.
- Для постинга в канал (бот — админ): 4 sendVideo/день — на порядки ниже лимитов. MP4 1080×1920 ~15–40 МБ влезает в 50 МБ (следить за битрейтом); свыше — local Bot API server (можно поднять на той же VM) или выгрузка видео YouTube + ссылка.
- Специфичных публичных лимитов на sendPoll/постов именно в каналах (частота) — **квота неизвестна (официальной цифры не нашёл)**; действуют общие лимиты выше. Общий лимит сообщений в сутки для ботов не публикуется — квота неизвестна (официальной цифры не нашёл).

---

## 8. Автоматизация и ToS — что запрещено, что вручную

- **Google (NotebookLM/Gemini Notebook, YouTube через API, TTS):** YouTube/TTS — легальный API-путь с OAuth; NotebookLM — только вручную (API нет, браузерная автоматизация против ToS, риск аккаунта, см. п.1). Источники: п.1, п.6.
- **GitHub Actions:** официальный запрет на «misuse» (непропорциональная нагрузка: CDN, serverless на Actions), мониторинг usage, санкции вплоть до бана аккаунта; рендер 4×~15 мин/день в public-репо — умеренное использование, но ToS-порог не квантифицирован (квота неизвестна (официальной цифры не нашёл)) — https://docs.github.com/en/site-policy/github-terms/github-terms-for-additional-products-and-features
- **Oracle:** idle-reclaim (CPU/сеть/память <20% за 7 дней) — «мозг» на поллинге должен генерить нагрузку/трафик; capacity-ошибки при создании; сервис для «небольших приложений и PoC» — https://docs.oracle.com/iaas/Content/FreeTier/freetier_topic-Always_Free_Resources.htm
- **Fly.io / HF Spaces:** новых бесплатных always-on опций нет (п.3).
- **Microsoft (edge-tts/Azure F0):** п.5 — edge-tts без правовой базы; Azure F0 без прав на коммерческий вывод.
- **YouTube:** маркировка синтетики при соответствии критериям (п.6); один раз — OAuth-консент (production-режим), дальше全自动; upload через API легален и специально поддержан.
- **Telegram Bot API:** официальная автоматизация (п.7), боту нужен разовый доступ к каналу (админ).
- **Честно про «без ноутбука»:** полностью автономно (поиск→очередь→рендер→хранение→публикация→подтверждение) можно собрать из Oracle VM + GitHub Actions + API Telegram/YouTube, НО: (а) разовые ручные действия: создание аккаунтов/токенов (Oracle, GitHub, Google OAuth, BotFather, верификация карт не нужна кроме GCP), периодический ручной ре-логин при экстренных событиях (смена токена, 7-дневные OAuth в Testing-режиме, капчи); (б) edge-tts в v3 — точка хрупкости: без ноутбука падение edge-tts чинится только заменой движка на локальный Piper; (в) NotebookLM в цикл не встраивается вообще.

---

## 9. Хранение/доставка файлов бесплатно

- **GitHub Releases (public repo):** до **1000 ассетов на релиз, каждый файл ≤ 2 ГиБ, суммарный размер релиза и bandwidth — без лимитов** — https://docs.github.com/en/repositories/releasing-projects-on-github/about-releases . Для архивов ≤15 МБ и готовых MP4 (15–40 МБ) — идеальный бесплатный «файловый склад» с прямыми download-URL. Прозрачно: в public-репо ассеты публичны (секретов в файлах быть не должно).
- **GitHub Actions artifacts:** retention по умолчанию 90 дней (обсуждения/доки: https://github.com/orgs/community/discussions/166576 , https://github.com/orgs/community/discussions/73875 ) — годится только как транзит, не архив.
- **Cloudflare R2:** free tier — **10 ГБ-месяц хранения, 1 млн Class A, 10 млн Class B операций, egress бесплатно** (данные обновлены 1 октября 2026; только для Standard storage) — https://developers.cloudflare.com/r2/pricing/ . Доставка видео в Telegram-бот (до 50 МБ) и раздача ссылок — без оплаты трафика. 10 ГБ ≈ 250–650 роликов по 15–40 МБ → хватит на 1–3 месяца с ротацией, либо хранить только последние N.
- **Telegram сам** — «облако»: файлы у Telegram, file_id персистентны (п.7) — перепост без повторной загрузки.
- Прочее: Cloudinary Free 25 кредитов/мес (п.2) — мало; Object Storage Oracle 20 ГБ (п.3) — можно как архив (без egress-fee? — политика egress Always Free в OCI для 10 ТБ/мес не подтверждена в этом исследовании — квота неизвестна (официальной цифры не нашёл)).

---

## СИНТЕЗ

### Сравнительная таблица вариантов рендера/цикла (4 выпуска/сутки)

| Вариант | Качество видео | Устойчивость | Автоматизация (ToS-чистота) | Реальная цена при 4/день | Главный риск |
|---|---|---|---|---|---|
| Ноутбук как сейчас (i5-6200U) | как есть | низкая (зависит от включённого ноутбука) | полная | $0 | ноутбук выключен → конвейер стоит |
| **A: Oracle ARM VM «мозг» + GitHub Actions public «рендер»** | 1080×1920, libx264, тот же стек | средняя: VM reclaim-риск, GHA cron-риск обходится триггером из VM | полная, ToS-чистая (API TG/YT, public Actions) | **$0** (карта не нужна) | idle-reclaim Oracle; ToS-дискреция GitHub; edge-tts хрупкость → заменить на Piper |
| B: Гибрид (ноутбук основной + облако бёрст/резерв) | как есть | высокая | полная | $0 (если бёрст на public Actions) | синхронизация двух исполнителей |
| C: Только GitHub Actions (cron + состояние в git) | то же | средняя-низкая (cron задержки, 60-дней авто-оф) | полная, но триггерная | $0 | cron-надёжность; нет поллинга TG |
| Cloud Run Jobs рендер | то же | высокая | полная | free tier частично покрывает (240k vCPU-с/мес), сверх — копейки, но **карта обязательна** | превышение → автосписание |
| Remotion (лицензия ок, свой compute) | высокое (React-рендер) | средняя | полная | $0 ПО + compute (AWS платно / GHA public бесплатно) | усложнение стека (переписывание рендера в React) |
| Shotstack/JSON2Video/Creatomate/Bannerbear | среднее-высокое | высокая | API, но free = trial/sandbox | $39–99/мес = **не бесплатно** | watermark/ToS free-плана |
| NotebookLM Video Overviews | своё, неконтролируемое | низкая (UI, без API) | **ручная** | $0 | бан-риск при автоматизации; нет русского 9:16-формата |

### «Облачный генератор фрагмента» vs «Полный облачный цикл»

- **Генератор отдельного фрагмента** (TTS-кусок, конвертация, клип) — легко и бесплатно: CloudConvert 10/день, Cloudinary 25 кредитов/мес, TTS-квоты (GCP 4M символов с картой; Piper локально на любом воркере). Проблема Tubecook не в фрагментах, а в **сборке (FFmpeg+ASS)** и **оркестрации**.
- **Полный цикл** (поиск→очередь→рендер→хранение→публикация→подтверждение→восстановление) собирается бесплатно ТОЛЬКО из «мозга» (Oracle VM: поллинг TG, SQLite, cron, keepalive) + «рук» (GitHub Actions public: workflow_dispatch → FFmpeg+Piper → выгрузка в Releases/R2 → sendVideo + videos.insert → отчёт в VM). Что всё ещё требует ручных действий/внимания:
  1. Первичная настройка токенов (BotFather, Google OAuth в production-режиме, PAT GitHub) — разово, с ноутбука.
  2. NotebookLM — вне цикла (только ручной экспорт, если вообще).
  3. Мониторинг «живости»: бот должен слать алерты владельцу; при reclaim VM или 60-дневном сне GHA — нужен ручной рестарт (или автогенерация активности — серая зона, но обычно делают keepalive-коммит).
  4. edge-tts (движок v3) — при блокировке требует правки кода; без ноутбука лечится только переходом на локальный Piper (рекомендуется сразу).

### 2–3 реалистичные архитектуры

**A. «Полностью бесплатно, без ноутбука» (рекомендуемая основа)**
- Компоненты: **Oracle Always Free ARM VM (2 OCPU/12 ГБ)** = systemd-сервисы: TG-поллинг-бот, планировщик (4 слота/день), SQLite-очередь, keepalive-скрипт (профилактика idle-reclaim, ~периодическая CPU/сеть-активность). **GitHub Actions в public репо** = рендер-воркер (workflow_dispatch через PAT/repository_dispatch из VM; в воркфлоу: piper-tts ru_RU → ffmpeg 1080×1920 + ASS-караоке → gh release upload / R2 put → Telegram sendVideo (≤50 МБ) → YouTube videos.insert (containsSyntheticMedia по критериям) → отчёт POST обратно в VM). Секреты: GitHub Secrets (TG token, YT refresh token, PAT, R2 keys).
- Хранение: SQLite на VM (бэкап в R2/репо), MP4 — GitHub Releases (постоянно) и/или R2 (10 ГБ, ротация).
- Отказы: VM умерла → GHA-сron-фолбэк (задержки, но цикл жив) + алерт; GHA упал/забанен → VM детектит по таймауту, повторный dispatch; YT-токен истёк → алерт, ручной refresh (изредка).
- Слабые места: idle-reclaim Oracle; ToS-дискреция GitHub (неквантифицированная); секреты в public-репо требуют гигиены; edge-tts — заменить на Piper ru_RU сразу.

**B. Гибрид (ноутбук основной, облако — бёрст/резерв)**
- Ноутбук рендерит как сейчас; Oracle VM держит бота/очередь/алерты; при выключенном ноутбуке или аврале VM дёргает тот же public-GHA воркфлоу как «резервные руки». Состояние — в git (SQLite синхронизируется коммитами) — конфликт решается «кто первый взял job». Минусы: два исполнителя → дубли/гонки; сложнее код. Плюсы: почти нулевой риск простоя и плавная миграция.

**C. Минимальный чистый (только GitHub, без VM)**
- Всё в public репо: cron 4×/день + workflow_dispatch; SQLite/JSON-состояние коммитится в ветку; видео → Releases; отправка TG/YT из Actions. Плюс: минимум движущихся частей. Минусы: cron GHA задерживается/пропускается (п.4), 60-дневное авто-отключение (нужен keepalive-бот или активность), нет мгновенного TG-поллинга (бот отвечает только в окнах рендера), любое «восстановление» = следующий cron-тик.

### Рекомендация

**Основной вариант — A (Oracle Always Free VM как «мозг» + GitHub Actions public-репо как рендер-воркер, TTS на локальном Piper ru_RU), с C как дешёвым фолбэком.**
Почему: это единственная комбинация, где (1) все компоненты официально бесплатны и постоянны (не trial: public-Actions бесплатны официально; Oracle Always Free — официально, с оговорками reclaim; R2/Releases — официально); (2) publication-каналы (YouTube API, Telegram Bot API) — легальные API без ToS-серых зон; (3) рендер-мощность Actions (4 vCPU) выше ноутбука; (4) отказ каждого компонента имеет облако-фолбэк. Cloud Run Jobs — хороший запасной рендер, но требует карту и следить за vCPU-секундами; Remotion — если захочется программируемый «красивый» рендер, но это переписывание стека.
Обязательные условия честности: TTS — заменить/дублировать edge-tts локальным Piper (ru_RU, MIT) при переходе; YouTube-маркировку делать по критериям (containsSyntheticMedia при фотореализме); в public-репо не хранить ничего приватного в артефактах; учесть, что «полностью без ручных действий» не бывает — разовая настройка токенов и редкие ре-авторизации остаются.

### «Квота неизвестна / проверять при настройке» (сводка)
- Shotstack sandbox: суточный/месячный объём рендеров и судьба production-использования sandbox — не опубликовано.
- GitHub Actions public: количественный порог «злоупотребления» ToS — не опубликован.
- Google OAuth (unverified, production): лимит пользователей/поведение sensitive-scope youtube.upload — проверить при настройке.
- Telegram: лимиты постов в канал/sendPoll — официальных цифр не нашёл.
- Fly.io: точный объём стартового trial новых аккаунтов — не нашёл официальной цифры.
- HF Spaces: точный таймаут сна free-железа (ранее 48 ч для cpu-basic) — актуальную цифру проверить при настройке.
- Oracle: политика egress-лимитов Always Free для Object Storage — не нашёл.
- YouTube: общий файловый лимит API-загрузки (256 ГБ/12 ч по общеизвестной справке) — в этом исследовании не проверял.
- Kokoro: появление русского в будущих версиях — следить (на октябрь 2026 в v1.0 отсутствует).
- NotebookLM: правила водяного знака/прав на Video Overviews — официального документа не нашёл (есть только справка про Download).

---
*Источники сохранены в /home/z/my-project/research/_raw/*.json (сырые выдачи поиска и страницы).*
