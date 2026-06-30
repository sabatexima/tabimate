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
    is_favorite TINYINT NOT NULL DEFAULT 0,
    linked_plan_id INT NULL,
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

# お気に入りはユーザーごとに持つ。共有された旅も閲覧ユーザー自身が
# お気に入り登録できるよう、(user_id, trip_id) の組で管理する。
# （旧来の trips.is_favorite は所有者単独の状態しか持てないため）
_CREATE_TRIP_FAVORITES_TABLE = """
CREATE TABLE IF NOT EXISTS trip_favorites (
    user_id    VARCHAR(255) NOT NULL,
    trip_id    INT NOT NULL,
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    PRIMARY KEY (user_id, trip_id),
    INDEX idx_tripfav_trip (trip_id)
) CHARACTER SET utf8mb4
"""


def _row_to_dict(row) -> dict:
    """SQLAlchemy の行を素の dict に変換する。"""
    return dict(row._mapping)


# プロセス内で確認済みのカラムをキャッシュし、information_schema 問い合わせを
# 毎回走らせない（スキーマは実行中に変わらない前提）。
_confirmed_columns: set = set()


def _ensure_column(conn, table: str, column: str, ddl: str) -> None:
    """既存テーブルに不足カラムがあれば追加する（冪等な遅延マイグレーション）。

    CREATE TABLE IF NOT EXISTS では既存テーブルへの列追加ができないため、
    information_schema で存在確認してから ALTER する（MySQL/TiDB 両対応）。
    一度確認できたカラムはプロセス内キャッシュして再問い合わせを避ける。
    """
    cache_key = f"{table}.{column}"
    if cache_key in _confirmed_columns:
        return
    exists = conn.execute(
        text(
            "SELECT COUNT(*) FROM information_schema.columns "
            "WHERE table_schema = DATABASE() AND table_name = :t AND column_name = :c"
        ),
        {"t": table, "c": column},
    ).scalar()
    if not exists:
        conn.execute(text(f"ALTER TABLE {table} ADD COLUMN {ddl}"))
        logger.info("カラム追加(遅延マイグレーション): %s.%s", table, column)
    _confirmed_columns.add(cache_key)


# お気に入りの旧→新スキーマ移行（trips.is_favorite → trip_favorites）を
# プロセス内で一度だけ実行するためのフラグ。
_favorites_migrated = False


def _migrate_favorites_once(conn) -> None:
    """旧来の trips.is_favorite=1 を所有者のお気に入りとして移送する（冪等・一度だけ）。

    INSERT IGNORE で重複は無視されるため複数回流れても安全だが、
    無駄なクエリを避けるためプロセス内で一度だけ実行する。
    """
    global _favorites_migrated
    if _favorites_migrated:
        return
    try:
        conn.execute(
            text(
                "INSERT IGNORE INTO trip_favorites (user_id, trip_id) "
                "SELECT user_id, id FROM trips WHERE is_favorite = 1"
            )
        )
    except Exception:
        # 旧列が無い等で失敗しても致命的ではない（新規DBなど）。
        logger.debug("お気に入り移行をスキップ", exc_info=True)
    _favorites_migrated = True


def _ensure_all(conn) -> None:
    """この機能で使う全テーブルを作成し、既存DBには不足列を遅延追加・移行する。"""
    conn.execute(text(_CREATE_TRIPS_TABLE))
    conn.execute(text(_CREATE_PHOTOS_TABLE))
    conn.execute(text(_CREATE_STICKERS_TABLE))
    conn.execute(text(_CREATE_TRIP_FAVORITES_TABLE))
    # 既存DB向け: お気に入り列が無ければ追加（移行元として保持）
    _ensure_column(conn, "trips", "is_favorite", "is_favorite TINYINT NOT NULL DEFAULT 0")
    # 既存DB向け: 旅に紐付ける旅行プランID列が無ければ追加（実績↔プランの重ね合わせ用）
    _ensure_column(conn, "trips", "linked_plan_id", "linked_plan_id INT NULL")
    # 旧来のお気に入りをユーザー別テーブルへ移送
    _migrate_favorites_once(conn)


# ----------------------------------------------------------------------
# trips
# ----------------------------------------------------------------------
def create_trip(user_id: str, title: str, start_date=None, end_date=None) -> int:
    """旅（振り返り）を新規作成し、その id を返す。"""
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
    """本人の旅を1件返す（他人の旅は取得不可）。無ければ None。"""
    with get_engine().connect() as conn:
        _ensure_all(conn)
        row = conn.execute(
            text("SELECT * FROM trips WHERE id = :id AND user_id = :uid"),
            {"id": trip_id, "uid": user_id},
        ).fetchone()
    return _row_to_dict(row) if row else None


