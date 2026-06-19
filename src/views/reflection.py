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
from services import exif, features, storage, trip_interpreter
from views.auth import login_required

reflection = Blueprint("reflection", __name__, url_prefix="/reflection")
logger = get_logger("views.reflection")

# 1リクエストあたりの写真枚数・サイズの上限（コスト/メモリ保護）
_MAX_FILES_PER_REQUEST = 50
_ALLOWED_EXT = {".jpg", ".jpeg", ".png", ".heic", ".webp", ".gif"}


def _uid() -> str:
    return session.get("user_id")


def _require_trip(trip_id: int) -> dict:
    """本人所有の旅でなければ 404。所有していれば trip dict を返す。"""
    trip = repo.get_trip(trip_id, _uid())
    if not trip:
        abort(404)
    return trip


def _collect_images(photos: list) -> list:
    """画像送付オプション有効時のみ、代表画像のバイト列を集める（既定は空）。

    コスト保護のため全枚数は送らず、均等サンプリングで数枚に絞る。
    実際の枚数上限・縮小は解釈エンジン側でも担保する。
    """
    if not trip_interpreter.send_images_enabled() or not photos:
        return []
    # 均等に最大8枚サンプリング（エンジン側で更に_MAX_IMAGESへ絞る）
    sample_n = min(8, len(photos))
    step = max(1, len(photos) // sample_n)
    sampled = photos[::step][:sample_n]
    images = []
    for p in sampled:
        data = storage.read_bytes(p["storage_path"])
        if data:
            images.append(data)
    logger.info("代表画像を収集: %d枚（送付オプション有効）", len(images))
    return images


# ----------------------------------------------------------------------
# 画面（UIの詳細はテンプレート側。ここでは入口のみ）
# ----------------------------------------------------------------------
@reflection.route("/")
@login_required
def index():
    trips = repo.get_trips(_uid())
    # 一覧カードのサムネイル用に、代表写真の配信URLを付与（無ければ None）
    for t in trips:
        t["cover_url"] = storage.get_url(t["cover_path"]) if t.get("cover_path") else None
    return render_template("reflection/index.html", trips=trips)


@reflection.route("/trips/<int:trip_id>")
@login_required
def trip_detail(trip_id: int):
    trip = _require_trip(trip_id)
    photos = repo.get_photos(trip_id)
    # 配信URLを付与（GCS署名付き or ローカル配信ルート）
    for p in photos:
        p["url"] = storage.get_url(p["storage_path"])
    achievements = repo.get_achievements(trip_id)
    reports = repo.get_reports(trip_id)
    return render_template(
        "reflection/trip.html",
        trip=trip, photos=photos,
        achievements=achievements, reports=reports,
    )


# ----------------------------------------------------------------------
# trips API
# ----------------------------------------------------------------------
@reflection.route("/trips", methods=["POST"])
@login_required
def create_trip():
    data = request.get_json(silent=True) or request.form
    title = (data.get("title") or "").strip()
    if not title:
        return jsonify({"error": "タイトルは必須です"}), 400
    start_date = data.get("start_date") or None
    end_date = data.get("end_date") or None
    trip_id = repo.create_trip(_uid(), title, start_date, end_date)
    logger.info("旅を作成: trip_id=%s user=%s", trip_id, _uid())
    return jsonify({"id": trip_id, "title": title}), 201


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
        if ext and ext not in _ALLOWED_EXT:
            logger.debug("非対応拡張子をスキップ: %s", f.filename)
            continue
        data = f.read()
        if not data:
            continue
        meta = exif.extract(data)
        storage_path = storage.save(
            _uid(), trip_id, f.filename, data,
            content_type=f.mimetype or "application/octet-stream",
        )
        photo_id = repo.add_photo(
            trip_id, _uid(), storage_path,
            taken_at=meta.get("taken_at"),
            lat=meta.get("lat"), lng=meta.get("lng"),
        )
        saved.append({
            "id": photo_id,
            "url": storage.get_url(storage_path),
            "taken_at": str(meta["taken_at"]) if meta.get("taken_at") else None,
            "lat": meta.get("lat"), "lng": meta.get("lng"),
        })

    logger.info("写真アップロード完了: trip_id=%s count=%d", trip_id, len(saved))
    return jsonify({"saved": saved, "count": len(saved)}), 201


# ----------------------------------------------------------------------
# ローカルFS保存写真の配信（GCS時は使わない）
# ----------------------------------------------------------------------
@reflection.route("/photo/<path:storage_path>")
@login_required
def serve_local_photo(storage_path: str):
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
# 機能A: 謎アチーブメント
# ----------------------------------------------------------------------
@reflection.route("/trips/<int:trip_id>/achievements/generate", methods=["POST"])
@login_required
def generate_achievements(trip_id: int):
    _require_trip(trip_id)
    photos = repo.get_photos(trip_id)
    feat = features.aggregate(photos)
    images = _collect_images(photos)
    items, usage = trip_interpreter.interpret_achievements(feat, images=images)
    repo.replace_achievements(trip_id, items)
    logger.info("称号生成: trip_id=%s count=%d tokens(in/out)=%d/%d",
                trip_id, len(items), usage["input_tokens"], usage["output_tokens"])
    # 称号本体のみ返す。獲得条件・トークン等の内部情報は返さない。
    return jsonify({"achievements": items})


@reflection.route("/trips/<int:trip_id>/achievements", methods=["GET"])
@login_required
def list_achievements(trip_id: int):
    _require_trip(trip_id)
    return jsonify({"achievements": repo.get_achievements(trip_id)})


# ----------------------------------------------------------------------
# 機能B: AI旅レポート
# ----------------------------------------------------------------------
@reflection.route("/trips/<int:trip_id>/report/generate", methods=["POST"])
@login_required
def generate_report(trip_id: int):
    _require_trip(trip_id)
    tone = request.args.get("tone") or (request.get_json(silent=True) or {}).get("tone") or "playful"
    area = request.args.get("area") or (request.get_json(silent=True) or {}).get("area") or None
    photos = repo.get_photos(trip_id)
    feat = features.aggregate(photos)
    images = _collect_images(photos)
    body, usage = trip_interpreter.interpret_report(feat, tone=tone, area=area, images=images)
    repo.save_report(
        trip_id, body=body, tone=tone, area=area,
        token_in=usage["input_tokens"], token_out=usage["output_tokens"],
    )
    logger.info("レポート生成: trip_id=%s tone=%s area=%s tokens(in/out)=%d/%d",
                trip_id, tone, area, usage["input_tokens"], usage["output_tokens"])
    return jsonify({"body": body, "tone": tone, "area": area})


@reflection.route("/trips/<int:trip_id>/report", methods=["GET"])
@login_required
def list_reports(trip_id: int):
    _require_trip(trip_id)
    return jsonify({"reports": repo.get_reports(trip_id)})
