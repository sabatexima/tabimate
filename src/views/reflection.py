"""旅の振り返り機能（Blueprint）。

機能A: 謎アチーブメント（短い解釈）／機能B: AI旅レポート（長い解釈）を
共通の解釈エンジン（services/trip_interpreter）経由で提供する。

設計方針:
- 旅の最中には何も要求しない。価値は「あとから」与える（不便益）。
- 称号の獲得条件はユーザーに開示しない（狙って取れないように）。
- コスト最優先: 安価モデル＋メタデータのみ送信。画像送付は任意（既定オフ）。
"""
import os

from flask import (Blueprint, Response, abort, jsonify, render_template,
                   request, session)

import db_reflection as repo
from chat.logger import get_logger
from services import exif, features, images, storage, trip_interpreter
from views.auth import login_required

reflection = Blueprint("reflection", __name__, url_prefix="/reflection")
logger = get_logger("views.reflection")

# 1リクエストあたりの写真枚数・サイズの上限（コスト/メモリ保護）
_MAX_FILES_PER_REQUEST = 50
_ALLOWED_EXT = {".jpg", ".jpeg", ".png", ".heic", ".webp", ".gif"}


def _uid() -> str:
    """現在ログイン中のユーザーIDを返す（短縮ヘルパ）。"""
    return session.get("user_id")


def _require_trip(trip_id: int) -> dict:
    """本人所有の旅でなければ 404。所有していれば trip dict を返す。"""
    trip = repo.get_trip(trip_id, _uid())
    if not trip:
        abort(404)
    return trip


