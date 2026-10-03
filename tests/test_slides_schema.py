"""しおりスライドの要求を、Google が公開している Slides API のスキーマで確かめる。

test_slides_export.py の検査は「こちらが思っている API の約束」を見ているだけで、
思い違いには気づけない。実際、両端の丸い札に FLOWCHART_TERMINATOR という
存在しない図形名を使っていて（正しくは FLOW_CHART_TERMINATOR）、本物の API なら
スライド作りが丸ごと失敗していた。それを見つけたのがこの検査。

スキーマは tests/data/slides_schema.json（公式の discovery 文書から、使う要求に
関係する部分だけを残した写し）。ネットワークは使わない。更新するときは:

    curl -s 'https://slides.googleapis.com/$discovery/rest?version=v1' > /tmp/d.json
    （tests/data/slides_schema.json の作り方は同じファイルの "note" を参照）

後半は、変なプラン（絵文字・長すぎる名前・空や None・数字の代わりの文字列・
制御文字・崩れた日付や時刻）を決まった種で大量に作って流し、落ちないこと・
スキーマを守ること・はみ出さないこと・「None」が画面に出ないことを見る。

実行: pytest tests/test_slides_schema.py
"""
import json
import os
import random
import sys

import pytest

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "src"))
sys.path.insert(0, os.path.dirname(__file__))
os.environ.setdefault("SECRET_KEY", "test-secret")

from services import slides_export as SX  # noqa: E402
import test_slides_export as T  # noqa: E402

_SCHEMA = json.load(open(os.path.join(os.path.dirname(__file__), "data", "slides_schema.json"),
                         encoding="utf-8"))
SCHEMAS = _SCHEMA["schemas"]


class SchemaError(AssertionError):
    pass


def _check(schema, value, path):
    if "$ref" in schema:
        schema = SCHEMAS[schema["$ref"]]
    kind = schema.get("type")
    if kind == "object" or "properties" in schema:
        if not isinstance(value, dict):
            raise SchemaError(f"{path}: object のはずが {type(value).__name__}")
        props = schema.get("properties", {})
        for key, v in value.items():
            if key not in props:
                raise SchemaError(f"{path}.{key}: スキーマに無い項目")
            if props[key].get("readOnly"):
                raise SchemaError(f"{path}.{key}: 読み取り専用の項目を書いている")
            _check(props[key], v, f"{path}.{key}")
    elif kind == "array":
        if not isinstance(value, list):
            raise SchemaError(f"{path}: array のはず")
        for i, v in enumerate(value):
            _check(schema["items"], v, f"{path}[{i}]")
    elif kind == "string":
        if not isinstance(value, str):
            raise SchemaError(f"{path}: string のはずが {value!r}")
        if "enum" in schema and value not in schema["enum"]:
            raise SchemaError(f"{path}: {value!r} は選べない値")
    elif kind == "number":
        if isinstance(value, bool) or not isinstance(value, (int, float)):
            raise SchemaError(f"{path}: number のはずが {value!r}")
    elif kind == "integer":
        if isinstance(value, bool) or not isinstance(value, int):
            raise SchemaError(f"{path}: integer のはずが {value!r}")
    elif kind == "boolean":
        if not isinstance(value, bool):
            raise SchemaError(f"{path}: boolean のはずが {value!r}")


# 各要求の fields（どの項目を書き換えるか）が指すスキーマ
_MASK_TARGET = {
    "updateShapeProperties": "ShapeProperties",
    "updateTextStyle": "TextStyle",
    "updateParagraphStyle": "ParagraphStyle",
    "updateLineProperties": "LineProperties",
    "updatePageProperties": "PageProperties",
}


def _check_mask(schema_name, mask):
    for field in mask.split(","):
        schema = SCHEMAS[schema_name]
        for part in field.split("."):
            props = schema.get("properties", {})
            if part not in props:
                raise SchemaError(f"fields の {field!r}: {part!r} が {schema_name} に無い")
            nxt = props[part]
            schema = SCHEMAS[nxt["$ref"]] if "$ref" in nxt else nxt


def check_requests(requests):
    _check({"$ref": "BatchUpdatePresentationRequest"}, {"requests": requests}, "body")
    for req in requests:
        (kind, body), = req.items()
        if kind in _MASK_TARGET:
            _check_mask(_MASK_TARGET[kind], body["fields"])


