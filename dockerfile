# 公式の Python イメージを使う（以前は ubuntu に apt で python3.10 を入れていた）。
# 依存はすべて wheel で入るので、コンパイラや開発ヘッダの要らない slim で足りる。
FROM python:3.13-slim

COPY requirements.txt /tmp/
RUN pip install --no-cache-dir -r /tmp/requirements.txt

WORKDIR /src
COPY src/ /src/

# timeout はプラン生成（長期旅行は数分〜十数分かかり得る）に合わせて Cloud Run 側(--timeout=3600)と揃える
CMD exec gunicorn --worker-class gthread --workers 1 --threads 20 --timeout 3600 --bind 0.0.0.0:${PORT:-8080} app:app
