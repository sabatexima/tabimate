"""スポット名 → 緯度経度の変換（ジオコーディング）を担う共通モジュール。

Nominatim(OpenStreetMap) を使い、当たらないときは国土地理院の住所検索APIへ
フォールバックする（どちらも無料・キー不要）。
プラン生成時のバッチ取得（geocode_spots）と、保存前データの無い旧プラン用の
オンデマンドプロキシ（/api/geocode → geocode_one）の両方から再利用される。

国の扱い:
  行き先の国は geocode_center が決める（まず日本で探し、無ければ世界で探す）。
  スポットの検索はその国に絞る（country）。日本なら従来どおり countrycodes=jp、
  海外ならその国コード。国土地理院は日本の地名しか持たないので海外では使わない。

精度向上の工夫:
  - 表記の正規化（NFKC・空白圧縮）と、括弧注釈・末尾総称を外したゆらぎ候補で再検索
  - 候補を複数取得し、目的地中心（center）に最も近いものを採用
  - 中心から遠すぎるヒット（同名の別地）は棄却する
    （誤ピンを立てるより「未配置」にしてカスタムピンで置いてもらう方が良い）
"""
import math
import os
import re
import time
import unicodedata

import requests

from logger import get_logger

logger = get_logger("geocoding")

_NOMINATIM_URL = "https://nominatim.openstreetmap.org/search"
# 国土地理院の住所検索API（無料・キー不要。地名・住所に強い日本特化のフォールバック）
_GSI_URL = "https://msearch.gsi.go.jp/address-search/AddressSearch"
# Google Places API (New) Text Search。GOOGLE_MAPS_API_KEY 設定時のみ使う。
# OSM/地理院に載らない飲食店・宿の名前に圧倒的に強い（月あたりの無料枠あり）。
_GOOGLE_PLACES_URL = "https://places.googleapis.com/v1/places:searchText"
# ブラウザからは User-Agent を設定できないため、サーバー側で必ず付与する。
_HEADERS = {"User-Agent": "tabimate/1.0 (travel planner app)", "Accept-Language": "ja"}
# Nominatim の利用規約上のレート制限（1 req/s）。モジュール全体で順守する。
_RATE_LIMIT_SEC = 1.0
_last_nominatim_at = 0.0
# 目的地中心からこれ以上離れたヒットは「同名の別地」とみなして棄却する既定値。
# 目的地の行政界が分かる場合は _radius_from_bbox で広さに応じた半径を使う
# （金沢のような市なら狭く、北海道のような広域なら広く）。
_MAX_DIST_KM = 120.0
# 適応半径の下限/上限。下限は「市が目的地でも近郊へ足を伸ばす」旅程を守る
# （金沢→白川郷≈50km・和倉温泉≈60km）。上限は広域旅行（道内周遊など）向け。
_MIN_RADIUS_KM = 80.0
_MAX_RADIUS_KM = 300.0


def _radius_from_bbox(south: float, west: float, north: float, east: float) -> float:
    """行政界バウンディングボックスから許容半径(km)を決める（半対角×1.5をクランプ）。"""
    half_diag = _dist_km(south, west, north, east) / 2
    return min(max(half_diag * 1.5, _MIN_RADIUS_KM), _MAX_RADIUS_KM)


def _throttle_nominatim() -> None:
    """Nominatim への全リクエストに 1 req/s を保証する（呼び出し元によらず）。"""
    global _last_nominatim_at
    wait = _RATE_LIMIT_SEC - (time.monotonic() - _last_nominatim_at)
    if wait > 0:
        time.sleep(wait)
    _last_nominatim_at = time.monotonic()


def _dist_km(lat1: float, lng1: float, lat2: float, lng2: float) -> float:
    """2点間の簡易距離（km）。緯度1度≈111km、経度1度は緯度に応じて縮む（111×cos φ）。

    以前は経度を 91km/度（北緯35°の値）で固定していた。日本ではそれで合うが、
    赤道近くでは2割短く、北欧では倍近く見積もりが狂う。2点の平均緯度から求める。
    """
    mean_lat = math.radians((lat1 + lat2) / 2)
    dlng_km = (lng1 - lng2) * 111.0 * math.cos(mean_lat)
    return (((lat1 - lat2) * 111.0) ** 2 + dlng_km ** 2) ** 0.5


