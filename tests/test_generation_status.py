"""リロード後に「生成中かどうか」を正しく答えられるかを見る。

ここが外れると、まだプランを作っている最中なのに「終わりませんでした」と
案内が出たり、逆にいつまでも「考えています」のままになったりする。

判断をプロセス内のメモリ（active_requests）だけに頼っていたのが元の作りだが、
Cloud Run は最大3インスタンスで動くので、リロードが別のインスタンスに当たると
「知らない＝終わった」と答えてしまう。DBの行から決めれば、どのインスタンスから
見ても同じ答えになる。

実行: pytest tests/test_generation_status.py
"""
import json
import os
import sys

import pytest

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "src"))
os.environ.setdefault("SECRET_KEY", "test-secret")
os.environ.setdefault("GOOGLE_API_KEY", "dummy")
os.environ.setdefault("TAVILY_API_KEY", "dummy")

USER = "u-1"


@pytest.fixture
def client(monkeypatch):
    """DBを差し替えたテストクライアント。state はテスト側で決める。"""
    import app as app_mod
    import db
    import views.planner as P

    app_mod.app.config["TESTING"] = True
    monkeypatch.setattr(db, "chat_request_state", lambda uid, rid: db._fake_state)
    # このインスタンスは「何も知らない」状態にする（＝別インスタンスが動かしている）
    monkeypatch.setattr(P, "active_requests", set())

    with app_mod.app.test_client() as c:
        with c.session_transaction() as s:
            s["user_id"] = USER
            s["user_email"] = "u@example.com"
        yield c, db


def _ask(client, rid="r1"):
    res = client.get(f"/generation_status?request_id={rid}")
    assert res.status_code == 200
    return json.loads(res.data)


def test_pending_is_reported_even_when_this_instance_does_not_know(client):
    """別のインスタンスが動かしている生成を「終わった」と答えないこと。

    これが元の不具合。active_requests に無いだけで完了扱いにしていた。
    """
    c, db = client
    db._fake_state = "pending"
    body = _ask(c)
    assert body["state"] == "pending"
    assert body["active"] is False, "このインスタンスは知らないという前提のテスト"


def test_done_when_the_reply_is_saved(client):
    c, db = client
    db._fake_state = "done"
    assert _ask(c)["state"] == "done"


def test_gone_when_the_rows_were_cleaned_up(client):
    """失敗・中断すると、その回の行はまとめて消える。"""
    c, db = client
    db._fake_state = "gone"
    assert _ask(c)["state"] == "gone"


def test_requires_login():
    """未ログインでは答えないこと。"""
    import app as app_mod

    with app_mod.app.test_client() as c:
        res = c.get("/generation_status?request_id=r1",
                    headers={"Accept": "application/json"})
    assert res.status_code == 401


# ---------------------------------------------------------------------------
# 行から状態を決める部分そのもの
# ---------------------------------------------------------------------------

class _FakeConn:
    def __init__(self, rows):
        self._rows = rows

    def execute(self, *args, **kwargs):
        self._last = args
        return self

    def fetchall(self):
        return self._rows

    def __enter__(self):
        return self

    def __exit__(self, *exc):
        return False


@pytest.mark.parametrize("rows,expected", [
    ([("user", 0), ("ai", 0)], "done"),     # 返答が保存された
    ([("user", 0)],            "pending"),  # まだ作っている最中
    ([("user", 3)],            "pending"),  # 3分経過。生成は数分かかることがある
    ([],                       "gone"),     # 失敗か中断で消えている
    ([("ai", 0)],              "done"),     # 返答だけ残っている場合も完了扱い
    # ワーカーが落ちるとユーザーの発言だけが残り続ける。いつまでも
    # 「考えています」を出さないよう、古すぎるものは諦める
    ([("user", 20)],           "gone"),
    ([("user", 999)],          "gone"),
    ([("user", None)],         "pending"),  # 経過時間が取れなくても止めない
])
def test_state_is_decided_by_the_rows(monkeypatch, rows, expected):
    import db

    monkeypatch.setattr(db, "_get_engine", lambda: type(
        "E", (), {"connect": staticmethod(lambda: _FakeConn(rows))})())
    assert db.chat_request_state(USER, "r1") == expected


def test_empty_request_id_is_gone():
    """request_id が無いときはDBを見に行かないこと。"""
    import db

    assert db.chat_request_state(USER, "") == "gone"


# ---------------------------------------------------------------------------
# ページに「まだ返事待ちの生成」を載せて返す部分
# ---------------------------------------------------------------------------

@pytest.fixture
def page(monkeypatch):
    """チャット画面を開けるテストクライアント。履歴と状態はテスト側で決める。"""
    import app as app_mod
    import db
    import views.planner as P

    app_mod.app.config["TESTING"] = True
    box = {"messages": [], "state": "gone"}
    monkeypatch.setattr(db, "get_chat_messages", lambda uid: box["messages"])
    monkeypatch.setattr(db, "chat_request_state", lambda uid, rid: box["state"])
    monkeypatch.setattr(P, "active_requests", set())

    with app_mod.app.test_client() as c:
        with c.session_transaction() as s:
            s["user_id"] = USER
            s["user_email"] = "u@example.com"
        yield c, box


def _chat_html(client):
    res = client.get("/chat")
    assert res.status_code == 200
    return res.get_data(as_text=True)


def test_page_carries_the_pending_generation(page):
    """返事待ちなら、その情報がページに載っていること。

    これがあるので、画面側は端末に控えを持たなくてよい。
    """
    c, box = page
    box["messages"] = [{"role": "user", "content": "車", "request_id": "r9"}]
    box["state"] = "pending"

    html = _chat_html(c)
    assert 'data-pending-request="r9"' in html
    assert 'data-pending-message="車"' in html


def test_page_is_quiet_when_the_reply_is_already_there(page):
    """返事が保存済みなら、何も載せないこと（勝手に考えていますを出さない）。"""
    c, box = page
    box["messages"] = [
        {"role": "user", "content": "車", "request_id": "r9"},
        {"role": "ai", "content": "できました", "request_id": "r9"},
    ]
    box["state"] = "done"

    assert "data-pending-request" not in _chat_html(c)


def test_page_is_quiet_when_the_generation_was_lost(page):
    """失敗・中断した回は載せないこと。"""
    c, box = page
    box["messages"] = [{"role": "user", "content": "車", "request_id": "r9"}]
    box["state"] = "gone"

    assert "data-pending-request" not in _chat_html(c)


def test_page_is_quiet_with_no_history(page):
    c, box = page
    box["messages"] = []
    assert "data-pending-request" not in _chat_html(c)


def test_quotes_in_the_message_cannot_break_the_attribute(page):
    """引用符を含む文でも、属性が壊れないこと（テンプレートの自動エスケープ）。"""
    c, box = page
    box["messages"] = [{"role": "user", "content": '"><script>x</script>',
                        "request_id": "r9"}]
    box["state"] = "pending"

    html = _chat_html(c)
    assert "<script>x</script>" not in html, "そのまま埋め込まれている"
    assert 'data-pending-request="r9"' in html
