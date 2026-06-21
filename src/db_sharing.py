"""共有機能のためのデータアクセス層。

旅の記録（trip）と旅行プラン（plan）を他者と共有するための2方式を扱う:
  - share_links  : 公開リンク。推測困難なトークン付きURLを知る人が閲覧できる。
  - share_grants : メール指定共有。指定したメールでログインした本人だけがアクセスできる。

権限（permission）は 'view'（閲覧のみ）/ 'edit'（編集可）の2種類。
セキュリティ方針:
  - トークンは secrets モジュールで生成（推測困難）。コードに直書きしない。
  - 公開リンクの既定は 'view'。編集可リンクは旅（trip）でのみ任意で発行できる。
  - プランはアプリ上に編集操作が無いため共有は常に 'view'。

既存 db.py の SQLAlchemy エンジン（コネクションプール）を共有し、
テーブルは既存の流儀に合わせて CREATE TABLE IF NOT EXISTS で遅延作成する。
"""
import secrets

from sqlalchemy import text

from chat.logger import get_logger
from db import get_engine

logger = get_logger("db_sharing")

# 共有対象の種別と権限の許容値（バリデーション用）
RESOURCE_TYPES = ("trip", "plan")
PERMISSIONS = ("view", "edit")

_TOKEN_BYTES = 24  # secrets.token_urlsafe のバイト長（約32文字の推測困難トークン）


_CREATE_LINKS_TABLE = """
CREATE TABLE IF NOT EXISTS share_links (
    id            INT AUTO_INCREMENT PRIMARY KEY,
    resource_type VARCHAR(10)  NOT NULL,
    resource_id   INT          NOT NULL,
    token         VARCHAR(64)  NOT NULL,
    permission    VARCHAR(10)  NOT NULL DEFAULT 'view',
    owner_user_id VARCHAR(255) NOT NULL,
    created_at    TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    UNIQUE KEY uq_share_token (token),
    INDEX idx_link_resource (resource_type, resource_id),
    INDEX idx_link_owner (owner_user_id)
) CHARACTER SET utf8mb4
"""

_CREATE_GRANTS_TABLE = """
CREATE TABLE IF NOT EXISTS share_grants (
    id            INT AUTO_INCREMENT PRIMARY KEY,
    resource_type VARCHAR(10)  NOT NULL,
    resource_id   INT          NOT NULL,
    grantee_email VARCHAR(255) NOT NULL,
    permission    VARCHAR(10)  NOT NULL DEFAULT 'view',
    owner_user_id VARCHAR(255) NOT NULL,
    created_at    TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    UNIQUE KEY uq_grant (resource_type, resource_id, grantee_email),
    INDEX idx_grant_resource (resource_type, resource_id),
    INDEX idx_grant_email (grantee_email)
) CHARACTER SET utf8mb4
"""


def _row_to_dict(row) -> dict:
    return dict(row._mapping)


def _ensure_all(conn) -> None:
    conn.execute(text(_CREATE_LINKS_TABLE))
    conn.execute(text(_CREATE_GRANTS_TABLE))


def _norm_email(email: str) -> str:
    return (email or "").strip().lower()


# ----------------------------------------------------------------------
# share_links（公開リンク）
# ----------------------------------------------------------------------
def create_share_link(resource_type: str, resource_id: int,
                      owner_user_id: str, permission: str = "view") -> dict:
    """公開リンクを発行する。

    同じ権限のリンクが既にあればそれを再利用し、無ければ新規トークンを生成する。
    （同じリソースに view/edit の2本まで持てる）
    """
    if permission not in PERMISSIONS:
        permission = "view"
    with get_engine().begin() as conn:
        _ensure_all(conn)
        existing = conn.execute(
            text(
                "SELECT id, token, permission FROM share_links "
                "WHERE resource_type = :rt AND resource_id = :rid "
                "AND owner_user_id = :uid AND permission = :perm LIMIT 1"
            ),
            {"rt": resource_type, "rid": resource_id, "uid": owner_user_id, "perm": permission},
        ).fetchone()
        if existing:
            d = _row_to_dict(existing)
            return {"id": d["id"], "token": d["token"], "permission": d["permission"]}

        token = secrets.token_urlsafe(_TOKEN_BYTES)
        result = conn.execute(
            text(
                "INSERT INTO share_links (resource_type, resource_id, token, permission, owner_user_id) "
                "VALUES (:rt, :rid, :token, :perm, :uid)"
            ),
            {"rt": resource_type, "rid": resource_id, "token": token,
             "perm": permission, "uid": owner_user_id},
        )
        logger.info("公開リンク発行: %s#%s perm=%s owner=%s", resource_type, resource_id, permission, owner_user_id)
        return {"id": result.lastrowid, "token": token, "permission": permission}


def get_link_by_token(token: str) -> dict | None:
    """トークンから共有リンク情報を取得する（公開閲覧の入口）。"""
    if not token:
        return None
    with get_engine().connect() as conn:
        _ensure_all(conn)
        row = conn.execute(
            text("SELECT * FROM share_links WHERE token = :token"),
            {"token": token},
        ).fetchone()
    if not row:
        return None
    d = _row_to_dict(row)
    if d.get("created_at") is not None:
        d["created_at"] = str(d["created_at"])
    return d


