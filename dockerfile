FROM ubuntu:22.04

RUN apt update \
    && apt install -y \
    python3.10 \
    python3-pip \
    curl \
    sudo \
    && apt-get autoremove -y && apt-get clean \
    && rm -rf /var/lib/apt/lists/*

COPY requirements.txt /tmp/
RUN pip install --no-cache-dir -r /tmp/requirements.txt

WORKDIR /src
COPY src/ /src/

CMD exec gunicorn --worker-class gthread --workers 1 --threads 20 --timeout 600 --bind 0.0.0.0:${PORT:-8080} app:app