def _pick_candidate(cands: list, center: tuple | None,
                    max_km: float = _MAX_DIST_KM) -> dict | None:
    """候補 [{"lat","lng"},...] から採用する1件を選ぶ。

    center 指定時は最も近いものを選び、max_km より遠ければ None（誤マッチ扱い）。
    center 無しは先頭（プロバイダのスコア順）を返す。
    """
    if not cands:
        return None
    if not center:
        return cands[0]
    best = min(cands, key=lambda c: _dist_km(c["lat"], c["lng"], center[0], center[1]))
    if _dist_km(best["lat"], best["lng"], center[0], center[1]) > max_km:
        return None
    return best


def _query_nominatim(q: str, viewbox: str | None = None,
                     center: tuple | None = None,
                     max_km: float = _MAX_DIST_KM,
                     country: str | None = "jp") -> dict | None:
    """Nominatim に1回問い合わせ、採用候補の {"lat","lng"} を返す。

    country（ISO 3166-1 小文字）でその国に絞る。None なら世界中から探す。
    候補は5件まで取得し、center（目的地中心）があれば最寄りを採用・遠方は棄却。
    viewbox 指定時はその範囲を優先（bounded=0 なので範囲外も除外せず順位補正のみ）。
    失敗・該当なしは None。
    """
    try:
        params = {"q": q, "format": "json", "limit": 5}
        if country:
            params["countrycodes"] = country
        if viewbox:
            params["viewbox"] = viewbox
            params["bounded"] = 0
        _throttle_nominatim()
        resp = requests.get(_NOMINATIM_URL, params=params, headers=_HEADERS, timeout=3)
        data = resp.json()
        if isinstance(data, list):
            cands = [{"lat": float(d["lat"]), "lng": float(d["lon"])} for d in data]
            return _pick_candidate(cands, center, max_km)
    except Exception as e:
        logger.warning("ジオコーディング失敗(Nominatim): q=%s, error=%s", q, e)
    return None


def _query_gsi(q: str, center: tuple | None = None,
               max_km: float = _MAX_DIST_KM) -> dict | None:
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
            return _pick_candidate(cands, center, max_km)
    except Exception as e:
        logger.warning("ジオコーディング失敗(地理院): q=%s, error=%s", q, e)
    return None


def _first_within(cands: list, center: tuple | None,
                  max_km: float = _MAX_DIST_KM) -> dict | None:
    """関連度順の候補から、許容半径内に入る最初の1件を返す（Google用）。

    Google は関連度順に返すため、その順位を尊重しつつ遠方の同名別地だけ弾く
    （最寄り優先にすると「似た名前の近所の別店」を拾い得る）。
    """
    if not cands:
        return None
    if not center:
        return cands[0]
    for c in cands:
        if _dist_km(c["lat"], c["lng"], center[0], center[1]) <= max_km:
            return c
    return None


def _query_google_places(q: str, center: tuple | None = None,
                         max_km: float = _MAX_DIST_KM,
                         country: str | None = "jp") -> dict | None:
    """Google Places (New) の Text Search で検索する。キー未設定・失敗時は None。

    飲食店・宿など「固有の店名」はOSM/地理院ではほぼ当たらないため、
    GOOGLE_MAPS_API_KEY があるときはこれを最初に試す。
    center 指定時はその周辺を優先（locationBias の上限は半径50km）。
    country は結果の地域バイアス（regionCode）。海外の行き先ではその国を渡す。
    """
    key = os.getenv("GOOGLE_MAPS_API_KEY")
    if not key:
        return None
    try:
        body = {"textQuery": q, "languageCode": "ja"}
        if country:
            body["regionCode"] = country.upper()
        if center:
            body["locationBias"] = {"circle": {
                "center": {"latitude": center[0], "longitude": center[1]},
                "radius": min(max_km * 1000.0, 50000.0),
            }}
        resp = requests.post(_GOOGLE_PLACES_URL, json=body, timeout=4, headers={
            "X-Goog-Api-Key": key,
            # 必要なのは座標だけ。FieldMaskを絞ると安価なSKUで済む
            "X-Goog-FieldMask": "places.location",
        })
        data = resp.json()
        # キー制限・API未有効化などは例外にならず error オブジェクトで返る。
        # 静かに失敗すると原因調査ができないため、必ずログに残す。
        if resp.status_code != 200 or "error" in data:
            err = data.get("error") or {}
            logger.warning("Google Places エラー: q=%s http=%s status=%s message=%s",
                           q, resp.status_code, err.get("status"), err.get("message"))
            return None
        cands = [
            {"lat": p["location"]["latitude"], "lng": p["location"]["longitude"]}
            for p in (data.get("places") or [])[:5] if p.get("location")
        ]
        if not cands:
            logger.info("Google Places: 該当なし q=%s", q)
            return None
        hit = _first_within(cands, center, max_km)
        if hit is None:
            logger.info("Google Places: 候補%d件すべて許容半径(%.0fkm)外で棄却 q=%s",
                        len(cands), max_km, q)
        return hit
    except Exception as e:
        logger.warning("ジオコーディング失敗(Google Places): q=%s, error=%s", q, e)
    return None