def _build(plan, weather=None):
    return SX.build_requests(plan, image_url=lambda n: f"https://example.run.app/static/img/{n}",
                             weather_days=weather, delete_slide="p_first")


# ----------------------------------------------------------------------
# 公式のスキーマ
# ----------------------------------------------------------------------
@pytest.mark.parametrize("name", list(T.SHAPES))
def test_requests_match_googles_published_schema(name):
    weather = [{"date": "2026-11-04", "emoji": "☔", "tmax": 14.4, "tmin": 8.6}]
    body, images = _build(T.SHAPES[name], weather)
    check_requests(body)
    check_requests(images)


def test_create_body_matches_the_presentation_schema():
    _check({"$ref": "Presentation"}, {"title": "旅のしおり — 金沢"}, "create")


def test_schema_copy_still_knows_the_pill_shape():
    """写しが古くなって、使っている図形名が消えていないか（消えたら作り直すこと）。"""
    shapes = SCHEMAS["Shape"]["properties"]["shapeType"]["enum"]
    for name in ("FLOW_CHART_TERMINATOR", "WEDGE_ROUND_RECTANGLE_CALLOUT", "ROUND_RECTANGLE",
                 "ELLIPSE", "TEXT_BOX", "RECTANGLE"):
        assert name in shapes, name
    assert "FLOWCHART_TERMINATOR" not in shapes


def test_the_checker_itself_catches_mistakes():
    """検査が素通りしないこと（わざと間違えた要求は落ちる）。"""
    bad_shape = [{"createShape": {"objectId": "tm_x_001", "shapeType": "FLOWCHART_TERMINATOR",
                                  "elementProperties": {"pageObjectId": "p"}}}]
    with pytest.raises(SchemaError, match="選べない値"):
        check_requests(bad_shape)
    bad_field = [{"updateTextStyle": {"objectId": "tm_x_001", "textRange": {"type": "ALL"},
                                      "style": {"bold": True}, "fields": "bold,colour"}}]
    with pytest.raises(SchemaError, match="colour"):
        check_requests(bad_field)
    unknown = [{"insertText": {"objectId": "tm_x_001", "text": "あ", "index": 0}}]
    with pytest.raises(SchemaError, match="スキーマに無い"):
        check_requests(unknown)


# ----------------------------------------------------------------------
# 変なプランを大量に流す
# ----------------------------------------------------------------------
_WORDS = ["兼六園", "エッフェル塔（Tour Eiffel）", "🍣寿司", "カフェ", "ホテル", "近江町市場 いきいき亭",
          "a" * 60, "とても" * 30, "Café de Flore", "ー", "", "  ", "😀👨‍👩‍👧‍👦🇯🇵", "\t", "改行\nあり",
          "制御\x0b文字", "​見えない", "<b>タグ</b>", "&amp;", "''\"\"", "1",
          "ルーヴル美術館（Musée du Louvre）", "https://example.com/very/long/path/without/spaces"]
_TIMES = ["09:00", "9:00", "０９：００", "09:00〜11:00", "9:00-10:30", "24:00", "", "10時", "AM 9:00"]
_HEADS = ["{n}日目", "【{n}日目】", "[{n}日目]", "{n}日目：金沢", "{n}日目 09:00 出発", "Day {n}", "第{n}日"]


def _word(r):
    return r.choice(_WORDS)


def _some(r, n):
    return [r.choice([_word(r), None, 123, _word(r) + _word(r)]) for _ in range(r.randint(0, n))]


def _schedule(r):
    out = ["※" + _word(r)] if r.random() < 0.2 else []
    for d in range(1, r.randint(0, 8) + 1):
        if r.random() < 0.9:
            out.append(r.choice(_HEADS).format(n=d if r.random() < 0.9 else r.randint(1, 20)))
        for _ in range(r.randint(0, 16)):
            out.append(f"{r.choice(_TIMES)} {_word(r)}"
                       f"{r.choice(['で昼食', 'にチェックイン', '発', 'へ移動', '', '（約1時間）'])}")
    if r.random() < 0.1:
        out.append(None)
    return out


