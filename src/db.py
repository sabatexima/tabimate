"""データベースアクセス層。

旅行プラン（travel_plans）とチャット履歴（chat_messages）の永続化を担う。
接続先は環境変数で切り替わる:
  - CLOUD_SQL_INSTANCE が設定されていれば Cloud SQL Connector 経由
  - それ以外は TiDB Cloud / 外部MySQL / ローカルDocker への通常接続
    （DB_SSL=true で TLS を有効化。TiDB Cloud は TLS 必須）

SQLAlchemy のエンジンはモジュール内で 1 つだけ生成し（QueuePool で接続を再利用）、
各関数はそのエンジンから接続を借りて SQL を実行する。テーブルは
CREATE TABLE IF NOT EXISTS により初回アクセス時に自動作成される。
"""

import json
import os
from pathlib import Path

from dotenv import load_dotenv
from sqlalchemy import create_engine, text
from sqlalchemy.pool import QueuePool

from chat.logger import get_logger

load_dotenv(Path(__file__).resolve().parent / ".env")

logger = get_logger("db")

_CLOUD_SQL_INSTANCE = os.getenv("CLOUD_SQL_INSTANCE")
_DB_USER = os.getenv("DB_USER", "root")
_DB_PASS = os.getenv("DB_PASS", "")
_DB_NAME = os.getenv("DB_NAME", "travel_db")
_DB_HOST = os.getenv("DB_HOST", "127.0.0.1")
_DB_PORT = int(os.getenv("DB_PORT", "3306"))
# TiDB Cloud / 外部MySQL は TLS 必須。DB_SSL=true で有効化する。
_DB_SSL = os.getenv("DB_SSL", "false").lower() == "true"
# TLS 検証に使う CA バンドル（コンテナの Ubuntu 既定パス）。環境変数で上書き可。
_DB_SSL_CA = os.getenv("DB_SSL_CA", "/etc/ssl/certs/ca-certificates.crt")

_engine = None
_connector = None


def _get_connector():
    global _connector
    if _connector is None:
        import atexit
        from google.cloud.sql.connector import Connector
        _connector = Connector()
        atexit.register(_connector.close)
    return _connector


def get_engine():
    """共有 SQLAlchemy エンジンを返す（他モジュールからの利用用）。"""
    return _get_engine()


def _get_engine():
    global _engine
    if _engine is not None:
        return _engine

    if _CLOUD_SQL_INSTANCE:
        def getconn():
            return _get_connector().connect(
                _CLOUD_SQL_INSTANCE,
                "pymysql",
                user=_DB_USER,
                password=_DB_PASS,
                db=_DB_NAME,
                charset="utf8mb4",
            )
        _engine = create_engine(
            "mysql+pymysql://",
            creator=getconn,
            poolclass=QueuePool,
            pool_size=5,
            max_overflow=10,
            pool_pre_ping=True,
            pool_recycle=1800,
        )
    else:
        # TiDB Cloud / 外部MySQL / ローカルDocker 共通の通常接続。
        # パスワードに記号が含まれても壊れないよう URL エンコードする。
        from urllib.parse import quote_plus
        url = (
            f"mysql+pymysql://{quote_plus(_DB_USER)}:{quote_plus(_DB_PASS)}"
            f"@{_DB_HOST}:{_DB_PORT}/{_DB_NAME}?charset=utf8mb4"
        )
        connect_args = {}
        if _DB_SSL:
            # CA を指定して TLS 検証する（TiDB Cloud は TLS 必須）
            connect_args["ssl"] = {"ca": _DB_SSL_CA}
        _engine = create_engine(
            url,
            connect_args=connect_args,
            poolclass=QueuePool,
            pool_size=5,
            max_overflow=10,
            pool_pre_ping=True,
            pool_recycle=1800,
        )
    return _engine


