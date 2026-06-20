"""共有機能（Blueprint）。

旅の記録（trip）と旅行プラン（plan）を他者と共有する。共有は2方式:
  - 公開リンク : 推測困難なトークンURL（/s/<token>）を知る人が閲覧（ログイン不要）
  - メール指定 : 指定メールでログインした本人だけがアクセス（/shared/...）

権限は view（閲覧のみ）/ edit（編集可）。編集は旅（写真追加・付箋生成）でのみ
意味を持つ。プランはアプリ上に編集操作が無いため常に閲覧専用。

アクセス制御方針:
  - 所有者本人は常にフル権限。
  - それ以外は「有効なトークン」または「自分のメール宛グラント」がある場合のみ。
  - 写真実体は本番では GCS 署名付きURL（時間制限つき）で配信されるため、
    共有閲覧者でも追加の認証なしに表示できる。
"""
from flask import (Blueprint, abort, jsonify, redirect, render_template,
                   request, session, url_for)

import db
import db_reflection as repo
import db_sharing as sharing
from chat.logger import get_logger
from services import exif, features, storage, trip_interpreter
from views.auth import login_required
from views.reflection import _collect_images_for_stickers

share = Blueprint("sharing", __name__)
logger = get_logger("views.sharing")

_ALLOWED_EXT = {".jpg", ".jpeg", ".png", ".heic", ".webp", ".gif"}
_MAX_FILES_PER_REQUEST = 50


# ----------------------------------------------------------------------
# アクセス判定ヘルパー
# ----------------------------------------------------------------------
def _is_owner(resource_type: str, resource_id: int, uid: str | None) -> dict | None:
    """uid がリソースの所有者なら、そのリソース dict を返す（でなければ None）。"""
    if not uid:
        return None
    if resource_type == "trip":
        return repo.get_trip(resource_id, uid)
    if resource_type == "plan":
        plan = db.get_travel_plan_by_id(resource_id)
        if plan and plan.get("google_user_id") == uid:
            return plan
    return None


def _resolve_permission(resource_type: str, resource_id: int, token: str | None) -> str | None:
    """現在のアクセス文脈での権限を返す。

    返り値: 'owner' / 'edit' / 'view' / None（アクセス不可）。
    判定順: 所有者 → 有効なトークン → 自分のメール宛グラント。
    """
    if resource_type not in sharing.RESOURCE_TYPES:
        return None
    uid = session.get("user_id")
    if _is_owner(resource_type, resource_id, uid):
        return "owner"
    if token:
        link = sharing.get_link_by_token(token)
        if (link and link["resource_type"] == resource_type
                and link["resource_id"] == resource_id):
            return link["permission"]
    email = session.get("user_email")
    if email:
        grant = sharing.get_grant_for_email(resource_type, resource_id, email)
        if grant:
            return grant["permission"]
    return None


def _can_edit(resource_type: str, permission: str | None) -> bool:
    """編集可否。プランは編集操作が無いので常に不可。"""
    if resource_type != "trip":
        return False
    return permission in ("owner", "edit")


def _require_owner(resource_type: str, resource_id: int) -> dict:
    """所有者でなければ 404。共有の発行・取消は所有者のみが行える。"""
    res = _is_owner(resource_type, resource_id, session.get("user_id"))
    if not res:
        abort(404)
    return res


# ----------------------------------------------------------------------
# 共有の管理API（所有者のみ・モーダルから利用）
# ----------------------------------------------------------------------
@share.route("/share/<resource_type>/<int:resource_id>", methods=["GET"])
@login_required
def list_shares(resource_type: str, resource_id: int):
    """このリソースの公開リンク・メール共有の一覧を返す（共有モーダル用）。"""
    if resource_type not in sharing.RESOURCE_TYPES:
        abort(404)
    _require_owner(resource_type, resource_id)
    uid = session["user_id"]
    links = sharing.get_links_for_resource(resource_type, resource_id, uid)
    for l in links:
        l["url"] = url_for("sharing.public_view", token=l["token"], _external=True)
    grants = sharing.get_grants_for_resource(resource_type, resource_id, uid)
    return jsonify({
        "resource_type": resource_type,
        "resource_id": resource_id,
        # プランは編集共有不可（UIで編集トグルを隠す判断に使う）
        "editable_supported": resource_type == "trip",
        "links": links,
        "grants": grants,
    })


