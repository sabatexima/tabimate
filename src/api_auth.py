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


def authenticate_app_token():
    """アプリの Bearer トークンを、この要求の間だけセッションに読み替える。

    app.before_request に登録して使う。デコレータではなくここで行うのは、
    共有まわり（views/sharing.py）のように login_required を通らず
    session を直接見るエンドポイントも、アプリから同じように使えるようにするため。

    セッションCookieは発行しない（modified を戻す）。アプリの認証情報は
    あくまでトークンだけ、という状態を保つ。
    """
    if session.get("user_id"):
        return  # ブラウザのセッションが既にある。触らない

    authz = request.headers.get("Authorization", "")
    if not authz.startswith("Bearer "):
        return

    data = verify_token(authz[7:].strip())
    if not data:
        return  # 無効なトークン。未ログインのまま各エンドポイントの判断に任せる

    session["user_id"] = data.get("sub")
    session["user_email"] = data.get("email", "")
    session["user_name"] = data.get("name", "")
    session.modified = False


def verify_google_id_token(id_token_str: str) -> dict | None:
    """iOSのGoogleサインインで得た ID トークンを検証し、ユーザー情報を返す。

    メール未検証のアカウントは共有機能の前提が崩れるため拒否する（Web版と同じ方針）。
    """
    # 宛先(aud)が誰なのかを必ず確かめる。google-auth は audience=None だと aud の検査を
    # まるごと省くため、未設定のまま呼ぶと「別のアプリ向けに発行されたIDトークン」まで
    # 通ってしまう（他人が作ったアプリで victim にサインインさせ、そのトークンで
    # なりすませる）。設定が無いときは検証せず断る。
    audience = os.getenv("GOOGLE_IOS_CLIENT_ID") or os.getenv("GOOGLE_CLIENT_ID")
    if not audience:
        logger.error("GOOGLE_IOS_CLIENT_ID / GOOGLE_CLIENT_ID が未設定のためアプリログインを拒否")
        return None

    try:
        from google.auth.transport import requests as ga_requests
        from google.oauth2 import id_token as google_id_token

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
