#!/bin/sh

# 'docker-compose' の代わりに、新しい 'docker compose' コマンドを使うんだな
if [ "$1" = "build" ]; then
  docker compose build
  docker compose up -d
else
  docker compose up -d
fi
