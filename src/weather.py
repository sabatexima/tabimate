"""旅行日の天気予報（Open-Meteo・APIキー不要）。

表示（保存/共有プラン）・生成（屋内/屋外の調整ヒント）の両方で再利用する。
予報が取れるのは概ね当日〜16日先まで。範囲外・日付不明・座標不明なら空を返す。
"""
import re
from datetime import date, timedelta

import requests

from chat.logger import get_logger

logger = get_logger("weather")

_URL = "https://api.open-meteo.com/v1/forecast"
# 雨・雪・雷など「屋外がつらい」WMOコード（生成時の屋内寄せ判断に使う）
_BAD_WEATHER_CODES = {51, 53, 55, 56, 57, 61, 63, 65, 66, 67, 71, 73, 75, 77,
                      80, 81, 82, 85, 86, 95, 96, 99}


def describe(code) -> tuple:
    """WMO 天気コード → (絵文字, ラベル)。"""
    table = [
        ({0}, '☀️', '快晴'),
        ({1, 2}, '🌤️', '晴れ'),
        ({3}, '☁️', 'くもり'),
        ({45, 48}, '🌫️', '霧'),
        ({51, 53, 55, 56, 57}, '🌦️', '霧雨'),
        ({61, 63, 65, 66, 67}, '🌧️', '雨'),
        ({71, 73, 75, 77}, '❄️', '雪'),
        ({80, 81, 82}, '🌦️', 'にわか雨'),
        ({85, 86}, '🌨️', 'にわか雪'),
        ({95, 96, 99}, '⛈️', '雷雨'),
    ]
    for codes, emoji, label in table:
        if code in codes:
            return emoji, label
    return '❓', '—'


def parse_date(travel_date) -> date | None:
    """旅行日文字列（YYYY-MM-DD / YYYY/M/D / YYYY年M月D日）→ date。失敗時 None。"""
    m = re.search(r'(\d{4})\D+(\d{1,2})\D+(\d{1,2})', str(travel_date or ''))
    if not m:
        return None
    try:
        return date(int(m.group(1)), int(m.group(2)), int(m.group(3)))
    except ValueError:
        return None


def _num_days(duration) -> int:
    """「N泊」→ N+1日、それ以外（日帰り等）→ 1日。"""
    nm = re.search(r'(\d+)\s*泊', str(duration or ''))
    return (int(nm.group(1)) + 1) if nm else 1


def forecast(lat, lng, start: date, end: date) -> list:
    """指定地点・期間の日別予報を返す。範囲外・失敗時は []。

    返り値: [{date, emoji, label, tmax, tmin, code}, ...]
    """
    today = date.today()
    if end < today or start > today + timedelta(days=16):
        return []
    start = max(start, today)
    try:
        resp = requests.get(_URL, params={
            'latitude': lat, 'longitude': lng,
            'daily': 'weathercode,temperature_2m_max,temperature_2m_min',
            'timezone': 'Asia/Tokyo',
            'start_date': start.strftime('%Y-%m-%d'),
            'end_date': end.strftime('%Y-%m-%d'),
        }, timeout=5)
        d = resp.json().get('daily', {})
    except Exception as e:
        logger.warning("天気取得失敗: lat=%s lng=%s error=%s", lat, lng, e)
        return []

    times = d.get('time', []) or []
    codes = d.get('weathercode', []) or []
    tmax = d.get('temperature_2m_max', []) or []
    tmin = d.get('temperature_2m_min', []) or []
    days = []
    for i, t in enumerate(times):
        code = codes[i] if i < len(codes) else None
        emoji, label = describe(code)
        days.append({
            'date': t, 'emoji': emoji, 'label': label, 'code': code,
            'tmax': round(tmax[i]) if i < len(tmax) and tmax[i] is not None else None,
            'tmin': round(tmin[i]) if i < len(tmin) and tmin[i] is not None else None,
        })
    return days


def plan_forecast(plan: dict) -> list:
    """保存/共有プランの目的地（最初のスポット座標）と旅行日から予報を返す。"""
    coords = plan.get('spot_coords') or []
    loc = next((c for c in coords if c.get('lat') is not None and c.get('lng') is not None), None)
    if not loc:
        return []
    start = parse_date(plan.get('travel_date'))
    if not start:
        return []
    end = start + timedelta(days=_num_days(plan.get('duration')) - 1)
    return forecast(loc['lat'], loc['lng'], start, end)


def generation_hint(destination: str, travel_date, duration) -> str:
    """生成用：目的地をジオコーディングして予報を取り、屋内/屋外調整の指示文を返す。

    予報が取れない（日付不明・16日より先・座標不明）場合は空文字（=天気考慮なし）。
    """
    start = parse_date(travel_date)
    if not start or not destination:
        return ""
    from geocoding import geocode_one
    center = geocode_one(destination)
    if not center:
        return ""
    end = start + timedelta(days=_num_days(duration) - 1)
    days = forecast(center['lat'], center['lng'], start, end)
    if not days:
        return ""
    parts = [f"{d['date']} {d['label']}"
             + (f"({d['tmin']}〜{d['tmax']}℃)" if d['tmax'] is not None else "")
             for d in days]
    bad = any(d['code'] in _BAD_WEATHER_CODES for d in days)
    advice = (
        "雨・雪・雷が予想される日は屋内中心のスポット（美術館・博物館・水族館・"
        "屋根のある商業施設・寺社の屋内拝観等）を多めに組み、屋外の長時間滞在は避けること。"
        if bad else
        "天候は概ね良好。屋外・景観スポットも安心して組み込んでよい。"
    )
    return "【旅行日の天気予報】" + " / ".join(parts) + "。" + advice
