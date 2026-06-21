"""Google OAuth によるログイン/ログアウトを担う Blueprint。

Authlib を使って Google の OpenID Connect で認証し、成功時に
ユーザーID・メール・氏名をセッションへ保存する。
login_required デコレータでログイン必須エンドポイントを保護する。
クライアントシークレット等は環境変数から読み込む（直書きしない）。
"""

import os
from functools import wraps
from flask import Blueprint, redirect, url_for, session, request, flash
from authlib.integrations.flask_client import OAuth
from chat.logger import get_logger

auth = Blueprint('auth', __name__, url_prefix='/auth')
oauth = OAuth()
logger = get_logger("views.auth")


def login_required(f):
    """未ログインなら login へリダイレクトするビュー保護デコレータ。"""
    @wraps(f)
    def decorated(*args, **kwargs):
        if not session.get('user_id'):
            logger.debug("未ログインアクセス: %s", request.path)
            return redirect(url_for('auth.login'))
        return f(*args, **kwargs)
    return decorated


def init_oauth(app):
    """アプリ起動時に Google OAuth クライアントを登録・初期化する。"""
    oauth.init_app(app)
    oauth.register(
        name='google',
        client_id=os.getenv('GOOGLE_CLIENT_ID'),
        client_secret=os.getenv('GOOGLE_CLIENT_SECRET'),
        server_metadata_url='https://accounts.google.com/.well-known/openid-configuration',
        client_kwargs={'scope': 'openid email profile'},
    )


@auth.route('/login')
def login():
    redirect_uri = url_for('auth.callback', _external=True)
    logger.info("ログイン開始: redirect_uri=%s", redirect_uri)
    return oauth.google.authorize_redirect(redirect_uri)


@auth.route('/callback')
def callback():
    """Google からのコールバックを受け、ユーザー情報をセッションに保存する。"""
    try:
        token = oauth.google.authorize_access_token()
        user = token.get('userinfo')
        # email_verified は通常 bool だが、文字列で返す実装もあるため両対応で判定
        ev = user.get('email_verified') if user else None
        email_verified = (ev is True) or (str(ev).lower() == 'true')
        if user and user.get('email') and email_verified:
            session['user_id']    = user['sub']
            session['user_email'] = user['email']
            session['user_name']  = user.get('name', user['email'])
            logger.info("ログイン成功: email=%s", user['email'])
        elif user and not email_verified:
            logger.warning("未検証メールのためログインを拒否: email=%s", user.get('email'))
            session['login_error'] = 'メールアドレスが未検証のためログインできません。'
        else:
            logger.warning("Google callback で userinfo が取得できませんでした")
            session['login_error'] = 'ログインに失敗しました。もう一度お試しください。'
    except Exception as e:
        logger.exception("Google OAuth callback でエラー: %s", e)
        session['login_error'] = 'ログインに失敗しました。もう一度お試しください。'
    return redirect(url_for('planner.home'))


@auth.route('/logout')
def logout():
    user_email = session.get('user_email')
    session.clear()
    logger.info("ログアウト: email=%s", user_email)
    return redirect(url_for('planner.home'))
