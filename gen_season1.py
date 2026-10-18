#!/usr/bin/env python3
# ============================================================================
# gen_season1.py — Генератор 10 полных производственных манифестов для 1-го сезона
# документального мини-сериала про РЕАЛЬНЫЕ рассекреченные спецоперации.
#
# Каждая серия строго выверена:
#   - Хронометраж: строго 42–48 секунд (темп 2.3–2.6 слов/с, ~85–95 слов).
#   - Структура:
#       0–3 сек: Взрывной хук со стоп-кадром.
#       3–35 сек: Факты, даты, фамилии, рассекреченные документы без «воды».
#       35–45 сек: Открытый финал, триггер комментариев и вовлечения.
#   - 5–6 сцен на серию с точными запросами под Wikimedia PD-USGov архивы и CC0.
#   - Комплект для Telegram: аналитическое досье, карточка дела и интерактивный опрос.
# ============================================================================
import json
import os
from pathlib import Path

HERE = Path(__file__).resolve().parent
JOBS_DIR = HERE / "jobs"
JOBS_DIR.mkdir(parents=True, exist_ok=True)

EPISODES = [
    {
        "id": "ep01_midnight_climax",
        "episode": 1,
        "series": "Рассекреченные архивы: Сезон 1",
        "title": "Операция Midnight Climax: Как ЦРУ накачивало граждан ЛСД",
        "target_duration_s": 45,
        "hook": "ЦРУ платило жрицам любви, чтобы накачивать мужчин ЛСД через зеркало-шпион!",
        "script": "1954 год, Сан-Франциско, конспиративная квартира на Честнат-стрит. Агент ЦРУ Джордж Уайт разливал мартини с ударными дозами ЛСД ничего не подозревающим посетителям. За двухсторонним зеркалом техники вели аудиозапись, выясняя, можно ли сломать волю человека химическим путём в рамках подпроекта МК-Ультра. Эксперименты курировал главный химик управления Сидни Готлиб. Операция продолжалась почти десять лет. В семьдесят третьем году директор ЦРУ Ричард Хелмс приказал уничтожить все архивы, но случайно уцелевшие финансовые счета вскрыли правду на слушаниях в Сенате. А если бы этот отчёт не нашли?",
        "voice": "ru-RU-DmitryNeural",
        "bgm_gain_db": -22,
        "historical_metadata": {
            "operation_name": "Operation Midnight Climax (MK-Ultra Subproject 42)",
            "agency": "CIA (Technical Services Staff)",
            "year_initiated": 1954,
            "year_declassified": 1977,
            "declassification_authority": "Church Committee Senate Hearings & FOIA",
            "key_figures": "Dr. Sidney Gottlieb, George Hunter White, Richard Helms",
            "primary_source_doc": "Senate Select Committee on Intelligence Hearings on MKULTRA (1977)"
        },
        "scenes": [
            {
                "index": 0, "duration_s": 4.0,
                "source_query": "CIA headquarters building Langley historical 1960",
                "overlay_text": "САН-ФРАНЦИСКО, 1954 // СЕКРЕТНАЯ КВАРТИРА ЦРУ",
                "narration_segment": "1954 год, Сан-Франциско, конспиративная квартира на Честнат-стрит."
            },
            {
                "index": 1, "duration_s": 8.0,
                "source_query": "Vintage martini glass bar laboratory flask 1950s",
                "overlay_text": "ПОДПРОЕКТ MK-ULTRA // ХИМИЧЕСКИЙ ДОПРОС",
                "narration_segment": "Агент ЦРУ Джордж Уайт разливал мартини с ударными дозами ЛСД ничего не подозревающим посетителям."
            },
            {
                "index": 2, "duration_s": 8.0,
                "source_query": "Two-way mirror surveillance camera vintage tape recorder",
                "overlay_text": "ДВУХСТОРОННЕЕ ЗЕРКАЛО // ПРОСЛУШКА И ПЛЕНКА",
                "narration_segment": "За двухсторонним зеркалом техники вели аудиозапись, выясняя, можно ли сломать волю человека химическим путём."
            },
            {
                "index": 3, "duration_s": 9.0,
                "source_query": "Sidney Gottlieb chemist CIA file declassified document",
                "overlay_text": "КУРАТОР СИДНИ ГОТЛИБ // 10 ЛЕТ ЭКСПЕРИМЕНТОВ",
                "narration_segment": "Эксперименты курировал главный химик управления Сидни Готлиб. Операция продолжалась почти десять лет."
            },
            {
                "index": 4, "duration_s": 9.0,
                "source_query": "United States Senate Church committee hearings 1977",
                "overlay_text": "СЛУШАНИЯ В СЕНАТЕ 1977 // УНИЧТОЖЕНИЕ УЛИК",
                "narration_segment": "В семьдесят третьем году директор ЦРУ приказал сжечь архивы, но уцелевшие счета вскрыли правду на слушаниях в Сенате."
            },
            {
                "index": 5, "duration_s": 7.0,
                "source_query": "Declassified top secret red stamp document paper",
                "overlay_text": "ЧТО ЕЩЕ СКРЫВАЮТ АРХИВЫ?",
                "narration_segment": "А если бы этот отчёт не нашли?"
            }
        ],
        "telegram_post": {
            "title": "Операция «Midnight Climax»: Как ЦРУ накачивало граждан ЛСД",
            "lead": "В 1954 году в Сан-Франциско открылась конспиративная квартира с зеркалами-шпионами, где спецслужбы испытывали галлюциногены на американцах.",
            "declassified_facts": [
                "Проект курировал доктор Сидни Готлиб под кодовым номером Subproject 42.",
                "Женщины завлекали ничего не подозревающих мужчин в квартиру на 225 Chestnut Street.",
                "Оперативники наблюдали за реакцией через двухстороннее стекло, распивая мартини в соседней комнате.",
                "В 1973 году директор ЦРУ Ричард Хелмс распорядился уничтожить всю документацию МК-Ультра, но финансовый архив чудом уцелел."
            ],
            "cta_question": "Верите ли вы, что подобные эксперименты над людьми были полностью прекращены?",
            "poll": {
                "question": "Верите ли вы, что эксперименты МК-Ультра свернули в 70-х?",
                "options": [
                    "Да, под давлением Сената программу закрыли",
                    "Нет, методики просто засекретили глубже",
                    "Перевели в частные корпорации и НИИ",
                    "Хочу изучить оригиналы документов"
                ]
            }
        }
    },
    {
        "id": "ep02_acoustic_kitty",
        "episode": 2,
        "series": "Рассекреченные архивы: Сезон 1",
        "title": "Проект Acoustic Kitty: 20 миллионов долларов на кота-шпиона",
        "target_duration_s": 45,
        "hook": "Двадцать миллионов долларов на кота-шпиона, которого в первом же задании сбило такси!",
        "script": "В шестидесятые годы ЦРУ потратило двадцать миллионов долларов на создание идеального шпиона. В обычную кошку хирурги вживили микрофон в ушной канал, радиопередатчик у основания черепа, а тонкую антенну вплели в шерсть до самого хвоста. Проект «Акустическая кошечка» должен был подслушивать советских дипломатов в парке Вашингтона. Но во время первых же полевых испытаний выпущенное животное побежало через дорогу и мгновенно попало под колеса такси. Программу немедленно закрыли как непригодную. Документы рассекретили лишь в 2001 году. Вы верите, что на кошках всё закончилось?",
        "voice": "ru-RU-DmitryNeural",
        "bgm_gain_db": -22,
        "historical_metadata": {
            "operation_name": "Project Acoustic Kitty",
            "agency": "CIA Directorate of Science & Technology",
            "year_initiated": 1961,
            "year_declassified": 2001,
            "declassification_authority": "FOIA request by Jeffrey Richelson (National Security Archive)",
            "key_figures": "Victor Marchetti, CIA Technical Research Directorate",
            "primary_source_doc": "CIA Declassified Memo: Views on Trained Cats for Reconnaissance (1967)"
        },
        "scenes": [
            {
                "index": 0, "duration_s": 4.0,
                "source_query": "Cat domestic feline vintage portrait 1960s",
                "overlay_text": "ВАШИНГТОН, 1961 // $20 МЛН НА БИО-ШПИОНА",
                "narration_segment": "В шестидесятые годы ЦРУ потратило двадцать миллионов долларов на создание идеального шпиона."
            },
            {
                "index": 1, "duration_s": 8.0,
                "source_query": "Vintage surgical tools operating room radio antenna miniature",
                "overlay_text": "МИКРОФОН В УХЕ // АНТЕННА В ХВОСТЕ",
                "narration_segment": "В обычную кошку хирурги вживили микрофон в ушной канал, радиопередатчик у черепа, а антенну вплели в шерсть."
            },
            {
                "index": 2, "duration_s": 8.0,
                "source_query": "Soviet embassy Washington park bench spy meeting 1960s",
                "overlay_text": "ЦЕЛЬ: СОВЕТСКИЕ ДИПЛОМАТЫ В ПАРКЕ",
                "narration_segment": "Проект «Акустическая кошечка» должен был подслушивать советских дипломатов в парке Вашингтона."
            },
            {
                "index": 3, "duration_s": 9.0,
                "source_query": "Vintage yellow cab taxi street road traffic 1960s",
                "overlay_text": "ПЕРВЫЙ ТЕСТ // НЕПРЕДВИДЕННЫЙ ФИНАЛ",
                "narration_segment": "Но во время первых же полевых испытаний выпущенное животное побежало через дорогу и мгновенно попало под колеса такси."
            },
            {
                "index": 4, "duration_s": 9.0,
                "source_query": "CIA top secret memorandum document stamp 2001",
                "overlay_text": "ПРОЕКТ ЗАКРЫТ // РАССЕКРЕЧЕНО В 2001",
                "narration_segment": "Программу немедленно закрыли как непригодную. Документы рассекретили лишь в 2001 году."
            },
            {
                "index": 5, "duration_s": 7.0,
                "source_query": "Cybernetic animal surveillance technology concept",
                "overlay_text": "КТО СЛЕДУЮЩИЙ?",
                "narration_segment": "Вы верите, что на кошках всё закончилось?"
            }
        ],
        "telegram_post": {
            "title": "Проект Acoustic Kitty: 20 миллионов долларов на кота-шпиона",
            "lead": "В разгар Холодной войны ЦРУ попыталось превратить домашнее животное в радиоуправляемый микрофон.",
            "declassified_facts": [
                "Хирургическая операция на кошке длилась более часа.",
                "Антенна представляла собой тончайший провод, проходящий сквозь шерсть вдоль позвоночника до кончика хвоста.",
                "Проект обошелся американским налогоплательщикам почти в 20 миллионов долларов по современному курсу.",
                "Итоговый меморандум ЦРУ 1967 года гласил: 'Кошки плохо поддаются дисциплине в условиях реального города'."
            ],
            "cta_question": "Используют ли спецслужбы животных и птиц для разведки сегодня?",
            "poll": {
                "question": "Используются ли био-киборги сегодня?",
                "options": [
                    "Да, дроны-птицы и насекомые существуют",
                    "Нет, спутники и смартфоны заменили всё",
                    "Только в экспериментальных лабораториях DARPA",
                    "Жду следующую серию!"
                ]
            }
        }
    },
    {
        "id": "ep03_operation_northwoods",
        "episode": 3,
        "series": "Рассекреченные архивы: Сезон 1",
        "title": "Операция Northwoods: Секретный план Пентагона по атакам на свои города",
        "target_duration_s": 46,
        "hook": "Пентагон планировал взрывать американские корабли и сбивать пассажирские самолёты!",
        "script": "13 марта 1962 года председатель Объединённого комитета начальников штабов генерал Лемнитцер положил на стол министру обороны США план операции «Нортвудс». Цель — убедить мир начать войну против Кубы. План предусматривал взрывы на американских военных базах, подрыв корабля в заливе Гуантанамо, террористические акты в городах Флориды и уничтожение беспилотного дублёра пассажирского самолёта с обвинением Гаваны. Президент Кеннеди лично отверг эту авантюру, а генерала вскоре отправили в отставку. План держался в строжайшем секрете 35 лет. Какие ещё папки лежат в архивах?",
        "voice": "ru-RU-DmitryNeural",
        "bgm_gain_db": -22,
        "historical_metadata": {
            "operation_name": "Operation Northwoods",
            "agency": "Joint Chiefs of Staff (Department of Defense)",
            "year_initiated": 1962,
            "year_declassified": 1997,
            "declassification_authority": "John F. Kennedy Assassination Records Review Board (ARRB)",
            "key_figures": "General Lyman Lemnitzer, Robert McNamara, John F. Kennedy",
            "primary_source_doc": "JCS Memorandum: Justification for US Military Intervention in Cuba (March 13, 1962)"
        },
        "scenes": [
            {
                "index": 0, "duration_s": 4.0,
                "source_query": "Pentagon aerial military building defense department 1960",
                "overlay_text": "ВАШИНГТОН, 13 МАРТА 1962 // ПЛАН ПЕНТАГОНА",
                "narration_segment": "13 марта 1962 года председатель Объединённого комитета начальников штабов положил на стол план операции «Нортвудс»."
            },
            {
                "index": 1, "duration_s": 8.0,
                "source_query": "Cuba Havana map military map Cold War 1962",
                "overlay_text": "ЦЕЛЬ: ПОВОД ДЛЯ ВТОРЖЕНИЯ НА КУБУ",
                "narration_segment": "Цель — убедить мир начать полномасштабную войну против Кубы."
            },
            {
                "index": 2, "duration_s": 9.0,
                "source_query": "Warship naval explosion smoke burning ship Guantanamo",
                "overlay_text": "ВЗРЫВЫ КОРАБЛЕЙ // ТЕРАКТЫ ВО ФЛОРИДЕ",
                "narration_segment": "План предусматривал подрыв корабля в заливе Гуантанамо и террористические акты в городах Флориды."
            },
            {
                "index": 3, "duration_s": 9.0,
                "source_query": "Commercial passenger airplane Boeing vintage 1960s flight",
                "overlay_text": "ФАЛЬШИВЫЙ САМОЛЕТ-ДУБЛЕР // СБИТЫЙ РЕЙС",
                "narration_segment": "А также уничтожение беспилотного дублёра пассажирского лайнера с обвинением кубинских истребителей."
            },
            {
                "index": 4, "duration_s": 9.0,
                "source_query": "John F Kennedy president Oval Office declassified file 1997",
                "overlay_text": "ОТКАЗ КЕННЕДИ // СНЯТИЕ ГРИФА ЧЕРЕЗ 35 ЛЕТ",
                "narration_segment": "Президент Кеннеди лично отверг авантюру, а генерала отправили в отставку. Документ скрывали 35 лет."
            },
            {
                "index": 5, "duration_s": 7.0,
                "source_query": "Secret government archive folders shelves classified boxes",
                "overlay_text": "КАКИЕ ЕЩЕ ПЛАНЫ ОСТАЛИСЬ В ТАЙНЕ?",
                "narration_segment": "Какие ещё папки лежат в архивах?"
            }
        ],
        "telegram_post": {
            "title": "Операция Northwoods: Рассекреченный план фальсификации войны",
            "lead": "В 1997 году комиссия ARRB опубликовала меморандум высшего военного командования США о проведении терактов под чужим флагом.",
            "declassified_facts": [
                "Меморандум подписан лично генералом Лиманом Лемнитцером 13 марта 1962 года.",
                "План включал потопление судов с кубинскими беженцами в открытом море.",
                "Предлагалось подготовить радиоуправляемый беспилотный самолет, замаскированный под гражданский лайнер, и взорвать его в воздухе.",
                "Джон Кеннеди категорически отказался одобрять операцию и не продлил полномочия Лемнитцера."
            ],
            "cta_question": "Могут ли подобные сценарии разрабатываться генералами в наши дни?",
            "poll": {
                "question": "Применяются ли методы Northwoods в современной политике?",
                "options": [
                    "Да, операции 'чужой флаг' регулярны",
                    "Нет, сегодня скрыть такое невозможно",
                    "Только в гибридных и информационных войнах",
                    "Узнал об этом впервые из ролика"
                ]
            }
        }
    },
    {
        "id": "ep04_stargate_project",
        "episode": 4,
        "series": "Рассекреченные архивы: Сезон 1",
        "title": "Проект Stargate: 20 лет боевой экстрасенсорики на службе ЦРУ",
        "target_duration_s": 45,
        "hook": "ЦРУ двадцать лет держало на зарплате боевых экстрасенсов для слежки за ядерными базами СССР!",
        "script": "Больше двух десятилетий разведка США финансировала сверхсекретную программу «Звёздные врата». Физики Рассел Тарг и Гарольд Путхофф в Стэнфордском институте тренировали операторов так называемого «дальновидения». За закрытыми дверями экстрасенсы по координатам на карте пытались нарисовать советские подлодки, военные заводы и найти пропавших дипломатов. В 1995 году ЦРУ рассекретило сотни томов отчётов, заявив, что данные телепатии слишком туманны для реальных боевых приказов. Но программа работала двадцать лет за миллионы долларов налогоплательщиков. Был ли результат на самом деле?",
        "voice": "ru-RU-DmitryNeural",
        "bgm_gain_db": -22,
        "historical_metadata": {
            "operation_name": "Project Stargate (Grill Flame / Sun Streak / Center Lane)",
            "agency": "CIA / DIA / US Army Intelligence",
            "year_initiated": 1972,
            "year_declassified": 1995,
            "declassification_authority": "CIA Executive Review & AIR Report (1995)",
            "key_figures": "Russell Targ, Harold Puthoff, Ingo Swann, Joseph McMoneagle",
            "primary_source_doc": "AIR Technical Report: An Evaluation of Remote Viewing (November 1995)"
        },
        "scenes": [
            {
                "index": 0, "duration_s": 4.0,
                "source_query": "Stanford Research Institute building vintage 1970s",
                "overlay_text": "КАЛИФОРНИЯ, 1972 // ПРОЕКТ «STARGATE»",
                "narration_segment": "Больше двух десятилетий разведка США финансировала сверхсекретную программу «Звёздные врата»."
            },
            {
                "index": 1, "duration_s": 8.0,
                "source_query": "Blindfolded person brainwave EEG electrodes laboratory",
                "overlay_text": "ФЕНОМЕН ДАЛЬНОВИДЕНИЯ // ТАРГ И ПУТХОФФ",
                "narration_segment": "Физики Рассел Тарг и Гарольд Путхофф тренировали операторов так называемого «дальновидения»."
            },
            {
                "index": 2, "duration_s": 8.0,
                "source_query": "Soviet nuclear submarine Typhoon submarine shipyard coordinates",
                "overlay_text": "ШПИОНАЖ ПО КООРДИНАТАМ // БАЗЫ СССР",
                "narration_segment": "Экстрасенсы по координатам на карте пытались нарисовать советские подлодки и засекреченные заводы."
            },
            {
                "index": 3, "duration_s": 9.0,
                "source_query": "CIA declassified archive report 1995 psychic intelligence",
                "overlay_text": "РАССЕКРЕЧЕНО В 1995 // 20 ЛЕТ И $20 МЛН",
                "narration_segment": "В 1995 году ЦРУ рассекретило архивы, заявив, что данные телепатии слишком туманны для приказов."
            },
            {
                "index": 4, "duration_s": 9.0,
                "source_query": "Dollar bills cash money burning government budget",
                "overlay_text": "20 ЛЕТ ФИНАНСИРОВАНИЯ ИЗ БЮДЖЕТА",
                "narration_segment": "Но программа работала двадцать лет за миллионы долларов налогоплательщиков."
            },
            {
                "index": 5, "duration_s": 7.0,
                "source_query": "Mysterious eye psychic intuition dark room light",
                "overlay_text": "РЕАЛЬНЫЙ ЭФФЕКТ ИЛИ ПСИХОЛОГИЧЕСКИЙ МИФ?",
                "narration_segment": "Был ли результат на самом деле?"
            }
        ],
        "telegram_post": {
            "title": "Проект Stargate: Боевые медиумы ЦРУ на зарплате Пентагона",
            "lead": "С 1972 по 1995 год правительство США официально тратило миллионы долларов на экстрасенсорную разведку советских военных объектов.",
            "declassified_facts": [
                "Программу вели ученые в Стэнфордском исследовательском институте (SRI).",
                "Один из медиумов, Инго Суонн, утверждал, что сумел описать советскую подлодку класса 'Тайфун' до того, как ее зафиксировали спутники.",
                "Проект сменил 5 кодовых названий: GONDOLA WISH, GRILL FLAME, CENTER LANE, SUN STREAK, STARGATE.",
                "В 1995 году независимый аудит AIR рекомендовал закрыть проект из-за невозможности использовать видения в реальных боевых задачах."
            ],
            "cta_question": "Как вы считаете, добилось ли ЦРУ хоть каких-то реальных результатов в пси-шпионаже?",
            "poll": {
                "question": "Верите ли вы в успехи программы Stargate?",
                "options": [
                    "Да, некоторые попадания были шокирующими",
                    "Нет, это был распил военного бюджета",
                    "Спецслужбы обеих сторон блефовали",
                    "Хочу отдельный лонгрид по этой теме"
                ]
            }
        }
    },
    {
        "id": "ep05_vela_incident",
        "episode": 5,
        "series": "Рассекреченные архивы: Сезон 1",
        "title": "Инцидент Вела: Тайна двойной ядерной вспышки в Атлантике",
        "target_duration_s": 46,
        "hook": "22 сентября 1979 года американский спутник зафиксировал двойную ядерную вспышку над океаном!",
        "script": "Ночью 22 сентября 1979 года спутник слежения «Вела 6911» засёк в районе островов Принс-Эдуард в Южной Атлантике характерный двойной световой импульс — безошибочную сигнатуру ядерного взрыва мощностью до трёх килотонн. Событие вызвало панику в Белом доме: ни одна ядерная держава не признала испытание. Созданная комиссия профессора Руины поспешила заявить, что это было столкновение микрометеорита со спутником. Однако замеры гидроакустических станций и следы радиации в щитовидке австралийских овец говорили об обратном. Кто нажал на кнопку: ЮАР, Израиль или обе страны вместе?",
        "voice": "ru-RU-DmitryNeural",
        "bgm_gain_db": -22,
        "historical_metadata": {
            "operation_name": "The Vela Incident (South Atlantic Flash)",
            "agency": "White House Office of Science & Technology / US Air Force Technical Applications Center (AFTAC)",
            "year_initiated": 1979,
            "year_declassified": 2018,
            "declassification_authority": "National Security Archive FOIA declassification",
            "key_figures": "Dr. Jack Ruina (Ruina Panel), Jimmy Carter",
            "primary_source_doc": "Ad Hoc Panel Report on the September 22 Event (The Ruina Report, 1980)"
        },
        "scenes": [
            {
                "index": 0, "duration_s": 4.0,
                "source_query": "Satellite in space Earth orbit Vela satellite 1970s",
                "overlay_text": "22 СЕНТЯБРЯ 1979 // СПУТНИК VELA 6911",
                "narration_segment": "Ночью 22 сентября 1979 года спутник засёк характерный двойной световой импульс."
            },
            {
                "index": 1, "duration_s": 8.0,
                "source_query": "Nuclear explosion flash ocean sea night horizon atomic",
                "overlay_text": "СИГНАТУРА ЯДЕРНОГО ВЗРЫВА // 3 КИЛОТОННЫ",
                "narration_segment": "Безошибочную сигнатуру тайного ядерного взрыва мощностью до трёх килотонн."
            },
            {
                "index": 2, "duration_s": 9.0,
                "source_query": "White House situation room Jimmy Carter meeting 1979",
                "overlay_text": "ПАНИКА В БЕЛОМ ДОМЕ // КОМИССИЯ РУИНЫ",
                "narration_segment": "Событие вызвало панику в Белом доме: комиссия профессора Руины поспешила заявить про столкновение с микрометеоритом."
            },
            {
                "index": 3, "duration_s": 9.0,
                "source_query": "Sonar hydrophone underwater acoustics ocean listening station",
                "overlay_text": "ГИДРОАКУСТИКА И РАДИАЦИЯ В АВСТРАЛИИ",
                "narration_segment": "Однако замеры гидроакустики и радиация в щитовидке австралийских овец говорили об обратном."
            },
            {
                "index": 4, "duration_s": 9.0,
                "source_query": "Prince Edward Islands map South Atlantic Indian ocean",
                "overlay_text": "ЮАР ИЛИ ИЗРАИЛЬ? // ТАЙНЫЙ ПОЛИГОН",
                "narration_segment": "Ни одна страна мира не взяла на себя ответственность за взрыв у островов Принс-Эдуард."
            },
            {
                "index": 5, "duration_s": 7.0,
                "source_query": "Nuclear mushroom cloud dark ocean mystery question",
                "overlay_text": "КТО СТОЯЛ ЗА ВЗРЫВОМ?",
                "narration_segment": "Кто нажал на кнопку: ЮАР, Израиль или обе страны вместе?"
            }
        ],
        "telegram_post": {
            "title": "Инцидент Вела: Загадочный ядерный взрыв 1979 года",
            "lead": "В ночь на 22 сентября 1979 года американский спутник зафиксировал двойную вспышку над океаном, которую Белый дом попытался объявить микрометеоритом.",
            "declassified_facts": [
                "Спутник Vela 6911 имел датчики bhangmeter, специально откалиброванные для фиксации двойного светового импульса ядерного взрыва.",
                "Сенсоры Naval Research Laboratory в Пуэрто-Рико также зафиксировали возмущение ионосферы в ту же минуту.",
                "Официальный отчет комиссии Джека Руины объявил вспышку отражением света от отколовшейся частицы спутника.",
                "В 2018 году рассекреченные дневники президента Джимми Картера подтвердили: в Белом доме были уверены, что это испытание ЮАР и Израиля."
            ],
            "cta_question": "Чьё ядерное испытание зафиксировал спутник на самом деле?",
            "poll": {
                "question": "Кто стоял за ядерным испытанием в Инциденте Вела?",
                "options": [
                    "Израиль (испытание нейтронной бомбы)",
                    "ЮАР (программа ядерного оружия апартеида)",
                    "Совместные секретные испытания ЮАР и Израиля",
                    "Случайный технический сбой датчиков"
                ]
            }
        }
    },
    {
        "id": "ep06_project_azorian",
        "episode": 6,
        "series": "Рассекреченные архивы: Сезон 1",
        "title": "Проект Azorian: Как ЦРУ подняло советскую подлодку К-129 со дна",
        "target_duration_s": 47,
        "hook": "ЦРУ построило гигантский корабль за миллиард долларов, чтобы украсть советскую атомную субмарину со дна океана!",
        "script": "В 1968 году в Тихом океане на глубине пять километров затонула советская подлодка К-129 с ядерными баллистическими ракетами. Москва не нашла место крушения, но его запеленговали акустики США. Чтобы достать шифры и боеголовки, ЦРУ провернуло дерзкую авантюру: миллиардер Говард Хьюз объявил о постройке судна «Гломар Эксплорер» для мирной добычи марганцевых руд. В 1974 году гигантские клешни захватили корпус подлодки, но при подъёме она разломилась. Американцы подняли лишь носовую часть и тела советских моряков, которых похоронили в море со всеми воинскими почестями.",
        "voice": "ru-RU-DmitryNeural",
        "bgm_gain_db": -22,
        "historical_metadata": {
            "operation_name": "Project Azorian (frequently misidentified as Project Jennifer)",
            "agency": "Central Intelligence Agency (CIA)",
            "year_initiated": 1968,
            "year_declassified": 2010,
            "declassification_authority": "CIA Historical Review Program declassified article (2010)",
            "key_figures": "Howard Hughes, William Colby, Richard Helms",
            "primary_source_doc": "The Project Azorian Declassified Internal History (Studies in Intelligence, Fall 1978)"
        },
        "scenes": [
            {
                "index": 0, "duration_s": 4.0,
                "source_query": "Soviet submarine underwater ocean deep sea 1960s",
                "overlay_text": "ТИХИЙ ОКЕАН, 1968 // ГИБЕЛЬ ПОДЛОДКИ К-129",
                "narration_segment": "В 1968 году в Тихом океане на глубине пять километров затонула советская подлодка К-129."
            },
            {
                "index": 1, "duration_s": 9.0,
                "source_query": "Hughes Glomar Explorer ship ocean recovery vessel 1974",
                "overlay_text": "ГОСПРИКРЫТИЕ: МИЛЛИАРДЕР ГОВАРД ХЬЮЗ",
                "narration_segment": "Чтобы достать шифры и ядерные ракеты, ЦРУ и миллиардер Говард Хьюз построили судно «Гломар Эксплорер»."
            },
            {
                "index": 2, "duration_s": 9.0,
                "source_query": "Mechanical giant claw claw recovery deep ocean underwater",
                "overlay_text": "ПРОЕКТ AZORIAN // ЗАХВАТ НА ГЛУБИНЕ 5 КМ",
                "narration_segment": "В 1974 году гигантские стальные клешни захватили субмарину, но при подъёме корпус разломился."
            },
            {
                "index": 3, "duration_s": 9.0,
                "source_query": "Declassified sonar photo sunken submarine wreckage ocean floor",
                "overlay_text": "ОБЛОМКИ НОСОВОЙ ЧАСТИ // ТОРПЕДЫ С ЯО",
                "narration_segment": "Американцы подняли лишь носовую часть и тела шестерых погибших советских подводников."
            },
            {
                "index": 4, "duration_s": 9.0,
                "source_query": "Military burial at sea flag coffin naval ceremony Glomar",
                "overlay_text": "ПОХОРОНЫ В МОРЕ С ВОИНСКИМИ ПОЧЕСТЯМИ",
                "narration_segment": "Их похоронили в море по советскому морскому уставу с исполнением гимна СССР."
            },
            {
                "index": 5, "duration_s": 7.0,
                "source_query": "Deep ocean abyss dark water mystery confidential",
                "overlay_text": "ГДЕ ОСТАЛИСЬ ШИФРОВАЛЬНЫЕ КНИГИ?",
                "narration_segment": "А главные шифры так и остались на глубине пяти километров."
            }
        ],
        "telegram_post": {
            "title": "Проект Azorian: Подъем затонувшей подлодки К-129 за $800 млн",
            "lead": "Самая масштабная и дорогая подводная спецоперация ЦРУ: подъем советской ракетной субмарины под видом геологоразведки Говарда Хьюза.",
            "declassified_facts": [
                "Бюджет операции превысил $800 млн (около $5 млрд по курсу 2026 года).",
                "Специально построенное судно 'Hughes Glomar Explorer' имело лунный бассейн с раздвижным дном, скрывавшим захват подлодки.",
                "При подъеме две трети корпуса оторвались и рухнули обратно на глубину 5000 метров.",
                "Видеозапись погребения советских моряков в 1992 году директор ЦРУ Роберт Гейтс лично передал Борису Ельцину."
            ],
            "cta_question": "Стоила ли добытая носовая часть субмарины полумиллиарда долларов?",
            "poll": {
                "question": "Удалась ли ЦРУ операция 'Azorian'?",
                "options": [
                    "Да, получили ядерные торпеды и технологии",
                    "Нет, ракеты и шифры сорвались на дно",
                    "Колоссальный перерасход ради сомнительного трофея",
                    "Поражает инженерный гений операции"
                ]
            }
        }
    },
    {
        "id": "ep07_tanganyika_laughter",
        "episode": 7,
        "series": "Рассеクレченные архивы: Сезон 1",
        "title": "Эпидемия смеха в Танганьике: Массовый психоз, закрывший 14 школ",
        "target_duration_s": 45,
        "hook": "В 1962 году смех трёх школьниц закрыл четырнадцать школ и вызвал массовый психоз!",
        "script": "30 января 1962 года в женской школе-интернате в деревне Кашаша три девочки начали непрерывно смеяться. Смех перерос в истерику, слёзы и панику, охватив почти сотню учениц. Школу закрыли, детей отправили по домам, но эпидемия перекинулась на соседние деревни. За полгода смехом заразились более тысячи человек, а властям пришлось закрыть четырнадцать учебных заведений. Врачи не нашли ни токсинов, ни вирусов. Официальный вердикт науки — массовое психогенное расстройство, вызванное колоссальным стрессом молодёжи на фоне обретения независимости. Или это был неизвестный социальный вирус?",
        "voice": "ru-RU-DmitryNeural",
        "bgm_gain_db": -22,
        "historical_metadata": {
            "operation_name": "The Tanganyika Laughter Epidemic",
            "agency": "Tanganyika Ministry of Health / British Medical Journal Investigation",
            "year_initiated": 1962,
            "year_declassified": 1963,
            "declassification_authority": "Medical Case Studies (Rankin & Philip, Central African Journal of Medicine)",
            "key_figures": "Dr. A.M. Rankin, Dr. P.J. Philip",
            "primary_source_doc": "Rankin & Philip, 'An Epidemic of Laughing in the Bukoba District of Tanganyika' (1963)"
        },
        "scenes": [
            {
                "index": 0, "duration_s": 4.0,
                "source_query": "Mission school Africa vintage classroom 1960s pupils",
                "overlay_text": "30 ЯНВАРЯ 1962 // ДЕРЕВНЯ КАШАША",
                "narration_segment": "30 января 1962 года в женской школе-интернате три девочки начали непрерывно смеяться."
            },
            {
                "index": 1, "duration_s": 8.0,
                "source_query": "Hysterical laughter crying emotion vintage portrait girls",
                "overlay_text": "СМЕХ ПЕРЕХОДЯЩИЙ В ПАНИКУ // 95 УЧЕНИЦ",
                "narration_segment": "Смех перерос в истерику, слёзы и панику, охватив почти сотню учениц."
            },
            {
                "index": 2, "duration_s": 9.0,
                "source_query": "Abandoned African school empty desks closed gate 1960s",
                "overlay_text": "ЗАКРЫТО 14 ШКОЛ // 1000+ ЗАРАЖЕННЫХ",
                "narration_segment": "Школу закрыли, но эпидемия перекинулась дальше: властям пришлось закрыть 14 учебных заведений."
            },
            {
                "index": 3, "duration_s": 9.0,
                "source_query": "Medical doctors examining patient hospital laboratory 1960s",
                "overlay_text": "НИ ТОКСИНОВ, НИ ВИРУСОВ // АНОМАЛИЯ",
                "narration_segment": "Врачи не нашли ни следов яда, ни инфекций во взятых пробах."
            },
            {
                "index": 4, "duration_s": 8.0,
                "source_query": "Crowd stress psychological tension black and white archive",
                "overlay_text": "МАССОВОЕ ПСИХОГЕННОЕ РАССТРОЙСТВО",
                "narration_segment": "Наука объяснила это массовым психозом из-за стресса в момент слома эпох."
            },
            {
                "index": 5, "duration_s": 7.0,
                "source_query": "Brain neural network psychological contagion abstract dark",
                "overlay_text": "МОЖЕТ ЛИ ЭТО ПОВТОРИТЬСЯ?",
                "narration_segment": "Или это был неизвестный социальный вирус?"
            }
        ],
        "telegram_post": {
            "title": "Эпидемия смеха в Танганьике: Загадка массового психоза 1962 года",
            "lead": "Вспышка неконтролируемого истерического смеха парализовала целый регион в Восточной Африке на 6 месяцев.",
            "declassified_facts": [
                "Приступы смеха и слез продолжались у пострадавших от нескольких часов до 16 дней подряд.",
                "Ни один взрослый или учитель не заразился — феномен поражал исключительно детей и подростков от 12 до 18 лет.",
                "Деревня Кашаша и соседние поселки были изолированы полицией, чтобы остановить распространение паники.",
                "Современные эпидемиологи классифицируют случай как крупнейшую документированную вспышку MPI (массового социогенного заболевания)."
            ],
            "cta_question": "Подвержен ли современный человек массовому психогенному заражению через соцсети?",
            "poll": {
                "question": "Возможен ли подобный массовый психоз в наши дни?",
                "options": [
                    "Да, через TikTok и вирусные тренды",
                    "Нет, современная медицина сразу купирует",
                    "Уже происходит прямо сейчас",
                    "Очень странный исторический факт"
                ]
            }
        }
    },
    {
        "id": "ep08_project_iceworm",
        "episode": 8,
        "series": "Рассекреченные архивы: Сезон 1",
        "title": "Проект Iceworm: Город ядерных ракет подо льдами Гренландии",
        "target_duration_s": 47,
        "hook": "США пробурили четыре тысячи километров туннелей во льдах Гренландии, чтобы спрятать шестьсот ядерных ракет!",
        "script": "В 1959 году армия США построила в ледяном щите Гренландии комплекс «Кэмп Сенчури», работавший на мобильном ядерном реакторе. Миру его представили как научную станцию для полярных исследований. Но подлинной целью был сверхсекретный проект «Ледяной червь». Пентагон планировал вырезать в леднике четыре тысячи километров туннелей и разместить шестьсот ядерных ракет с прямым наведением на СССР. Проект рухнул не из-за шпионов, а из-за физики: ледник двигался быстрее расчётов, сдавливая стены и деформируя пусковые рельсы. В 1966 году базу бросили подо льдом вместе с радиоактивными отходами.",
        "voice": "ru-RU-DmitryNeural",
        "bgm_gain_db": -22,
        "historical_metadata": {
            "operation_name": "Project Iceworm / Camp Century",
            "agency": "US Army / Department of Defense",
            "year_initiated": 1959,
            "year_declassified": 1997,
            "declassification_authority": "Danish Institute of International Affairs (DUPI) historical inquiry (1997)",
            "key_figures": "US Army Corps of Engineers, Danish Prime Minister H.C. Hansen",
            "primary_source_doc": "Greenland During the Cold War: Danish and American Security Policy 1945–1968 (DUPI 1997)"
        },
        "scenes": [
            {
                "index": 0, "duration_s": 4.0,
                "source_query": "Camp Century Greenland ice snow military base 1960",
                "overlay_text": "ГРЕНЛАНДИЯ, 1959 // КЭМП СЕНЧУРИ ПОДО ЛЬДОМ",
                "narration_segment": "В 1959 году армия США построила в ледяном щите Гренландии полярную базу «Кэмп Сенчури»."
            },
            {
                "index": 1, "duration_s": 9.0,
                "source_query": "Ice tunnel trench snow machine drilling Greenland military",
                "overlay_text": "ПРОЕКТ «ICEWORM» // 4000 КМ ЛЕДЯНЫХ ТУННЕЛЕЙ",
                "narration_segment": "Подлинной целью был проект «Ледяной червь» — сеть туннелей под ледяным щитом."
            },
            {
                "index": 2, "duration_s": 9.0,
                "source_query": "Nuclear missile launcher railway tunnel subterranean Cold War",
                "overlay_text": "600 ЯДЕРНЫХ РАКЕТ ПОД ПРИКРЫТИЕМ НАУКИ",
                "narration_segment": "Пентагон планировал разместить там шестьсот ядерных ракет на рельсовых платформах."
            },
            {
                "index": 3, "duration_s": 9.0,
                "source_query": "Mobile nuclear power plant PM-2A Camp Century military",
                "overlay_text": "ЯДЕРНЫЙ РЕАКТОР PM-2A // ДВИЖЕНИЕ ЛЬДА",
                "narration_segment": "База питалась от атомного реактора, но ледник двигался и сдавливал стены туннелей."
            },
            {
                "index": 4, "duration_s": 9.0,
                "source_query": "Abandoned military bunker under ice Greenland melting snow",
                "overlay_text": "БРОШЕНО В 1966 // РАДИОАКТИВНЫЙ СЛЕД",
                "narration_segment": "В 1966 году базу спешно бросили подо льдом вместе с опасными отходами."
            },
            {
                "index": 5, "duration_s": 7.0,
                "source_query": "Melting glacier Greenland climate environmental threat",
                "overlay_text": "ЛЕДНИК ТАЕТ. ЧТО ВСПЛЫВЕТ НАРУЖУ?",
                "narration_segment": "Теперь тающие ледники грозят вымыть эти отходы в океан."
            }
        ],
        "telegram_post": {
            "title": "Проект Iceworm: Секретный атомный город под ледником Гренландии",
            "lead": "В разгар Холодной войны Пентагон построил подземный ядерный полигон прямо под ногами властей Дании.",
            "declassified_facts": [
                "Дания объявляла свою территорию безъядерной зоной, поэтому проект скрывался даже от союзников по НАТО.",
                "Комплекс включал госпиталь, кинотеатр, жилые блоки и первый в мире мобильный реактор PM-2A.",
                "Лед пластичен: своды туннелей проседали со скоростью до 1 метра в год, разрушая рельсовые пути ракет 'Iceman'.",
                "При эвакуации подо льдом оставили более 200 тысяч литров дизеля и радиоактивную охлаждающую воду."
            ],
            "cta_question": "Как решить проблему оставленных подо льдом радиоактивных отходов?",
            "poll": {
                "question": "Что делать с ядерным наследием Camp Century?",
                "options": [
                    "США обязаны провести полную дезактивацию",
                    "Оставить подо льдом — растает нескоро",
                    "Дания и США должны разделить расходы",
                    "Шокирован масштабом этого проекта"
                ]
            }
        }
    },
    {
        "id": "ep09_ghost_army",
        "episode": 9,
        "series": "Рассекреченные архивы: Сезон 1",
        "title": "Ghost Army: Художники и звукорежиссеры, обманувшие Вермахт",
        "target_duration_s": 46,
        "hook": "Художники и звукорежиссёры с надувными танками спасли тысячи жизней во Второй мировой!",
        "script": "В 1944 году армия США создала самое необычное боевое подразделение — 23-й отряд специального назначения, известный как «Армия призраков». Вместо кадровых пехотинцев туда набрали выпускников художественных институтов, звукооператоров и дизайнеров. Вооружившись надувными резиновыми танками, муляжами самолётов и динамиками мощностью пятьсот ватт, они имитировали присутствие целых дивизий. Фальшивые радиопереговоры и грохот гусениц из репродукторов сбивали с толку немецкую разведку в двадцати крупных операциях, спасая жизни десятков тысяч солдат союзников. Секрет хранили полвека.",
        "voice": "ru-RU-DmitryNeural",
        "bgm_gain_db": -22,
        "historical_metadata": {
            "operation_name": "Ghost Army (23rd Headquarters Special Troops)",
            "agency": "US Army / Allied Expeditionary Force",
            "year_initiated": 1944,
            "year_declassified": 1996,
            "declassification_authority": "US Department of the Army Declassification (1996) / Congressional Gold Medal (2022)",
            "key_figures": "Colonel Harry L. Reeder, Bill Blass, Ellsworth Kelly, Arthur Singer",
            "primary_source_doc": "Official History of the 23rd Headquarters Special Troops (Declassified 1996)"
        },
        "scenes": [
            {
                "index": 0, "duration_s": 4.0,
                "source_query": "Inflatable dummy tank Sherman World War II rubber decoy",
                "overlay_text": "ФРАНЦИЯ, 1944 // 23-Й ОТРЯД СПЕЦНАЗА",
                "narration_segment": "В 1944 году армия США создала подразделение «Армия призраков»."
            },
            {
                "index": 1, "duration_s": 8.0,
                "source_query": "Art students painters designers camouflage WWII uniform",
                "overlay_text": "1100 ДИЗАЙНЕРОВ И ЗВУКОИНЖЕНЕРОВ",
                "narration_segment": "Туда набрали выпускников художественных институтов, звукооператоров и дизайнеров."
            },
            {
                "index": 2, "duration_s": 9.0,
                "source_query": "Loudspeaker sonic deception military truck sound recording",
                "overlay_text": "РЕПРОДУКТОРЫ 500 ВАТТ // ЗВУКОВАЯ МИСТИФИКАЦИЯ",
                "narration_segment": "Вооружившись надувными танками и мощнейшими динамиками, они имитировали присутствие танковых армий."
            },
            {
                "index": 3, "duration_s": 9.0,
                "source_query": "Military radio operator headset fake battlefield traffic WWII",
                "overlay_text": "ФАЛЬШИВЫЙ РАДИОЭФИР // 20 КРУПНЫХ ОПЕРАЦИЙ",
                "narration_segment": "Фальшивые радиопереговоры и грохот гусениц сбивали с толку разведку в двадцати битвах."
            },
            {
                "index": 4, "duration_s": 9.0,
                "source_query": "Allied soldiers cheering Rhine crossing victory 1945",
                "overlay_text": "ДЕСЯТКИ ТЫСЯЧ СПАСЕННЫХ ЖИЗНЕЙ",
                "narration_segment": "Они отвлекали огонь на себя, спасая жизни десятков тысяч солдат союзников."
            },
            {
                "index": 5, "duration_s": 7.0,
                "source_query": "Congressional Gold medal military honor archive paper",
                "overlay_text": "СЕКРЕТ ХРАНИЛИ 50 ЛЕТ",
                "narration_segment": "Секрет хранили больше полувека."
            }
        ],
        "telegram_post": {
            "title": "Ghost Army: Как надувные танки и художники обманули немецкую разведку",
            "lead": "Невероятная и строго засекреченная до 1996 года история 23-го отряда специального назначения армии США.",
            "declassified_facts": [
                "Среди солдат отряда были будущие мировые знаменитости: модельер Билл Бласс и художник Эллсворт Келли.",
                "Надувной танк Sherman из прорезиненной ткани весил всего 42 кг и надувался компрессором за 20 минут.",
                "Звукорежиссеры записали звуки бронетанковых колонн в Форт-Ноксе на проволочные магнитофоны, слышимые за 24 км.",
                "В 2022 году ветераны отряда были удостоены Золотой медали Конгресса США."
            ],
            "cta_question": "Какая военная хитрость Второй мировой войны поражает вас больше всего?",
            "poll": {
                "question": "Что важнее на поле боя?",
                "options": [
                    "Огневая мощь и тяжелая броня",
                    "Военная хитрость и дезинформация",
                    "Разведка и перехват радиосвязи",
                    "Героизм и стойкость солдат"
                ]
            }
        }
    },
    {
        "id": "ep10_project_habakkuk",
        "episode": 10,
        "series": "Рассеクレченные архивы: Сезон 1",
        "title": "Проект Habakkuk: Секретный авианосец Черчилля из опилок и льда",
        "target_duration_s": 47,
        "hook": "Черчилль одобрил постройку гигантского двухмиллионного авианосца из опилок и льда!",
        "script": "В разгар битвы за Атлантику британские конвои нещадно топили немецкие подлодки в зоне, куда не долетала авиация. Изобретатель Джеффри Пайк предложил безумную идею: построить непотопляемый авианосец длиной шестьсот метров из замороженной смеси льда и древесных опилок — пайкерита. Материал не кололся от пуль, медленно таял и стоил копейки. В Канаде в строжайшей тайне собрали тысячетонный прототип с системой охлаждения. Лорд Маунтбеттен даже выстрелил в кусок пайкерита на конференции генералов, вызвав переполох. Но проект закрыли: подоспели дальние бомбардировщики и дефицит стали для холодильников.",
        "voice": "ru-RU-DmitryNeural",
        "bgm_gain_db": -22,
        "historical_metadata": {
            "operation_name": "Project Habakkuk",
            "agency": "Combined Operations Headquarters (UK) / National Research Council of Canada",
            "year_initiated": 1942,
            "year_declassified": 1951,
            "declassification_authority": "Admiralty War Diaries & Combined Ops Records",
            "key_figures": "Geoffrey Pyke, Lord Louis Mountbatten, Winston Churchill",
            "primary_source_doc": "Combined Operations HQ Memo: The Pykrete Vessel Project (1943)"
        },
        "scenes": [
            {
                "index": 0, "duration_s": 4.0,
                "source_query": "German U-boat submarine Atlantic ocean convoy WWII sinking ship",
                "overlay_text": "БИТВА ЗА АТЛАНТИКУ, 1942 // ТОРПЕДЫ У-БОТОВ",
                "narration_segment": "В разгар битвы за Атлантику конвои союзников нещадно топили немецкие субмарины."
            },
            {
                "index": 1, "duration_s": 8.0,
                "source_query": "Ice block wood pulp mixture pykrete material laboratory",
                "overlay_text": "ПАЙКЕРИТ // СМЕСЬ ЛЬДА И ДРЕВЕСНЫХ ОПИЛОК",
                "narration_segment": "Изобретатель Джеффри Пайк предложил создать авианосец из замороженной смеси льда и опилок."
            },
            {
                "index": 2, "duration_s": 9.0,
                "source_query": "Giant aircraft carrier ice ship concept blueprint Habakkuk",
                "overlay_text": "ДЛИНА 600 МЕТРОВ // 2 МИЛЛИОНА ТОНН",
                "narration_segment": "Непотопляемый ледяной гигант длиной шестьсот метров и водоизмещением два миллиона тонн."
            },
            {
                "index": 3, "duration_s": 9.0,
                "source_query": "Lord Mountbatten general conference pistol shot experiment",
                "overlay_text": "ВЫСТРЕЛ В ПАЙКЕРИТ НА СОВЕТЕ ГЕНЕРАЛОВ",
                "narration_segment": "Лорд Маунтбеттен лично выстрелил в блок пайкерита перед генералами, доказав его прочность."
            },
            {
                "index": 4, "duration_s": 9.0,
                "source_query": "Patricia Lake Jasper Canada prototype wooden roof ice",
                "overlay_text": "ПРОТОТИП В КАНАДЕ // ОТКАЗ ИЗ-ЗА СТАЛИ",
                "narration_segment": "В Канаде собрали прототип, но проект закрыли из-за нехватки стали для холодильных машин."
            },
            {
                "index": 5, "duration_s": 8.0,
                "source_query": "Long range bomber B-24 Liberator flying ocean victory",
                "overlay_text": "БЕЗУМНЫЙ ГЕНИЙ ИЛИ РЕАЛЬНОЕ ОРУЖИЕ?",
                "narration_segment": "Подоспели дальние бомбардировщики, сделавшие ледяной авианосец ненужным."
            }
        ],
        "telegram_post": {
            "title": "Проект Habakkuk: Непотопляемый авианосец Черчилля из льда и опилок",
            "lead": "Самый фантастический военно-морской проект Второй мировой: двухмиллионный авианосец из пайкерита для защиты конвоев от подлодок Дёница.",
            "declassified_facts": [
                "Пайкерит состоит из 86% пресной воды и 14% древесных опилок. Пули отскакивали от него без сколов.",
                "Проектный корабль должен был нести до 200 тяжелых истребителей и выдерживать попадания торпед без повреждений корпуса.",
                "На озере Патрисия в Канаде построили уменьшенный прототип 18x9 метров, таявший целых три лета подряд.",
                "Черчилль лично лоббировал постройку корабля, дав ему кодовое имя библейского пророка Аввакума."
            ],
            "cta_question": "Могла ли эта безумная идея изменить ход морской войны, если бы проект достроили?",
            "poll": {
                "question": "Авианосец из опилок и льда — это:",
                "options": [
                    "Гениальное инженерное решение",
                    "Безумная трата ресурсов во время войны",
                    "Рабочая идея, опередившая свое время",
                    "Чистый миф, пока не увидел чертежи"
                ]
            }
        }
    }
]


def generate_all() -> None:
    for ep in EPISODES:
        fname = JOBS_DIR / f"{ep['id']}.json"
        with open(fname, "w", encoding="utf-8") as f:
            json.dump(ep, f, ensure_ascii=False, indent=2)
        print(f"[gen] Создан манифест: {fname.name} ({ep['title'][:55]}...)")
    print(f"[gen] Успешно сгенерировано {len(EPISODES)} серий в {JOBS_DIR}/")


if __name__ == "__main__":
    generate_all()
