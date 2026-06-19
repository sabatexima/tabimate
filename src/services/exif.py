"""写真の EXIF から撮影時刻・GPS座標を抽出する。

Pillow を使用。EXIF が無い／壊れている場合は None を返し、
後段（手動補完）に委ねる。例外は握りつぶさず None 返却で吸収する。
"""
import io
from datetime import datetime

from chat.logger import get_logger

logger = get_logger("services.exif")

# EXIF タグ ID（Pillow の数値タグ）
_DATETIME_ORIGINAL = 36867  # DateTimeOriginal
_DATETIME = 306             # DateTime
_GPS_IFD = 34853            # GPSInfo


def _to_degrees(value) -> float:
    """EXIF GPS の (度, 分, 秒) を10進度に変換する。"""
    d, m, s = value
    return float(d) + float(m) / 60.0 + float(s) / 3600.0


def _parse_dt(raw: str):
    if not raw:
        return None
    raw = str(raw).strip()
    for fmt in ("%Y:%m:%d %H:%M:%S", "%Y-%m-%d %H:%M:%S"):
        try:
            return datetime.strptime(raw, fmt)
        except (ValueError, TypeError):
            continue
    return None


def extract(data: bytes) -> dict:
    """画像バイト列から {taken_at, lat, lng} を抽出する。取れない値は None。"""
    result = {"taken_at": None, "lat": None, "lng": None}
    try:
        from PIL import Image
        img = Image.open(io.BytesIO(data))
        exif = img.getexif()
        if not exif:
            return result

        # 撮影時刻
        taken_raw = exif.get(_DATETIME_ORIGINAL) or exif.get(_DATETIME)
        if not taken_raw:
            # DateTimeOriginal は ExifIFD 内にあることが多い
            try:
                ifd = exif.get_ifd(0x8769)  # ExifIFD
                taken_raw = ifd.get(_DATETIME_ORIGINAL)
            except Exception:
                taken_raw = None
        result["taken_at"] = _parse_dt(taken_raw)

        # GPS
        gps = exif.get_ifd(_GPS_IFD) if hasattr(exif, "get_ifd") else None
        if gps:
            lat = gps.get(2)
            lat_ref = gps.get(1)
            lng = gps.get(4)
            lng_ref = gps.get(3)
            if lat and lng and lat_ref and lng_ref:
                lat_deg = _to_degrees(lat)
                lng_deg = _to_degrees(lng)
                if str(lat_ref).upper().startswith("S"):
                    lat_deg = -lat_deg
                if str(lng_ref).upper().startswith("W"):
                    lng_deg = -lng_deg
                result["lat"] = round(lat_deg, 6)
                result["lng"] = round(lng_deg, 6)
    except Exception:
        logger.debug("EXIF抽出に失敗（メタデータなしとして処理）", exc_info=True)

    return result