_CREATE_PLANS_TABLE = """
CREATE TABLE IF NOT EXISTS travel_plans (
    id               INT AUTO_INCREMENT PRIMARY KEY,
    google_user_id   VARCHAR(255),
    user_email       VARCHAR(255),
    destination      VARCHAR(255)  NOT NULL,
    travel_date      VARCHAR(255),
    duration         VARCHAR(255),
    num_people       INT,
    budget_limit     INT,
    departure_location VARCHAR(255),
    transport_cost   INT,
    remaining_budget INT,
    status           VARCHAR(50),
    feedback         TEXT,
    themes           JSON,
    special_requirements JSON,
    spots            JSON,
    spot_coords      JSON,
    restaurants      JSON,
    restaurant_coords JSON,
    schedule_items   JSON,
    accommodation    JSON,
    accommodation_coords JSON,
    budget_estimate  JSON,
    custom_pins      JSON,
    rating           INT NULL,
    rating_comment   TEXT NULL,
    created_at       TIMESTAMP DEFAULT CURRENT_TIMESTAMP
) CHARACTER SET utf8mb4
"""

# 既存DBに rating / rating_comment 列が無い場合に遅延追加する（一度確認したらキャッシュ）
_plan_columns_ensured = False


def _ensure_plan_columns(conn) -> None:
    global _plan_columns_ensured
    if _plan_columns_ensured:
        return
    for col, ddl in (("rating", "INT NULL"), ("rating_comment", "TEXT NULL"),
                     ("spot_coords", "JSON NULL"), ("restaurant_coords", "JSON NULL"),
                     ("accommodation_coords", "JSON NULL"), ("custom_pins", "JSON NULL")):
        exists = conn.execute(
            text(
                "SELECT COUNT(*) FROM information_schema.columns "
                "WHERE table_schema = DATABASE() AND table_name = 'travel_plans' AND column_name = :c"
            ),
            {"c": col},
        ).scalar()
        if not exists:
            conn.execute(text(f"ALTER TABLE travel_plans ADD COLUMN {col} {ddl}"))
    _plan_columns_ensured = True

_CREATE_CHAT_TABLE = """
CREATE TABLE IF NOT EXISTS chat_messages (
    id             INT AUTO_INCREMENT PRIMARY KEY,
    google_user_id VARCHAR(255)  NOT NULL,
    role           VARCHAR(10)   NOT NULL,
    content        MEDIUMTEXT    NOT NULL,
    request_id     VARCHAR(255),
    created_at     TIMESTAMP(3) DEFAULT CURRENT_TIMESTAMP(3)
) CHARACTER SET utf8mb4
"""


def _row_to_dict(row) -> dict:
    return dict(row._mapping)


def get_travel_plans(google_user_id: str) -> list:
    with _get_engine().connect() as conn:
        conn.execute(text(_CREATE_PLANS_TABLE))
        _ensure_plan_columns(conn)
        rows = conn.execute(
            text(
                "SELECT id, destination, travel_date, duration, num_people, "
                "budget_limit, departure_location, transport_cost, remaining_budget, "
                "status, feedback, themes, special_requirements, "
                "spots, spot_coords, restaurants, restaurant_coords, schedule_items, "
                "accommodation, accommodation_coords, budget_estimate, custom_pins, "
                "rating, rating_comment, created_at "
                "FROM travel_plans WHERE google_user_id = :uid ORDER BY created_at DESC"
            ),
            {"uid": google_user_id},
        ).fetchall()

    result = []
    for row in rows:
        d = _row_to_dict(row)
        for col in ("themes", "special_requirements", "spots", "spot_coords",
                    "restaurants", "restaurant_coords", "schedule_items",
                    "accommodation", "accommodation_coords", "budget_estimate", "custom_pins"):
            if isinstance(d.get(col), str):
                try:
                    d[col] = json.loads(d[col])
                except Exception:
                    d[col] = []
            elif d.get(col) is None:
                d[col] = []
        d["schedule"] = d.pop("schedule_items", [])
        if d.get("created_at"):
            d["created_at"] = str(d["created_at"])
        result.append(d)
    return result


