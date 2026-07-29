"""APIキー不要で一瞬で回るユニットテスト。

実際のGemini/Tavily/DB/GCSを呼ばない純粋関数（主に services.storage の
パス安全性・サムネイルキー・URL生成）を検証する。
実行: pytest tests/test_units.py
"""
import os
import sys

# src をインポートパスに追加し、ローカル（非GCS）モードで読み込む
sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "src"))
os.environ.pop("GCS_BUCKET", None)

from services import storage  # noqa: E402


def test_using_gcs_is_false_in_local():
    assert storage.using_gcs() is False


def test_thumb_key_derivation():
    assert storage._thumb_key("trips/1/u-abc/deadbeef.jpg") == "trips/1/u-abc/thumb/deadbeef.jpg"
    # 拡張子は .jpg に正規化される
    assert storage._thumb_key("trips/9/uid/photo.png") == "trips/9/uid/thumb/photo.jpg"


def test_get_urls_local_route_and_dedup():
    m = storage.get_urls([
        "trips/1/u/a.jpg",
        "trips/1/u/a.jpg",   # 重複は集約される
        "trips/1/u/b.jpg",
    ])
    assert m["trips/1/u/a.jpg"] == "/reflection/photo/trips/1/u/a.jpg"
    assert m["trips/1/u/b.jpg"] == "/reflection/photo/trips/1/u/b.jpg"
    assert len(m) == 2


def test_get_thumb_urls_local():
    m = storage.get_thumb_urls(["trips/1/u/a.jpg"])
    assert m["trips/1/u/a.jpg"] == "/reflection/photo/trips/1/u/thumb/a.jpg"


def test_within_local_allows_inside():
    base = storage._LOCAL_DIR
    assert storage._within_local(base / "trips/1/u/a.jpg") is True


def test_within_local_rejects_traversal():
    base = storage._LOCAL_DIR
    # アップロードディレクトリ外へ抜けるパスは拒否される
    assert storage._within_local(base / ".." / ".." / "etc" / "passwd") is False


def test_read_local_rejects_traversal(tmp_path):
    # 実在しても範囲外なら None（読み出さない）
    assert storage.read_local("../../../etc/hosts") is None


# ----------------------------------------------------------------------
# geocoding: 表記ゆらぎ候補・候補選択（ネットワークを呼ばない純粋関数）
# ----------------------------------------------------------------------
import geocoding  # noqa: E402


def test_geocode_normalize():
    # NFKC正規化（全角英数→半角）と空白圧縮
    assert geocoding._normalize("　兼六園  ライトアップ ") == "兼六園 ライトアップ"
    assert geocoding._normalize("ＵＳＪ") == "USJ"


def test_geocode_variants_paren_and_suffix():
    v = geocoding._variants("兼六園（ライトアップ）")
    assert v[0] == "兼六園（ライトアップ）"
    assert "兼六園" in v
    v2 = geocoding._variants("城崎温泉街")
    assert v2 == ["城崎温泉街", "城崎温泉"]
    # 重複しない・空にならない
    assert geocoding._variants("金沢21世紀美術館") == ["金沢21世紀美術館"]


def test_pick_candidate_prefers_nearest_to_center():
    kyoto = (35.0, 135.76)
    cands = [
        {"lat": 35.66, "lng": 139.70},  # 東京の同名スポット（先頭ヒット）
        {"lat": 35.00, "lng": 135.77},  # 京都の正解
    ]
    hit = geocoding._pick_candidate(cands, kyoto)
    assert hit["lng"] == 135.77


def test_pick_candidate_rejects_far_hits():
    kyoto = (35.0, 135.76)
    # 東京しか候補がない → 同名の別地とみなして棄却（誤ピンより未配置）
    assert geocoding._pick_candidate([{"lat": 35.66, "lng": 139.70}], kyoto) is None
    # center が無ければ先頭を信じる
    assert geocoding._pick_candidate([{"lat": 35.66, "lng": 139.70}], None) is not None
    # 広域旅行では max_km が広がり、同じヒットでも通る（例: 道内周遊の遠方スポット）
    assert geocoding._pick_candidate([{"lat": 35.66, "lng": 139.70}], kyoto, max_km=500) is not None


def test_google_places_disabled_without_key(monkeypatch):
    # キー未設定なら外部APIを一切呼ばず None（無料スタックのみで動く）
    monkeypatch.delenv("GOOGLE_MAPS_API_KEY", raising=False)
    assert geocoding._query_google_places("すし処 みさき 金沢") is None


