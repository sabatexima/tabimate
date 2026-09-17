"""チャット画面の JS とテンプレートが噛み合っているかを見る。

ここが外れると、画面は表示されるのに操作だけが効かなくなる。エラーも出ないので
気づきにくい（実際「こんな旅はどう？」のチップは、名前の衝突でスクリプトごと
読み込まれておらず、押しても無反応のままだった）。

実行: pytest tests/test_static_js.py
"""
import re
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parent.parent
HOME_JS = ROOT / "src" / "static" / "js" / "home.js"
HOME_HTML = ROOT / "src" / "templates" / "home.html"


def _inline_scripts(html: str) -> list[str]:
    """テンプレートに直接書かれた <script> の中身（src= のものは除く）。"""
    return [
        m.group(1)
        for m in re.finditer(r"<script(?![^>]*\bsrc=)[^>]*>(.*?)</script>", html, re.S)
    ]


def _top_level_declarations(js: str) -> set[str]:
    """スクリプト直下（インデント無し、または2スペース）の const / let の名前。

    home.js は関数で囲っていないので、これらはページ全体で共有される。
    """
    return {
        m.group(2)
        for m in re.finditer(r"^ {0,2}(const|let)\s+([A-Za-z_$][\w$]*)\s*=", js, re.M)
    }


def test_home_js_element_ids_exist_in_template():
    """home.js が探す id が、テンプレートに実在すること。

    getElementById が null を返すと、その先で例外になって以降の処理が全部止まる。
    """
    js = HOME_JS.read_text()
    html = HOME_HTML.read_text()

    wanted = set(re.findall(r"getElementById\(['\"]([\w-]+)['\"]\)", js))
    assert wanted, "id の抽出に失敗している（抽出そのものが壊れている可能性）"

    missing = sorted(i for i in wanted if f'id="{i}"' not in html)
    assert not missing, f"home.js が探しているのに home.html に無い id: {missing}"


def test_inline_scripts_do_not_shadow_home_js_names():
    """テンプレート内のスクリプトが、home.js と同じ名前を宣言していないこと。

    home.js の `const chatBox` と、後続スクリプトの `var chatBox` は衝突し、
    後続スクリプト**全体**が SyntaxError で実行されなくなる（構文検査は通る）。
    これで「こんな旅はどう？」のチップが無反応になっていた。
    """
    declared = _top_level_declarations(HOME_JS.read_text())
    assert "chatBox" in declared, "home.js の宣言を読み取れていない（抽出が壊れている）"

    clashes = []
    for script in _inline_scripts(HOME_HTML.read_text()):
        for name in re.findall(r"\b(?:var|let|const)\s+([A-Za-z_$][\w$]*)", script):
            if name in declared:
                clashes.append(name)

    assert not clashes, (
        f"home.js と同じ名前をテンプレート側で宣言している: {sorted(set(clashes))}。"
        "スクリプト全体が動かなくなるので、名前を変えるか home.js へ移すこと"
    )


# ----------------------------------------------------------------------
# plan-map.js: 複数日のプランで、ピンがどの日に出てくるか
# ----------------------------------------------------------------------
PLAN_MAP_JS = ROOT / "src" / "static" / "js" / "plan-map.js"


def _run_plan_map_days(points: list[dict], schedule: list[str]) -> dict | None:
    """plan-map.js を node で読み込み、daysByItinerary の答えを JSON で受け取る。

    ファイルは読み込み時に document と L（Leaflet）を触るので、そこだけ空の
    代わりを置く。地図の描画までは動かさない（それは実機の仕事）。
    """
    import json
    import subprocess

    harness = """
      const fs = require('fs');
      global.window = global;
      global.document = { querySelector: () => null };
      global.L = {};
      global.localStorage = { getItem: () => null, setItem: () => {} };
      global.sessionStorage = global.localStorage;
      require('vm').runInThisContext(fs.readFileSync(process.argv[1], 'utf8'));
      const input = JSON.parse(process.argv[2]);
      const r = window.planMapDays(input.points, input.schedule);
      process.stdout.write(JSON.stringify(r === null ? null : {
        days: r.days,
        daysOf: input.points.map(p => [...r.daysOf.get(p)].sort()),
      }));
    """
    out = subprocess.run(
        ["node", "-e", harness, str(PLAN_MAP_JS),
         json.dumps({"points": points, "schedule": schedule}, ensure_ascii=False)],
        capture_output=True, text=True, check=True,
    )
    return json.loads(out.stdout)


