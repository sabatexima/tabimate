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