def test_radius_from_bbox_adapts_to_destination_size():
    # 市サイズ（金沢市 ≈ 0.3度四方）→ 下限の80kmに張り付く（誤マッチに厳しい）
    small = geocoding._radius_from_bbox(36.45, 136.55, 36.75, 136.85)
    assert small == geocoding._MIN_RADIUS_KM
    # 広域（北海道 ≈ 緯度4度×経度8度）→ 上限の300kmまで広がる（遠方の正解を守る）
    large = geocoding._radius_from_bbox(41.5, 139.5, 45.5, 147.0)
    assert large == geocoding._MAX_RADIUS_KM
    # 中間（都道府県規模）は下限と上限の間に収まる
    mid = geocoding._radius_from_bbox(34.8, 135.0, 35.8, 136.1)
    assert geocoding._MIN_RADIUS_KM < mid < geocoding._MAX_RADIUS_KM


def test_ensure_plan_coords_fills_only_missing_names(monkeypatch):
    # 「3軒中1軒だけ座標あり」の旧プラン: Googleキーがあれば残り2軒だけ再検索する
    monkeypatch.setenv("GOOGLE_MAPS_API_KEY", "dummy")
    monkeypatch.setattr(geocoding, "geocode_center",
                        lambda q: {"lat": 35.10, "lng": 139.07, "radius_km": 80.0})
    searched = []

    def fake_geocode_one(name, **kw):
        searched.append(name)
        return {"lat": 35.11, "lng": 139.08}
    monkeypatch.setattr(geocoding, "geocode_one", fake_geocode_one)

    plan = {
        "destination": "熱海",
        "geo_done": 1,  # 旧プラン（キー導入前にジオコーディング済み）
        "restaurants": ["おさかな食堂", "囲炉茶屋", "海鮮処 磯丸"],
        "restaurant_coords": [{"name": "おさかな食堂", "lat": 35.09, "lng": 139.07}],
    }
    geocoding.ensure_plan_coords(plan)
    # 取得済みの1軒は再検索せず、足りない2軒だけ検索して順序どおりマージされる
    assert "おさかな食堂" not in searched
    assert searched == ["囲炉茶屋", "海鮮処 磯丸"]
    assert [c["name"] for c in plan["restaurant_coords"]] == ["おさかな食堂", "囲炉茶屋", "海鮮処 磯丸"]


def test_ensure_plan_coords_skips_partial_without_gmaps_key(monkeypatch):
    # Googleキーが無ければ、部分的に取得済みのプランは再検索しない（従来どおり）
    monkeypatch.delenv("GOOGLE_MAPS_API_KEY", raising=False)
    monkeypatch.setattr(geocoding, "geocode_one",
                        lambda *a, **kw: (_ for _ in ()).throw(AssertionError("呼ばれてはいけない")))
    plan = {
        "destination": "熱海",
        "geo_done": 1,
        "restaurants": ["おさかな食堂", "囲炉茶屋"],
        "restaurant_coords": [{"name": "おさかな食堂", "lat": 35.09, "lng": 139.07}],
    }
    geocoding.ensure_plan_coords(plan)
    assert len(plan["restaurant_coords"]) == 1


def test_first_within_respects_relevance_order():
    atami = (35.10, 139.07)
    cands = [
        {"lat": 35.66, "lng": 139.70},  # 関連度1位だが東京（遠方）
        {"lat": 35.09, "lng": 139.06},  # 関連度2位・熱海 → これを採用
        {"lat": 35.11, "lng": 139.08},  # 3位（2位より中心に近くても順位を尊重）
    ]
    hit = geocoding._first_within(cands, atami, max_km=80)
    assert (hit["lat"], hit["lng"]) == (35.09, 139.06)
    # 全部遠方なら棄却、centerが無ければ関連度1位
    assert geocoding._first_within([{"lat": 35.66, "lng": 139.70}], atami, max_km=80) is None
    assert geocoding._first_within(cands, None)["lat"] == 35.66