def test_plan_map_assigns_pins_to_days():
    """宿は両日に、観光はその日にだけ、見つからないものはどの日にも属さないこと。"""
    points = [{"name": "熱海城"}, {"name": "ホテル熱海"}, {"name": "起雲閣"}, {"name": "謎の場所"}]
    r = _run_plan_map_days(points, [
        "1日目", "10:00 熱海城", "17:00 ホテル熱海にチェックイン",
        "【2日目】", "09:00 ホテル熱海を出発", "10:00 起雲閣",
    ])
    assert r["days"] == [1, 2]
    assert r["daysOf"] == [[1], [1, 2], [2], []]


def test_plan_map_has_no_day_filter_for_single_day_plans():
    """見出しが無い、またはピンのある日が1日だけなら、切り替えは出さない（null）。"""
    assert _run_plan_map_days([{"name": "熱海城"}], ["09:00 熱海城", "12:00 昼食"]) is None
    assert _run_plan_map_days([{"name": "熱海城"}],
                              ["1日目", "10:00 熱海城", "2日目", "終日フリー"]) is None
    assert _run_plan_map_days([], ["1日目", "2日目"]) is None


def test_plan_map_needs_most_pins_dated_before_offering_the_filter():
    """照合できたピンが半分に満たなければ、切り替えを出さないこと。

    日を選ぶと日の付かないピンは消える。照合が弱いまま切り替えを出すと、
    押した瞬間に地図から店が消えて壊れて見える。
    """
    dated = ["1日目", "10:00 熱海城", "2日目", "10:00 起雲閣"]
    # 4件中2件（ちょうど半分）は出す
    r = _run_plan_map_days(
        [{"name": "熱海城"}, {"name": "起雲閣"}, {"name": "謎の店A"}, {"name": "謎の店B"}], dated)
    assert r is not None and r["days"] == [1, 2]
    # 5件中2件（半分未満）は出さない
    assert _run_plan_map_days(
        [{"name": "熱海城"}, {"name": "起雲閣"},
         {"name": "謎の店A"}, {"name": "謎の店B"}, {"name": "謎の店C"}], dated) is None


def test_plan_map_day_headers_match_the_agent_rule():
    """全角数字・角括弧・「N日目：地名」も見出しとして扱うこと（agents.py の _days_in と同じ）。"""
    points = [{"name": "熱海城"}, {"name": "起雲閣"}]
    r = _run_plan_map_days(points, ["１日目：熱海へ", "10:00 熱海城", "[2日目] 帰路", "10:00 起雲閣"])
    assert r["days"] == [1, 2] and r["daysOf"] == [[1], [2]]


# ----------------------------------------------------------------------
# 金額の入力欄（旅の会計）
# ----------------------------------------------------------------------
def test_amount_field_is_not_a_spinner():
    """金額に数値スピナー（上下の矢印）を付けないこと。

    1円刻みの矢印は数千円〜数万円の入力に使い道が無いうえ、type="number" は
    フィールドの上でページをスクロールすると値が勝手に変わる。しおりは縦に
    長いので、記録した金額が知らないうちにずれる経路になっていた。

    代わりに inputmode="numeric" を残し、スマホの数字キーパッドは保つ。
    """
    js = (ROOT / "src" / "static" / "js" / "plan-detail.js").read_text(encoding="utf-8")
    field = re.search(r'<input[^>]*class="account-input"[^>]*>', js, re.S)
    assert field, "会計の入力欄が見つからない"
    markup = field.group(0)
    assert 'type="number"' not in markup, "数値スピナーが戻っている"
    assert 'type="text"' in markup
    assert 'inputmode="numeric"' in markup, "スマホの数字キーパッドが外れている"


