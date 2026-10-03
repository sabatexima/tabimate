"""写真ストレージの抽象化レイヤ。

本番は GCS（Google Cloud Storage）、ローカル開発はファイルシステムに保存する。
環境変数 GCS_BUCKET が設定されていれば GCS、なければローカルFSにフォールバックする。

保存実体はストレージ側に置き、DB にはここで返す storage_path（識別子）のみを記録する。
配信は get_url() が返す URL（GCSは署名付きURL、ローカルは内部配信ルート）を使う。
"""
import os
import threading
import time
import uuid
from concurrent.futures import ThreadPoolExecutor
from datetime import timedelta
from pathlib import Path

from logger import get_logger

logger = get_logger("services.storage")

_GCS_BUCKET = os.getenv("GCS_BUCKET")
_LOCAL_DIR = Path(os.getenv("LOCAL_UPLOAD_DIR", Path(__file__).resolve().parents[1] / "uploads"))
_SIGNED_URL_TTL = int(os.getenv("SIGNED_URL_TTL_SECONDS", "3600"))
# 署名に使うSAを明示したい場合のみ設定（未設定ならデフォルト認証から自動取得）
_SIGNER_SA = os.getenv("GCS_SIGNER_SA")

_gcs_client = None
_signer_credentials = None

# 署名付きURLのキャッシュ（storage_path -> (url, 失効エポック秒）。
# 署名はIAM signBlobへのリモート呼び出しでコストがあるため、URL有効期限の少し手前まで使い回す。
_url_cache: dict[str, tuple[str, float]] = {}
_url_cache_lock = threading.Lock()
_URL_CACHE_MARGIN = 300  # 失効の5分前には作り直す
_SIGN_MAX_WORKERS = 8    # 並列署名のワーカー上限


def _get_gcs_client():
    """GCSクライアントを遅延生成して使い回す（初回アクセス時のみ生成）。"""
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
    """GCSバケットが設定されていれば True（未設定ならローカルFSにフォールバック）。"""
    return bool(_GCS_BUCKET)


def _make_key(user_id: str, trip_id: int, filename: str) -> str:
    """写真の保存キーを生成する（trips/旅ID/ユーザーID/ランダム.拡張子）。衝突しないようUUID付き。"""
    ext = Path(filename).suffix.lower() or ".bin"
    return f"trips/{trip_id}/{user_id}/{uuid.uuid4().hex}{ext}"


def _thumb_key(key: str) -> str:
    """オリジナルのキーから対応するサムネイルのキーを導出する（同じ所有者配下）。"""
    if "/" in key:
        head, name = key.rsplit("/", 1)
        base = name.rsplit(".", 1)[0]
        return f"{head}/thumb/{base}.jpg"
    return f"thumb/{key}.jpg"


def _within_local(path: Path) -> bool:
    """resolve 後のパスがアップロードディレクトリ配下かを安全に判定する。"""
    base = _LOCAL_DIR.resolve()
    try:
        return path.resolve().is_relative_to(base)
    except AttributeError:  # Python < 3.9 フォールバック
        return str(path.resolve()).startswith(str(base) + os.sep)


def exists(storage_path: str) -> bool:
    """指定キーの実体が存在するか（GCS/ローカル）。バックフィルの重複生成回避に使う。"""
    if using_gcs():
        try:
            return _get_gcs_client().bucket(_GCS_BUCKET).blob(storage_path).exists()
        except Exception:
            return False
    path = _LOCAL_DIR / storage_path
    return _within_local(path) and path.resolve().is_file()


def save_at(key: str, data: bytes, content_type: str = "image/jpeg") -> str:
    """キーを指定してバイト列を保存する（サムネイル等、キーを自前で決めたい用途）。"""
    if using_gcs():
        bucket = _get_gcs_client().bucket(_GCS_BUCKET)
        bucket.blob(key).upload_from_string(data, content_type=content_type)
        return key
    dest = _LOCAL_DIR / key
    dest.parent.mkdir(parents=True, exist_ok=True)
    dest.write_bytes(data)
    return key


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


def _cached_url(storage_path: str) -> str | None:
    """有効期限内のキャッシュ済み署名URLがあれば返す。"""
    now = time.time()
    with _url_cache_lock:
        hit = _url_cache.get(storage_path)
        if hit and hit[1] > now:
            return hit[0]
    return None


def _store_url(storage_path: str, url: str) -> None:
    """署名付きURLを失効少し手前を期限としてキャッシュする（再署名の頻度を下げる）。"""
    with _url_cache_lock:
        _url_cache[storage_path] = (url, time.time() + max(_SIGNED_URL_TTL - _URL_CACHE_MARGIN, 60))


def _sign_url(storage_path: str) -> str:
    """GCSの署名付きURLを1件生成する（IAM signBlob方式）。"""
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


def get_url(storage_path: str) -> str:
    """配信用URLを返す。GCSは署名付きURL（キャッシュ利用）、ローカルは内部配信ルート。"""
    if using_gcs():
        cached = _cached_url(storage_path)
        if cached:
            return cached
        url = _sign_url(storage_path)
        _store_url(storage_path, url)
        return url
    # ローカル: Flask の配信ルート経由（views/reflection.py の serve_local_photo）
    return f"/reflection/photo/{storage_path}"