def _collect_images_for_stickers(photos: list, sample_n: int = 8) -> list:
    """付箋生成のため、代表画像のバイト列を集める。

    付箋は写真の中身に根ざすので画像送付は必須（オプション判定はしない）。
    コスト保護のため全枚数は送らず、均等サンプリングで数枚に絞る。
    実際の枚数上限・縮小は解釈エンジン側でも担保する。
    """
    if not photos:
        return []
    # 旅全体を均等にカバーするようサンプリング（エンジン側で更に上限へ絞る）
    sample_n = min(sample_n, len(photos))
    step = max(1, len(photos) // sample_n)
    sampled = photos[::step][:sample_n]
    images = []
    for p in sampled:
        data = storage.read_bytes(p["storage_path"])
        if data:
            images.append(data)
    logger.info("付箋用の代表画像を収集: %d枚", len(images))
    return images


# ----------------------------------------------------------------------
# 画面（UIの詳細はテンプレート側。ここでは入口のみ）
# ----------------------------------------------------------------------
def _load_trip_cards() -> tuple[list, list]:
    """一覧に出す（自分の旅, 共有された旅）を、表紙URL付きで返す。

    画面（index）とアプリ向けJSON（api_trips）で同じものを見せるため、
    取得の仕方をここ1か所に置く。
    """
    trips = repo.get_trips(_uid())

    # 自分宛に共有された旅も同じ画面にまとめて表示する
    import db_sharing
    grants = db_sharing.get_grants_for_email(session.get("user_email"))
    shared_ids = [g["resource_id"] for g in grants if g["resource_type"] == "trip"]
    perm_by_id = {g["resource_id"]: g["permission"] for g in grants if g["resource_type"] == "trip"}
    grant_by_id = {g["resource_id"]: g["id"] for g in grants if g["resource_type"] == "trip"}
    shared_trips = repo.get_trip_cards(shared_ids, viewer_id=_uid()) if shared_ids else []
    for t in shared_trips:
        t["permission"] = perm_by_id.get(t["id"], "view")
        t["grant_id"] = grant_by_id.get(t["id"])

    # 一覧カードの表紙は、サムネイル＋（フォールバック用に）原寸URLをまとめて取得
    cover_paths = [t["cover_path"] for t in trips + shared_trips if t.get("cover_path")]
    cover_thumbs = storage.get_thumb_urls(cover_paths)
    cover_fulls = storage.get_urls(cover_paths)
    for t in trips + shared_trips:
        cp = t.get("cover_path")
        t["cover_url"] = cover_thumbs.get(cp) if cp else None
        t["cover_url_full"] = cover_fulls.get(cp) if cp else None

    return trips, shared_trips


@reflection.route("/")
@login_required
def index():
    """旅の振り返り一覧（自分の旅＋共有された旅）を表示する。"""
    trips, shared_trips = _load_trip_cards()
    return render_template("reflection/index.html", trips=trips, shared_trips=shared_trips)


@reflection.route("/api/trips")
@login_required
def api_trips():
    """振り返り一覧をJSONで返す（ネイティブアプリ用）。"""
    trips, shared_trips = _load_trip_cards()
    return jsonify({"trips": trips, "shared_trips": shared_trips})


@reflection.route("/api/trips/<int:trip_id>")
@login_required
def api_trip_detail(trip_id: int):
    """1つの旅の中身をJSONで返す（写真・付箋・ベストショット・足あと）。

    共有された旅も開けるようにする（一覧に出しておいて開けないのはおかしいため）。
    その場合は権限を添えて、アプリ側が編集の可否を判断できるようにする。
    """
    if not _can_view_trip(trip_id):
        abort(404)
    # 所有者フィルタを通さずに取り、一覧カードと同じ形（写真枚数・表紙など）にそろえる
    cards = repo.get_trip_cards([trip_id], viewer_id=_uid())
    if not cards:
        abort(404)
    # 重ね合わせはアプリの画面に無いので、その材料集め（プラン一覧・座標取得）は省く
    data = _trip_detail_data(trip_id, trip=cards[0], include_plan_link=False)

    trip = dict(data["trip"], photo_count=len(data["photos"]))
    if not repo.get_trip(trip_id, _uid()):
        import db_sharing
        grant = db_sharing.get_grant_for_email("trip", trip_id, session.get("user_email"))
        trip["permission"] = (grant or {}).get("permission", "view")
    return jsonify({
        "trip": trip,
        "photos": data["photos"],
        "stickers": data["stickers"],
        "best_shots": data["best_shots"],
        "footprints": data["footprints"],
    })


@reflection.route("/api/digest")
@login_required
def api_digest():
    """年間ダイジェストをJSONで返す（年の一覧つき）。"""
    data = _digest_data(request.args.get("year") or "")
    return jsonify({
        "year": data["year"],
        "years": data["years"],
        "trips": data["trips"],
        "photo_total": data["photo_total"],
        "stickers": data["stickers"],
    })


def _digest_data(requested_year: str) -> dict:
    """年間ダイジェストの材料を組み立てる（画面とアプリで共用）。"""
    from datetime import date

    all_trips = repo.get_trips(_uid())

    def trip_year(t: dict) -> str:
        d = t.get("start_date") or t.get("created_at") or ""
        return str(d)[:4]

    years = sorted({trip_year(t) for t in all_trips if trip_year(t)}, reverse=True)
    year = requested_year
    if year not in years:
        year = years[0] if years else str(date.today().year)

    trips = [t for t in all_trips if trip_year(t) == year]
    # タイムラインは日付の古い順（日付未設定は作成日で代用済み）
    trips.sort(key=lambda t: str(t.get("start_date") or t.get("created_at") or ""))

    # 表紙サムネイル
    cover_paths = [t["cover_path"] for t in trips if t.get("cover_path")]
    cover_thumbs = storage.get_thumb_urls(cover_paths)
    for t in trips:
        cp = t.get("cover_path")
        t["cover_url"] = cover_thumbs.get(cp) if cp else None

    # 月ごとにまとめる（旅がある月だけ）
    months: dict[int, list] = {}
    for t in trips:
        d = str(t.get("start_date") or t.get("created_at") or "")
        try:
            m = int(d[5:7])
        except ValueError:
            m = 0
        months.setdefault(m, []).append(t)
    month_groups = [(m, months[m]) for m in sorted(months)]

    return {
        "year": year,
        "years": years,
        "trips": trips,
        "month_groups": month_groups,
        "photo_total": sum(t.get("photo_count") or 0 for t in trips),
        "stickers": [s for t in trips for s in (t.get("stickers_preview") or [])],
    }


@reflection.route("/digest")
@login_required
def digest():
    """年間ダイジェスト：その年の旅・写真・付箋を絵本の1ページにまとめて見せる。"""
    d = _digest_data(request.args.get("year") or "")
    return render_template(
        "reflection/digest.html",
        year=d["year"], years=d["years"], trips=d["trips"],
        month_groups=d["month_groups"], photo_total=d["photo_total"],
        stickers=d["stickers"],
    )


def _trip_detail_data(trip_id: int, trip: dict | None = None,
                      include_plan_link: bool = True) -> dict:
    """1つの旅の中身を集める（画面とアプリで共用）。

    trip を渡さない場合は本人所有であることを要求する。共有された旅を見せるときは
    呼び出し側で閲覧資格を確かめ、取得済みの trip を渡すこと。
    include_plan_link=False で「プランとの重ね合わせ」の材料集めを省く。
    """
    if trip is None:
        trip = _require_trip(trip_id)
    photos = repo.get_photos(trip_id)
    # 配信URLを付与（一覧はサムネイル、拡大は原寸。署名はキャッシュ＋並列でまとめて取得）
    paths = [p["storage_path"] for p in photos]
    url_map = storage.get_urls(paths)
    thumb_map = storage.get_thumb_urls(paths)
    for p in photos:
        p["url"] = url_map.get(p["storage_path"])
        p["thumb_url"] = thumb_map.get(p["storage_path"])
    stickers = repo.get_stickers(trip_id)

    # ちゃむのベストショット（保存済みなら photo_id → 表示URL を解決して渡す）
    best_shots = []
    raw_best = trip.get("best_shots")
    if isinstance(raw_best, str):
        try:
            import json as _json
            raw_best = _json.loads(raw_best)
        except Exception:
            raw_best = []
    if raw_best:
        by_id = {p["id"]: p for p in photos}  # 削除済みの写真は自然に除外される
        for b in raw_best:
            p = by_id.get(b.get("photo_id"))
            if p:
                best_shots.append({
                    "url": p.get("url"), "thumb_url": p.get("thumb_url"),
                    "reason": b.get("reason", ""),
                })
    # 撮影地マップ用：GPS のある写真だけを撮影時刻順に並べた「足あと」点列
    footprints = [
        {
            "lat": p["lat"], "lng": p["lng"],
            "thumb": p.get("thumb_url") or p.get("url"),
            "taken": str(p["taken_at"]) if p.get("taken_at") else None,
        }
        for p in photos
        if p.get("lat") is not None and p.get("lng") is not None
    ]
    footprints.sort(key=lambda x: x["taken"] or "")

    # 実績↔プランの重ね合わせ：紐付け用に自分のプラン一覧と、紐付け済みプランの
    # 観光スポット座標（計画地点）を渡す。
    # この処理はプラン一覧の取得に加え、未取得なら座標の取得（外部API）まで行うため、
    # 重ね合わせを使わない呼び出し（アプリ向けJSON）では丸ごと省く。
    my_plans, planned = [], []
    linked_plan_id = trip.get("linked_plan_id")
    if include_plan_link:
        from db import get_travel_plans, get_travel_plan_by_id
        my_plans = [{"id": p["id"], "destination": p.get("destination") or "（無題）"}
                    for p in get_travel_plans(_uid())]
        if linked_plan_id:
            lp = get_travel_plan_by_id(linked_plan_id)
            if lp and lp.get("google_user_id") == _uid():
                # 旧プランで座標未取得でも重ね合わせが出るよう、ここで取得・キャッシュ
                from geocoding import ensure_plan_coords
                ensure_plan_coords(lp)
                planned = lp.get("spot_coords") or []
            else:
                linked_plan_id = None  # 紐付け先が消えている/他人のものなら無効化
    return {
        "trip": trip, "photos": photos, "stickers": stickers,
        "footprints": footprints, "best_shots": best_shots,
        "my_plans": my_plans, "linked_plan_id": linked_plan_id,
        "planned_points": planned,
    }


@reflection.route("/trips/<int:trip_id>")
@login_required
def trip_detail(trip_id: int):
    """1つの旅の詳細（写真タイムライン・付箋など）を表示する。"""
    d = _trip_detail_data(trip_id)
    return render_template(
        "reflection/trip.html",
        trip=d["trip"], photos=d["photos"], stickers=d["stickers"],
        footprints=d["footprints"], my_plans=d["my_plans"],
        linked_plan_id=d["linked_plan_id"], planned_points=d["planned_points"],
        best_shots=d["best_shots"],
    )


# ----------------------------------------------------------------------
# trips API
# ----------------------------------------------------------------------
@reflection.route("/trips", methods=["POST"])
@login_required
def create_trip():
    """新しい旅（振り返り）を作成する。タイトル必須。"""
    data = request.get_json(silent=True) or request.form
    title = (data.get("title") or "").strip()
    if not title:
        return jsonify({"error": "タイトルは必須です"}), 400
    start_date = data.get("start_date") or None
    end_date = data.get("end_date") or None
    trip_id = repo.create_trip(_uid(), title, start_date, end_date)
    logger.info("旅を作成: trip_id=%s user=%s", trip_id, _uid())
    return jsonify({"id": trip_id, "title": title}), 201


@reflection.route("/trips/<int:trip_id>", methods=["PATCH"])
@login_required
def update_trip(trip_id: int):
    """旅の情報（タイトル / 出発日・帰宅日 / 一覧の表紙写真）を後から編集する。"""
    _require_trip(trip_id)
    data = request.get_json(silent=True) or request.form
    # 表紙写真の更新（null/空文字で解除＝最古の写真に戻す）
    if "cover_photo_id" in data:
        raw = data.get("cover_photo_id")
        photo_id = None
        if raw not in (None, "", "null"):
            try:
                photo_id = int(raw)
            except (TypeError, ValueError):
                return jsonify({"error": "cover_photo_id が不正です"}), 400
        ok = repo.set_trip_cover(trip_id, _uid(), photo_id)
        if not ok:
            return jsonify({"error": "この旅の写真ではありません"}), 400
        logger.info("旅の表紙変更: trip_id=%s photo_id=%s user=%s", trip_id, photo_id, _uid())
        return jsonify({"updated": True, "cover_photo_id": photo_id})
    # 日付の更新（start_date / end_date のいずれかが含まれていれば日付モード）
    if "start_date" in data or "end_date" in data:
        start_date = (data.get("start_date") or "").strip() or None
        end_date = (data.get("end_date") or "").strip() or None
        if start_date and end_date and end_date < start_date:
            return jsonify({"error": "帰宅日は出発日以降にしてください"}), 400
        ok = repo.update_trip_dates(trip_id, _uid(), start_date, end_date)
        logger.info("旅の日程変更: trip_id=%s user=%s", trip_id, _uid())
        return jsonify({"updated": ok, "start_date": start_date, "end_date": end_date})
    # タイトルの更新
    title = (data.get("title") or "").strip()
    if not title:
        return jsonify({"error": "タイトルは必須です"}), 400
    ok = repo.rename_trip(trip_id, _uid(), title)
    logger.info("旅のタイトル変更: trip_id=%s user=%s", trip_id, _uid())
    return jsonify({"updated": ok, "title": title})


@reflection.route("/trips/<int:trip_id>/linked-plan", methods=["PATCH"])
@login_required
def update_trip_linked_plan(trip_id: int):
    """旅に旅行プランを紐付け／解除する（実績↔プランの重ね合わせ用）。"""
    _require_trip(trip_id)
    data = request.get_json(silent=True) or {}
    raw = data.get("plan_id")
    plan_id = None
    if raw not in (None, "", "none"):
        try:
            plan_id = int(raw)
        except (TypeError, ValueError):
            return jsonify({"error": "plan_id が不正です"}), 400
        # 紐付け先は自分のプランに限定する
        from db import get_travel_plan_by_id
        lp = get_travel_plan_by_id(plan_id)
        if not lp or lp.get("google_user_id") != _uid():
            return jsonify({"error": "プランが見つかりません"}), 404
    ok = repo.set_trip_linked_plan(trip_id, _uid(), plan_id)
    logger.info("旅のプラン紐付け: trip_id=%s plan_id=%s user=%s", trip_id, plan_id, _uid())
    return jsonify({"updated": ok, "plan_id": plan_id})


def _can_view_trip(trip_id: int) -> bool:
    """この旅を本人が見られるか（所有者 or 共有を受けている）。

    お気に入りはユーザー単位なので、所有者だけでなく共有された閲覧者も
    自分のお気に入りとして登録できる。閲覧資格をここで確認する。
    """
    if repo.get_trip(trip_id, _uid()):
        return True
    import db_sharing
    grant = db_sharing.get_grant_for_email("trip", trip_id, session.get("user_email"))
    return grant is not None


@reflection.route("/trips/<int:trip_id>/favorite", methods=["PATCH"])
@login_required
def toggle_favorite(trip_id: int):
    """旅のお気に入り状態を切り替える（所有者・共有された閲覧者の双方が可能）。

    お気に入りはユーザー単位（trip_favorites）で保持する。
    body の favorite が与えられればその値に、無ければ現在値を反転する。
    """
    if not _can_view_trip(trip_id):
        abort(404)
    data = request.get_json(silent=True) or {}
    if "favorite" in data:
        favorite = bool(data.get("favorite"))
    else:
        favorite = not repo.is_trip_favorite(_uid(), trip_id)
    repo.set_trip_favorite(trip_id, _uid(), favorite)
    logger.info("お気に入り更新: trip_id=%s user=%s favorite=%s", trip_id, _uid(), favorite)
    return jsonify({"is_favorite": favorite})


@reflection.route("/trips/<int:trip_id>", methods=["DELETE"])
@login_required
def delete_trip(trip_id: int):
    """旅とその関連データ（写真・称号・レポート）をまとめて削除する。

    DBレコードを消す前に、ストレージ上の写真実体も削除して
    孤立ファイル（無駄なコスト）を残さないようにする。
    """
    _require_trip(trip_id)
    # 先に写真の実体をストレージから削除（DB削除後はパスが取れなくなるため）
    photos = repo.get_photos(trip_id)
    for p in photos:
        storage.delete(p["storage_path"])
    ok = repo.delete_trip(trip_id, _uid())
    logger.info("旅を削除: trip_id=%s user=%s photos=%d", trip_id, _uid(), len(photos))
    return jsonify({"deleted": ok})


# ----------------------------------------------------------------------
# 写真アップロード（保存＋メタデータ抽出）
# ----------------------------------------------------------------------
@reflection.route("/trips/<int:trip_id>/photos", methods=["POST"])
@login_required
def upload_photos(trip_id: int):
    """旅に写真を複数アップロードし、保存しつつEXIF（撮影日時・位置）を抽出する。"""
    _require_trip(trip_id)
    files = request.files.getlist("photos") or request.files.getlist("photo")
    if not files:
        return jsonify({"error": "写真が選択されていません"}), 400
    if len(files) > _MAX_FILES_PER_REQUEST:
        return jsonify({"error": f"一度にアップロードできるのは{_MAX_FILES_PER_REQUEST}枚までです"}), 400

    saved = []
    for f in files:
        if not f or not f.filename:
            continue
        ext = os.path.splitext(f.filename)[1].lower()
        # 許可拡張子のみ受け入れる（拡張子なしも拒否。MIMEだけに頼らない）。
        if ext not in _ALLOWED_EXT:
            logger.debug("非対応拡張子をスキップ: %s", f.filename)
            continue
        data = f.read()
        if not data:
            continue
        meta = exif.extract(data)  # EXIFは元データから取得（HEICもpillow-heifで開ければ取れる）
        # HEIC等はJPEGへ正規化（ブラウザ表示できない問題を防ぐ）
        data, ctype, _ext = images.normalize(data, f.filename)
        filename = f.filename
        if ctype == "image/jpeg":
            filename = os.path.splitext(f.filename)[0] + ".jpg"
        storage_path = storage.save(
            _uid(), trip_id, filename, data,
            content_type=ctype or f.mimetype or "application/octet-stream",
        )
        # 一覧表示用のサムネイルを生成・保存（失敗時は原寸へフォールバック）
        thumb = images.thumbnail(data)
        if thumb:
            storage.save_at(storage._thumb_key(storage_path), thumb, "image/jpeg")
        photo_id = repo.add_photo(
            trip_id, _uid(), storage_path,
            taken_at=meta.get("taken_at"),
            lat=meta.get("lat"), lng=meta.get("lng"),
        )
        original_url = storage.get_url(storage_path)
        saved.append({
            "id": photo_id,
            "url": original_url,
            "thumb_url": storage.get_thumb_url(storage_path) if thumb else original_url,
            "taken_at": str(meta["taken_at"]) if meta.get("taken_at") else None,
            "lat": meta.get("lat"), "lng": meta.get("lng"),
        })

    logger.info("写真アップロード完了: trip_id=%s count=%d", trip_id, len(saved))
    return jsonify({"saved": saved, "count": len(saved)}), 201


@reflection.route("/trips/<int:trip_id>/photos/<int:photo_id>", methods=["DELETE"])
@login_required
def delete_photo(trip_id: int, photo_id: int):
    """写真を1枚削除する（本人の旅のみ）。ストレージ実体も消す。"""
    _require_trip(trip_id)
    storage_path = repo.delete_photo(photo_id, trip_id)
    if storage_path is None:
        return jsonify({"deleted": False}), 404
    storage.delete(storage_path)
    logger.info("写真を削除: trip_id=%s photo_id=%s", trip_id, photo_id)
    return jsonify({"deleted": True})


# ----------------------------------------------------------------------
# ローカルFS保存写真の配信（GCS時は使わない）
# ----------------------------------------------------------------------
@reflection.route("/photo/<path:storage_path>")
@login_required
def serve_local_photo(storage_path: str):
    """ローカル保存の写真を本人にのみ配信する（GCS運用時は使わない）。"""
    # storage_path 形式: trips/{trip_id}/{user_id}/{uuid}.ext
    # 本人の写真のみ配信（パスの user_id セグメントで照合）
    parts = storage_path.split("/")
    if len(parts) < 3 or parts[2] != _uid():
        abort(404)
    data = storage.read_local(storage_path)
    if data is None:
        abort(404)
    return Response(data, mimetype="image/jpeg")


# ----------------------------------------------------------------------
# 付箋（sticker）― アプリの主役
# ----------------------------------------------------------------------
@reflection.route("/trips/<int:trip_id>/stickers/generate", methods=["POST"])
@login_required
def generate_stickers(trip_id: int):
    """写真から特徴量を集計し、AIで旅の思い出を「付箋」の言葉に生成して保存する。"""
    _require_trip(trip_id)
    photos = repo.get_photos(trip_id)
    if not photos:
        return jsonify({"error": "写真を入れると付箋を作れます"}), 400
    feat = features.aggregate(photos)
    images = _collect_images_for_stickers(photos)
    items, usage = trip_interpreter.interpret_stickers(feat, images=images)
    repo.replace_stickers(trip_id, items)
    logger.info("付箋生成: trip_id=%s count=%d tokens(in/out)=%d/%d",
                trip_id, len(items), usage["input_tokens"], usage["output_tokens"])
    # 付箋の言葉のみ返す。basis（生成根拠）・トークン等の内部情報は返さない。
    return jsonify({"stickers": [{"text": it["text"]} for it in items]})


@reflection.route("/trips/<int:trip_id>/best_shots", methods=["POST"])
@login_required
def generate_best_shots(trip_id: int):
    """写真から、ちゃむが「飾りたいいちばんの一枚」を選んで保存する。"""
    _require_trip(trip_id)
    photos = repo.get_photos(trip_id)
    if len(photos) < 3:
        return jsonify({"error": "写真が3枚以上あると、ベストショットを選べます"}), 400
    # 旅全体を均等サンプリングしつつ、選ばれた画像→写真を特定できるよう対応を保つ
    sample_n = min(12, len(photos))
    step = max(1, len(photos) // sample_n)
    sampled = photos[::step][:sample_n]
    images, valid = [], []
    for p in sampled:
        data = storage.read_bytes(p["storage_path"])
        if data:
            images.append(data)
            valid.append(p)
    if len(images) < 3:
        return jsonify({"error": "写真を読み込めませんでした。もう一度お試しください。"}), 400
    picks, usage = trip_interpreter.select_best_photos(images)
    best = [{"photo_id": valid[pk["index"]]["id"], "reason": pk["reason"]}
            for pk in picks if pk["index"] < len(valid)]
    repo.set_trip_best_shots(trip_id, _uid(), best)
    logger.info("ベストショット選出: trip_id=%s picks=%d tokens(in/out)=%d/%d",
                trip_id, len(best), usage.get("input_tokens", 0), usage.get("output_tokens", 0))
    return jsonify({"count": len(best)})


@reflection.route("/trips/<int:trip_id>/stickers", methods=["GET"])
@login_required
def list_stickers(trip_id: int):
    """旅の付箋一覧をJSONで返す。"""
    _require_trip(trip_id)
    return jsonify({"stickers": repo.get_stickers(trip_id)})


@reflection.route("/trips/<int:trip_id>/stickers/<int:sticker_id>", methods=["DELETE"])
@login_required
def delete_sticker(trip_id: int, sticker_id: int):
    """旅の付箋を1枚削除する。"""
    _require_trip(trip_id)
    ok = repo.delete_sticker(sticker_id, trip_id)
    return jsonify({"deleted": ok})
