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
# 署名に使うSAを明示したい場合のみ設定（未設定ならデフォルト認証から自動取得）
_SIGNER_SA = os.getenv("GCS_SIGNER_SA")

_gcs_client = None
_signer_credentials = None


def _get_gcs_client():
    global _gcs_client
    if _gcs_client is None:
        from google.cloud import storage as gcs
        _gcs_client = gcs.Client()
    return _gcs_client


def _get_signing_info():
    """署名付きURL生成に必要な (service_account_email, access_token) を返す。

    Cloud Run のデフォルト認証（メタデータサーバ経由）には秘密鍵が無いため、
    通常の generate_signed_url は失敗する。代わりに IAM signBlob API を使う方式
    （service_account_email + access_token を渡す）で署名する。
    アクセストークンは期限切れ時のみ更新する。
    """
    global _signer_credentials
    import google.auth
    from google.auth.transport import requests as google_requests

    if _signer_credentials is None:
        _signer_credentials, _ = google.auth.default(
            scopes=["https://www.googleapis.com/auth/cloud-platform"]
        )
    if not _signer_credentials.valid:
        _signer_credentials.refresh(google_requests.Request())

    sa_email = _SIGNER_SA or getattr(_signer_credentials, "service_account_email", None)
    return sa_email, _signer_credentials.token


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
        sa_email, token = _get_signing_info()
        return blob.generate_signed_url(
            version="v4",
            expiration=timedelta(seconds=_SIGNED_URL_TTL),
            method="GET",
            # Cloud Run のデフォルトSAでも署名できるよう IAM signBlob 方式を使う
            service_account_email=sa_email,
            access_token=token,
        )
    # ローカル: Flask の配信ルート経由（views/reflection.py の serve_local_photo）
    return f"/reflection/photo/{storage_path}"


def read_bytes(storage_path: str) -> bytes | None:
    """保存実体のバイト列を返す（GCS/ローカルどちらでも）。取得不可は None。

    解釈エンジンへ代表画像を送る（任意機能）際に使う。
    """
    if using_gcs():
        try:
            bucket = _get_gcs_client().bucket(_GCS_BUCKET)
            blob = bucket.blob(storage_path)
            return blob.download_as_bytes()
        except Exception:
            logger.warning("GCSからの読み出しに失敗: %s", storage_path, exc_info=True)
            return None
    return read_local(storage_path)


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