def test_amount_field_validates_before_sending():
    """type="number" をやめたぶん、数字かどうかを送信前に見ていること。

    ブラウザ任せの入力制限が無くなるので、ここが抜けると NaN が
    サーバーへ飛ぶ（JSON では null になり、記録が黙って消える）。
    """
    js = (ROOT / "src" / "static" / "js" / "plan-detail.js").read_text(encoding="utf-8")
    submit = re.search(r"const submit = \(\) => \{(.*?)\n    \};", js, re.S)
    assert submit, "会計の送信処理が見つからない"
    body = submit.group(1)
    assert re.search(r"\\d\+?\$?/\.test\(|\^\\\\d\+\$", body) or r"/^\d+$/" in body, \
        "数字かどうかの判定が無い"
    assert "parseInt" in body


# ----------------------------------------------------------------------
# 地図の拡大率（タイルが無い段まで寄らないこと）
# ----------------------------------------------------------------------
MAP_JS = [ROOT / "src" / "static" / "js" / "plan-map.js",
          ROOT / "src" / "static" / "js" / "footprint-map.js"]


def _calls_of(name: str, js: str) -> list[str]:
    """`name(...)` の呼び出しを、括弧を数えて丸ごと取り出す。

    正規表現だと fitBounds(L.latLngBounds(xs.map(p => [a, b])).pad(0.2), …) のような
    入れ子を拾いきれず、1件も見つからないのに素通りしてしまう（実際そうなった）。
    """
    out = []
    for m in re.finditer(re.escape(name) + r"\(", js):
        depth, i = 0, m.end() - 1
        while i < len(js):
            if js[i] == "(":
                depth += 1
            elif js[i] == ")":
                depth -= 1
                if depth == 0:
                    out.append(js[m.start():i + 1])
                    break
            i += 1
    return out


@pytest.mark.parametrize("path", MAP_JS, ids=lambda p: p.name)
def test_tile_layer_declares_the_sources_real_zoom_limit(path):
    """配信元が実際に持っている拡大段（maxNativeZoom）を Leaflet に伝えること。

    水彩（Stamen Watercolor）は手描きで、通常の地図ほど深い段を持たない。
    これを伝えないと、深く拡大したとき無い段のタイルを取りに行って404になり、
    ピンと線だけが浮いた灰色の地図になる。伝えてあれば Leaflet が
    手前の段を引き伸ばして使う。

    実測: 伝えたとき z16 まで／外すと z17・z18 まで取りに行っていた。
    """
    js = path.read_text(encoding="utf-8")
    assert "maxNativeZoom" in js, "配信元の上限を伝えていない"
    assert re.search(r"maxNativeZoom:\s*STADIA_KEY\s*\?", js), \
        "水彩と通常タイルで上限を出し分けていない"
    assert not re.search(r"L\.tileLayer\([^)]*maxZoom:\s*\d+\s*\}", js), \
        "タイル層の設定が直書きのまま（tileOptions を通していない）"


@pytest.mark.parametrize("path", MAP_JS, ids=lambda p: p.name)
def test_fit_bounds_never_zooms_past_the_tiles(path):
    """ピンが密集していても、タイルのある段より深く寄せないこと。

    fitBounds は収まるまで寄せるので、1つの街の中だけを回るプランだと
    上限を付けないまま一気に深い段へ飛ぶ。
    """
    js = path.read_text(encoding="utf-8")
    calls = _calls_of("fitBounds", js)
    assert calls, "fitBounds が見つからない"
    for call in calls:
        assert "maxZoom" in call, f"上限の無い fitBounds がある: {call[:90]}"