@share.route("/share/<resource_type>/<int:resource_id>/link", methods=["POST"])
@login_required
def create_link(resource_type: str, resource_id: int):
    if resource_type not in sharing.RESOURCE_TYPES:
        abort(404)
    _require_owner(resource_type, resource_id)
    data = request.get_json(silent=True) or request.form
    permission = (data.get("permission") or "view").strip()
    if permission not in sharing.PERMISSIONS:
        permission = "view"
    # プランは編集共有を許可しない
    if resource_type != "trip":
        permission = "view"
    link = sharing.create_share_link(resource_type, resource_id, session["user_id"], permission)
    link["url"] = url_for("sharing.public_view", token=link["token"], _external=True)
    return jsonify(link), 201


@share.route("/share/link/<int:link_id>", methods=["DELETE"])
@login_required
def revoke_link(link_id: int):
    ok = sharing.delete_link(link_id, session["user_id"])
    return jsonify({"deleted": ok})


@share.route("/share/<resource_type>/<int:resource_id>/grant", methods=["POST"])
@login_required
def add_grant(resource_type: str, resource_id: int):
    if resource_type not in sharing.RESOURCE_TYPES:
        abort(404)
    _require_owner(resource_type, resource_id)
    data = request.get_json(silent=True) or request.form
    email = (data.get("email") or "").strip()
    if not email or "@" not in email:
        return jsonify({"error": "正しいメールアドレスを入力してください"}), 400
    permission = (data.get("permission") or "view").strip()
    if permission not in sharing.PERMISSIONS:
        permission = "view"
    if resource_type != "trip":
        permission = "view"
    # 自分自身への共有は意味が無いので弾く
    if email.lower() == (session.get("user_email") or "").lower():
        return jsonify({"error": "自分以外のメールアドレスを指定してください"}), 400
    grant = sharing.add_grant(resource_type, resource_id, session["user_id"], email, permission)
    return jsonify(grant), 201


@share.route("/share/grant/<int:grant_id>", methods=["DELETE"])
@login_required
def revoke_grant(grant_id: int):
    ok = sharing.delete_grant(grant_id, session["user_id"])
    return jsonify({"deleted": ok})


# ----------------------------------------------------------------------
# 共有された側の閲覧
# ----------------------------------------------------------------------
@share.route("/s/<token>")
def public_view(token: str):
    """公開リンク（トークン）からの閲覧。ログイン不要。"""
    link = sharing.get_link_by_token(token)
    if not link:
        abort(404)
    rtype = link["resource_type"]
    rid = link["resource_id"]
    can_edit = _can_edit(rtype, link["permission"])
    return _render_shared(rtype, rid, can_edit=can_edit, share_token=token)


@share.route("/shared")
@login_required
def shared_with_me():
    """自分のメール宛に共有された旅・プランの一覧。"""
    email = session.get("user_email")
    grants = sharing.get_grants_for_email(email)
    trips, plans = [], []
    for g in grants:
        if g["resource_type"] == "trip":
            t = repo.get_trip_by_id(g["resource_id"])
            if t:
                t["permission"] = g["permission"]
                trips.append(t)
        elif g["resource_type"] == "plan":
            p = db.get_travel_plan_by_id(g["resource_id"])
            if p:
                p["permission"] = "view"
                plans.append(p)
    return render_template("shared/index.html", trips=trips, plans=plans)


@share.route("/shared/<resource_type>/<int:resource_id>")
@login_required
def shared_view(resource_type: str, resource_id: int):
    """メール共有された本人による閲覧（ログイン必須・セッションで権限判定）。"""
    if resource_type not in sharing.RESOURCE_TYPES:
        abort(404)
    perm = _resolve_permission(resource_type, resource_id, token=None)
    if perm is None:
        abort(404)
    can_edit = _can_edit(resource_type, perm)
    return _render_shared(resource_type, resource_id, can_edit=can_edit, share_token=None)


def _render_shared(resource_type: str, resource_id: int, can_edit: bool, share_token: str | None):
    """共有閲覧ページを描画する（trip / plan 共通の入口）。"""
    if resource_type == "trip":
        trip = repo.get_trip_by_id(resource_id, viewer_id=session.get("user_id"))
        if not trip:
            abort(404)
        photos = repo.get_photos(resource_id)
        for p in photos:
            p["url"] = storage.get_url(p["storage_path"])
        stickers = repo.get_stickers(resource_id)
        return render_template(
            "shared/trip.html",
            trip=trip, photos=photos, stickers=stickers,
            can_edit=can_edit, share_token=share_token,
        )
    if resource_type == "plan":
        plan = db.get_travel_plan_by_id(resource_id)
        if not plan:
            abort(404)
        return render_template("shared/plan.html", plan=plan)
    abort(404)


