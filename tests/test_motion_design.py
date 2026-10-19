"""Motion design v4.1: юридические виды сцен, карточки-шаблоны, фото,
граф сцены без просвечивания текста при xfade."""
import json
import re
from pathlib import Path

import pytest
from PIL import Image

from tubecook.media import gfx, scenes as S
from tubecook.media.render import _scene_filter_graph

from conftest import words_of

REPO = Path(__file__).resolve().parent.parent

VODOKANAL = {
    "topic": "Запорожская община против Водоканала",
    "hook": "Суд против Водоканала: прецедент в Запорожье!",
    "script": ("Суд против Водоканала: прецедент в Запорожье, который "
               "касается каждого плательщика коммунальных услуг! "
               "Коммунальное предприятие требовало оплату и начисляло долги, "
               "но жители общины обратились в суд. "
               "Запорожский окружной административный суд, дело номер 280 "
               "дробь 8165 дробь 23. "
               "Вердикт суда: иск удовлетворен частично, действия Водоканала "
               "признаны незаконными. "
               "Главный вывод: проверяйте основания любых начислений. "
               "Подписывайтесь!"),
    "visual_plan": [
        {"scene": 0, "kind": "hook", "text": "...",
         "description": "Динамичный акцентный заголовок"},
        {"scene": 1, "kind": "problem", "text": "...",
         "description": "Спор по начислениям, фото КП Водоканал"},
        {"scene": 2, "kind": "fact_card", "text": "...",
         "description": "Карточка дела: Дело № 280/8165/23 • "
                        "Запорожский окружной админсуд"},
        {"scene": 3, "kind": "verdict", "text": "...",
         "description": "Решение суда: Действия Водоканала противоправны • "
                        "Обязать выдать первичные документы"},
        {"scene": 4, "kind": "practical_value", "text": "...",
         "description": "Практический вывод: 1. Проверка договора • "
                        "2. Аудит начислений • 3. Судебная защита"},
    ],
    "meta": {"primary_case_number": "280/8165/23"},
}


# ------------------------------------------------------------- виды сцен

def test_legal_kinds_from_hook_indexed_plan():
    """План, индексированный по сценам (с hook): body-фразы получают свои
    юридические виды, hook/outro не протекают в тело (баг rc1 устранён)."""
    words = words_of(VODOKANAL["script"])
    sc_list = S.build_scenes(VODOKANAL, words, words[-1]["end"])
    kinds = [sc.kind for sc in sc_list]
    assert kinds[0] == "hook"
    assert kinds[1] == "problem"       # в rc1 из-за смещения это был hook
    assert kinds[2] == "case"
    assert kinds[3] == "verdict"
    assert kinds[4] == "practical_value"
    assert kinds[-1] == "outro"
    # никаких hook в середине
    assert "hook" not in kinds[1:-1]
    assert "outro" not in kinds[:-1]


def test_case_scene_extracts_number_and_subtitle():
    words = words_of(VODOKANAL["script"])
    sc_list = S.build_scenes(VODOKANAL, words, words[-1]["end"])
    case = next(sc for sc in sc_list if sc.kind == "case")
    assert case.case_number == "280/8165/23"
    assert case.kinetic == "ДЕЛО № 280/8165/23"    # scale-up акцент
    assert case.badge == "ДЕЛО № 280/8165/23"
    assert "Запорожский окружной админсуд" in case.subtitle


def test_verdict_and_steps_points():
    words = words_of(VODOKANAL["script"])
    sc_list = S.build_scenes(VODOKANAL, words, words[-1]["end"])
    verdict = next(sc for sc in sc_list if sc.kind == "verdict")
    assert verdict.badge == "РЕШЕНИЕ СУДА"
    assert any("противоправны" in p for p in verdict.points)
    assert any("документы" in p for p in verdict.points)

    steps = next(sc for sc in sc_list if sc.kind == "practical_value")
    assert steps.badge == "ПРАКТИЧЕСКИЙ ВЫВОД"
    assert len(steps.points) == 3


def test_problem_scene_badge():
    words = words_of(VODOKANAL["script"])
    sc_list = S.build_scenes(VODOKANAL, words, words[-1]["end"])
    problem = next(sc for sc in sc_list if sc.kind == "problem")
    assert problem.badge == "СТОРОНЫ СПОРА"


def test_fact_card_alias_maps_to_case():
    # план body-конвенции: ["fact_card"] относится к первому body-предложению
    assert S._classify("x", 1, 5, [{"kind": "fact_card"}]) == "case"


def test_plan_description_parsing():
    label, points = S.parse_plan_description(
        "Решение суда: Действия противоправны • Обязать выдать документы")
    assert label == "Решение суда"
    assert points == ["Действия противоправны", "Обязать выдать документы"]


