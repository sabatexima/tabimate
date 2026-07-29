"""チャット画面の JS とテンプレートが噛み合っているかを見る。

ここが外れると、画面は表示されるのに操作だけが効かなくなる。エラーも出ないので
気づきにくい（実際「こんな旅はどう？」のチップは、名前の衝突でスクリプトごと
読み込まれておらず、押しても無反応のままだった）。

実行: pytest tests/test_static_js.py
"""
import re
from pathlib import Path

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