def verify_place_exists(name: str, context: str | None = None,
                        country: str | None = "jp") -> bool | None:
    """Google Places で「その名前の場所が実在するか」を確認する。

    プラン生成時に、LLMが創作した店・宿を候補から落とすために使う。
    country は地域バイアス。海外の行き先で JP のままだと、実在する店を
    「見つからない」と誤って落としかねない。
    返り値: True=実在 / False=見つからない / None=検証できない（キー未設定・APIエラー）。
    None は「わからない」なので、呼び出し側は除外しないこと。
    """
    key = os.getenv("GOOGLE_MAPS_API_KEY")
    if not key:
        return None
    q = _normalize(f"{name} {context}" if context else name)
    if not q:
        return None
    try:
        body = {"textQuery": q, "languageCode": "ja"}
        if country:
            body["regionCode"] = country.upper()
        resp = requests.post(_GOOGLE_PLACES_URL, json=body, timeout=4, headers={
            "X-Goog-Api-Key": key,
            "X-Goog-FieldMask": "places.location",
        })
        data = resp.json()
        if resp.status_code != 200 or "error" in data:
            err = data.get("error") or {}
            logger.warning("Google Places エラー(実在確認): q=%s http=%s status=%s message=%s",
                           q, resp.status_code, err.get("status"), err.get("message"))
            return None
        return bool(data.get("places"))
    except Exception as e:
        logger.warning("実在確認失敗(Google Places): q=%s error=%s", q, e)
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


def _variants(query: str, overseas: bool = False) -> list:
    """検索に使う表記ゆらぎ候補を、当たりやすい順に返す（重複は除く）。

    1. 正規化した名前そのまま
    2. 括弧注釈を外した名前（「兼六園（ライトアップ）」→「兼六園」）
    3. 末尾の総称を外した名前（「城崎温泉街」→「城崎温泉」。2の結果にも適用）

    overseas のときは、括弧の中身を**最初**に試す。海外の名前はエージェントが
    「日本語名（現地語名）」の形で書く（例: エッフェル塔（Tour Eiffel））。
    地図データに載っているのは現地語名なので、そちらが最も当たりやすい。
    """
    out = []

    def add(q):
        """重複と空文字を避けて候補に足す（試す順番は保つ）。"""
        q = q.strip()
        if q and q not in out:
            out.append(q)

    if overseas:
        for m in _PAREN_RE.finditer(query):
            add(m.group(0)[1:-1])
    add(query)
    no_paren = _PAREN_RE.sub("", query)
    add(no_paren)
    for base in (query, no_paren):
        for suf in _TRIM_SUFFIXES:
            if base.endswith(suf) and len(base) > len(suf) + 1:
                add(base[: -len(suf)])
                break
    return out


def geocode_center(query: str) -> dict | None:
    """目的地の中心座標・広さに応じた許容半径(km)・国コードを返す。失敗時は None。

    まず日本に絞って探し、当たらなければ世界で探す。日本の地名を先に見るのは、
    「パリ」のような曖昧さの無い名前でも、国内の同名地（例: 大阪の「アメリカ村」）を
    国内旅行の文脈で正しく拾うため。海外の行き先はここで初めて分かる。

    Nominatim の boundingbox（行政界）から半径を適応的に決める：
    市が目的地なら狭く（誤マッチに厳しく）、都道府県・広域なら広く
    （道内周遊の知床のような遠方の正解を弾かない）。
    返り値: {"lat": float, "lng": float, "radius_km": float, "country_code": str}
            country_code は ISO 3166-1 の小文字（"jp", "fr" …）。不明なら ""。
    """
    q = _normalize(query)
    if not q:
        return None
    for country in ("jp", None):
        try:
            params = {"q": q, "format": "json", "limit": 1, "addressdetails": 1}
            if country:
                params["countrycodes"] = country
            _throttle_nominatim()
            resp = requests.get(_NOMINATIM_URL, params=params, headers=_HEADERS, timeout=3)
            data = resp.json()
        except Exception as e:
            logger.warning("ジオコーディング失敗(中心取得): q=%s, error=%s", q, e)
            return None  # 通信の不調なら2周目も同じなので、待たずに諦める
        if isinstance(data, list) and data:
            d = data[0]
            radius = _MAX_DIST_KM
            bb = d.get("boundingbox")
            if bb and len(bb) == 4:
                south, north, west, east = (float(x) for x in bb)
                radius = _radius_from_bbox(south, west, north, east)
            cc = ((d.get("address") or {}).get("country_code") or country or "").lower()
            return {"lat": float(d["lat"]), "lng": float(d["lon"]),
                    "radius_km": radius, "country_code": cc}
    return None


