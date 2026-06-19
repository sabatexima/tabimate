import json
import os
import threading
import time
import uuid
from collections import defaultdict

from flask import Blueprint, Response, render_template, request, session, stream_with_context

from chat.chat import chat
from chat.logger import get_logger
from views.auth import login_required

planner = Blueprint("planner", __name__)
logger = get_logger("views.planner")


class _ActiveRequests:
    """Redis-backed active request tracker with in-process fallback.

    Redisが利用可能な場合はそちらを使い、複数ワーカー間でキャンセル状態を共有する。
    REDIS_URL未設定時はプロセス内setにフォールバックする（開発環境向け）。
    """

    _PREFIX = "active_req:"
    _TTL = 600  # seconds

    def __init__(self):
        self._local: set = set()
        self._lock = threading.Lock()
        self._redis = None

        redis_url = os.getenv("REDIS_URL")
        if redis_url:
            try:
                import redis as redis_lib
                client = redis_lib.from_url(redis_url, decode_responses=True)
                client.ping()
                self._redis = client
                logger.info("Redis接続成功: active_requestsはRedisで管理します")
            except Exception:
                logger.warning("Redis接続失敗: active_requestsはプロセス内setにフォールバックします")

    def add(self, request_id: str) -> None:
        if self._redis:
            self._redis.setex(f"{self._PREFIX}{request_id}", self._TTL, "1")
        else:
            with self._lock:
                self._local.add(request_id)

    def discard(self, request_id: str) -> None:
        if self._redis:
            self._redis.delete(f"{self._PREFIX}{request_id}")
        else:
            with self._lock:
                self._local.discard(request_id)

    def __contains__(self, request_id: str) -> bool:
        if self._redis:
            return self._redis.exists(f"{self._PREFIX}{request_id}") > 0
        with self._lock:
            return request_id in self._local


active_requests = _ActiveRequests()

_rate_lock = threading.Lock()
_rate_log: dict[str, list[float]] = defaultdict(list)
_RATE_LIMIT = 5   # リクエスト数
_RATE_WINDOW = 60 # 秒


def _is_rate_limited(user_id: str) -> bool:
    now = time.time()
    with _rate_lock:
        timestamps = _rate_log[user_id]
        timestamps[:] = [t for t in timestamps if now - t < _RATE_WINDOW]
        if len(timestamps) >= _RATE_LIMIT:
            return True
        timestamps.append(now)
        return False


@planner.route("/")
def home():
    logger.debug("ホームアクセス")
    return render_template("home.html")


@planner.route("/saved_plans")
@login_required
def saved_plans():
    return render_template("saved_plans.html")


@planner.route('/send_message', methods=['POST'])
@login_required
def send_message():
    from db import delete_chat_messages_by_request, get_chat_messages, save_chat_message

    user_id = session['user_id']

    if _is_rate_limited(user_id):
        logger.warning("レートリミット超過: user_id=%s", user_id)
        return json.dumps({'status': 'ERROR', 'message': 'リクエストが多すぎます。しばらくお待ちください。'}), 429, {'Content-Type': 'application/json'}

    user_message = request.form['message']
    request_id = request.form.get('request_id') or str(uuid.uuid4())

    active_requests.add(request_id)
    save_chat_message(user_id, 'user', user_message, request_id)
    messages = get_chat_messages(user_id)

    result: dict = {}
    done_event = threading.Event()

    def run_chat():
        try:
            result['response'] = chat(
                user_message,
                messages_history=messages,
                request_id=request_id,
                active_requests=active_requests,
            )
        except Exception:
            logger.exception("メッセージ処理中にエラーが発生しました: request_id=%s", request_id)
            result['error'] = True
        finally:
            done_event.set()

    threading.Thread(target=run_chat, daemon=True).start()

    def generate():
        try:
            while not done_event.wait(timeout=3):
                yield "data: {\"status\": \"thinking\"}\n\n"

            if result.get('error'):
                delete_chat_messages_by_request(user_id, request_id)
                yield f"data: {json.dumps({'status': 'ERROR', 'message': 'プランの生成中にエラーが発生しました'})}\n\n"
                return

            ai_response = result.get('response')
            if ai_response is None or request_id not in active_requests:
                delete_chat_messages_by_request(user_id, request_id)
                logger.info("リクエストがキャンセルされました: request_id=%s", request_id)
                yield f"data: {json.dumps({'status': 'ABORTED', 'id': request_id})}\n\n"
                return

            save_chat_message(user_id, 'ai', ai_response, request_id)
            logger.info("メッセージ処理完了: request_id=%s", request_id)
            yield f"data: {json.dumps({'status': 'OK', 'id': request_id})}\n\n"
        finally:
            active_requests.discard(request_id)

    return Response(
        stream_with_context(generate()),
        content_type='text/event-stream',
        headers={'Cache-Control': 'no-cache', 'X-Accel-Buffering': 'no'},
    )