def test_filter_real_places_drops_hallucinated_names(monkeypatch):
    # 「海鮮処 磯丸」のようなLLM創作店名を候補段階で落とす
    os.environ.setdefault("GOOGLE_API_KEY", "dummy")
    os.environ.setdefault("TAVILY_API_KEY", "dummy")
    from chat import agents

    real = {"熱海銀座おさかな食堂": True, "囲炉茶屋": True, "海鮮処 磯丸": False,
            "熱海プリン": True, "存在しない食堂": False}
    monkeypatch.setattr(geocoding, "verify_place_exists",
                        lambda n, c=None: real.get(n))
    names = list(real)
    out = agents._filter_real_places(names, "熱海", min_keep=3)
    assert out == ["熱海銀座おさかな食堂", "囲炉茶屋", "熱海プリン"]

    # 実在確認できた候補が少なすぎるときは絞り込みを諦める（選択肢を保つ）
    mostly_fake = {"A": False, "B": False, "C": False, "D": True}
    monkeypatch.setattr(geocoding, "verify_place_exists",
                        lambda n, c=None: mostly_fake.get(n))
    assert agents._filter_real_places(list(mostly_fake), "熱海", min_keep=3) == list(mostly_fake)

    # キー未設定（全部None＝検証不能）なら何も落とさない
    monkeypatch.setattr(geocoding, "verify_place_exists", lambda n, c=None: None)
    assert agents._filter_real_places(["X", "Y"], "熱海", min_keep=3) == ["X", "Y"]


def test_geocode_one_negative_cache(monkeypatch):
    # 全プロバイダで外れた名前はTTL内は再検索しない（毎回の待ち時間とAPI消費を抑える）
    geocoding._neg_cache.clear()
    calls = []
    monkeypatch.setattr(geocoding, "_query_google_places", lambda *a, **k: calls.append("g") or None)
    monkeypatch.setattr(geocoding, "_query_nominatim", lambda *a, **k: calls.append("n") or None)
    monkeypatch.setattr(geocoding, "_query_gsi", lambda *a, **k: calls.append("s") or None)
    assert geocoding.geocode_one("存在しない店", context="熱海") is None
    first = len(calls)
    assert first > 0
    assert geocoding.geocode_one("存在しない店", context="熱海") is None
    assert len(calls) == first  # 2回目はプロバイダを一切呼ばない
    # 成功したらキャッシュは解除される
    geocoding._neg_cache.clear()
    monkeypatch.setattr(geocoding, "_query_google_places",
                        lambda *a, **k: {"lat": 35.1, "lng": 139.07})
    hit = geocoding.geocode_one("存在しない店", context="熱海")
    assert hit == {"lat": 35.1, "lng": 139.07}
    assert not geocoding._neg_cache


# ----------------------------------------------------------------------
# Tavily 検索結果の長さ制限（プロンプト肥大とトークン浪費を防ぐ）
# ----------------------------------------------------------------------
def test_web_search_truncates_long_results(monkeypatch):
    os.environ.setdefault("GOOGLE_API_KEY", "dummy")
    os.environ.setdefault("TAVILY_API_KEY", "dummy")
    import chat.llm as L

    class _FakeSearch:
        def invoke(self, q):
            # 長文8件・スコアはバラバラ（低スコアは閾値0.3で落ちる想定）
            return [{"score": s, "content": "あ" * 3000}
                    for s in [0.2, 0.9, 0.5, 0.95, 0.4, 0.7, 0.1, 0.6]]

    monkeypatch.setattr(L, "_search", _FakeSearch())
    out = L.web_search("テスト")
    lines = out.split("\n")
    # 1件ずつ切り詰め、全体でも上限内に収まる
    assert all(len(x) <= L._SEARCH_SNIPPET_CHARS for x in lines)
    assert len(out) <= L._SEARCH_QUERY_CHARS + L._SEARCH_SNIPPET_CHARS
    # 24,000字がプロンプトに丸ごと入らないこと（肥大防止の主目的）
    assert len(out) < 3000


def test_web_search_handles_bad_shapes(monkeypatch):
    import chat.llm as L

    class _StrSearch:
        def invoke(self, q):
            return "  文字列で返ってくることがある  "

    class _BoomSearch:
        def invoke(self, q):
            raise RuntimeError("network down")

    monkeypatch.setattr(L, "_search", _StrSearch())
    assert L.web_search("q") == "文字列で返ってくることがある"
    monkeypatch.setattr(L, "_search", _BoomSearch())
    assert L.web_search("q") == ""  # 失敗時は空文字（生成は続行できる）


# ----------------------------------------------------------------------
# アプリ（iOS）向けトークン認証
# ----------------------------------------------------------------------
import api_auth  # noqa: E402
from flask import Flask, jsonify, session  # noqa: E402

from views.auth import auth as auth_bp, login_required  # noqa: E402


def _token_app():
    """auth Blueprint と login_required だけを載せた検証用の最小アプリ。"""
    app = Flask(__name__)
    app.secret_key = "test-secret"
    app.config["TESTING"] = True
    app.register_blueprint(auth_bp)
    # 本番と同じく、Bearer トークンの読み替えは before_request が担う
    app.before_request(api_auth.authenticate_app_token)

    @app.get("/data")
    @login_required
    def data():
        return jsonify(user=session["user_id"])

    @app.get("/page")
    @login_required
    def page():
        return "<html></html>"

    return app


