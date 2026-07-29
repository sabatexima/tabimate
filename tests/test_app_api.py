"""ネイティブアプリ向けAPIの単体テスト（APIキー・DB不要）。

DBアクセスはすべて差し替えて、views 層の判断（認可・整形・省略）だけを検証する。
実行: pytest tests/test_app_api.py
"""
import json
import os
import sys

import pytest

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "src"))
os.environ.setdefault("SECRET_KEY", "test-secret")
os.environ.setdefault("GOOGLE_API_KEY", "dummy")
os.environ.setdefault("TAVILY_API_KEY", "dummy")

import api_auth  # noqa: E402

OWNER = "u-owner"
FRIEND = "u-friend"
FRIEND_EMAIL = "friend@example.com"

TRIP = {
    "id": 1, "user_id": OWNER, "title": "熱海でのんびり",
    "start_date": "2026-08-14", "end_date": "2026-08-15",
    "is_favorite": 0, "photo_count": 4, "cover_path": "p/a.jpg",
    "stickers_preview": ["海がきれいだった"], "created_at": "2026-08-16 10:00:00",
    "linked_plan_id": 99, "best_shots": json.dumps([{"photo_id": 11, "reason": "光がきれい"}]),
}
PHOTOS = [
    {"id": 11, "trip_id": 1, "storage_path": "p/a.jpg",
     "taken_at": "2026-08-14 09:00:00", "lat": 35.09, "lng": 139.07},
    {"id": 12, "trip_id": 1, "storage_path": "p/b.jpg",
     "taken_at": None, "lat": None, "lng": None},
]


@pytest.fixture
def env(monkeypatch):
    """DBとストレージを差し替えたアプリと、呼び出し記録を返す。"""
    import app as app_mod
    import db
    import db_reflection as repo
    import db_sharing
    import views.reflection as R
    from services import storage

    flask_app = app_mod.app
    flask_app.config["TESTING"] = True
    flask_app.config["PROPAGATE_EXCEPTIONS"] = False
    flask_app.logger.disabled = True

    calls = {"geocode": 0, "plans_listed": 0}

    monkeypatch.setattr(repo, "get_trips", lambda uid: [dict(TRIP)] if uid == OWNER else [])
    monkeypatch.setattr(repo, "get_trip",
                        lambda tid, uid: dict(TRIP) if uid == OWNER and tid == TRIP["id"] else None)
    monkeypatch.setattr(repo, "get_trip_by_id", lambda tid: dict(TRIP))
    monkeypatch.setattr(repo, "get_trip_cards",
                        lambda ids, viewer_id=None: [dict(TRIP)] if TRIP["id"] in ids else [])
    monkeypatch.setattr(repo, "get_photos", lambda tid: [dict(p) for p in PHOTOS])
    monkeypatch.setattr(repo, "get_stickers",
                        lambda tid: [{"id": 5, "text": "波の音がずっと聞こえてた"}])
    monkeypatch.setattr(storage, "get_urls", lambda paths: {p: f"/reflection/photo/{p}" for p in paths})
    monkeypatch.setattr(storage, "get_thumb_urls",
                        lambda paths: {p: f"/reflection/photo/thumb/{p}" for p in paths})

    def _plans(uid):
        calls["plans_listed"] += 1
        return [{"id": 99, "destination": "熱海", "google_user_id": OWNER}]
    monkeypatch.setattr(db, "get_travel_plans", _plans)
    monkeypatch.setattr(db, "get_travel_plan_by_id",
                        lambda pid: {"id": pid, "google_user_id": OWNER, "spot_coords": []})

    import geocoding

    def _ensure(plan):
        calls["geocode"] += 1
    monkeypatch.setattr(geocoding, "ensure_plan_coords", _ensure)

    # 既定では誰にも共有していない。テストごとに上書きする
    monkeypatch.setattr(db_sharing, "get_grants_for_email", lambda email: [])
    monkeypatch.setattr(db_sharing, "get_grant_for_email", lambda rt, rid, email: None)

    return {"app": flask_app, "calls": calls, "sharing": db_sharing, "reflection": R}


def headers_for(user_id, email=""):
    """そのユーザーとしてアプリから叩くためのヘッダ。"""
    token = api_auth.issue_token(user_id, email, "テスト")
    return {"Authorization": f"Bearer {token}"}


