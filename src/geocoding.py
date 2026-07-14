"""スポット名 → 緯度経度の変換（ジオコーディング）を担う共通モジュール。

Nominatim(OpenStreetMap) を日本(countrycodes=jp)に絞って利用し、
当たらないときは国土地理院の住所検索APIへフォールバックする（どちらも無料・キー不要）。
プラン生成時のバッチ取得（geocode_spots）と、保存前データの無い旧プラン用の
オンデマンドプロキシ（/api/geocode → geocode_one）の両方から再利用される。

精度向上の工夫:
  - 表記の正規化（NFKC・空白圧縮）と、括弧注釈・末尾総称を外したゆらぎ候補で再検索
  - 候補を複数取得し、目的地中心（center）に最も近いものを採用
  - 中心から遠すぎるヒット（同名の別地）は棄却する
    （誤ピンを立てるより「未配置」にしてカスタムピンで置いてもらう方が良い）
"""
import re
import time
import unicodedata

import requests

from chat.logger import get_logger

logger = get_logger("geocoding")

_NOMINATIM_URL = "https://nominatim.openstreetmap.org/search"
# 国土地理院の住所検索API（無料・キー不要。地名・住所に強い日本特化のフォールバック）
_GSI_URL = "https://msearch.gsi.go.jp/address-search/AddressSearch"
# ブラウザからは User-Agent を設定できないため、サーバー側で必ず付与する。
_HEADERS = {"User-Agent": "tabimate/1.0 (travel planner app)", "Accept-Language": "ja"}
# Nominatim の利用規約上のレート制限（1 req/s）。モジュール全体で順守する。
_RATE_LIMIT_SEC = 1.0
_last_nominatim_at = 0.0
# 目的地中心からこれ以上離れたヒットは「同名の別地」とみなして棄却する
_MAX_DIST_KM = 120.0


def _throttle_nominatim() -> None:
    """Nominatim への全リクエストに 1 req/s を保証する（呼び出し元によらず）。"""
    global _last_nominatim_at
    wait = _RATE_LIMIT_SEC - (time.monotonic() - _last_nominatim_at)
    if wait > 0:
        time.sleep(wait)
    _last_nominatim_at = time.monotonic()


def _dist_km(lat1: float, lng1: float, lat2: float, lng2: float) -> float:
    """日本近辺用の簡易距離（km）。緯度1度≈111km、経度1度≈91km(cos35°)で近似。"""
    return (((lat1 - lat2) * 111.0) ** 2 + ((lng1 - lng2) * 91.0) ** 2) ** 0.5


def _pick_candidate(cands: list, center: tuple | None) -> dict | None:
    """候補 [{"lat","lng"},...] から採用する1件を選ぶ。

    center 指定時は最も近いものを選び、それでも遠すぎるなら None（誤マッチ扱い）。
    center 無しは先頭（プロバイダのスコア順）を返す。
    """
    if not cands:
        return None
    if not center:
        return cands[0]
    best = min(cands, key=lambda c: _dist_km(c["lat"], c["lng"], center[0], center[1]))
    if _dist_km(best["lat"], best["lng"], center[0], center[1]) > _MAX_DIST_KM:
        return None
    return best


def _query_nominatim(q: str, viewbox: str | None = None,
                     center: tuple | None = None) -> dict | None:
    """Nominatim に1回問い合わせ、採用候補の {"lat","lng"} を返す（日本に限定）。

    候補は5件まで取得し、center（目的地中心）があれば最寄りを採用・遠方は棄却。
    viewbox 指定時はその範囲を優先（bounded=0 なので範囲外も除外せず順位補正のみ）。
    失敗・該当なしは None。
    """
    try:
        params = {"q": q, "format": "json", "limit": 5, "countrycodes": "jp"}
        if viewbox:
            params["viewbox"] = viewbox
            params["bounded"] = 0
        _throttle_nominatim()
        resp = requests.get(_NOMINATIM_URL, params=params, headers=_HEADERS, timeout=3)
        data = resp.json()
        if isinstance(data, list):
            cands = [{"lat": float(d["lat"]), "lng": float(d["lon"])} for d in data]
            return _pick_candidate(cands, center)
    except Exception as e:
        logger.warning("ジオコーディング失敗(Nominatim): q=%s, error=%s", q, e)
    return None