def _odd_plan(r):
    fields = [
        ("travel_date", lambda: r.choice(["2026年11月3日", "2026/2/29", "来週", "", "2026年13月40日", None])),
        ("duration", lambda: r.choice(["日帰り", "1泊2日", "13泊14日", "0泊2日", "", None, "未定"])),
        ("num_people", lambda: r.choice([1, 2, 30, 0, None, "2", "二人"])),
        ("departure_location", lambda: _word(r)),
        ("total_per_person", lambda: r.choice([68000, 0, None, "68000", "6万8千円", -5, 10 ** 9, 12.5])),
        ("budget_limit", lambda: r.choice([80000, 0, None, "80,000", 1])),
        ("themes", lambda: _some(r, 5)), ("spots", lambda: _some(r, 9)),
        ("restaurants", lambda: _some(r, 7)), ("accommodation", lambda: _some(r, 3)),
        ("schedule", lambda: _schedule(r)),
        ("budget_estimate", lambda: ["■ " + _word(r)] + _some(r, 30)),
        ("packing_list", lambda: _some(r, 30)),
        ("feedback", lambda: r.choice(["", None, _word(r) * r.randint(1, 40)])),
    ]
    plan = {"destination": _word(r) or "金沢"} if r.random() < 0.95 else {}
    for key, make in fields:
        if r.random() < 0.85:
            plan[key] = make()
    return plan


@pytest.mark.parametrize("chunk", range(4))
def test_odd_plans_never_break_the_slides(chunk):
    for seed in range(chunk * 100, chunk * 100 + 100):
        r = random.Random(seed)
        plan = _odd_plan(r)
        weather = ([{"date": "2026-11-03", "emoji": "☀️", "tmax": r.choice([18, None, 18.6]), "tmin": 9}]
                   if r.random() < 0.5 else None)
        try:
            body, images = _build(plan, weather)
            check_requests(body)
            check_requests(images)
            T._validate(body, images, delete="p_first")
        except Exception as e:
            raise AssertionError(f"seed={seed}: {e}") from e
        shown = " ".join(q["insertText"]["text"] for q in body if "insertText" in q)
        assert "None" not in shown, f"seed={seed}: 「None」が画面に出ている"
        assert not any(ord(c) < 32 and c != "\n" for c in shown), f"seed={seed}: 制御文字が残っている"


# ----------------------------------------------------------------------
# 部品
# ----------------------------------------------------------------------
def test_numbers_written_as_text_are_read_or_skipped():
    assert SX._num(68000) == 68000 and SX._num(12.9) == 12
    assert SX._num("80,000") == 80000 and SX._num("８００００円") == 80000 and SX._num("2人") == 2
    for bad in (None, True, 0, -5, "6万8千円", "二人", "", "abc"):
        assert SX._num(bad) is None, bad


def test_clean_drops_control_characters_and_breaks_long_runs():
    assert SX._clean("制御\x0b文字\x00") == "制御文字"
    assert SX._clean("改行\nあり") == "改行\nあり" and SX._clean("改行\nあり", one_line=True) == "改行 あり"
    family = "👨‍👩‍👧‍👦"
    assert SX._clean(family) == family, "絵文字をつなぐ文字まで落としている"
    long = SX._clean("a" * 60)
    assert long.replace("​", "") == "a" * 60 and "​" in long
    assert SX._clean(long) == long, "2回通すと印が増える"
    assert SX._clean("エッフェル塔（Tour Eiffel）") == "エッフェル塔（Tour Eiffel）"


def test_items_skip_empty_values():
    assert SX._items(["兼六園", None, "", "  ", 123, {"x": 1}, "改行\nあり"]) == ["兼六園", "123", "改行 あり"]
    assert SX._items("兼六園") == [] and SX._items(None) == []


def test_wrap_estimate_moves_whole_words_to_the_next_line():
    """英単語は途中で切れない。入らなければ丸ごと次の行へ（空きができる）。"""
    words = " ".join(["Bouillon"] * 6)   # 1語 4.4字ぶん
    per_line = 10.0
    assert SX._wrap_lines(words, per_line) == 3, "2語ずつしか入らない"
    assert SX._wrap_lines("あ" * 25, per_line) == 3
    assert SX._width("👨‍👩‍👧‍👦") == 1


def test_feedback_with_many_line_breaks_fits_the_bubble():
    plan = T._plan(feedback="\n".join(["ひとこと"] * 40))
    body, _ = SX.build_requests(plan)
    T._validate(body)
    note = next(q["insertText"]["text"] for q in body
                if "insertText" in q and q["insertText"]["text"].startswith("ひとこと"))
    assert note.endswith("…") and note.count("\n") < 10
