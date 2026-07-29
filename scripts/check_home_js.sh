#!/usr/bin/env bash
# チャット画面の JavaScript を、本物のブラウザで動かして確かめる。
#
# なぜ要るか: ここの不具合は「構文は正しいのに実行時に何も起きない」形で出る。
# 実際 home.html のインラインスクリプトが home.js の const と同じ名前を var で
# 宣言していたため、スクリプト全体が SyntaxError で死んでいて「こんな旅はどう？」の
# チップが無反応になっていた。node --check では見つからない。
#
#   使い方: scripts/check_home_js.sh
#   必要なもの: Chrome か Chromium（無ければ検査を飛ばす）
set -euo pipefail

ROOT="$(cd "$(dirname "$0")/.." && pwd)"

# ----------------------------------------------------------------------
# ブラウザを探す
# ----------------------------------------------------------------------
CHROME=""
# CHROME_PATH は未設定でも動くこと（:- を外すと set -u で即死し、しかも
# エラーが見えないまま「検査していないのに終わった」状態になる）
CANDIDATES=(
  "${CHROME_PATH:-}"
  /opt/pw-browsers/chromium-*/chrome-linux/chrome
  google-chrome
  google-chrome-stable
  chromium
  chromium-browser
  "/Applications/Google Chrome.app/Contents/MacOS/Google Chrome"
)
for c in "${CANDIDATES[@]}"; do
  [ -n "$c" ] || continue
  if [ -x "$c" ]; then CHROME="$c"; break; fi
  found="$(command -v "$c" 2>/dev/null || true)"
  if [ -n "$found" ]; then CHROME="$found"; break; fi
done

if [ -z "$CHROME" ]; then
  # 手元では飛ばしてよいが、CI で黙って飛ばすと「ずっと緑なのに何も見ていない」
  # という一番たちの悪い状態になる。CI では止める
  if [ -n "${CI:-}" ]; then
    echo "ERROR: Chrome / Chromium が見つかりません（CI では必須です）" >&2
    exit 1
  fi
  echo "▸ Chrome / Chromium が見つからないので、この検査は飛ばします"
  exit 0
fi
echo "▸ ブラウザ: $CHROME"

# ----------------------------------------------------------------------
# 検査ページを配る（file:// だと localStorage が使えないため HTTP で出す）
# ----------------------------------------------------------------------
PORT=$(python3 -c "
import socket
s = socket.socket(); s.bind(('127.0.0.1', 0)); print(s.getsockname()[1]); s.close()")
python3 -m http.server "$PORT" --bind 127.0.0.1 --directory "$ROOT" >/dev/null 2>&1 &
SERVER=$!
trap 'kill $SERVER 2>/dev/null || true' EXIT

for _ in $(seq 20); do
  curl -sf "http://127.0.0.1:$PORT/tests/js/home_chat.html" -o /dev/null && break
  sleep 0.2
done

# ----------------------------------------------------------------------
# ケースごとに動かす
# ----------------------------------------------------------------------
declare -a NAMES=(
  [1]="起動時に挨拶と履歴が一度だけ描かれる"
  [2]="生成中に「新しいチャット」を押すと、止めてから消す"
  [3]="リセットに失敗したら画面を消さない"
  [4]="?q= で来たらリセットしてから送る"
  [5]="リロード直後、履歴が二重に描かれない"
  [6]="生成中か確かめられないとき、決めつけない"
  [7]="復元中に新しい相談が来ても、生成が二重に走らない"
)

failed=0
for case in 1 2 3 4 5 6 7; do
  url="http://127.0.0.1:$PORT/tests/js/home_chat.html?case=$case"
  case "$case" in 4|7) url="$url&q=%E6%B8%A9%E6%B3%89" ;; esac
  out=$("$CHROME" --headless --no-sandbox --disable-gpu --disable-dev-shm-usage \
        --virtual-time-budget=8000 --dump-dom "$url" 2>/dev/null \
        | sed -n 's/.*<pre id="result">\(.*\)<\/pre>.*/\1/p' | head -1)
  if [ "$out" = "ALL PASS" ]; then
    echo "  ✓ ${NAMES[$case]}"
  else
    echo "  ✗ ${NAMES[$case]}"
    echo "      ${out:-（結果を取り出せませんでした）}"
    failed=1
  fi
done

[ "$failed" = "0" ] && echo "▸ すべて通りました" || { echo "▸ 失敗あり"; exit 1; }
