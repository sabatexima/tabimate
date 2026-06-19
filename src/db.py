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
        url = (
            f"mysql+pymysql://{_DB_USER}:{_DB_PASS}"
            f"@{_DB_HOST}:{_DB_PORT}/{_DB_NAME}?charset=utf8mb4"
        )
        _engine = create_engine(
            url,
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
    restaurants      JSON,
    schedule_items   JSON,
    accommodation    JSON,
    budget_estimate  JSON,
    created_at       TIMESTAMP DEFAULT CURRENT_TIMESTAMP
) CHARACTER SET utf8mb4
"""

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
        rows = conn.execute(
            text(
                "SELECT id, destination, travel_date, duration, num_people, "
                "budget_limit, departure_location, transport_cost, remaining_budget, "
                "status, feedback, themes, special_requirements, "
                "spots, restaurants, schedule_items, accommodation, budget_estimate, created_at "
                "FROM travel_plans WHERE google_user_id = :uid ORDER BY created_at DESC"
            ),
            {"uid": google_user_id},
        ).fetchall()

    result = []
    for row in rows:
        d = _row_to_dict(row)
        for col in ("themes", "special_requirements", "spots", "restaurants",
                    "schedule_items", "accommodation", "budget_estimate"):
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
                    themes, special_requirements, spots, restaurants,
                    schedule_items, accommodation, budget_estimate
                ) VALUES (
                    :google_user_id, :user_email,
                    :destination, :travel_date, :duration, :num_people,
                    :budget_limit, :departure_location, :transport_cost,
                    :remaining_budget, :status, :feedback,
                    :themes, :special_requirements, :spots, :restaurants,
                    :schedule_items, :accommodation, :budget_estimate
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
                "restaurants":          json.dumps(state.get("restaurants", []), ensure_ascii=False),
                "schedule_items":       json.dumps(state.get("schedule", []), ensure_ascii=False),
                "accommodation":        json.dumps(state.get("accommodation", []), ensure_ascii=False),
                "budget_estimate":      json.dumps(state.get("budget_estimate", []), ensure_ascii=False),
            },
        )
        return result.lastrowid