def _query_gsi(q: str, center: tuple | None = None) -> dict | None:
    """国土地理院の住所検索でフォールバック検索する。失敗・該当なしは None。

    OSMに登録の少ない地名・施設でも当たることがある。座標形式は [lng, lat]。
    """
    try:
        resp = requests.get(_GSI_URL, params={"q": q}, headers=_HEADERS, timeout=3)
        data = resp.json()
        if isinstance(data, list):
            cands = []
            for d in data[:5]:
                coords = (d.get("geometry") or {}).get("coordinates") or []
                if len(coords) >= 2:
                    cands.append({"lat": float(coords[1]), "lng": float(coords[0])})
            return _pick_candidate(cands, center)
    except Exception as e:
        logger.warning("ジオコーディング失敗(地理院): q=%s, error=%s", q, e)
    return None


def _viewbox_around(lat: float, lng: float, pad: float = 0.4) -> str:
    """中心(lat,lng)の周囲 ±pad度の viewbox 文字列 'x1,y1,x2,y2'（x=経度,y=緯度）。"""
    return f"{lng - pad},{lat - pad},{lng + pad},{lat + pad}"


# 末尾に付くと検索でヒットしにくくなる総称（失敗時のみ外して再検索する）。
# 例: 「城崎温泉街」→「城崎温泉」 / 「祇園周辺」→「祇園」
_TRIM_SUFFIXES = ("街", "エリア", "周辺", "付近", "一帯", "地区", "地域", "界隈", "あたり")
# LLMが付けがちな括弧注釈（「兼六園（ライトアップ）」等）。外すと当たりやすい。
_PAREN_RE = re.compile(r"[（(][^（）()]*[）)]")


def _normalize(q: str) -> str:
    """全角/半角ゆれ・連続空白を吸収する（NFKC正規化＋空白圧縮）。"""
    return re.sub(r"\s+", " ", unicodedata.normalize("NFKC", q or "")).strip()


def _variants(query: str) -> list:
    """検索に使う表記ゆらぎ候補を、当たりやすい順に返す（重複は除く）。

    1. 正規化した名前そのまま
    2. 括弧注釈を外した名前（「兼六園（ライトアップ）」→「兼六園」）
    3. 末尾の総称を外した名前（「城崎温泉街」→「城崎温泉」。2の結果にも適用）
    """
    out = []

    def add(q):
        q = q.strip()
        if q and q not in out:
            out.append(q)

    add(query)
    no_paren = _PAREN_RE.sub("", query)
    add(no_paren)
    for base in (query, no_paren):
        for suf in _TRIM_SUFFIXES:
            if base.endswith(suf) and len(base) > len(suf) + 1:
                add(base[: -len(suf)])
                break
    return out


def geocode_one(query: str, context: str | None = None, viewbox: str | None = None,
                center: tuple | None = None) -> dict | None:
    """スポット名1件を緯度経度に変換する。失敗時は None。

    表記ゆらぎ候補（_variants）を順に、次の2プロバイダで段階的に検索する:
      1. Nominatim: 候補そのまま → 「候補, context」（店名など単独で当たりにくいもの向け）
      2. 国土地理院: 候補そのまま（OSM未登録の地名の救済）
    viewbox はNominatimの順位補正、center は最寄り採用と遠方誤マッチの棄却に使う。
    返り値: {"lat": float, "lng": float} もしくは None
    """
    query = _normalize(query)
    if not query:
        return None
    variants = _variants(query)
    for q in variants:
        hit = _query_nominatim(q, viewbox=viewbox, center=center)
        if hit:
            return hit
        if context:
            hit = _query_nominatim(f"{q}, {context}", viewbox=viewbox, center=center)
            if hit:
                return hit
    for q in variants:
        hit = _query_gsi(q, center=center)
        if hit:
            return hit
    return None


