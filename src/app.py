"""たびメイト アプリのエントリポイント。

Flask アプリ本体を生成し、各機能を Blueprint として登録する:
  - planner    : 旅行プラン作成チャット（メイン機能）
  - auth       : Google OAuth ログイン
  - reflection : 旅の振り返り（写真アップロード・実績・レポート）

Cloud Run などのリバースプロキシ配下で動かすため ProxyFix を適用し、
HTTPS / ホスト名を正しく認識させている。
"""

from flask import Flask
from werkzeug.middleware.proxy_fix import ProxyFix
from dotenv import load_dotenv
import os
import socket

# .env を読み込み、APIキーやDB接続情報などを環境変数として利用可能にする
load_dotenv(os.path.join(os.path.dirname(os.path.abspath(__file__)), '.env'))

from views.planner import planner
from views.auth import auth, init_oauth
from views.reflection import reflection
from views.sharing import share

app = Flask(__name__)
# Cloud Run のプロキシが付与する X-Forwarded-Proto / Host を信頼し、
# 生成するURL（OAuthコールバック等）を正しいスキーム・ホストにする
app.wsgi_app = ProxyFix(app.wsgi_app, x_proto=1, x_host=1)

# Cloud Run 上では K_SERVICE が自動設定される。これを本番判定に使う。
_IS_PROD = bool(os.getenv('K_SERVICE'))

# セッション署名鍵。本番(Cloud Run)で未設定なら、既知の鍵での署名（セッション偽造）を
# 防ぐため起動を失敗させる。ローカルのみ開発用フォールバックを使う。
_secret_key = os.getenv('SECRET_KEY')
if not _secret_key:
    if _IS_PROD:
        raise RuntimeError(
            'SECRET_KEY が未設定です。本番では必ず環境変数 / Secret Manager で設定してください。'
        )
    _secret_key = 'dev-secret-change-in-production'
app.secret_key = _secret_key

# セッションCookieの堅牢化（本番はHTTPSのみ送信）。
# SameSite=Lax は OAuth のトップレベルGETリダイレクトでもCookieが送られる。
app.config.update(
    SESSION_COOKIE_HTTPONLY=True,
    SESSION_COOKIE_SAMESITE='Lax',
    SESSION_COOKIE_SECURE=_IS_PROD,
    STADIA_API_KEY=os.environ.get('STADIA_API_KEY', ''),
    # リクエスト全体のサイズ上限。巨大アップロードによるメモリ枯渇/DoSを防ぐ。
    # 写真は複数枚まとめて送るため余裕を持たせつつ、青天井は避ける（既定100MB）。
    MAX_CONTENT_LENGTH=int(os.getenv('MAX_CONTENT_LENGTH_MB', '100')) * 1024 * 1024,
)


@app.errorhandler(413)
def _too_large(_e):
    """アップロードが上限超過のとき、クラッシュではなく分かりやすいエラーを返す。"""
    from flask import jsonify
    return jsonify({"error": "アップロードできるサイズを超えています。枚数を減らすか分けてお試しください。"}), 413


@app.errorhandler(404)
def _not_found(_e):
    """存在しないURL・削除済みリソース用の、世界観に合わせた404ページ。"""
    from flask import render_template
    return render_template(
        'error.html', code=404,
        heading='ページが見つかりません',
        message='お探しのページは、移動したか削除された可能性があります。\n共有リンクの場合は、共有が解除されているかもしれません。',
    ), 404


@app.errorhandler(500)
def _server_error(_e):
    """想定外のエラー用の500ページ（詳細はログにのみ出す）。"""
    from flask import render_template
    return render_template(
        'error.html', code=500,
        heading='エラーが発生しました',
        message='ごめんなさい、うまく処理できませんでした。\n少し時間をおいて、もう一度お試しください。',
    ), 500


@app.after_request
def _security_headers(resp):
    """基本的なセキュリティヘッダを付与する（MIMEスニッフ抑止・クリックジャッキング対策等）。"""
    resp.headers.setdefault('X-Content-Type-Options', 'nosniff')
    resp.headers.setdefault('X-Frame-Options', 'SAMEORIGIN')
    resp.headers.setdefault('Referrer-Policy', 'strict-origin-when-cross-origin')
    return resp


app.register_blueprint(planner, url_prefix='/')
app.register_blueprint(auth)
app.register_blueprint(reflection)
app.register_blueprint(share)
init_oauth(app)


def _parse_date(value):
    """文字列(YYYY-MM-DD)/date/datetime を date に正規化する。失敗時は None。"""
    from datetime import date, datetime
    if value is None or value == "":
        return None
    if isinstance(value, datetime):
        return value.date()
    if isinstance(value, date):
        return value
    try:
        return datetime.strptime(str(value)[:10], "%Y-%m-%d").date()
    except (ValueError, TypeError):
        return None


@app.template_filter("tripdates")
def tripdates(start, end=None):
    """旅の出発日・帰宅日を日本語で読みやすく整形する。

    例:
      単日              -> 2026年6月13日
      同年同月の期間    -> 2026年6月13日〜15日
      同年別月の期間    -> 2026年6月13日〜7月2日
      年をまたぐ期間    -> 2026年12月30日〜2027年1月2日
    """
    s = _parse_date(start)
    e = _parse_date(end)
    if not s and not e:
        return ""
    if s and not e:
        e = s
    if e and not s:
        s = e
    if s == e:
        return f"{s.year}年{s.month}月{s.day}日"
    if s.year != e.year:
        return f"{s.year}年{s.month}月{s.day}日〜{e.year}年{e.month}月{e.day}日"
    if s.month != e.month:
        return f"{s.year}年{s.month}月{s.day}日〜{e.month}月{e.day}日"
    return f"{s.year}年{s.month}月{s.day}日〜{e.day}日"

if __name__ == "__main__":
    # ローカル開発用の簡易サーバ起動（本番は Gunicorn を使用）
    port = 5007
    try:
        local_ip = socket.gethostbyname(socket.gethostname())
    except Exception:
        local_ip = "取得できませんでした"
    print(f"  ローカル:   http://localhost:{port}")
    print(f"  ネットワーク: http://{local_ip}:{port}")
    app.run(debug=True, host='0.0.0.0', port=port)
