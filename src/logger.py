"""全モジュール共通のロガー。get_logger("名前") でどこからでも同じ設定を使う。

出し先は2つ:
  標準出力  INFO以上。Cloud Run ではこれがそのままログとして拾われる
  src/logs/app.log  DEBUG以上。手元で細かく追いたいとき用（5MB×3で回す）

Cloud Run ではファイルには書かない。あちらのディスクはメモリの上にあるので、
書き足すほどインスタンスのメモリを食い、いずれ落とされる（生成の途中でも）。
以前は本番でも上限なしで書き続けていた。

ここが src/ 直下にあるのは、views も db も services も chat も使う横断的なものだから。
以前は chat/logger.py にいて、DB層まで「AIの層」に依存する形になっていた。
"""
import logging
import os
import sys
from logging.handlers import RotatingFileHandler
from pathlib import Path

LOG_DIR = Path(__file__).resolve().parent / "logs"  # src/logs（chat/ にあった頃と同じ場所）
_ON_CLOUD_RUN = bool(os.getenv("K_SERVICE"))   # Cloud Run が自動で入れる

logger = logging.getLogger("travel_planner")
logger.setLevel(logging.DEBUG)

_fmt = logging.Formatter(
    "%(asctime)s %(levelname)s %(name)s %(message)s",
    datefmt="%Y-%m-%d %H:%M:%S",
)

_ch = logging.StreamHandler(sys.stdout)
_ch.setLevel(logging.INFO)
_ch.setFormatter(_fmt)
logger.addHandler(_ch)

if not _ON_CLOUD_RUN:
    LOG_DIR.mkdir(exist_ok=True)
    _fh = RotatingFileHandler(LOG_DIR / "app.log", maxBytes=5 * 1024 * 1024, backupCount=3,
                              encoding="utf-8")
    _fh.setLevel(logging.DEBUG)
    _fh.setFormatter(_fmt)
    logger.addHandler(_fh)


def get_logger(name: str = "") -> logging.Logger:
    """"travel_planner" 配下の名前空間付きロガーを返す（全モジュール共通の入口）。"""
    return logging.getLogger(f"travel_planner.{name}" if name else "travel_planner")
