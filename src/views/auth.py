"""Google OAuth によるログイン/ログアウトを担う Blueprint。

Authlib を使って Google の OpenID Connect で認証し、成功時に
ユーザーID・メール・氏名をセッションへ保存する。
login_required デコレータでログイン必須エンドポイントを保護する。
クライアントシークレット等は環境変数から読み込む（直書きしない）。
"""

import json
import os
from functools import wraps
from flask import Blueprint, redirect, url_for, session, request
from authlib.integrations.flask_client import OAuth
from chat.logger import get_logger

auth = Blueprint('auth', __name__, url_prefix='/auth')
oauth = OAuth()
logger = get_logger("views.auth")


def login_required(f):
    """ログイン必須のビュー保護デコレータ。

    アプリの Bearer トークンは app.before_request（api_auth.authenticate_app_token）が
    セッションへ読み替え済みなので、ここでは session を見るだけでよい。
    未認証時、アプリ側には 401 JSON を返す（ログイン画面へのリダイレクトは無意味なため）。
    """
    @wraps(f)
    def decorated(*args, **kwargs):
        if session.get('user_id'):
            return f(*args, **kwargs)

        # トークンを持ってきたのに通っていない＝期限切れか改ざん。作り直しを促す
        if request.headers.get('Authorization', '').startswith('Bearer '):
            return json.dumps({'status': 'ERROR', 'message': '認証が無効です。再ログインしてください。'}), 401, {'Content-Type': 'application/json'}

        logger.debug("未ログインアクセス: %s", request.path)
        # APIクライアント（JSONを期待する要求）にはリダイレクトではなく401を返す。
        # 判定の主役は Accept ヘッダ: ブラウザの画面遷移は必ず text/html を含み、
        # fetch/XHR やアプリは既定で */* を送るため、これで確実に切り分けられる。
        accept = request.headers.get('Accept', '')
        wants_json = (
            'text/html' not in accept
            or request.path.startswith('/api/')
            or request.is_json
            or request.headers.get('X-Requested-With') == 'XMLHttpRequest'
        )
        if wants_json:
            return json.dumps({'status': 'ERROR', 'message': 'ログインが必要です'}), 401, {'Content-Type': 'application/json'}
        return redirect(url_for('auth.login'))
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
    """Google の認証画面へリダイレクトしてOAuthフローを開始する。"""
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
    """セッションを破棄してホームへ戻る。"""
    user_email = session.get('user_email')
    session.clear()
    logger.info("ログアウト: email=%s", user_email)
    return redirect(url_for('planner.home'))


@auth.route('/app/signin', methods=['POST'])
def app_signin():
    """iOSアプリ用サインイン。GoogleのIDトークンを検証してアプリ用トークンを返す。

    リクエスト: {"id_token": "<GoogleサインインのIDトークン>"}
    レスポンス: {"status":"OK","token":"...","user":{"email":...,"name":...}}
    """
    from api_auth import issue_token, verify_google_id_token

    data = request.get_json(silent=True) or {}
    id_token_str = (data.get('id_token') or '').strip()
    if not id_token_str:
        return json.dumps({'status': 'ERROR', 'message': 'id_token が必要です'}), 400, {'Content-Type': 'application/json'}

    user = verify_google_id_token(id_token_str)
    if not user:
        return json.dumps({'status': 'ERROR', 'message': 'サインインに失敗しました'}), 401, {'Content-Type': 'application/json'}

    token = issue_token(user['sub'], user['email'], user['name'])
    logger.info("アプリサインイン: email=%s", user['email'])
    return json.dumps({
        'status': 'OK', 'token': token,
        'user': {'email': user['email'], 'name': user['name']},
    }, ensure_ascii=False), 200, {'Content-Type': 'application/json'}


@auth.route('/app/me', methods=['GET'])
def app_me():
    """アプリ用トークンの有効性確認（起動時の自動ログイン判定に使う）。"""
    from api_auth import verify_token

    authz = request.headers.get('Authorization', '')
    data = verify_token(authz[7:].strip()) if authz.startswith('Bearer ') else None
    if not data:
        return json.dumps({'status': 'ERROR', 'message': '認証が無効です'}), 401, {'Content-Type': 'application/json'}
    return json.dumps({
        'status': 'OK',
        'user': {'email': data.get('email', ''), 'name': data.get('name', '')},
    }, ensure_ascii=False), 200, {'Content-Type': 'application/json'}