def get_travel_plan_by_id(plan_id: int) -> dict | None:
    """所有者を問わず1件のプランを取得する（共有閲覧で使用）。

    アクセス制御は呼び出し側（共有トークン / メール権限の確認）で行う前提。
    返り値は get_travel_plans の各要素と同じ形（JSON列はパース済み、
    schedule_items は schedule にリネーム）。
    """
    with _get_engine().connect() as conn:
        conn.execute(text(_CREATE_PLANS_TABLE))
        _ensure_plan_columns(conn)
        row = conn.execute(
            text(
                "SELECT id, google_user_id, destination, travel_date, duration, num_people, "
                "budget_limit, departure_location, transport_cost, remaining_budget, "
                "status, feedback, themes, special_requirements, "
                "spots, spot_coords, restaurants, restaurant_coords, schedule_items, "
                "accommodation, accommodation_coords, budget_estimate, custom_pins, "
                "rating, rating_comment, created_at "
                "FROM travel_plans WHERE id = :id"
            ),
            {"id": plan_id},
        ).fetchone()
    if not row:
        return None
    d = _row_to_dict(row)
    for col in ("themes", "special_requirements", "spots", "spot_coords",
                "restaurants", "restaurant_coords", "schedule_items",
                "accommodation", "accommodation_coords", "budget_estimate", "custom_pins"):
        if isinstance(d.get(col), str):
            try:
                d[col] = json.loads(d[col])
            except Exception:
                d[col] = []
        elif d.get(col) is None:
            d[col] = []
    d["schedule"] = d.pop("schedule_items", [])
    if d.get("created_at"):
        d["created_at"] = str(d["created_at"])
    return d


def rate_travel_plan(plan_id: int, google_user_id: str, rating: int, comment: str = "") -> bool:
    """保存プランに★評価とコメントを記録する（本人のプランのみ）。

    1プラン1評価（上書き式）。誤入力の修正のため、評価済みでも再記録で上書きできる。
    """
    with _get_engine().begin() as conn:
        conn.execute(text(_CREATE_PLANS_TABLE))
        _ensure_plan_columns(conn)
        result = conn.execute(
            text(
                "UPDATE travel_plans SET rating = :rating, rating_comment = :comment "
                "WHERE id = :id AND google_user_id = :uid"
            ),
            {"rating": rating, "comment": comment or "", "id": plan_id, "uid": google_user_id},
        )
        return result.rowcount > 0


def get_rated_plans(google_user_id: str, limit: int = 8) -> list:
    """評価済みプランを新しい順に返す（次回生成の好み反映に使う）。"""
    with _get_engine().connect() as conn:
        conn.execute(text(_CREATE_PLANS_TABLE))
        _ensure_plan_columns(conn)
        rows = conn.execute(
            text(
                "SELECT destination, themes, rating, rating_comment "
                "FROM travel_plans WHERE google_user_id = :uid AND rating IS NOT NULL "
                "ORDER BY created_at DESC LIMIT :lim"
            ),
            {"uid": google_user_id, "lim": limit},
        ).fetchall()
    result = []
    for row in rows:
        d = _row_to_dict(row)
        if isinstance(d.get("themes"), str):
            try:
                d["themes"] = json.loads(d["themes"])
            except Exception:
                d["themes"] = []
        elif d.get("themes") is None:
            d["themes"] = []
        result.append(d)
    return result


