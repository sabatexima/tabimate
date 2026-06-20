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
# セッション署名鍵。本番は環境変数 SECRET_KEY を必ず設定する
app.secret_key = os.getenv('SECRET_KEY', 'dev-secret-change-in-production')

app.register_blueprint(planner, url_prefix='/')
app.register_blueprint(auth)
app.register_blueprint(reflection)
app.register_blueprint(share)
init_oauth(app)

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
