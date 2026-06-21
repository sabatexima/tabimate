"""メイン機能（旅行プラン作成チャット）の画面・APIを束ねる Blueprint。

主な責務:
  - ホーム/保存プラン画面の表示
  - チャット送信(/send_message)を SSE でストリーミング応答
    （別スレッドで chat() を実行し、待機中は thinking を送出、
      キャンセル可能にするため active_requests で状態を共有）
  - チャット履歴・保存プランの取得/削除
  - 簡易レートリミットによる多重リクエスト抑制
"""

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
    """処理中リクエストの追跡器（Redis優先・プロセス内フォールバック）。

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
_MAX_MESSAGE_LEN = 2000  # 1発話あたりの最大文字数（過大入力によるコスト増を抑制）
_last_rate_sweep = 0.0   # 最後に古いエントリを掃除した時刻


def _is_rate_limited(user_id: str) -> bool:
    """直近 _RATE_WINDOW 秒で _RATE_LIMIT 回を超えていれば True を返す。"""
    now = time.time()
    with _rate_lock:
        # 定期的に古いユーザーのエントリを掃除し、_rate_log の無制限な増加を防ぐ
        global _last_rate_sweep
        if now - _last_rate_sweep > _RATE_WINDOW:
            for uid in list(_rate_log.keys()):
                _rate_log[uid][:] = [t for t in _rate_log[uid] if now - t < _RATE_WINDOW]
                if not _rate_log[uid]:
                    del _rate_log[uid]
            _last_rate_sweep = now

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
    """ユーザー発話を受け取り、AI応答を SSE でストリーミング返却する。

    chat() を別スレッドで実行し、完了までは thinking イベントを送り続ける。
    途中でキャンセル/エラーの場合は該当リクエストのメッセージを削除する。
    """
    from db import delete_chat_messages_by_request, get_chat_messages, save_chat_message

    user_id = session['user_id']

    if _is_rate_limited(user_id):
        logger.warning("レートリミット超過: user_id=%s", user_id)
        return json.dumps({'status': 'ERROR', 'message': 'リクエストが多すぎます。しばらくお待ちください。'}), 429, {'Content-Type': 'application/json'}

    user_message = (request.form.get('message') or '').strip()
    if not user_message:
        return json.dumps({'status': 'ERROR', 'message': 'メッセージが空です'}), 400, {'Content-Type': 'application/json'}
    if len(user_message) > _MAX_MESSAGE_LEN:
        user_message = user_message[:_MAX_MESSAGE_LEN]
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
        return json.dumps({'status': 'ERROR', 'message': 'サーバーエラーが発生しました。しばらくして再度お試しください。'}), 500, {'Content-Type': 'application/json'}


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
        return json.dumps({'status': 'ERROR', 'message': 'サーバーエラーが発生しました。しばらくして再度お試しください。'}), 500, {'Content-Type': 'application/json'}


def _can_edit_plan(plan: dict, plan_id: int) -> bool:
    """ログイン中のユーザーがこのプランを編集できるか（所有者 or 編集権限の共有相手）。"""
    if not plan:
        return False
    if plan.get('google_user_id') == session.get('user_id'):
        return True
    import db_sharing
    grant = db_sharing.get_grant_for_email('plan', plan_id, session.get('user_email'))
    return bool(grant and grant.get('permission') == 'edit')


def _plan_to_view_dict(state: dict, plan_id: int, created_at) -> dict:
    """生成結果(TravelPlanState)を、一覧描画と同じ形のプラン辞書に整える（プレビュー用）。"""
    return {
        'id': plan_id,
        'destination': state.get('destination'),
        'travel_date': state.get('travel_date'),
        'duration': state.get('duration'),
        'num_people': state.get('num_people'),
        'budget_limit': state.get('budget_limit'),
        'departure_location': state.get('departure_location'),
        'transport_cost': state.get('transport_cost'),
        'remaining_budget': state.get('remaining_budget'),
        'status': state.get('status'),
        'feedback': state.get('feedback'),
        'themes': state.get('themes', []),
        'special_requirements': state.get('special_requirements', []),
        'spots': state.get('spots', []),
        'restaurants': state.get('restaurants', []),
        'schedule': state.get('schedule', []),
        'accommodation': state.get('accommodation', []),
        'budget_estimate': state.get('budget_estimate', []),
        'created_at': created_at,
    }


@planner.route('/edit_saved_plan/<int:plan_id>', methods=['POST'])
@login_required
def edit_saved_plan(plan_id):
    """保存済みプランをチャット指示で修正し、修正案（プレビュー）を返す。

    この時点では保存しない。確定は /apply_saved_plan で行う。
    """
    from db import get_travel_plan_by_id
    from chat.chat import edit_saved_plan as run_plan_edit

    user_id = session['user_id']
    if _is_rate_limited(user_id):
        return json.dumps({'status': 'ERROR', 'message': 'リクエストが多すぎます。しばらくお待ちください。'}), 429, {'Content-Type': 'application/json'}

    data = request.get_json(silent=True) or request.form
    message = (data.get('message') or '').strip()
    if not message:
        return json.dumps({'status': 'ERROR', 'message': '修正したい内容を入力してください'}), 400, {'Content-Type': 'application/json'}
    if len(message) > _MAX_MESSAGE_LEN:
        message = message[:_MAX_MESSAGE_LEN]

    plan = get_travel_plan_by_id(plan_id)
    if not plan:
        return json.dumps({'status': 'ERROR', 'message': 'プランが見つかりません'}), 404, {'Content-Type': 'application/json'}
    if not _can_edit_plan(plan, plan_id):
        return json.dumps({'status': 'ERROR', 'message': 'このプランを編集する権限がありません'}), 403, {'Content-Type': 'application/json'}

    # 生成に時間がかかるため、本体チャットと同様に SSE でストリーミングする
    # （生成中は thinking を送り続け、接続のアイドル切断を防ぐ）。
    result: dict = {}
    done_event = threading.Event()

    def run_edit():
        try:
            final_state = run_plan_edit(plan, message)
            # まだ保存しない。修正案（プレビュー）として返す
            result['plan'] = _plan_to_view_dict(final_state, plan_id, plan.get('created_at'))
        except ValueError as e:
            result['error_message'] = str(e)  # 予算超過などユーザーに伝える値域エラー
        except Exception:
            logger.exception("保存プランのチャット修正に失敗: plan_id=%s", plan_id)
            result['error'] = True
        finally:
            done_event.set()

    threading.Thread(target=run_edit, daemon=True).start()

    def generate():
        while not done_event.wait(timeout=3):
            yield 'data: {"status": "thinking"}\n\n'
        if result.get('plan') is not None:
            logger.info("保存プランをチャット修正: plan_id=%s", plan_id)
            yield f"data: {json.dumps({'status': 'OK', 'plan': result['plan']}, ensure_ascii=False, default=str)}\n\n"
        elif result.get('error_message'):
            yield f"data: {json.dumps({'status': 'ERROR', 'message': result['error_message']}, ensure_ascii=False)}\n\n"
        else:
            yield 'data: {"status": "ERROR", "message": "修正中にエラーが発生しました。もう一度お試しください。"}\n\n'

    return Response(
        stream_with_context(generate()),
        content_type='text/event-stream',
        headers={'Cache-Control': 'no-cache', 'X-Accel-Buffering': 'no'},
    )


@planner.route('/apply_saved_plan/<int:plan_id>', methods=['POST'])
@login_required
def apply_saved_plan(plan_id):
    """プレビューした修正案を確定して保存（上書き）する。生成は走らない。"""
    from db import get_travel_plan_by_id, update_travel_plan

    plan = get_travel_plan_by_id(plan_id)
    if not plan:
        return json.dumps({'status': 'ERROR', 'message': 'プランが見つかりません'}), 404, {'Content-Type': 'application/json'}
    if not _can_edit_plan(plan, plan_id):
        return json.dumps({'status': 'ERROR', 'message': 'このプランを編集する権限がありません'}), 403, {'Content-Type': 'application/json'}

    data = request.get_json(silent=True) or {}
    new_plan = data.get('plan')
    if not isinstance(new_plan, dict):
        return json.dumps({'status': 'ERROR', 'message': '更新内容が不正です'}), 400, {'Content-Type': 'application/json'}

    # 共有編集でも書き換える対象は所有者の行（共同編集＝上書き）
    update_travel_plan(plan_id, plan.get('google_user_id'), new_plan)
    logger.info("保存プランの修正を確定: plan_id=%s", plan_id)
    return json.dumps({'status': 'OK', 'plan': get_travel_plan_by_id(plan_id)}, ensure_ascii=False, default=str), 200, {'Content-Type': 'application/json'}


@planner.route('/get_my_plans')
@login_required
def get_my_plans():
    try:
        from db import get_travel_plans
        plans = get_travel_plans(session['user_id'])
        return json.dumps({'status': 'OK', 'plans': plans}, ensure_ascii=False, default=str), 200, {'Content-Type': 'application/json'}
    except Exception as e:
        logger.exception("プラン一覧取得失敗: %s", e)
        return json.dumps({'status': 'ERROR', 'message': 'サーバーエラーが発生しました。しばらくして再度お試しください。'}), 500, {'Content-Type': 'application/json'}


@planner.route('/get_shared_plans')
@login_required
def get_shared_plans():
    """自分宛に共有された旅行プランを返す（保存プラン画面に統合表示する）。"""
    try:
        import db_sharing
        from db import get_travel_plan_by_id
        grants = db_sharing.get_grants_for_email(session.get('user_email'))
        plans = []
        for g in grants:
            if g['resource_type'] != 'plan':
                continue
            p = get_travel_plan_by_id(g['resource_id'])
            if p:
                p['grant_id'] = g['id']
                p['permission'] = g['permission']
                plans.append(p)
        return json.dumps({'status': 'OK', 'plans': plans}, ensure_ascii=False, default=str), 200, {'Content-Type': 'application/json'}
    except Exception as e:
        logger.exception("共有プラン一覧取得失敗: %s", e)
        return json.dumps({'status': 'ERROR', 'message': 'サーバーエラーが発生しました。しばらくして再度お試しください。'}), 500, {'Content-Type': 'application/json'}
