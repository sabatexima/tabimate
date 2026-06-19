"""旅の振り返り機能のためのデータアクセス層。

既存 db.py の SQLAlchemy エンジン（コネクションプール）を共有し、
テーブルは既存の流儀に合わせて CREATE TABLE IF NOT EXISTS で遅延作成する。
"""
import json

from sqlalchemy import text

from chat.logger import get_logger
from db import get_engine

logger = get_logger("db_reflection")


_CREATE_TRIPS_TABLE = """
CREATE TABLE IF NOT EXISTS trips (
    id          INT AUTO_INCREMENT PRIMARY KEY,
    user_id     VARCHAR(255) NOT NULL,
    title       VARCHAR(255) NOT NULL,
    start_date  DATE,
    end_date    DATE,
    created_at  TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    INDEX idx_trips_user (user_id)
) CHARACTER SET utf8mb4
"""

_CREATE_PHOTOS_TABLE = """
CREATE TABLE IF NOT EXISTS photos (
    id           INT AUTO_INCREMENT PRIMARY KEY,
    trip_id      INT NOT NULL,
    user_id      VARCHAR(255) NOT NULL,
    storage_path VARCHAR(512) NOT NULL,
    taken_at     DATETIME NULL,
    lat          DOUBLE NULL,
    lng          DOUBLE NULL,
    caption      VARCHAR(512) NULL,
    created_at   TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    INDEX idx_photos_trip (trip_id)
) CHARACTER SET utf8mb4
"""

_CREATE_ACHIEVEMENTS_TABLE = """
CREATE TABLE IF NOT EXISTS achievements (
    id          INT AUTO_INCREMENT PRIMARY KEY,
    trip_id     INT NOT NULL,
    title       VARCHAR(255) NOT NULL,
    flavor_text TEXT,
    created_at  TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    INDEX idx_ach_trip (trip_id)
) CHARACTER SET utf8mb4
"""

_CREATE_REPORTS_TABLE = """
CREATE TABLE IF NOT EXISTS trip_reports (
    id                 INT AUTO_INCREMENT PRIMARY KEY,
    trip_id            INT NOT NULL,
    area               VARCHAR(255) NULL,
    tone               VARCHAR(50),
    body               TEXT,
    token_usage_input  INT DEFAULT 0,
    token_usage_output INT DEFAULT 0,
    created_at         TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    INDEX idx_report_trip (trip_id)
) CHARACTER SET utf8mb4
"""

# 付箋（sticker）: 旅の写真から生成する短い言葉。アプリの主役。
# text   = ユーザーに見せる短い付箋の言葉（例:「曇り空が同行者」）
# basis  = 生成根拠（写真の何から来たか）。内部用でユーザーには返さない。
_CREATE_STICKERS_TABLE = """
CREATE TABLE IF NOT EXISTS stickers (
    id          INT AUTO_INCREMENT PRIMARY KEY,
    trip_id     INT NOT NULL,
    text        VARCHAR(255) NOT NULL,
    basis       TEXT NULL,
    created_at  TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    INDEX idx_sticker_trip (trip_id)
) CHARACTER SET utf8mb4
"""


def _row_to_dict(row) -> dict:
    return dict(row._mapping)


def _ensure_all(conn) -> None:
    conn.execute(text(_CREATE_TRIPS_TABLE))
    conn.execute(text(_CREATE_PHOTOS_TABLE))
    conn.execute(text(_CREATE_ACHIEVEMENTS_TABLE))
    conn.execute(text(_CREATE_REPORTS_TABLE))
    conn.execute(text(_CREATE_STICKERS_TABLE))


# ----------------------------------------------------------------------
# trips
# ----------------------------------------------------------------------
def create_trip(user_id: str, title: str, start_date=None, end_date=None) -> int:
    with get_engine().begin() as conn:
        _ensure_all(conn)
        result = conn.execute(
            text(
                "INSERT INTO trips (user_id, title, start_date, end_date) "
                "VALUES (:uid, :title, :start, :end)"
            ),
            {"uid": user_id, "title": title, "start": start_date, "end": end_date},
        )
        return result.lastrowid


