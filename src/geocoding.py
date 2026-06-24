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


def _query_nominatim(q: str) -> dict | None:
    try:
        resp = requests.get(
            _NOMINATIM_URL,
            params={"q": q, "format": "json", "limit": 1, "countrycodes": "jp"},
            headers=_HEADERS,
            timeout=3,
        )
        data = resp.json()
        if isinstance(data, list) and data:
            return {"lat": float(data[0]["lat"]), "lng": float(data[0]["lon"])}
    except Exception as e:
        logger.warning("ジオコーディング失敗: q=%s, error=%s", q, e)
    return None


# 末尾に付くと Nominatim でヒットしにくくなる総称（失敗時のみ外して再検索する）。
# 例: 「城崎温泉街」→「城崎温泉」 / 「祇園周辺」→「祇園」
_TRIM_SUFFIXES = ("街", "エリア", "周辺", "付近", "一帯", "地区", "地域", "界隈", "あたり")


def geocode_one(query: str, context: str | None = None) -> dict | None:
    """スポット名1件を緯度経度に変換する。失敗時は None。

    段階的にゆるめて再検索する（いずれも前段が失敗したときだけ実行）:
      1. 名前そのまま
      2. 「名前, context」（context 指定時。店名など単独では当たりにくいグルメ/宿向け）
      3. 末尾の総称（〜街/〜周辺 等）を外した名前（「城崎温泉街」→「城崎温泉」）
    返り値: {"lat": float, "lng": float} もしくは None
    """
    query = (query or "").strip()
    if not query:
        return None
    hit = _query_nominatim(query)
    if hit is None and context:
        hit = _query_nominatim(f"{query}, {context}")
    if hit is None:
        for suf in _TRIM_SUFFIXES:
            if query.endswith(suf) and len(query) > len(suf) + 1:
                trimmed = query[: -len(suf)]
                hit = _query_nominatim(trimmed)
                if hit is None and context:
                    hit = _query_nominatim(f"{trimmed}, {context}")
                break  # 末尾に該当する総称は1つだけなので1回試せば十分
    return hit


def geocode_spots(spots: list, known: dict | None = None, context: str | None = None) -> list:
    """スポット名のリストを順にジオコーディングし、成功したものだけ返す。

    返り値: [{"name": str, "lat": float, "lng": float}, ...]（順序は入力どおり）

    known: 既知の {name: {"lat","lng"}} を渡すと、その名前は再取得せず流用する
           （編集時に変わっていないスポットの再ジオコーディングを避ける）。
    context: 名前単独で当たらない場合の再検索キー（グルメ/宿は目的地を渡すと精度↑）。
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
        coords = geocode_one(name, context=context)
        if coords:
            results.append({"name": name, "lat": coords["lat"], "lng": coords["lng"]})
    return results


def ensure_plan_coords(plan: dict) -> dict:
    """プランの地図座標が未取得なら取得して plan に詰め、DBへ永続化する。

    地図を初めて開いたとき（＝リクエスト中）に1回だけジオコーディングし、以後は
    キャッシュを使う。保存処理をブロックしないための遅延取得。
    観光は名前のみ、グルメ/宿は目的地を文脈にして精度を上げる。
    """
    dest = plan.get("destination")
    changed = False

    def fill(coord_field, name_field, context=None):
        nonlocal changed
        if plan.get(coord_field):
            return
        names = plan.get(name_field) or []
        if not names:
            return
        plan[coord_field] = geocode_spots(names, context=context)
        changed = True

    # context は「名前単独で失敗したとき」だけ使う（観光も含め、化けを防ぎつつ精度を上げる）
    fill("spot_coords", "spots", context=dest)
    fill("restaurant_coords", "restaurants", context=dest)
    fill("accommodation_coords", "accommodation", context=dest)

    if changed and plan.get("id"):
        from db import update_plan_coords
        update_plan_coords(
            plan["id"],
            plan.get("spot_coords") or [],
            plan.get("restaurant_coords") or [],
            plan.get("accommodation_coords") or [],
        )
    return plan
