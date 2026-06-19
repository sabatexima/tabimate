"""写真ストレージの抽象化レイヤ。

本番は GCS（Google Cloud Storage）、ローカル開発はファイルシステムに保存する。
環境変数 GCS_BUCKET が設定されていれば GCS、なければローカルFSにフォールバックする。

保存実体はストレージ側に置き、DB にはここで返す storage_path（識別子）のみを記録する。
配信は get_url() が返す URL（GCSは署名付きURL、ローカルは内部配信ルート）を使う。
"""
import os
import uuid
from datetime import timedelta
from pathlib import Path

from chat.logger import get_logger

logger = get_logger("services.storage")

_GCS_BUCKET = os.getenv("GCS_BUCKET")
_LOCAL_DIR = Path(os.getenv("LOCAL_UPLOAD_DIR", Path(__file__).resolve().parents[1] / "uploads"))
_SIGNED_URL_TTL = int(os.getenv("SIGNED_URL_TTL_SECONDS", "3600"))

_gcs_client = None


def _get_gcs_client():
    global _gcs_client
    if _gcs_client is None:
        from google.cloud import storage as gcs
        _gcs_client = gcs.Client()
    return _gcs_client


def using_gcs() -> bool:
    return bool(_GCS_BUCKET)


def _make_key(user_id: str, trip_id: int, filename: str) -> str:
    ext = Path(filename).suffix.lower() or ".bin"
    return f"trips/{trip_id}/{user_id}/{uuid.uuid4().hex}{ext}"


def save(user_id: str, trip_id: int, filename: str, data: bytes,
         content_type: str = "application/octet-stream") -> str:
    """写真バイト列を保存し、storage_path（識別子）を返す。"""
    key = _make_key(user_id, trip_id, filename)

    if using_gcs():
        bucket = _get_gcs_client().bucket(_GCS_BUCKET)
        blob = bucket.blob(key)
        blob.upload_from_string(data, content_type=content_type)
        logger.info("GCSへ保存: bucket=%s key=%s bytes=%d", _GCS_BUCKET, key, len(data))
        return key

    # ローカルFSフォールバック
    dest = _LOCAL_DIR / key
    dest.parent.mkdir(parents=True, exist_ok=True)
    dest.write_bytes(data)
    logger.info("ローカルへ保存: path=%s bytes=%d", dest, len(data))
    return key


def get_url(storage_path: str) -> str:
    """配信用URLを返す。GCSは署名付きURL、ローカルは内部配信ルート。"""
    if using_gcs():
        bucket = _get_gcs_client().bucket(_GCS_BUCKET)
        blob = bucket.blob(storage_path)
        return blob.generate_signed_url(
            version="v4",
            expiration=timedelta(seconds=_SIGNED_URL_TTL),
            method="GET",
        )
    # ローカル: Flask の配信ルート経由（views/reflection.py の serve_local_photo）
    return f"/reflection/photo/{storage_path}"


def read_local(storage_path: str) -> bytes | None:
    """ローカルFS保存の写真を読み出す（GCS時は使わない）。"""
    if using_gcs():
        return None
    path = (_LOCAL_DIR / storage_path).resolve()
    # ディレクトリトラバーサル防止
    if not str(path).startswith(str(_LOCAL_DIR.resolve())):
        logger.warning("不正なパスアクセスを拒否: %s", storage_path)
        return None
    if not path.is_file():
        return None
    return path.read_bytes()