def get_trip_by_id(trip_id: int, viewer_id: str | None = None) -> dict | None:
    """所有者を問わず1件の旅を取得する（共有閲覧で使用）。

    アクセス制御は呼び出し側（共有トークン / メール権限の確認）で行う前提。
    is_favorite は viewer_id 視点で算出する（未指定なら 0）。
    """
    with get_engine().connect() as conn:
        _ensure_all(conn)
        row = conn.execute(
            text("SELECT * FROM trips WHERE id = :id"),
            {"id": trip_id},
        ).fetchone()
        if not row:
            return None
        d = _row_to_dict(row)
        fav = 0
        if viewer_id:
            fav = conn.execute(
                text("SELECT 1 FROM trip_favorites WHERE user_id = :uid AND trip_id = :tid"),
                {"uid": viewer_id, "tid": trip_id},
            ).fetchone() is not None
    for k in ("start_date", "end_date", "created_at"):
        if d.get(k) is not None:
            d[k] = str(d[k])
    d["is_favorite"] = 1 if fav else 0
    return d


def get_trips(user_id: str) -> list:
    """ユーザーの旅一覧を返す。

    一覧カード（SNSフィード風）をリッチに描画するため、各旅に
      - photo_count     : 写真枚数
      - cover_path      : 大きく見せる代表写真の storage_path（最古の1枚／無ければ None）
      - stickers_preview: カードのバッジ用、代表付箋の言葉を最新2枚まで（list）
    を相関サブクエリで付与する（N+1を避けるため1クエリで取得）。

    付箋プレビューは GROUP_CONCAT の区切り指定が TiDB で扱いづらいため、
    最新・2番目の2つのスカラーサブクエリ（LIMIT offset）で取得し、
    Python 側で None を除いた list にまとめる。
    """
    with get_engine().connect() as conn:
        _ensure_all(conn)
        rows = conn.execute(
            text(
                "SELECT t.*, "
                "  (SELECT COUNT(*) FROM photos p WHERE p.trip_id = t.id) AS photo_count, "
                "  (SELECT p.storage_path FROM photos p WHERE p.trip_id = t.id "
                "     ORDER BY p.taken_at ASC, p.id ASC LIMIT 1) AS cover_path, "
                "  (SELECT s.text FROM stickers s WHERE s.trip_id = t.id "
                "     ORDER BY s.id DESC LIMIT 1) AS sticker1, "
                "  (SELECT s.text FROM stickers s WHERE s.trip_id = t.id "
                "     ORDER BY s.id DESC LIMIT 1 OFFSET 1) AS sticker2, "
                "  (SELECT 1 FROM trip_favorites f WHERE f.trip_id = t.id AND f.user_id = :uid) AS viewer_favorite "
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
        d["is_favorite"] = 1 if d.pop("viewer_favorite", None) else 0
        d["stickers_preview"] = [s for s in (d.pop("sticker1", None), d.pop("sticker2", None)) if s]
        result.append(d)
    return result


def get_trip_cards(trip_ids: list, viewer_id: str | None = None) -> list:
    """指定IDの旅を、一覧カード用のリッチ形式（写真枚数・代表写真・付箋）で返す。

    共有された旅をアルバムに混ぜて表示するために使う。get_trips と同じ整形。
    is_favorite は viewer_id 視点で算出する（未指定なら 0）。
    入力順は問わず created_at 降順で返す。
    """
    ids = [int(i) for i in trip_ids if i is not None]
    if not ids:
        return []
    placeholders = ", ".join(f":id{i}" for i in range(len(ids)))
    params = {f"id{i}": v for i, v in enumerate(ids)}
    params["viewer"] = viewer_id
    with get_engine().connect() as conn:
        _ensure_all(conn)
        rows = conn.execute(
            text(
                "SELECT t.*, "
                "  (SELECT COUNT(*) FROM photos p WHERE p.trip_id = t.id) AS photo_count, "
                "  (SELECT p.storage_path FROM photos p WHERE p.trip_id = t.id "
                "     ORDER BY p.taken_at ASC, p.id ASC LIMIT 1) AS cover_path, "
                "  (SELECT s.text FROM stickers s WHERE s.trip_id = t.id "
                "     ORDER BY s.id DESC LIMIT 1) AS sticker1, "
                "  (SELECT s.text FROM stickers s WHERE s.trip_id = t.id "
                "     ORDER BY s.id DESC LIMIT 1 OFFSET 1) AS sticker2, "
                "  (SELECT 1 FROM trip_favorites f WHERE f.trip_id = t.id AND f.user_id = :viewer) AS viewer_favorite "
                f"FROM trips t WHERE t.id IN ({placeholders}) ORDER BY t.created_at DESC"
            ),
            params,
        ).fetchall()
    result = []
    for row in rows:
        d = _row_to_dict(row)
        for k in ("start_date", "end_date", "created_at"):
            if d.get(k) is not None:
                d[k] = str(d[k])
        d["is_favorite"] = 1 if d.pop("viewer_favorite", None) else 0
        d["stickers_preview"] = [s for s in (d.pop("sticker1", None), d.pop("sticker2", None)) if s]
        result.append(d)
    return result


def is_trip_favorite(user_id: str, trip_id: int) -> bool:
    """指定ユーザーがこの旅をお気に入り登録しているか。"""
    with get_engine().connect() as conn:
        _ensure_all(conn)
        row = conn.execute(
            text("SELECT 1 FROM trip_favorites WHERE user_id = :uid AND trip_id = :tid"),
            {"uid": user_id, "tid": trip_id},
        ).fetchone()
    return row is not None


def set_trip_favorite(trip_id: int, user_id: str, favorite: bool) -> bool:
    """旅のお気に入り状態をユーザー単位で設定する。

    所有者でも共有された閲覧者でも、自分のお気に入りとして登録/解除できる。
    アクセス制御（その旅を見られるか）は呼び出し側で担保する前提。
    """
    with get_engine().begin() as conn:
        _ensure_all(conn)
        if favorite:
            conn.execute(
                text(
                    "INSERT IGNORE INTO trip_favorites (user_id, trip_id) "
                    "VALUES (:uid, :tid)"
                ),
                {"uid": user_id, "tid": trip_id},
            )
        else:
            conn.execute(
                text("DELETE FROM trip_favorites WHERE user_id = :uid AND trip_id = :tid"),
                {"uid": user_id, "tid": trip_id},
            )
        return True


def rename_trip(trip_id: int, user_id: str, title: str) -> bool:
    """旅のタイトルを更新する（本人の旅のみ）。更新できたら True。"""
    with get_engine().begin() as conn:
        _ensure_all(conn)
        result = conn.execute(
            text("UPDATE trips SET title = :title WHERE id = :id AND user_id = :uid"),
            {"title": title, "id": trip_id, "uid": user_id},
        )
        return result.rowcount > 0


def set_trip_linked_plan(trip_id: int, user_id: str, plan_id) -> bool:
    """旅に旅行プランを紐付ける（本人の旅のみ）。plan_id=None で解除。"""
    with get_engine().begin() as conn:
        _ensure_all(conn)
        exists = conn.execute(
            text("SELECT 1 FROM trips WHERE id = :id AND user_id = :uid"),
            {"id": trip_id, "uid": user_id},
        ).fetchone()
        if not exists:
            return False
        conn.execute(
            text("UPDATE trips SET linked_plan_id = :pid WHERE id = :id AND user_id = :uid"),
            {"pid": plan_id, "id": trip_id, "uid": user_id},
        )
    return True


def update_trip_dates(trip_id: int, user_id: str, start_date, end_date) -> bool:
    """旅の出発日・帰宅日を更新する（本人の旅のみ）。

    None を渡すとその日付はクリアされる。対象の旅が存在し本人のものなら True。
    （同じ値で更新すると MySQL の rowcount が 0 になるため、行の存在で判定する）
    """
    with get_engine().begin() as conn:
        _ensure_all(conn)
        exists = conn.execute(
            text("SELECT 1 FROM trips WHERE id = :id AND user_id = :uid"),
            {"id": trip_id, "uid": user_id},
        ).fetchone()
        if not exists:
            return False
        conn.execute(
            text(
                "UPDATE trips SET start_date = :start, end_date = :end "
                "WHERE id = :id AND user_id = :uid"
            ),
            {"start": start_date, "end": end_date, "id": trip_id, "uid": user_id},
        )
    return True


def delete_trip(trip_id: int, user_id: str) -> bool:
    """本人の旅を関連データ（写真・付箋・お気に入り）ごと削除する。消せれば True。"""
    with get_engine().begin() as conn:
        _ensure_all(conn)
        # 関連データも掃除
        conn.execute(text("DELETE FROM photos WHERE trip_id = :id"), {"id": trip_id})
        conn.execute(text("DELETE FROM stickers WHERE trip_id = :id"), {"id": trip_id})
        conn.execute(text("DELETE FROM trip_favorites WHERE trip_id = :id"), {"id": trip_id})
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
    """旅に写真メタデータ（保存先・撮影日時・位置等）を1件追加し、その id を返す。"""
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


def delete_photo(photo_id: int, trip_id: int) -> str | None:
    """写真を1枚削除し、その storage_path を返す（無ければ None）。

    ストレージ実体の削除は呼び出し側が返り値の storage_path を使って行う。
    trip_id でも絞ることで、他の旅の写真を消せないようにする。
    """
    with get_engine().begin() as conn:
        _ensure_all(conn)
        row = conn.execute(
            text("SELECT storage_path FROM photos WHERE id = :pid AND trip_id = :tid"),
            {"pid": photo_id, "tid": trip_id},
        ).fetchone()
        if not row:
            return None
        storage_path = row._mapping["storage_path"]
        conn.execute(
            text("DELETE FROM photos WHERE id = :pid AND trip_id = :tid"),
            {"pid": photo_id, "tid": trip_id},
        )
    return storage_path


def get_photos(trip_id: int) -> list:
    """旅の写真を撮影日時の古い順で返す（タイムライン表示用）。"""
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