def get_trip(trip_id: int, user_id: str) -> dict | None:
    with get_engine().connect() as conn:
        _ensure_all(conn)
        row = conn.execute(
            text("SELECT * FROM trips WHERE id = :id AND user_id = :uid"),
            {"id": trip_id, "uid": user_id},
        ).fetchone()
    return _row_to_dict(row) if row else None


def get_trips(user_id: str) -> list:
    """ユーザーの旅一覧を返す。

    一覧カードをリッチに描画するため、各旅に
      - photo_count : 写真枚数
      - cover_path  : サムネイルに使う代表写真の storage_path（最古の1枚／無ければ None）
    を相関サブクエリで付与する（N+1を避けるため1クエリで取得）。
    """
    with get_engine().connect() as conn:
        _ensure_all(conn)
        rows = conn.execute(
            text(
                "SELECT t.*, "
                "  (SELECT COUNT(*) FROM photos p WHERE p.trip_id = t.id) AS photo_count, "
                "  (SELECT p.storage_path FROM photos p WHERE p.trip_id = t.id "
                "     ORDER BY p.taken_at ASC, p.id ASC LIMIT 1) AS cover_path "
                "FROM trips t WHERE t.user_id = :uid ORDER BY t.created_at DESC"
            ),
            {"uid": user_id},
        ).fetchall()
    result = []
    for row in rows:
        d = _row_to_dict(row)
        for k in ("start_date", "end_date", "created_at"):
            if d.get(k) is not None:
                d[k] = str(d[k])
        result.append(d)
    return result


def delete_trip(trip_id: int, user_id: str) -> bool:
    with get_engine().begin() as conn:
        _ensure_all(conn)
        # 関連データも掃除
        conn.execute(text("DELETE FROM photos WHERE trip_id = :id"), {"id": trip_id})
        conn.execute(text("DELETE FROM achievements WHERE trip_id = :id"), {"id": trip_id})
        conn.execute(text("DELETE FROM trip_reports WHERE trip_id = :id"), {"id": trip_id})
        conn.execute(text("DELETE FROM stickers WHERE trip_id = :id"), {"id": trip_id})
        result = conn.execute(
            text("DELETE FROM trips WHERE id = :id AND user_id = :uid"),
            {"id": trip_id, "uid": user_id},
        )
        return result.rowcount > 0


# ----------------------------------------------------------------------
# photos
# ----------------------------------------------------------------------
def add_photo(trip_id: int, user_id: str, storage_path: str,
              taken_at=None, lat=None, lng=None, caption=None) -> int:
    with get_engine().begin() as conn:
        _ensure_all(conn)
        result = conn.execute(
            text(
                "INSERT INTO photos (trip_id, user_id, storage_path, taken_at, lat, lng, caption) "
                "VALUES (:tid, :uid, :path, :taken, :lat, :lng, :cap)"
            ),
            {
                "tid": trip_id, "uid": user_id, "path": storage_path,
                "taken": taken_at, "lat": lat, "lng": lng, "cap": caption,
            },
        )
        return result.lastrowid


def get_photos(trip_id: int) -> list:
    with get_engine().connect() as conn:
        _ensure_all(conn)
        rows = conn.execute(
            text("SELECT * FROM photos WHERE trip_id = :tid ORDER BY taken_at ASC, id ASC"),
            {"tid": trip_id},
        ).fetchall()
    result = []
    for row in rows:
        d = _row_to_dict(row)
        for k in ("taken_at", "created_at"):
            if d.get(k) is not None:
                d[k] = str(d[k])
        result.append(d)
    return result