def get_links_for_resource(resource_type: str, resource_id: int, owner_user_id: str) -> list:
    """所有者がモーダルで一覧表示するための、リソースの公開リンク一覧。"""
    with get_engine().connect() as conn:
        _ensure_all(conn)
        rows = conn.execute(
            text(
                "SELECT id, token, permission, created_at FROM share_links "
                "WHERE resource_type = :rt AND resource_id = :rid AND owner_user_id = :uid "
                "ORDER BY id ASC"
            ),
            {"rt": resource_type, "rid": resource_id, "uid": owner_user_id},
        ).fetchall()
    result = []
    for row in rows:
        d = _row_to_dict(row)
        if d.get("created_at") is not None:
            d["created_at"] = str(d["created_at"])
        result.append(d)
    return result


def delete_link(link_id: int, owner_user_id: str) -> bool:
    """公開リンクを失効させる（本人のリンクのみ）。"""
    with get_engine().begin() as conn:
        _ensure_all(conn)
        result = conn.execute(
            text("DELETE FROM share_links WHERE id = :id AND owner_user_id = :uid"),
            {"id": link_id, "uid": owner_user_id},
        )
        return result.rowcount > 0


# ----------------------------------------------------------------------
# share_grants（メール指定共有）
# ----------------------------------------------------------------------
def add_grant(resource_type: str, resource_id: int, owner_user_id: str,
              grantee_email: str, permission: str = "view") -> dict:
    """メール指定で共有を付与する（同一相手への再付与は権限を更新）。"""
    if permission not in PERMISSIONS:
        permission = "view"
    email = _norm_email(grantee_email)
    with get_engine().begin() as conn:
        _ensure_all(conn)
        # UNIQUE 制約に当たる場合は権限を更新（upsert 相当）
        conn.execute(
            text(
                "INSERT INTO share_grants (resource_type, resource_id, grantee_email, permission, owner_user_id) "
                "VALUES (:rt, :rid, :email, :perm, :uid) "
                "ON DUPLICATE KEY UPDATE permission = :perm"
            ),
            {"rt": resource_type, "rid": resource_id, "email": email,
             "perm": permission, "uid": owner_user_id},
        )
        row = conn.execute(
            text(
                "SELECT id, grantee_email, permission FROM share_grants "
                "WHERE resource_type = :rt AND resource_id = :rid AND grantee_email = :email"
            ),
            {"rt": resource_type, "rid": resource_id, "email": email},
        ).fetchone()
    logger.info("メール共有付与: %s#%s -> %s perm=%s", resource_type, resource_id, email, permission)
    return _row_to_dict(row) if row else {}


def get_grants_for_resource(resource_type: str, resource_id: int, owner_user_id: str) -> list:
    """所有者がモーダルで一覧表示するための、リソースのメール共有一覧。"""
    with get_engine().connect() as conn:
        _ensure_all(conn)
        rows = conn.execute(
            text(
                "SELECT id, grantee_email, permission, created_at FROM share_grants "
                "WHERE resource_type = :rt AND resource_id = :rid AND owner_user_id = :uid "
                "ORDER BY id ASC"
            ),
            {"rt": resource_type, "rid": resource_id, "uid": owner_user_id},
        ).fetchall()
    result = []
    for row in rows:
        d = _row_to_dict(row)
        if d.get("created_at") is not None:
            d["created_at"] = str(d["created_at"])
        result.append(d)
    return result


def delete_grant(grant_id: int, owner_user_id: str) -> bool:
    """メール共有を取り消す（本人の付与のみ）。"""
    with get_engine().begin() as conn:
        _ensure_all(conn)
        result = conn.execute(
            text("DELETE FROM share_grants WHERE id = :id AND owner_user_id = :uid"),
            {"id": grant_id, "uid": owner_user_id},
        )
        return result.rowcount > 0


def delete_grant_as_grantee(grant_id: int, grantee_email: str) -> bool:
    """共有された側が、自分宛の共有を解除する（自分のメール宛グラントのみ）。

    所有者が取り消す delete_grant とは別物で、ここでは grantee_email 本人だけが
    自分宛のグラントを削除できる（他人宛のグラントは消せない）。
    """
    email = _norm_email(grantee_email)
    if not email:
        return False
    with get_engine().begin() as conn:
        _ensure_all(conn)
        result = conn.execute(
            text("DELETE FROM share_grants WHERE id = :id AND grantee_email = :email"),
            {"id": grant_id, "email": email},
        )
        return result.rowcount > 0


def get_grant_for_email(resource_type: str, resource_id: int, grantee_email: str) -> dict | None:
    """指定リソースに対する、あるメールの共有権限を返す（アクセス判定用）。"""
    email = _norm_email(grantee_email)
    if not email:
        return None
    with get_engine().connect() as conn:
        _ensure_all(conn)
        row = conn.execute(
            text(
                "SELECT id, permission, owner_user_id FROM share_grants "
                "WHERE resource_type = :rt AND resource_id = :rid AND grantee_email = :email"
            ),
            {"rt": resource_type, "rid": resource_id, "email": email},
        ).fetchone()
    return _row_to_dict(row) if row else None


def get_grants_for_email(grantee_email: str) -> list:
    """あるメール宛に共有された全リソース（「共有された旅・プラン」一覧用）。"""
    email = _norm_email(grantee_email)
    if not email:
        return []
    with get_engine().connect() as conn:
        _ensure_all(conn)
        rows = conn.execute(
            text(
                "SELECT id, resource_type, resource_id, permission, owner_user_id, created_at "
                "FROM share_grants WHERE grantee_email = :email ORDER BY created_at DESC"
            ),
            {"email": email},
        ).fetchall()
    result = []
    for row in rows:
        d = _row_to_dict(row)
        if d.get("created_at") is not None:
            d["created_at"] = str(d["created_at"])
        result.append(d)
    return result