def geocode_spots(spots: list, known: dict | None = None, context: str | None = None,
                  viewbox: str | None = None, center: tuple | None = None) -> list:
    """スポット名のリストを順にジオコーディングし、成功したものだけ返す。

    返り値: [{"name": str, "lat": float, "lng": float}, ...]（順序は入力どおり）

    known: 既知の {name: {"lat","lng"}} を渡すと、その名前は再取得せず流用する
           （編集時に変わっていないスポットの再ジオコーディングを避ける）。
    context: 名前単独で当たらない場合の再検索キー（グルメ/宿は目的地を渡すと精度↑）。
    center: 目的地の中心 (lat, lng)。最寄り候補の採用と遠方誤マッチの棄却に使う。
    ※ Nominatim の 1 req/s は _throttle_nominatim がモジュール全体で保証する。
    """
    known = known or {}
    results = []
    for name in spots or []:
        if not name:
            continue
        hit = known.get(name)
        if hit and hit.get("lat") is not None and hit.get("lng") is not None:
            results.append({"name": name, "lat": hit["lat"], "lng": hit["lng"]})
            continue
        coords = geocode_one(name, context=context, viewbox=viewbox, center=center)
        if coords:
            results.append({"name": name, "lat": coords["lat"], "lng": coords["lng"]})
    return results


def ensure_plan_coords(plan: dict) -> dict:
    """プランの地図座標が未取得なら取得して plan に詰め、DBへ永続化する。

    地図を初めて開いたとき（＝リクエスト中）に1回だけジオコーディングし、以後は
    キャッシュを使う。保存処理をブロックしないための遅延取得。
    観光は名前のみ、グルメ/宿は目的地を文脈にして精度を上げる。
    """
    # 既に一度ジオコーディング済み（geo_done）なら何もしない。失敗カテゴリの
    # 毎回再取得（地図を開くたびに数秒）を防ぐ。編集時は geo_done が 0 に戻る。
    if plan.get("geo_done"):
        return plan

    dest = plan.get("destination")
    changed = False

    # 目的地を一度ジオコーディングして中心を得て、その周辺を優先範囲(viewbox)にする。
    # center は「最寄り候補の採用」と「同名の別地の棄却」にも使う。
    viewbox = None
    center = None
    need = any(not plan.get(f) and plan.get(n) for f, n in (
        ("spot_coords", "spots"), ("restaurant_coords", "restaurants"),
        ("accommodation_coords", "accommodation")))
    if dest and need:
        c = geocode_one(dest)
        if c:
            center = (c["lat"], c["lng"])
            viewbox = _viewbox_around(c["lat"], c["lng"])

    def fill(coord_field, name_field, context=None):
        nonlocal changed
        if plan.get(coord_field):
            return
        names = plan.get(name_field) or []
        if not names:
            return
        plan[coord_field] = geocode_spots(names, context=context, viewbox=viewbox, center=center)
        changed = True

    # context は「名前単独で失敗したとき」だけ使う（観光も含め、化けを防ぎつつ精度を上げる）
    fill("spot_coords", "spots", context=dest)
    fill("restaurant_coords", "restaurants", context=dest)
    fill("accommodation_coords", "accommodation", context=dest)

    if changed and plan.get("id"):
        from db import update_plan_coords
        # 1件でも取得できたら done として以後スキップ。全滅なら done にせず次回再試行
        # （Nominatim の一時的な不調を救う。OSM未登録だらけの場合は毎回試行になる）。
        found = bool((plan.get("spot_coords") or []) or (plan.get("restaurant_coords") or [])
                     or (plan.get("accommodation_coords") or []))
        update_plan_coords(
            plan["id"],
            plan.get("spot_coords") or [],
            plan.get("restaurant_coords") or [],
            plan.get("accommodation_coords") or [],
            geo_done=1 if found else 0,
        )
        plan["geo_done"] = 1 if found else 0
    return plan