def get_urls(storage_paths) -> dict:
    """複数の storage_path の配信URLをまとめて返す（storage_path -> url）。

    GCSでは未キャッシュ分の署名を並列生成して、写真の多いページの待ち時間を短縮する
    （従来は枚数ぶん直列にIAM signBlobを呼んでいた）。
    """
    paths = list(dict.fromkeys(storage_paths))  # 重複除去・順序維持
    if not using_gcs():
        return {p: f"/reflection/photo/{p}" for p in paths}

    result: dict[str, str] = {}
    missing = []
    for p in paths:
        cached = _cached_url(p)
        if cached:
            result[p] = cached
        else:
            missing.append(p)

    if missing:
        _get_signing_info()  # 認証情報を先に初期化し、並列時のトークン更新競合を避ける

        def _work(p):
            """1枚ぶんの署名URLを作ってキャッシュする（並列で呼ばれる）。"""
            url = _sign_url(p)
            _store_url(p, url)
            return p, url

        with ThreadPoolExecutor(max_workers=min(_SIGN_MAX_WORKERS, len(missing))) as ex:
            for p, url in ex.map(_work, missing):
                result[p] = url

    return result


def get_thumb_url(storage_path: str) -> str:
    """サムネイルの配信URLを返す（オリジナルのキーから導出）。"""
    return get_url(_thumb_key(storage_path))


def get_thumb_urls(storage_paths) -> dict:
    """オリジナルpath -> サムネイルURL のマップを返す（署名はキャッシュ＋並列）。"""
    paths = list(dict.fromkeys(storage_paths))
    thumb_for = {p: _thumb_key(p) for p in paths}
    thumb_urls = get_urls(thumb_for.values())
    return {p: thumb_urls.get(tk) for p, tk in thumb_for.items()}


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
    path = _LOCAL_DIR / storage_path
    # ディレクトリトラバーサル防止（前方一致ではなくパス包含で判定）
    if not _within_local(path):
        logger.warning("不正なパスアクセスを拒否: %s", storage_path)
        return None
    path = path.resolve()
    if not path.is_file():
        return None
    return path.read_bytes()


def _delete_key(key: str) -> bool:
    """単一キーの実体を削除する（存在しなくても True／失敗時のみ False）。"""
    if using_gcs():
        try:
            _get_gcs_client().bucket(_GCS_BUCKET).blob(key).delete(if_generation_match=None)
            return True
        except Exception as e:
            if e.__class__.__name__ == "NotFound":
                return True  # 既に無い場合は許容
            logger.warning("GCSからの削除に失敗: %s", key, exc_info=True)
            return False

    path = _LOCAL_DIR / key
    if not _within_local(path):
        logger.warning("不正なパスの削除を拒否: %s", key)
        return False
    try:
        rp = path.resolve()
        if rp.is_file():
            rp.unlink()
        return True
    except Exception:
        logger.warning("ローカルからの削除に失敗: %s", key, exc_info=True)
        return False


def delete(storage_path: str) -> bool:
    """保存実体を削除する（GCS/ローカルどちらでも）。サムネイルも併せて掃除する。

    旅や写真の削除時に呼び、ストレージ上の孤立ファイル（＝無駄なコスト）を防ぐ。
    対象が存在しなくても True を返す（冪等）。失敗時のみ False。
    """
    ok = _delete_key(storage_path)
    _delete_key(_thumb_key(storage_path))  # サムネイルも削除（無ければ無視）
    return ok


class TempImages:
    """Google（スライド）に写真を取りに来てもらうための一時置き場。GCS のときだけ使える。

    アルバムのスライドは、写真を URL で渡すと Google が取りに来てコピーを持つ
    （貼ったあとは元のファイルが無くてもよい）。そこで、枠に合わせて切り抜いた写真を
    ここに置いて署名付き URL を渡し、貼り終わったら cleanup() で消す。
    途中で落ちて残った物は、次に使うときに sweep() で消す。
    手元（ローカル保存）では Google が取りに来られないので、put は None を返す。
    """

    PREFIX = "slides-tmp/"

    def __init__(self):
        self.base = f"{self.PREFIX}{uuid.uuid4().hex}/"
        self.keys: list = []
        self._lock = threading.Lock()
        self._signer_ready = False

    def put(self, name: str, data: bytes) -> str | None:
        if not using_gcs():
            return None
        with self._lock:
            if not self._signer_ready:
                _get_signing_info()   # 並列で呼ばれる前に一度だけ（トークン更新の取り合いを避ける）
                self._signer_ready = True
        key = self.base + name
        save_at(key, data, "image/jpeg")
        with self._lock:
            self.keys.append(key)
        return _sign_url(key)

    def cleanup(self) -> None:
        keys, self.keys = self.keys, []
        if keys:
            with ThreadPoolExecutor(max_workers=min(8, len(keys))) as ex:
                list(ex.map(_delete_key, keys))

    @classmethod
    def sweep(cls, max_age_hours: int = 6) -> int:
        """前に作りかけて残った一時ファイル（max_age_hours より古い物）を消す。"""
        if not using_gcs():
            return 0
        from datetime import datetime, timezone
        cutoff = datetime.now(timezone.utc) - timedelta(hours=max_age_hours)
        old = [b.name for b in _get_gcs_client().list_blobs(_GCS_BUCKET, prefix=cls.PREFIX)
               if b.time_created and b.time_created < cutoff]
        for key in old:
            _delete_key(key)
        if old:
            logger.info("スライド用の一時ファイルを掃除: %d件", len(old))
        return len(old)