def share_trip_with(env, permission="view"):
    """TRIP を FRIEND に共有した状態にする。"""
    env["sharing"].get_grants_for_email = lambda email: (
        [{"id": 7, "resource_type": "trip", "resource_id": TRIP["id"], "permission": permission}]
        if email == FRIEND_EMAIL else []
    )
    env["sharing"].get_grant_for_email = lambda rt, rid, email: (
        {"permission": permission}
        if rt == "trip" and rid == TRIP["id"] and email == FRIEND_EMAIL else None
    )


# ----------------------------------------------------------------------
# 認証（Bearer トークンの読み替え）
# ----------------------------------------------------------------------
def test_bearer_token_is_accepted_on_every_endpoint(env):
    """login_required を通らないエンドポイントでもトークンが効くこと。

    共有まわり（views/sharing.py）は session を直接見るため、
    before_request で読み替えていないとアプリから一切使えない。
    """
    share_trip_with(env, "edit")
    with env["app"].test_client() as c:
        # 写真を付けずに送っているので 400。認可を通過した証拠になる
        r = c.post(f"/shared/trip/{TRIP['id']}/photos", headers=headers_for(FRIEND, FRIEND_EMAIL))
    assert r.status_code == 400


def test_bearer_token_does_not_leave_a_session_cookie(env):
    """アプリの認証情報はトークンだけ。セッションCookieを持たせない。"""
    with env["app"].test_client() as c:
        r = c.get("/reflection/api/trips", headers=headers_for(OWNER))
    assert r.status_code == 200
    assert "Set-Cookie" not in r.headers


def test_expired_or_tampered_token_is_rejected(env):
    with env["app"].test_client() as c:
        r = c.get("/reflection/api/trips", headers={"Authorization": "Bearer garbage"})
    assert r.status_code == 401


# ----------------------------------------------------------------------
# 振り返り一覧・詳細
# ----------------------------------------------------------------------
def test_trips_returns_own_and_shared_separately(env):
    share_trip_with(env, "view")
    with env["app"].test_client() as c:
        body = c.get("/reflection/api/trips",
                     headers=headers_for(FRIEND, FRIEND_EMAIL)).get_json()
    assert body["trips"] == []                       # 自分の旅は無い
    assert len(body["shared_trips"]) == 1            # もらった旅だけ
    assert body["shared_trips"][0]["permission"] == "view"
    assert body["shared_trips"][0]["grant_id"] == 7


def test_trip_detail_includes_photo_count(env):
    """一覧→詳細で写真枚数が 0 に見えないこと（詳細の trip にも枚数を入れる）。"""
    with env["app"].test_client() as c:
        body = c.get(f"/reflection/api/trips/{TRIP['id']}",
                     headers=headers_for(OWNER)).get_json()
    assert body["trip"]["photo_count"] == len(PHOTOS)


def test_trip_detail_resolves_best_shot_and_footprints(env):
    with env["app"].test_client() as c:
        body = c.get(f"/reflection/api/trips/{TRIP['id']}",
                     headers=headers_for(OWNER)).get_json()
    # ベストショットは photo_id から表示URLに解決される
    assert body["best_shots"] == [{
        "url": "/reflection/photo/p/a.jpg",
        "thumb_url": "/reflection/photo/thumb/p/a.jpg",
        "reason": "光がきれい",
    }]
    # 足あとは位置情報のある写真だけ
    assert len(body["footprints"]) == 1
    assert body["footprints"][0]["lat"] == 35.09


def test_trip_detail_skips_plan_overlay_work(env):
    """アプリの画面に無い「プランとの重ね合わせ」の準備をしないこと。

    ここを省かないと、旅を開くたびにプラン一覧の取得と座標の取得（外部API）が走る。
    """
    with env["app"].test_client() as c:
        c.get(f"/reflection/api/trips/{TRIP['id']}", headers=headers_for(OWNER))
    assert env["calls"]["plans_listed"] == 0
    assert env["calls"]["geocode"] == 0


def test_html_trip_detail_still_prepares_plan_overlay(env):
    """一方、Web版の画面では今までどおり重ね合わせの材料を用意すること。"""
    with env["app"].test_client() as c:
        r = c.get(f"/reflection/trips/{TRIP['id']}",
                  headers={**headers_for(OWNER), "Accept": "text/html"})
    assert r.status_code == 200
    assert env["calls"]["plans_listed"] == 1
    assert env["calls"]["geocode"] == 1