# ----------------------------------------------------------------------
# achievements
# ----------------------------------------------------------------------
def replace_achievements(trip_id: int, items: list) -> None:
    """既存の称号を消して付け直す（再生成時の重複防止）。items=[{title, flavor_text}]"""
    with get_engine().begin() as conn:
        _ensure_all(conn)
        conn.execute(text("DELETE FROM achievements WHERE trip_id = :tid"), {"tid": trip_id})
        for it in items:
            conn.execute(
                text(
                    "INSERT INTO achievements (trip_id, title, flavor_text) "
                    "VALUES (:tid, :title, :flavor)"
                ),
                {"tid": trip_id, "title": it.get("title", ""), "flavor": it.get("flavor_text", "")},
            )


def get_achievements(trip_id: int) -> list:
    with get_engine().connect() as conn:
        _ensure_all(conn)
        rows = conn.execute(
            text("SELECT id, title, flavor_text, created_at FROM achievements "
                 "WHERE trip_id = :tid ORDER BY id ASC"),
            {"tid": trip_id},
        ).fetchall()
    result = []
    for row in rows:
        d = _row_to_dict(row)
        if d.get("created_at") is not None:
            d["created_at"] = str(d["created_at"])
        result.append(d)
    return result


# ----------------------------------------------------------------------
# stickers（付箋）: アプリの主役。再生成時は付け直す。
# ----------------------------------------------------------------------
def replace_stickers(trip_id: int, items: list) -> None:
    """既存の付箋を消して付け直す（再生成時の重複防止）。items=[{text, basis}]"""
    with get_engine().begin() as conn:
        _ensure_all(conn)
        conn.execute(text("DELETE FROM stickers WHERE trip_id = :tid"), {"tid": trip_id})
        for it in items:
            conn.execute(
                text(
                    "INSERT INTO stickers (trip_id, text, basis) "
                    "VALUES (:tid, :text, :basis)"
                ),
                {"tid": trip_id, "text": it.get("text", ""), "basis": it.get("basis", "")},
            )


def get_stickers(trip_id: int) -> list:
    """付箋一覧を返す。basis（生成根拠）はユーザー非表示なので含めない。"""
    with get_engine().connect() as conn:
        _ensure_all(conn)
        rows = conn.execute(
            text("SELECT id, text, created_at FROM stickers "
                 "WHERE trip_id = :tid ORDER BY id ASC"),
            {"tid": trip_id},
        ).fetchall()
    result = []
    for row in rows:
        d = _row_to_dict(row)
        if d.get("created_at") is not None:
            d["created_at"] = str(d["created_at"])
        result.append(d)
    return result


def delete_sticker(sticker_id: int, trip_id: int) -> bool:
    """付箋を1枚削除する（本人の旅に紐づくものだけ）。"""
    with get_engine().begin() as conn:
        _ensure_all(conn)
        result = conn.execute(
            text("DELETE FROM stickers WHERE id = :sid AND trip_id = :tid"),
            {"sid": sticker_id, "tid": trip_id},
        )
        return result.rowcount > 0


# ----------------------------------------------------------------------
# trip_reports
# ----------------------------------------------------------------------
def save_report(trip_id: int, body: str, tone: str, area=None,
                token_in: int = 0, token_out: int = 0) -> int:
    with get_engine().begin() as conn:
        _ensure_all(conn)
        result = conn.execute(
            text(
                "INSERT INTO trip_reports (trip_id, area, tone, body, token_usage_input, token_usage_output) "
                "VALUES (:tid, :area, :tone, :body, :ti, :to)"
            ),
            {"tid": trip_id, "area": area, "tone": tone, "body": body, "ti": token_in, "to": token_out},
        )
        return result.lastrowid


def get_reports(trip_id: int) -> list:
    with get_engine().connect() as conn:
        _ensure_all(conn)
        rows = conn.execute(
            text("SELECT id, area, tone, body, token_usage_input, token_usage_output, created_at "
                 "FROM trip_reports WHERE trip_id = :tid ORDER BY created_at DESC"),
            {"tid": trip_id},
        ).fetchall()
    result = []
    for row in rows:
        d = _row_to_dict(row)
        if d.get("created_at") is not None:
            d["created_at"] = str(d["created_at"])
        result.append(d)
    return result