def update_travel_plan(plan_id: int, google_user_id: str, state: dict) -> bool:
    """既存の保存プランを上書き更新する（本人のプランのみ）。チャット修正で使用。"""
    with _get_engine().begin() as conn:
        conn.execute(text(_CREATE_PLANS_TABLE))
        result = conn.execute(
            text("""
                UPDATE travel_plans SET
                    destination = :destination,
                    travel_date = :travel_date,
                    duration = :duration,
                    num_people = :num_people,
                    budget_limit = :budget_limit,
                    departure_location = :departure_location,
                    transport_cost = :transport_cost,
                    remaining_budget = :remaining_budget,
                    status = :status,
                    feedback = :feedback,
                    themes = :themes,
                    special_requirements = :special_requirements,
                    spots = :spots,
                    spot_coords = :spot_coords,
                    restaurants = :restaurants,
                    restaurant_coords = :restaurant_coords,
                    schedule_items = :schedule_items,
                    accommodation = :accommodation,
                    accommodation_coords = :accommodation_coords,
                    budget_estimate = :budget_estimate
                WHERE id = :id AND google_user_id = :uid
            """),
            {
                "id":                   plan_id,
                "uid":                  google_user_id,
                "destination":          state.get("destination"),
                "travel_date":          state.get("travel_date"),
                "duration":             state.get("duration"),
                "num_people":           state.get("num_people"),
                "budget_limit":         state.get("budget_limit"),
                "departure_location":   state.get("departure_location"),
                "transport_cost":       state.get("transport_cost"),
                "remaining_budget":     state.get("remaining_budget"),
                "status":               state.get("status"),
                "feedback":             state.get("feedback"),
                "themes":               json.dumps(state.get("themes", []), ensure_ascii=False),
                "special_requirements": json.dumps(state.get("special_requirements", []), ensure_ascii=False),
                "spots":                json.dumps(state.get("spots", []), ensure_ascii=False),
                "spot_coords":          json.dumps(state.get("spot_coords", []), ensure_ascii=False),
                "restaurants":          json.dumps(state.get("restaurants", []), ensure_ascii=False),
                "restaurant_coords":    json.dumps(state.get("restaurant_coords", []), ensure_ascii=False),
                "schedule_items":       json.dumps(state.get("schedule", []), ensure_ascii=False),
                "accommodation":        json.dumps(state.get("accommodation", []), ensure_ascii=False),
                "accommodation_coords": json.dumps(state.get("accommodation_coords", []), ensure_ascii=False),
                "budget_estimate":      json.dumps(state.get("budget_estimate", []), ensure_ascii=False),
            },
        )
        return result.rowcount > 0


def update_plan_coords(plan_id: int, spot_coords, restaurant_coords, accommodation_coords) -> bool:
    """プランの地図座標列だけを更新する（地図初回表示時の遅延ジオコーディング用）。"""
    with _get_engine().begin() as conn:
        conn.execute(text(_CREATE_PLANS_TABLE))
        _ensure_plan_columns(conn)
        result = conn.execute(
            text(
                "UPDATE travel_plans SET spot_coords = :s, restaurant_coords = :r, "
                "accommodation_coords = :a WHERE id = :id"
            ),
            {
                "s": json.dumps(spot_coords or [], ensure_ascii=False),
                "r": json.dumps(restaurant_coords or [], ensure_ascii=False),
                "a": json.dumps(accommodation_coords or [], ensure_ascii=False),
                "id": plan_id,
            },
        )
        return result.rowcount > 0


def update_plan_custom_pins(plan_id: int, google_user_id: str, custom_pins) -> bool:
    """ユーザーが手動設置したカスタムピンを保存する（本人のプランのみ）。"""
    with _get_engine().begin() as conn:
        conn.execute(text(_CREATE_PLANS_TABLE))
        _ensure_plan_columns(conn)
        exists = conn.execute(
            text("SELECT 1 FROM travel_plans WHERE id = :id AND google_user_id = :uid"),
            {"id": plan_id, "uid": google_user_id},
        ).fetchone()
        if not exists:
            return False
        conn.execute(
            text("UPDATE travel_plans SET custom_pins = :p WHERE id = :id AND google_user_id = :uid"),
            {"p": json.dumps(custom_pins or [], ensure_ascii=False), "id": plan_id, "uid": google_user_id},
        )
    return True


def delete_travel_plan(plan_id: int, google_user_id: str) -> bool:
    with _get_engine().begin() as conn:
        result = conn.execute(
            text("DELETE FROM travel_plans WHERE id = :id AND google_user_id = :uid"),
            {"id": plan_id, "uid": google_user_id},
        )
        return result.rowcount > 0