# ----------------------------------------------------------------------
# 共有された旅の閲覧可否
# ----------------------------------------------------------------------
def test_shared_trip_can_be_opened_with_permission(env):
    """一覧に出す以上、開けなければならない。"""
    share_trip_with(env, "edit")
    with env["app"].test_client() as c:
        r = c.get(f"/reflection/api/trips/{TRIP['id']}",
                  headers=headers_for(FRIEND, FRIEND_EMAIL))
    assert r.status_code == 200
    # アプリが編集の可否を判断できるよう権限を添える
    assert r.get_json()["trip"]["permission"] == "edit"


def test_unrelated_user_cannot_open_trip(env):
    with env["app"].test_client() as c:
        r = c.get(f"/reflection/api/trips/{TRIP['id']}",
                  headers=headers_for("u-stranger", "stranger@example.com"))
    assert r.status_code == 404


def test_unrelated_user_cannot_edit_shared_trip(env):
    with env["app"].test_client() as c:
        r = c.post(f"/shared/trip/{TRIP['id']}/photos",
                   headers=headers_for("u-stranger", "stranger@example.com"))
    assert r.status_code == 403


def test_view_only_grantee_cannot_edit(env):
    """閲覧だけの相手は写真を足せない。"""
    share_trip_with(env, "view")
    with env["app"].test_client() as c:
        r = c.post(f"/shared/trip/{TRIP['id']}/photos",
                   headers=headers_for(FRIEND, FRIEND_EMAIL))
    assert r.status_code == 403


# ----------------------------------------------------------------------
# 年間ダイジェスト
# ----------------------------------------------------------------------
def test_digest_defaults_to_latest_year_and_totals_photos(env):
    with env["app"].test_client() as c:
        body = c.get("/reflection/api/digest", headers=headers_for(OWNER)).get_json()
    assert body["year"] == "2026"
    assert body["years"] == ["2026"]
    assert body["photo_total"] == TRIP["photo_count"]
    assert body["stickers"] == TRIP["stickers_preview"]


def test_digest_unknown_year_falls_back(env):
    """持っていない年を指定されても落ちず、ある年を返す。"""
    with env["app"].test_client() as c:
        body = c.get("/reflection/api/digest?year=1999",
                     headers=headers_for(OWNER)).get_json()
    assert body["year"] == "2026"


# ----------------------------------------------------------------------
# 季節のアイデア
# ----------------------------------------------------------------------
def test_ideas_shape(env):
    """アプリのチップが読める形（emoji / label / prompt）で返ること。"""
    with env["app"].test_client() as c:
        body = c.get("/api/ideas").get_json()
    assert body["status"] == "OK"
    assert len(body["ideas"]) >= 3
    for idea in body["ideas"]:
        assert set(idea) == {"emoji", "label", "prompt"}
        assert idea["emoji"] and idea["label"] and idea["prompt"]


# ----------------------------------------------------------------------
# チャット履歴（プランの構造化データ付き）
# ----------------------------------------------------------------------
def test_chat_messages_attach_plan_and_survive_broken_json(env, monkeypatch):
    import db

    rows = [
        {"role": "user", "content": "熱海に行きたい", "request_id": "r1", "plan_json": None},
        {"role": "ai", "content": "<div>プラン</div>", "request_id": "r1",
         "plan_json": json.dumps({"destination": "熱海", "spots": ["起雲閣"]})},
        {"role": "ai", "content": "壊れたJSON", "request_id": "r2", "plan_json": "{壊れ"},
    ]

    def fake(uid):
        out = []
        for row in rows:
            d = dict(row)
            raw = d.pop("plan_json", None)
            try:
                d["plan"] = json.loads(raw) if raw else None
            except (ValueError, TypeError):
                d["plan"] = None
            out.append(d)
        return out

    monkeypatch.setattr(db, "get_chat_messages_with_plans", fake)
    with env["app"].test_client() as c:
        body = c.get("/api/chat_messages", headers=headers_for(OWNER)).get_json()

    messages = body["messages"]
    assert messages[0]["plan"] is None                       # ユーザー発話
    assert messages[1]["plan"]["destination"] == "熱海"       # プラン提示
    assert messages[2]["plan"] is None                       # 壊れていても落とさない
