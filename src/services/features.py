"""写真メタデータから「特徴量」をコード側で集計する。

生のメタデータ全件を Gemini に投げると高コストなので、ここで人間が読める
要約特徴量に落としてから渡す（トークン節約）。

入力: photos のリスト（各 dict に taken_at, lat, lng, caption）
出力: Gemini に渡しやすい dict（数値・短い説明）
"""
import math
from collections import Counter
from datetime import datetime

from chat.logger import get_logger

logger = get_logger("services.features")


def _parse_dt(v):
    if v is None:
        return None
    if isinstance(v, datetime):
        return v
    for fmt in ("%Y-%m-%d %H:%M:%S", "%Y-%m-%dT%H:%M:%S", "%Y:%m:%d %H:%M:%S"):
        try:
            return datetime.strptime(str(v)[:19], fmt)
        except (ValueError, TypeError):
            continue
    return None


def _haversine_km(lat1, lng1, lat2, lng2) -> float:
    r = 6371.0
    p1, p2 = math.radians(lat1), math.radians(lat2)
    dp = math.radians(lat2 - lat1)
    dl = math.radians(lng2 - lng1)
    a = math.sin(dp / 2) ** 2 + math.cos(p1) * math.cos(p2) * math.sin(dl / 2) ** 2
    return 2 * r * math.asin(math.sqrt(a))


def _time_band(hour: int) -> str:
    if 5 <= hour < 9:
        return "早朝"
    if 9 <= hour < 12:
        return "午前"
    if 12 <= hour < 15:
        return "昼"
    if 15 <= hour < 18:
        return "夕方"
    if 18 <= hour < 22:
        return "夜"
    return "深夜"


def aggregate(photos: list) -> dict:
    """写真メタデータから特徴量を集計する。"""
    total = len(photos)
    feat: dict = {
        "photo_count": total,
        "has_location": False,
        "has_timestamps": False,
    }
    if total == 0:
        return feat

    # --- 時刻系 ---
    times = [t for t in (_parse_dt(p.get("taken_at")) for p in photos) if t]
    if times:
        times.sort()
        feat["has_timestamps"] = True
        feat["first_photo_at"] = times[0].strftime("%Y-%m-%d %H:%M")
        feat["last_photo_at"] = times[-1].strftime("%Y-%m-%d %H:%M")
        feat["span_hours"] = round((times[-1] - times[0]).total_seconds() / 3600.0, 1)

        # 時間帯の偏り
        bands = Counter(_time_band(t.hour) for t in times)
        feat["time_band_distribution"] = dict(bands)
        feat["peak_time_band"] = bands.most_common(1)[0][0]

        # 日別撮影枚数
        per_day = Counter(t.strftime("%Y-%m-%d") for t in times)
        feat["days_active"] = len(per_day)
        feat["photos_per_day"] = dict(per_day)
        feat["busiest_day"] = per_day.most_common(1)[0][0]

        # 撮影間隔（連続写真の平均・最大）
        gaps = [(times[i + 1] - times[i]).total_seconds() / 60.0 for i in range(len(times) - 1)]
        if gaps:
            feat["avg_gap_minutes"] = round(sum(gaps) / len(gaps), 1)
            feat["max_gap_minutes"] = round(max(gaps), 1)

    # --- 位置系 ---
    coords = [(p.get("lat"), p.get("lng")) for p in photos
              if p.get("lat") is not None and p.get("lng") is not None]
    if coords:
        feat["has_location"] = True
        feat["located_photo_count"] = len(coords)
        lats = [c[0] for c in coords]
        lngs = [c[1] for c in coords]
        feat["bounding_box"] = {
            "lat_min": round(min(lats), 5), "lat_max": round(max(lats), 5),
            "lng_min": round(min(lngs), 5), "lng_max": round(max(lngs), 5),
        }
        # 中心からの広がり（おおよその訪問範囲）
        clat, clng = sum(lats) / len(lats), sum(lngs) / len(lngs)
        feat["center"] = {"lat": round(clat, 5), "lng": round(clng, 5)}
        spread = max(_haversine_km(clat, clng, la, ln) for la, ln in coords)
        feat["spread_km"] = round(spread, 2)

        # 総移動距離（撮影時刻順に連結）。時刻がなければ配列順。
        if times and len(times) == total:
            ordered = [c for _, c in sorted(
                zip([_parse_dt(p.get("taken_at")) or datetime.min for p in photos], coords)
            )]
        else:
            ordered = coords
        dist = sum(
            _haversine_km(ordered[i][0], ordered[i][1], ordered[i + 1][0], ordered[i + 1][1])
            for i in range(len(ordered) - 1)
        )
        feat["total_travel_km"] = round(dist, 2)

    # --- キャプション ---
    captions = [p.get("caption") for p in photos if p.get("caption")]
    if captions:
        feat["caption_count"] = len(captions)
        feat["captions_sample"] = captions[:10]

    logger.debug("特徴量を集計: photo_count=%d keys=%s", total, list(feat.keys()))
    return feat
