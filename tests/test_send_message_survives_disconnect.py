"""生成がクライアントの接続に左右されないことを見る。

もともとは AI の返事を保存しているのが SSE の送信側（generate）だった。生成中に
リロードすると接続が切れ、その generator は次の yield で止まる。すると:

  1. save_chat_message に到達しない → AIの返事は保存されない（生成が捨てられる）
  2. finally の active_requests.discard だけ走る → サーバーは「生成していない」と答える

つまりリロードした瞬間に、サーバー自身がその生成を無かったことにしていた。
「時間が経ったら出た／出なかった」がその時々で変わったのは、切断の検知が
すぐ起きるとは限らないため。

保存を別スレッド側へ移したので、誰も見ていなくても結果は残る。ここが崩れると
「送ってリロードしたらプランが消える」に戻るので、必ず押さえておく。

実行: pytest tests/test_send_message_survives_disconnect.py
"""
import os
import sys
import time

import pytest

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "src"))
os.environ.setdefault("SECRET_KEY", "test-secret")
os.environ.setdefault("GOOGLE_API_KEY", "dummy")
os.environ.setdefault("TAVILY_API_KEY", "dummy")

USER = "u-1"
RID = "r-1"


@pytest.fixture
def env(monkeypatch):
    """AIとDBを差し替えたテストクライアントと、記録用の箱を返す。"""
    import app as app_mod
    import db
    import views.planner as P

    log = {"saved": [], "deleted": []}

    monkeypatch.setattr(db, "save_chat_message",
                        lambda uid, role, content, rid=None, plan_json=None:
                        log["saved"].append((role, content, rid)))
    monkeypatch.setattr(db, "delete_chat_messages_by_request",
                        lambda uid, rid: log["deleted"].append(rid))
    monkeypatch.setattr(db, "get_chat_messages", lambda uid: [])
    monkeypatch.setattr(P, "_is_rate_limited", lambda uid: False)
    monkeypatch.setattr(P, "active_requests", set())

    app_mod.app.config["TESTING"] = True
    with app_mod.app.test_client() as c:
        with c.session_transaction() as s:
            s["user_id"] = USER
            s["user_email"] = "u@example.com"
        yield c, log, P


def _wait(cond, timeout=5.0):
    """別スレッドの仕事が終わるのを待つ。"""
    limit = time.time() + timeout
    while time.time() < limit:
        if cond():
            return True
        time.sleep(0.02)
    return False


def _slow_ai(release):
    """release['go'] が立つまで返らないAI（＝まだ作っている最中を作る）。"""
    def slow(*args, **kwargs):
        while not release["go"]:
            time.sleep(0.01)
        return ("できました", {"destination": "静岡"})
    return slow


def _send_then_disconnect(client):
    """送信して、本文を読まずに接続を切る（リロードと同じ状況）。

    buffered=False が要る。既定ではテストクライアントが本文を読み切ってしまい、
    切断を再現できない。
    それでも冒頭のイベントは少しだけ読まれるので、AIを遅くしておくのも必須。
    即答するAIだと、その1回の読み取りで保存まで到達してしまい、壊れたコードでも
    通ってしまう（実際それで取り逃がした）。
    """
    res = client.post("/send_message", buffered=False,
                      data={"message": "車", "request_id": RID})
    assert res.status_code == 200
    res.close()
    return res


def _ai_saved(log):
    return [x for x in log["saved"] if x[0] == "ai"]


def test_reply_survives_a_disconnect_during_generation(env, monkeypatch):
    """生成中に切断されても、AIの返事が保存されること。ここが元の不具合の核。"""
    client, log, P = env
    release = {"go": False}
    monkeypatch.setattr(P, "_ai_chat", _slow_ai(release))

    _send_then_disconnect(client)
    release["go"] = True  # 切れたあとにAIが完成する

    assert _wait(lambda: _ai_saved(log)), \
        "誰も見ていないと返事が保存されない（生成が捨てられている）"
    assert ("ai", "できました", RID) in log["saved"]
    assert log["deleted"] == [], "成功した回を捨ててはいけない"