# ----------------------------------------------------------------------
# 共有された旅の編集（edit 権限が必要・旅のみ）
# ----------------------------------------------------------------------
def _require_trip_edit(trip_id: int):
    """共有された旅への編集権限を確認し、(trip, owner_id) を返す。

    トークン（公開リンク）またはログイン中のメールグラントを受け付ける。
    """
    token = request.values.get("token")
    perm = _resolve_permission("trip", trip_id, token=token)
    if not _can_edit("trip", perm):
        abort(403)
    trip = repo.get_trip_by_id(trip_id)
    if not trip:
        abort(404)
    return trip, trip["user_id"]


@share.route("/shared/trip/<int:trip_id>/photos", methods=["POST"])
def shared_upload_photos(trip_id: int):
    import os
    trip, owner_id = _require_trip_edit(trip_id)
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
            continue
        data = f.read()
        if not data:
            continue
        meta = exif.extract(data)
        # 写真は旅の所有者に紐づけて保存（パス・配信の一貫性のため）
        storage_path = storage.save(
            owner_id, trip_id, f.filename, data,
            content_type=f.mimetype or "application/octet-stream",
        )
        photo_id = repo.add_photo(
            trip_id, owner_id, storage_path,
            taken_at=meta.get("taken_at"),
            lat=meta.get("lat"), lng=meta.get("lng"),
        )
        saved.append({
            "id": photo_id,
            "url": storage.get_url(storage_path),
            "taken_at": str(meta["taken_at"]) if meta.get("taken_at") else None,
        })
    logger.info("共有編集で写真アップロード: trip_id=%s count=%d", trip_id, len(saved))
    return jsonify({"saved": saved, "count": len(saved)}), 201


@share.route("/shared/trip/<int:trip_id>/stickers/generate", methods=["POST"])
def shared_generate_stickers(trip_id: int):
    _require_trip_edit(trip_id)
    photos = repo.get_photos(trip_id)
    if not photos:
        return jsonify({"error": "写真を入れると付箋を作れます"}), 400
    feat = features.aggregate(photos)
    images = _collect_images_for_stickers(photos)
    items, usage = trip_interpreter.interpret_stickers(feat, images=images)
    repo.replace_stickers(trip_id, items)
    logger.info("共有編集で付箋生成: trip_id=%s count=%d", trip_id, len(items))
    return jsonify({"stickers": [{"text": it["text"]} for it in items]})


# ----------------------------------------------------------------------
# 共有された旅の削除操作（edit 権限が必要・旅のみ）
# ----------------------------------------------------------------------
@share.route("/shared/trip/<int:trip_id>/photos/<int:photo_id>", methods=["DELETE"])
def shared_delete_photo(trip_id: int, photo_id: int):
    """共有された旅の写真を1枚削除する（編集権限が必要）。"""
    _require_trip_edit(trip_id)
    storage_path = repo.delete_photo(photo_id, trip_id)
    if storage_path is None:
        return jsonify({"deleted": False}), 404
    storage.delete(storage_path)
    logger.info("共有編集で写真削除: trip_id=%s photo_id=%s", trip_id, photo_id)
    return jsonify({"deleted": True})


@share.route("/shared/trip/<int:trip_id>/stickers/<int:sticker_id>", methods=["DELETE"])
def shared_delete_sticker(trip_id: int, sticker_id: int):
    """共有された旅の付箋を1枚削除する（編集権限が必要）。"""
    _require_trip_edit(trip_id)
    ok = repo.delete_sticker(sticker_id, trip_id)
    return jsonify({"deleted": ok})


@share.route("/shared/trip/<int:trip_id>", methods=["DELETE"])
def shared_delete_trip(trip_id: int):
    """共有された旅を丸ごと削除する（編集権限が必要）。

    所有者の削除と同様に、DB削除の前にストレージ上の写真実体も消す。
    """
    trip, owner_id = _require_trip_edit(trip_id)
    photos = repo.get_photos(trip_id)
    for p in photos:
        storage.delete(p["storage_path"])
    ok = repo.delete_trip(trip_id, owner_id)
    logger.info("共有編集で旅を削除: trip_id=%s owner=%s photos=%d", trip_id, owner_id, len(photos))
    return jsonify({"deleted": ok})