def get_chat_messages(google_user_id: str) -> list:
    with _get_engine().connect() as conn:
        conn.execute(text(_CREATE_CHAT_TABLE))
        rows = conn.execute(
            text(
                "SELECT role, content, request_id FROM chat_messages "
                "WHERE google_user_id = :uid ORDER BY created_at ASC"
            ),
            {"uid": google_user_id},
        ).fetchall()
    return [_row_to_dict(r) for r in rows]


def save_chat_message(google_user_id: str, role: str, content: str, request_id: str = None) -> None:
    with _get_engine().begin() as conn:
        conn.execute(text(_CREATE_CHAT_TABLE))
        conn.execute(
            text(
                "INSERT INTO chat_messages (google_user_id, role, content, request_id) "
                "VALUES (:uid, :role, :content, :rid)"
            ),
            {"uid": google_user_id, "role": role, "content": content, "rid": request_id},
        )


def clear_chat_messages(google_user_id: str) -> None:
    with _get_engine().begin() as conn:
        conn.execute(
            text("DELETE FROM chat_messages WHERE google_user_id = :uid"),
            {"uid": google_user_id},
        )


def delete_chat_messages_by_request(google_user_id: str, request_id: str) -> None:
    with _get_engine().begin() as conn:
        conn.execute(
            text(
                "DELETE FROM chat_messages WHERE google_user_id = :uid AND request_id = :rid"
            ),
            {"uid": google_user_id, "rid": request_id},
        )


def save_travel_plan(state: dict, google_user_id: str = None, user_email: str = None) -> int:
    with _get_engine().begin() as conn:
        conn.execute(text(_CREATE_PLANS_TABLE))
        result = conn.execute(
            text("""
                INSERT INTO travel_plans (
                    google_user_id, user_email,
                    destination, travel_date, duration, num_people,
                    budget_limit, departure_location, transport_cost,
                    remaining_budget, status, feedback,
                    themes, special_requirements, spots, spot_coords,
                    restaurants, restaurant_coords,
                    schedule_items, accommodation, accommodation_coords, budget_estimate
                ) VALUES (
                    :google_user_id, :user_email,
                    :destination, :travel_date, :duration, :num_people,
                    :budget_limit, :departure_location, :transport_cost,
                    :remaining_budget, :status, :feedback,
                    :themes, :special_requirements, :spots, :spot_coords,
                    :restaurants, :restaurant_coords,
                    :schedule_items, :accommodation, :accommodation_coords, :budget_estimate
                )
            """),
            {
                "google_user_id":       google_user_id,
                "user_email":           user_email,
                "destination":          state.get("destination"),
                "travel_date":          state.get("travel_date"),
                "duration":             state.get("duration"),
                "num_people":           state.get("num_people"),
                "budget_limit":         state.get("budget_limit"),
                "departure_location":   state.get("departure_location"),
                "transport_cost":       state.get("transport_cost"),
                "remaining_budget":     state.get("remaining_budget"),
                "status":               state.get("status"),
                "feedback":             state.get("feedback"),
                "themes":               json.dumps(state.get("themes", []), ensure_ascii=False),
                "special_requirements": json.dumps(state.get("special_requirements", []), ensure_ascii=False),
                "spots":                json.dumps(state.get("spots", []), ensure_ascii=False),
                "spot_coords":          json.dumps(state.get("spot_coords", []), ensure_ascii=False),
                "restaurants":          json.dumps(state.get("restaurants", []), ensure_ascii=False),
                "restaurant_coords":    json.dumps(state.get("restaurant_coords", []), ensure_ascii=False),
                "schedule_items":       json.dumps(state.get("schedule", []), ensure_ascii=False),
                "accommodation":        json.dumps(state.get("accommodation", []), ensure_ascii=False),
                "accommodation_coords": json.dumps(state.get("accommodation_coords", []), ensure_ascii=False),
                "budget_estimate":      json.dumps(state.get("budget_estimate", []), ensure_ascii=False),
            },
        )
        return result.lastrowid