def test_the_server_admits_it_is_still_generating(env, monkeypatch):
    """切断されても、作っている最中は「生成中」と答えること。

    ここが外れると、リロードした人に「終わりませんでした」と出てしまう。
    """
    client, log, P = env
    release = {"go": False}
    monkeypatch.setattr(P, "_ai_chat", _slow_ai(release))

    _send_then_disconnect(client)
    try:
        assert RID in P.active_requests, "作っている最中なのに生成中でないと答える"
        assert not _ai_saved(log), "まだ保存されては困る"
    finally:
        release["go"] = True
    assert _wait(lambda: RID not in P.active_requests), "終わったのに生成中のまま"


def test_aborted_generation_is_cleaned_up(env, monkeypatch):
    """停止ボタンで中断された回は、そのやりとりを残さないこと。"""
    client, log, P = env

    def aborting(*args, **kwargs):
        P.active_requests.discard(RID)  # 停止ボタンが押された状況
        return (None, None)

    monkeypatch.setattr(P, "_ai_chat", aborting)
    _send_then_disconnect(client)

    assert _wait(lambda: log["deleted"] == [RID]), "中断した回が消えていない"
    assert not _ai_saved(log), "中断なのに保存している"


def test_failed_generation_is_cleaned_up(env, monkeypatch):
    """途中で落ちた回も、そのやりとりを残さないこと。"""
    client, log, P = env

    def boom(*args, **kwargs):
        raise RuntimeError("AIが落ちた")

    monkeypatch.setattr(P, "_ai_chat", boom)
    _send_then_disconnect(client)

    assert _wait(lambda: log["deleted"] == [RID]), "失敗した回が消えていない"
    assert not _ai_saved(log)
    assert _wait(lambda: RID not in P.active_requests), "失敗したのに生成中のまま"


def test_stream_reports_the_outcome(env, monkeypatch):
    """本文を読んだときは、これまでどおり結果が流れてくること。"""
    client, log, P = env
    monkeypatch.setattr(P, "_ai_chat", lambda *a, **k: ("できました", None))

    body = client.post("/send_message",
                       data={"message": "車", "request_id": RID}).get_data(as_text=True)
    assert '"status": "OK"' in body or '"status":"OK"' in body, body
    assert RID in body
    assert _ai_saved(log), "読んだ場合も保存されること"


def test_thinking_is_sent_while_waiting(env, monkeypatch):
    """生成中は thinking が流れること（画面の「考えています」の元）。"""
    client, log, P = env
    release = {"go": False}
    monkeypatch.setattr(P, "_ai_chat", _slow_ai(release))

    res = client.post("/send_message", buffered=False,
                      data={"message": "車", "request_id": RID})
    try:
        first = next(res.response)
        assert b"thinking" in first, first
    finally:
        release["go"] = True
        res.close()


def test_abort_that_lands_just_before_the_save_is_honoured(env, monkeypatch):
    """保存の直前に停止が届いても、返事が残らないこと。

    AIが完成してから保存するまでの隙間に /abort_request が入ると、abort 側は
    まだ存在しない返事を消しに行くので、そのあと保存した行が取り残される。
    中断したのに返事だけ現れる、という分かりにくい壊れ方になる。
    """
    import db

    client, log, P = env
    monkeypatch.setattr(P, "_ai_chat", lambda *a, **k: ("できました", None))

    real_save = db.save_chat_message

    def save_then_abort(uid, role, content, rid=None, plan_json=None):
        real_save(uid, role, content, rid, plan_json)
        if role == "ai":
            P.active_requests.discard(RID)  # ちょうどこの隙間に停止が届いた

    monkeypatch.setattr(db, "save_chat_message", save_then_abort)
    _send_then_disconnect(client)

    assert _wait(lambda: log["deleted"] == [RID]), "取り残した返事を片づけていない"
