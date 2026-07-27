"""ネイティブアプリ（iOS）向けのトークン認証。

ブラウザ版はセッションCookieで認証しているが、アプリからはCookieを使えない。
そこで「Googleサインインで得た ID トークン」をサーバーで検証し、
アプリ用の自前アクセストークン（署名付き・期限付き）を発行する。

以降のAPIは Authorization: Bearer <token> で認証する。
Web版のセッション認証はそのまま残し、両方を受け付ける（既存機能を壊さない）。
"""
import os
import time

from flask import request, session
from itsdangerous import BadSignature, SignatureExpired, URLSafeTimedSerializer

from chat.logger import get_logger

logger = get_logger("api_auth")

# アプリ用トークンの有効期間（既定30日）。期限切れは再サインインで取り直す。
TOKEN_MAX_AGE_SEC = int(os.getenv("APP_TOKEN_MAX_AGE_SEC", str(30 * 24 * 3600)))
_SALT = "tabimate-app-token"


def _serializer() -> URLSafeTimedSerializer:
    """SECRET_KEY を使う署名器（鍵が変わると既存トークンは自動的に無効になる）。"""
    secret = os.getenv("SECRET_KEY") or "dev-secret-change-in-production"
    return URLSafeTimedSerializer(secret, salt=_SALT)


def issue_token(user_id: str, email: str, name: str) -> str:
    """アプリ用アクセストークンを発行する。"""
    return _serializer().dumps({
        "sub": user_id, "email": email, "name": name, "iat": int(time.time()),
    })


def verify_token(token: str) -> dict | None:
    """アプリ用トークンを検証し、ユーザー情報を返す。無効・期限切れは None。"""
    try:
        return _serializer().loads(token, max_age=TOKEN_MAX_AGE_SEC)
    except SignatureExpired:
        logger.info("アプリトークンの期限切れ")
    except BadSignature:
        logger.info("アプリトークンの署名が不正")
    return None


def verify_google_id_token(id_token_str: str) -> dict | None:
    """iOSのGoogleサインインで得た ID トークンを検証し、ユーザー情報を返す。

    メール未検証のアカウントは共有機能の前提が崩れるため拒否する（Web版と同じ方針）。
    """
    try:
        from google.auth.transport import requests as ga_requests
        from google.oauth2 import id_token as google_id_token

        # iOS用クライアントIDがあればそれを、無ければWeb用を許可する
        audience = os.getenv("GOOGLE_IOS_CLIENT_ID") or os.getenv("GOOGLE_CLIENT_ID")
        info = google_id_token.verify_oauth2_token(
            id_token_str, ga_requests.Request(), audience
        )
        if not info.get("email_verified"):
            logger.info("メール未検証のためアプリログインを拒否")
            return None
        return {
            "sub": info["sub"],
            "email": info.get("email", ""),
            "name": info.get("name") or info.get("email", ""),
        }
    except Exception:
        logger.exception("GoogleIDトークンの検証に失敗")
        return None


def current_user_id() -> str | None:
    """リクエストの認証主体を返す（Bearerトークン優先、無ければWebセッション）。"""
    auth = request.headers.get("Authorization", "")
    if auth.startswith("Bearer "):
        data = verify_token(auth[7:].strip())
        if data:
            return data.get("sub")
        return None
    return session.get("user_id")
