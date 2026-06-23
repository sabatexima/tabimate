"""スポット名 → 緯度経度の変換（ジオコーディング）を担う共通モジュール。

Nominatim(OpenStreetMap) を日本(countrycodes=jp)に絞って利用する。
プラン生成時のバッチ取得（geocode_spots）と、保存前データの無い旧プラン用の
オンデマンドプロキシ（/api/geocode → geocode_one）の両方から再利用される。
"""
import time

import requests

from chat.logger import get_logger

logger = get_logger("geocoding")

_NOMINATIM_URL = "https://nominatim.openstreetmap.org/search"
# ブラウザからは User-Agent を設定できないため、サーバー側で必ず付与する。
_HEADERS = {"User-Agent": "tabimate/1.0 (travel planner app)", "Accept-Language": "ja"}
# Nominatim の利用規約上のレート制限（1 req/s）。バッチ取得で順守する。
_RATE_LIMIT_SEC = 1.0


def geocode_one(query: str) -> dict | None:
    """スポット名1件を緯度経度に変換する。失敗時は None。

    返り値: {"lat": float, "lng": float} もしくは None
    """
    query = (query or "").strip()
    if not query:
        return None
    try:
        resp = requests.get(
            _NOMINATIM_URL,
            params={"q": query, "format": "json", "limit": 1, "countrycodes": "jp"},
            headers=_HEADERS,
            timeout=5,
        )
        data = resp.json()
        if isinstance(data, list) and data:
            return {"lat": float(data[0]["lat"]), "lng": float(data[0]["lon"])}
    except Exception as e:
        logger.warning("ジオコーディング失敗: q=%s, error=%s", query, e)
    return None


def geocode_spots(spots: list, known: dict | None = None) -> list:
    """スポット名のリストを順にジオコーディングし、成功したものだけ返す。

    返り値: [{"name": str, "lat": float, "lng": float}, ...]（順序は入力どおり）

    known: 既知の {name: {"lat","lng"}} を渡すと、その名前は再取得せず流用する
           （編集時に変わっていないスポットの再ジオコーディングを避ける）。
    """
    known = known or {}
    results = []
    pending = 0  # 実際に外部APIを叩いた回数（レート制限の間隔調整用）
    for name in spots or []:
        if not name:
            continue
        hit = known.get(name)
        if hit and hit.get("lat") is not None and hit.get("lng") is not None:
            results.append({"name": name, "lat": hit["lat"], "lng": hit["lng"]})
            continue
        if pending > 0:
            time.sleep(_RATE_LIMIT_SEC)
        pending += 1
        coords = geocode_one(name)
        if coords:
            results.append({"name": name, "lat": coords["lat"], "lng": coords["lng"]})
    return results
