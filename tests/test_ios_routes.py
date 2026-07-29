"""iOSアプリが叩くURLが、サーバーに実在するかを突き合わせる。

型やJSONの形は他のテストで見ているが、「パスとメソッドが合っているか」は
どこでも見ていなかった。ここを1文字打ち間違えても、実行時に404や405になるまで
気づけない（しかもアプリ側は「うまくいきませんでした」としか言わない）。

Swift のソースから APIClient に渡しているパスを抜き出し、Flask のルーティングに
実際に当ててみる。
実行: pytest tests/test_ios_routes.py
"""
import os
import re
import sys
from pathlib import Path

import pytest

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "src"))
os.environ.setdefault("SECRET_KEY", "test-secret")
os.environ.setdefault("GOOGLE_API_KEY", "dummy")
os.environ.setdefault("TAVILY_API_KEY", "dummy")

IOS_DIR = Path(__file__).resolve().parent.parent / "ios" / "TabiMate"

def _swift_sources() -> str:
    return "\n".join(f.read_text() for f in sorted(IOS_DIR.rglob("*.swift")))


def _paths_returned_by(func_name: str) -> list[str]:
    """パスを組み立てて返す関数（editBase など）の中の文字列を、ソースから読む。

    ここをテスト側にベタ書きすると、実装が変わったときに気づけない
    （実際それで、共有側の入口の書き間違いを取り逃がした）。
    """
    src = _swift_sources()
    m = re.search(rf"func {func_name}\([^)]*\)\s*->\s*String\s*\{{(.*?)\n    \}}", src, re.S)
    if not m:
        return []
    return re.findall(r'"([^"]+)"', m.group(1))


def _enum_raw_values(enum_name: str) -> list[str]:
    """`enum X: String { case a; case b }` の値をソースから読む。"""
    src = _swift_sources()
    m = re.search(rf"enum {enum_name}: String \{{(.*?)\n    \}}", src, re.S)
    if not m:
        return []
    return [c for line in m.group(1).splitlines()
            for c in re.findall(r"^\s*case (\w+)", line)]


def expansions() -> dict[str, list[str]]:
    """Swift の文字列補間をどう具体化するか（すべてソースから取る）。"""
    return {
        # 自分の旅と共有された旅で入口が変わる
        "editBase(tripId: tripId, shared: shared)": _paths_returned_by("editBase"),
        # 共有できるリソースの種類
        "resource.rawValue": _enum_raw_values("Resource"),
    }

# APIClient への呼び出し。`APIClient.shared` の後で改行することがあるので
# 空白と改行をまたげるようにしておく（取りこぼすと素通ししてしまう）。
CALL = re.compile(
    r'APIClient\s*\.\s*(?:shared\s*\.\s*(get|post)|request)\s*\(\s*"([^"]+)"([^)]*)',
    re.S,
)


def _expand(path: str) -> list[str]:
    """`\\(...)` を含むパスを、実際にありうる形に展開する。"""
    results = [path]
    for token, values in expansions().items():
        marker = "\\(" + token + ")"
        if not any(marker in p for p in results):
            continue
        assert values, f"{token} の展開先をソースから読み取れませんでした"
        results = [p.replace(marker, v) for p in results for v in values]
    # 残った補間（ID など）は 1 に寄せる
    return [re.sub(r"\\\([^)]*\)", "1", p) for p in results]


def ios_requests() -> list[tuple[str, str, str]]:
    """(ソース, パス, メソッド) の一覧を Swift から集める。"""
    out = []
    for f in sorted(IOS_DIR.rglob("*.swift")):
        src = f.read_text()
        for m in CALL.finditer(src):
            verb, raw_path, rest = m.group(1), m.group(2), m.group(3)
            method = re.search(r'method:\s*"(\w+)"', rest)
            method = method.group(1) if method else (verb.upper() if verb else "GET")
            for path in _expand(raw_path):
                out.append((f.name, path, method))
    return out


@pytest.fixture(scope="module")
def matcher():
    import app as app_mod
    return app_mod.app.url_map.bind("localhost")


def test_extraction_found_every_service_file():
    """抽出そのものが壊れていないこと（0件なのに全部通った、を防ぐ）。"""
    reqs = ios_requests()
    assert len(reqs) >= 30, f"抜き出せたのが {len(reqs)} 件しかない。抽出が壊れている可能性"
    sources = {src for src, _, _ in reqs}
    for expected in ["PlanService.swift", "ChatService.swift",
                     "ReflectionService.swift", "ShareService.swift"]:
        assert expected in sources, f"{expected} から1件も抜き出せていない"


@pytest.mark.parametrize("source,path,method", ios_requests(),
                         ids=lambda v: v if isinstance(v, str) else str(v))
def test_ios_path_exists_on_server(matcher, source, path, method):
    """アプリが叩くパスが、そのメソッドでサーバーに存在すること。"""
    from werkzeug.exceptions import MethodNotAllowed, NotFound

    try:
        matcher.match("/" + path, method=method)
    except NotFound:
        pytest.fail(f"{source}: {method} /{path} に対応するルートがサーバーにありません")
    except MethodNotAllowed as e:
        pytest.fail(f"{source}: /{path} は存在しますが {method} を受け付けません"
                    f"（受け付けるのは {sorted(e.valid_methods or [])}）")


def test_login_required_paths_are_protected(matcher):
    """アプリが使うエンドポイントが、うっかり誰でも触れる状態になっていないこと。

    季節のアイデアとサインインだけは、ログイン前に使うので例外。
    """
    import app as app_mod

    open_paths = {"/api/ideas", "/auth/app/signin"}
    unprotected = []
    for _, path, method in ios_requests():
        full = "/" + path
        if full in open_paths:
            continue
        with app_mod.app.test_client() as c:
            res = c.open(full, method=method)
        # 未ログインなら 401（アプリ向け）が返るはず。
        # 403 は共有まわりの権限判定なので、これも保護されている
        if res.status_code not in (401, 403):
            unprotected.append((path, method, res.status_code))
    assert not unprotected, f"未ログインでも通ってしまうものがあります: {unprotected}"