def is_overseas(country_code: str | None) -> bool:
    """国コードが「日本以外の判明した国」なら True。不明（空）は国内扱い。"""
    return bool(country_code) and country_code.lower() != "jp"


# 見つからなかった名前を一定時間おぼえて、地図を開くたびの再検索を抑える
# （プロセス内・TTL付き）。API不調による失敗を永久に焼き付けないよう、
# DBには保存せず時間経過とインスタンス再起動で自然に再試行へ戻る。
_NEG_TTL_SEC = 6 * 3600
_neg_cache: dict = {}


def _neg_key(query: str, context: str | None) -> str:
    """「見つからなかった」を覚えるキー。同じ地名でも文脈が違えば別扱いにする。"""
    return f"{query}\x00{context or ''}"


def geocode_one(query: str, context: str | None = None, viewbox: str | None = None,
                center: tuple | None = None,
                max_km: float = _MAX_DIST_KM,
                country: str | None = "jp") -> dict | None:
    """スポット名1件を緯度経度に変換する。失敗時は None。

    プロバイダの優先順:
      0. Google Places（GOOGLE_MAPS_API_KEY 設定時のみ）: 店名・宿名に圧倒的に強い
      1. Nominatim: 表記ゆらぎ候補そのまま → 「候補, context」
      2. 国土地理院: 候補そのまま（OSM未登録の地名の救済。日本のみ）
    viewbox はNominatimの順位補正、center は最寄り採用と遠方誤マッチの棄却に使う。
    country は行き先の国（geocode_center が返す country_code）。海外ではその国に絞り、
    表記ゆらぎでは括弧内の現地語名を先に試す。
    返り値: {"lat": float, "lng": float} もしくは None
    """
    query = _normalize(query)
    if not query:
        return None
    overseas = is_overseas(country)
    # 直近に全プロバイダで外れた名前はTTL内は再検索しない（毎回の待ち時間とAPI消費を抑える）
    key = _neg_key(query, context)
    failed_at = _neg_cache.get(key)
    if failed_at and (time.monotonic() - failed_at) < _NEG_TTL_SEC:
        return None
    # Google はあいまいな表記に強いので、1回だけ「名前＋目的地」で当てにいく
    hit = _query_google_places(f"{query} {context}" if context else query,
                               center=center, max_km=max_km, country=country)
    if hit:
        _neg_cache.pop(key, None)
        return hit
    variants = _variants(query, overseas=overseas)
    for q in variants:
        hit = _query_nominatim(q, viewbox=viewbox, center=center, max_km=max_km, country=country)
        if hit is None and context:
            hit = _query_nominatim(f"{q}, {context}", viewbox=viewbox, center=center,
                                   max_km=max_km, country=country)
        if hit:
            _neg_cache.pop(key, None)
            return hit
    if not overseas:  # 国土地理院は日本の地名しか持たない
        for q in variants:
            hit = _query_gsi(q, center=center, max_km=max_km)
            if hit:
                _neg_cache.pop(key, None)
                return hit
    _neg_cache[key] = time.monotonic()
    return None