def test_image_resolved_only_if_exists(tmp_path, monkeypatch):
    """image_url из плана -> абсолютный путь, только если файл есть."""
    photo = tmp_path / "photo.jpg"
    Image.new("RGB", (640, 480), (30, 60, 120)).save(photo)
    payload = dict(VODOKANAL)
    plan = [dict(x) for x in VODOKANAL["visual_plan"]]
    plan[1]["image_url"] = str(photo)
    payload["visual_plan"] = plan
    monkeypatch.chdir(tmp_path)

    words = words_of(payload["script"])
    sc_list = S.build_scenes(payload, words, words[-1]["end"])
    problem = next(sc for sc in sc_list if sc.kind == "problem")
    assert problem.image == str(photo)

    # несуществующий путь -> фото отключено, карточка остаётся валидной
    plan[1]["image_url"] = "assets/no_such_file.jpg"
    payload["visual_plan"] = plan
    sc_list = S.build_scenes(payload, words, words[-1]["end"])
    problem = next(sc for sc in sc_list if sc.kind == "problem")
    assert problem.image == ""


# ------------------------------------------------------------- карточки

def _render(kind: str, scene: dict, tmp_path: Path) -> dict:
    scene.setdefault("index", 0)
    scene["kind"] = kind
    scene.setdefault("out_dir", str(tmp_path / "sc"))
    return gfx.render_scene_layers(scene)


@pytest.mark.parametrize("kind,extra", [
    ("case", {"case_number": "280/8165/23", "subtitle": "Запорожский окружной админсуд",
              "text": "Дело о начислениях", "points": []}),
    ("verdict", {"points": ["Действия противоправны", "Выдать документы"],
                 "text": "Вердикт"}),
    ("problem", {"text": "Спор по начислениям коммунальных услуг", "image": ""}),
    ("practical_value", {"points": ["Проверка договора", "Аудит", "Суд"],
                         "text": "Вывод"}),
])
def test_legal_cards_render_1080x1920(kind, extra, tmp_path):
    layers = _render(kind, extra, tmp_path)
    card = Image.open(layers["card"])
    assert card.size == (1080, 1920)
    assert card.mode == "RGBA"
    # карточка не пустая: есть непрозрачные пиксели
    alpha = card.getchannel("A")
    assert alpha.getextrema()[1] > 200


def test_problem_card_with_photo(tmp_path):
    photo = tmp_path / "v.jpg"
    Image.new("RGB", (900, 600), (10, 120, 90)).save(photo)
    layers = _render("problem", {"text": "Спор по начислениям",
                                 "image": str(photo)}, tmp_path)
    card = Image.open(layers["card"])
    # в центре рамки фото — зелёный оттенок исходника, не фон
    px = card.convert("RGBA").getpixel((540, 850))
    assert px[1] > px[0]                     # зелёный канал доминирует


# --------------------------------------------------- xfade без просвечивания

def test_scene_graph_card_fades_inside_body():
    """Тело сцены: карточка гаснет К КОНЦУ тела (переходы строятся отдельно
    из безкарточных клипов -> в окне кроссфейда текста нет физически)."""
    dur = 8.0
    g = _scene_filter_graph(dur, frames=240, W=1080, H=1920, fps=30,
                            zamp=0.04, slide_t=0.55, slide_off=170,
                            direction=-1, accx="(W-w)/2", accy="(H-h)/2",
                            first=False, last=False)
    card = [x for x in g if "[card]" in x][0]
    assert "alpha=1" in card                     # гаснет именно альфа карточки
    m = re.search(r"fade=t=out:st=([\d.]+):d=([\d.]+):alpha=1", card)
    fout_st, fout_d = float(m.group(1)), float(m.group(2))
    assert fout_st + fout_d <= dur + 0.01        # погасла к концу тела
    m = re.search(r"fade=t=in:st=([\d.]+)", card)
    assert float(m.group(1)) < 0.35              # въезд сразу после перехода
    assert any("zoompan" in x for x in g)


def test_last_scene_card_lives_to_freeze():
    """Финальная сцена: без fade-out — карточка живёт до стоп-кадра tpad."""
    g = _scene_filter_graph(6.0, 180, 1080, 1920, 30, 0.04, 0.55, 170,
                            -1, "(W-w)/2", "(H-h)/2", first=False, last=True)
    card = [x for x in g if "[card]" in x][0]
    assert "fade=t=out" not in card


def test_bgonly_clip_has_no_card_layer():
    """Клипы переходов строятся без карточного слоя вообще."""
    from tubecook.media.render import _bgonly_filter_graph, _transition_cmd
    g = _bgonly_filter_graph(11, 1080, 1920, 30, 0.04, "(W-w)/2", "(H-h)/2")
    joined = " ".join(g)
    assert "card" not in joined and "fade" not in joined
    # команда перехода: только два mp4-входа, никаких card-PNG
    cmd = _transition_cmd(Path("bg_a.mp4"), Path("bg_b.mp4"),
                          Path("t.mp4"), "smoothleft", 11 / 30, 30)
    inputs = [a for a in cmd if a.endswith(".mp4") or a.endswith(".png")]
    assert "bg_a.mp4" in inputs and "bg_b.mp4" in inputs
    assert not any(a.endswith(".png") for a in inputs)


def test_scene_graph_first_scene_fades_in_early():
    g = _scene_filter_graph(6.0, 180, 1080, 1920, 30, 0.04, 0.55, 170,
                            -1, "(W-w)/2", "(H-h)/2", first=True, last=False)
    card = [x for x in g if "[card]" in x][0]
    m = re.search(r"fade=t=in:st=([\d.]+)", card)
    assert float(m.group(1)) < 0.35          # первая сцена — без задержки xfade
