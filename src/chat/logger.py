import logging
import sys
from pathlib import Path

LOG_DIR = Path(__file__).resolve().parents[1] / "logs"
LOG_DIR.mkdir(exist_ok=True)

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

_fh = logging.FileHandler(LOG_DIR / "app.log", encoding="utf-8")
_fh.setLevel(logging.DEBUG)
_fh.setFormatter(_fmt)
logger.addHandler(_fh)


def get_logger(name: str = "") -> logging.Logger:
    """"travel_planner" 配下の名前空間付きロガーを返す（全モジュール共通の入口）。"""
    return logging.getLogger(f"travel_planner.{name}" if name else "travel_planner")