def geocode_spots(spots: list, known: dict | None = None, context: str | None = None,
                  viewbox: str | None = None, center: tuple | None = None,
                  max_km: float = _MAX_DIST_KM, country: str | None = "jp") -> list:
    """スポット名のリストを順にジオコーディングし、成功したものだけ返す。

    返り値: [{"name": str, "lat": float, "lng": float}, ...]（順序は入力どおり）

    known: 既知の {name: {"lat","lng"}} を渡すと、その名前は再取得せず流用する
           （編集時に変わっていないスポットの再ジオコーディングを避ける）。
    context: 名前単独で当たらない場合の再検索キー（グルメ/宿は目的地を渡すと精度↑）。
    center: 目的地の中心 (lat, lng)。最寄り候補の採用と遠方誤マッチの棄却に使う。
    country: 行き先の国コード。海外ならその国に絞って探す。
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
        coords = geocode_one(name, context=context, viewbox=viewbox, center=center,
                             max_km=max_km, country=country)
        if coords:
            results.append({"name": name, "lat": coords["lat"], "lng": coords["lng"]})
    return results


def ensure_plan_coords(plan: dict) -> dict:
    """プランの地図座標が未取得なら取得して plan に詰め、DBへ永続化する。

    地図を初めて開いたとき（＝リクエスト中）に1回だけジオコーディングし、以後は
    キャッシュを使う。保存処理をブロックしないための遅延取得。
    観光は名前のみ、グルメ/宿は目的地を文脈にして精度を上げる。
    """
    # 既に一度ジオコーディング済み（geo_done）なら基本は何もしない。失敗分の
    # 毎回再取得（地図を開くたびに数秒）を防ぐ。編集時は geo_done が 0 に戻る。
    # 例外: Google Places キーが使えるときは、「まだ座標が付いていない名前」だけ
    # 再挑戦する（キー導入前に諦めた旧プランの飲食店・宿を救済するため。
    # それでも当たらない名前は開くたび数件の再検索になるが、コストは小さい）。
    if plan.get("geo_done") and not os.getenv("GOOGLE_MAPS_API_KEY"):
        return plan

    dest = plan.get("destination")
    changed = False

    # 既に座標が付いている名前は再検索しない。足りない名前だけを対象にする
    # （「グルメ3軒中1軒だけ当たった」プランの残り2軒を救済できるように、
    #  カテゴリ単位ではなく名前単位で判定する）。
    def _existing(coord_field):
        """すでに座標が付いている名前 → その座標。"""
        return {c["name"]: c for c in (plan.get(coord_field) or [])
                if c and c.get("name") and c.get("lat") is not None}

    def _missing(coord_field, name_field):
        """まだ座標が無い名前だけを返す（ここが問い合わせの対象）。"""
        done = _existing(coord_field)
        return [n for n in (plan.get(name_field) or []) if n and n not in done]

    fields = (("spot_coords", "spots"), ("restaurant_coords", "restaurants"),
              ("accommodation_coords", "accommodation"))

    # 目的地を一度ジオコーディングして中心を得て、その周辺を優先範囲(viewbox)にする。
    # center は「最寄り候補の採用」に、max_km（目的地の広さに応じた許容半径）は
    # 「同名の別地の棄却」に使う。
    viewbox = None
    center = None
    max_km = _MAX_DIST_KM
    country = "jp"  # 中心が取れなければ従来どおり日本として探す
    if dest and any(_missing(f, n) for f, n in fields):
        c = geocode_center(dest)
        if c:
            center = (c["lat"], c["lng"])
            max_km = c["radius_km"]
            country = c.get("country_code") or "jp"
            # 優先範囲も許容半径に合わせて広げる（1度≈91〜111km）
            viewbox = _viewbox_around(c["lat"], c["lng"], pad=max(0.4, max_km / 100))

    def fill(coord_field, name_field, context=None):
        """1カテゴリぶん（観光・グルメ・宿）の座標を埋める。

        足りない名前だけを問い合わせ、取れたものを plan に書き戻す。
        1件も取れなくても他のカテゴリは続ける。
        """
        nonlocal changed
        missing = _missing(coord_field, name_field)
        if not missing:
            return
        # 部分的にでも取得済みで、Google Places が使えない場合は再試行しない
        # （無料スタックだけで外れた名前は次も外れる可能性が高く、開くたびに遅くなるだけ）
        if plan.get(coord_field) and not os.getenv("GOOGLE_MAPS_API_KEY"):
            return
        logger.info("座標を取得: plan_id=%s %s=%s", plan.get("id"), name_field, missing)
        names = plan.get(name_field) or []
        plan[coord_field] = geocode_spots(names, known=_existing(coord_field),
                                          context=context, viewbox=viewbox,
                                          center=center, max_km=max_km, country=country)
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
