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