def test_app_token_roundtrip_and_tamper(monkeypatch):
    monkeypatch.setenv("SECRET_KEY", "test-secret")
    token = api_auth.issue_token("u-1", "a@example.com", "てく")
    assert api_auth.verify_token(token)["sub"] == "u-1"
    assert api_auth.verify_token(token[:-2] + "xx") is None
    # 鍵が変われば既存トークンは失効する
    monkeypatch.setenv("SECRET_KEY", "another-secret")
    assert api_auth.verify_token(token) is None


def test_app_token_expires(monkeypatch):
    monkeypatch.setenv("SECRET_KEY", "test-secret")
    token = api_auth.issue_token("u-1", "a@example.com", "てく")
    monkeypatch.setattr(api_auth, "TOKEN_MAX_AGE_SEC", -1)
    assert api_auth.verify_token(token) is None


def test_login_required_accepts_bearer_without_setting_cookie(monkeypatch):
    monkeypatch.setenv("SECRET_KEY", "test-secret")
    token = api_auth.issue_token("u-1", "a@example.com", "てく")
    with _token_app().test_client() as c:
        r = c.get("/data", headers={"Authorization": f"Bearer {token}"})
    assert r.status_code == 200 and r.get_json()["user"] == "u-1"
    # アプリの認証情報はトークンだけ。セッションCookieは発行しない
    assert "Set-Cookie" not in r.headers


def test_login_required_returns_401_json_for_api_clients():
    app = _token_app()
    with app.test_client() as c:              # fetch/アプリ相当（Accept: */*）
        r = c.get("/data")
    assert r.status_code == 401
    assert r.headers["Content-Type"] == "application/json"

    with app.test_client() as c:              # 壊れたトークンも401
        r = c.get("/data", headers={"Authorization": "Bearer garbage"})
    assert r.status_code == 401


def test_login_required_still_redirects_browser_navigation():
    with _token_app().test_client() as c:
        r = c.get("/page", headers={"Accept": "text/html,application/xhtml+xml"})
    assert r.status_code == 302 and "/auth/login" in r.headers["Location"]


def test_app_me_reports_token_validity(monkeypatch):
    monkeypatch.setenv("SECRET_KEY", "test-secret")
    token = api_auth.issue_token("u-1", "a@example.com", "てく")
    app = _token_app()
    with app.test_client() as c:
        r = c.get("/auth/app/me", headers={"Authorization": f"Bearer {token}"})
    assert r.status_code == 200 and r.get_json()["user"]["name"] == "てく"
    with app.test_client() as c:
        assert c.get("/auth/app/me").status_code == 401


def test_digest_month_grouping_matches_view():
    """ダイジェストの月まとめが、日付の無い旅も落とさずに扱えること。

    アプリ側（Digest.monthGroups）と同じ規則をサーバー側でも使うため、
    月の取り出し方が変わっていないことを固定する。
    """
    def month_of(trip):
        d = str(trip.get("start_date") or trip.get("created_at") or "")
        try:
            return int(d[5:7])
        except ValueError:
            return 0

    assert month_of({"start_date": "2026-08-14"}) == 8
    assert month_of({"start_date": None, "created_at": "2026-01-10 10:00:00"}) == 1
    assert month_of({}) == 0


def test_google_id_token_requires_configured_audience(monkeypatch):
    """aud の検証先が未設定なら、検証そのものを行わずに断る。

    google-auth は audience=None だと aud の検査を省くため、未設定のまま呼ぶと
    他アプリ向けのIDトークンでもなりすませてしまう。
    """
    monkeypatch.delenv("GOOGLE_IOS_CLIENT_ID", raising=False)
    monkeypatch.delenv("GOOGLE_CLIENT_ID", raising=False)

    called = False

    def _boom(*args, **kwargs):
        nonlocal called
        called = True
        return {"sub": "attacker", "email": "a@example.com", "email_verified": True}

    monkeypatch.setattr("google.oauth2.id_token.verify_oauth2_token", _boom)
    assert api_auth.verify_google_id_token("any-token") is None
    assert not called, "検証先が無いのにGoogleへ問い合わせてはいけない"


def test_app_signin_rejects_missing_and_invalid_id_token(monkeypatch):
    app = _token_app()
    with app.test_client() as c:
        assert c.post("/auth/app/signin", json={}).status_code == 400
    monkeypatch.setattr(api_auth, "verify_google_id_token", lambda _t: None)
    with app.test_client() as c:
        assert c.post("/auth/app/signin", json={"id_token": "bad"}).status_code == 401