@planner.route('/abort_request', methods=['POST'])
@login_required
def abort_request():
    from db import delete_chat_messages_by_request

    user_id = session['user_id']
    request_id = request.form.get('request_id')
    if request_id:
        active_requests.discard(request_id)
        delete_chat_messages_by_request(user_id, request_id)
        logger.info("中断リクエスト受信: request_id=%s", request_id)
    return json.dumps({'status': 'ABORT_SIGNAL_SENT_AND_REMOVED'}), 200, {'Content-Type': 'application/json'}


@planner.route('/reset_chat', methods=['POST'])
@login_required
def reset_chat():
    from db import clear_chat_messages
    clear_chat_messages(session['user_id'])
    logger.info("チャット履歴をリセット: user_id=%s", session['user_id'])
    return json.dumps({'status': 'OK'}), 200, {'Content-Type': 'application/json'}


@planner.route('/get_messages')
@login_required
def get_messages():
    from db import get_chat_messages
    return json.dumps(get_chat_messages(session['user_id'])), 200, {'Content-Type': 'application/json'}


@planner.route('/save_plan', methods=['POST'])
@login_required
def save_plan():
    try:
        plan = request.get_json(force=True)
        from db import save_travel_plan
        plan_id = save_travel_plan(
            plan,
            google_user_id=session.get('user_id'),
            user_email=session.get('user_email'),
        )
        logger.info("プラン保存成功: plan_id=%s", plan_id)
        return json.dumps({'status': 'OK', 'id': plan_id}), 200, {'Content-Type': 'application/json'}
    except Exception as e:
        logger.exception("プラン保存失敗: %s", e)
        return json.dumps({'status': 'ERROR', 'message': str(e)}), 500, {'Content-Type': 'application/json'}


@planner.route('/delete_plan/<int:plan_id>', methods=['DELETE'])
@login_required
def delete_plan(plan_id):
    try:
        from db import delete_travel_plan
        deleted = delete_travel_plan(plan_id, session['user_id'])
        if deleted:
            logger.info("プラン削除成功: plan_id=%s", plan_id)
            return json.dumps({'status': 'OK'}), 200, {'Content-Type': 'application/json'}
        logger.warning("プラン削除失敗（未発見）: plan_id=%s", plan_id)
        return json.dumps({'status': 'ERROR', 'message': 'プランが見つかりません'}), 404, {'Content-Type': 'application/json'}
    except Exception as e:
        logger.exception("プラン削除失敗: plan_id=%s, error=%s", plan_id, e)
        return json.dumps({'status': 'ERROR', 'message': str(e)}), 500, {'Content-Type': 'application/json'}


@planner.route('/get_my_plans')
@login_required
def get_my_plans():
    try:
        from db import get_travel_plans
        plans = get_travel_plans(session['user_id'])
        return json.dumps({'status': 'OK', 'plans': plans}, ensure_ascii=False, default=str), 200, {'Content-Type': 'application/json'}
    except Exception as e:
        logger.exception("プラン一覧取得失敗: %s", e)
        return json.dumps({'status': 'ERROR', 'message': str(e)}), 500, {'Content-Type': 'application/json'}
