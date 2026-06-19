from flask import Flask
from werkzeug.middleware.proxy_fix import ProxyFix
from dotenv import load_dotenv
import os
import socket

load_dotenv(os.path.join(os.path.dirname(os.path.abspath(__file__)), '.env'))

from views.planner import planner
from views.auth import auth, init_oauth

app = Flask(__name__)
app.wsgi_app = ProxyFix(app.wsgi_app, x_proto=1, x_host=1)
app.secret_key = os.getenv('SECRET_KEY', 'dev-secret-change-in-production')

app.register_blueprint(planner, url_prefix='/')
app.register_blueprint(auth)
init_oauth(app)

if __name__ == "__main__":
    port = 5007
    try:
        local_ip = socket.gethostbyname(socket.gethostname())
    except Exception:
        local_ip = "取得できませんでした"
    print(f"  ローカル:   http://localhost:{port}")
    print(f"  ネットワーク: http://{local_ip}:{port}")
    app.run(debug=True, host='0.0.0.0', port=port)
