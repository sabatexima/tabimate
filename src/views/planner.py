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

from flask import Blueprint, Response, abort, render_template, request, session, stream_with_context

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
_RATE_LIMIT = 20  # リクエスト数（条件入力は1問1答で何度も送るため、通常会話で超えない値にする）
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


# 地図・座標・天気など外部API（Nominatim/Open-Meteo）を叩く系のゆるいレート制限。
# 連打で外部APIに負荷をかけたり制限/banされるのを防ぐ保険（通常利用では超えない）。
_geo_rate_log: dict[str, list[float]] = defaultdict(list)
_GEO_RATE_LIMIT = 40


def _geo_rate_limited(user_id: str) -> bool:
    now = time.time()
    with _rate_lock:
        ts = _geo_rate_log[user_id]
        ts[:] = [t for t in ts if now - t < _RATE_WINDOW]
        if len(ts) >= _GEO_RATE_LIMIT:
            return True
        ts.append(now)
        return False


def _seasonal_ideas():
    """今の月に合った「こんな旅はどう？」のチップを返す（季節外れの提案を防ぐ）。

    各要素は (emoji, ラベル, チャットに送る文) のタプル。
    """
    from datetime import date
    m = date.today().month
    if m in (3, 4, 5):
        seasonal = [("🌸", "桜・お花見めぐり", "桜やお花見が楽しめる春の旅がしたい"),
                    ("🍓", "いちご狩り", "いちご狩りが楽しめる日帰り旅がしたい")]
    elif m == 6:
        seasonal = [("💠", "紫陽花の名所", "紫陽花が見頃の名所をめぐる旅がしたい"),
                    ("🌊", "海辺でのんびり", "海の見える場所でのんびりする旅がしたい")]
    elif m in (7, 8):
        seasonal = [("🏖️", "海・ビーチ", "海やビーチで遊ぶ夏の旅がしたい"),
                    ("🎆", "夏祭り・花火", "夏祭りや花火大会を楽しむ旅がしたい")]
    elif m in (9, 10, 11):
        seasonal = [("🍁", "紅葉狩り", "紅葉狩りが楽しめる秋の旅がしたい"),
                    ("🍇", "秋の味覚狩り", "ぶどう狩りなど秋の味覚狩りの旅がしたい")]
    else:  # 12, 1, 2
        seasonal = [("♨️", "温泉でほっこり", "温泉でゆっくり過ごす冬の旅がしたい"),
                    ("✨", "イルミネーション", "イルミネーションを楽しむ旅がしたい")]
    evergreen = [
        ("🍡", "食べ歩き日帰り", "近場で食べ歩きの日帰り旅がしたい"),
        ("👨‍👩‍👧", "家族でおでかけ", "子連れで安心して楽しめる家族旅行"),
        ("🎨", "ひとり美術館めぐり", "一人でゆっくり美術館をめぐる旅がしたい"),
    ]
    return seasonal + evergreen


@planner.route("/")
def home():
    """世界観を伝えるホーム（ハブ）。プラン作成チャットへは /chat から。"""
    logger.debug("ホームアクセス")
    return render_template("welcome.html", ideas=_seasonal_ideas())


@planner.route("/chat")
def chat():
    """旅行プラン作成チャット画面（旧ホーム）。"""
    logger.debug("チャットアクセス")
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
                user_id=user_id,
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
        # 座標は保存時には取らない（保存を即時に保つ）。地図を初めて開いたときに
        # /api/plan_geo がまとめてジオコーディングしDBにキャッシュする。
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
        'total_per_person': state.get('total_per_person'),
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

    # 座標はここでは取らない（スポットが変わり得るので一旦クリアし、次に地図を
    # 開いたとき /api/plan_geo が取り直してキャッシュする）。保存を即時に保つ。
    new_plan['spot_coords'] = []
    new_plan['restaurant_coords'] = []
    new_plan['accommodation_coords'] = []

    # 共有編集でも書き換える対象は所有者の行（共同編集＝上書き）
    update_travel_plan(plan_id, plan.get('google_user_id'), new_plan)
    logger.info("保存プランの修正を確定: plan_id=%s", plan_id)
    return json.dumps({'status': 'OK', 'plan': get_travel_plan_by_id(plan_id)}, ensure_ascii=False, default=str), 200, {'Content-Type': 'application/json'}


@planner.route('/rate_plan/<int:plan_id>', methods=['POST'])
@login_required
def rate_plan(plan_id):
    """保存プランに★評価（1〜5）とコメントを記録する（本人のみ）。"""
    from db import rate_travel_plan
    data = request.get_json(silent=True) or request.form
    try:
        rating = int(data.get('rating'))
    except (TypeError, ValueError):
        return json.dumps({'status': 'ERROR', 'message': '評価（1〜5）を指定してください'}), 400, {'Content-Type': 'application/json'}
    if rating < 1 or rating > 5:
        return json.dumps({'status': 'ERROR', 'message': '評価は1〜5で指定してください'}), 400, {'Content-Type': 'application/json'}
    comment = (data.get('comment') or '').strip()[:1000]
    ok = rate_travel_plan(plan_id, session['user_id'], rating, comment)
    if not ok:
        return json.dumps({'status': 'ERROR', 'message': 'プランが見つかりません'}), 404, {'Content-Type': 'application/json'}
    return json.dumps({'status': 'OK'}), 200, {'Content-Type': 'application/json'}


def _build_plan_ics(plan: dict) -> str:
    """保存プランを iCalendar(.ics) 文字列に変換する（Google カレンダー等に取込可能）。

    スケジュールは自由文のため、旅行日〜期間から終日イベントを1件作り、
    観光・グルメ・宿・スケジュール・費用を説明文にまとめる。
    """
    import re
    from datetime import date, datetime, timedelta

    def esc(s):
        return (str(s or '').replace('\\', '\\\\').replace(';', '\\;')
                .replace(',', '\\,').replace('\n', '\\n'))

    # 旅行日の抽出（YYYY-MM-DD / YYYY/MM/DD / YYYY年M月D日）。取れなければ今日。
    m = re.search(r'(\d{4})[-/年](\d{1,2})[-/月](\d{1,2})', str(plan.get('travel_date') or ''))
    try:
        start = date(int(m.group(1)), int(m.group(2)), int(m.group(3))) if m else date.today()
    except ValueError:
        start = date.today()
    # 期間 → 日数（「N泊」→ N+1日、それ以外は1日）
    nm = re.search(r'(\d+)\s*泊', str(plan.get('duration') or ''))
    end = start + timedelta(days=(int(nm.group(1)) + 1 if nm else 1))

    lines = []
    def add(label, items):
        if items:
            lines.append(f"{label}: " + "、".join(items))
    add('✨観光', plan.get('spots'))
    add('🍱グルメ', plan.get('restaurants'))
    add('🏨宿泊', plan.get('accommodation'))
    if plan.get('schedule'):
        lines.append('📅スケジュール')
        lines.extend(plan.get('schedule'))
    if plan.get('budget_estimate'):
        lines.append('💰費用')
        lines.extend(plan.get('budget_estimate'))

    summary = f"🗾 {plan.get('destination') or '旅行'} 旅行プラン"
    dtstamp = datetime.utcnow().strftime('%Y%m%dT%H%M%SZ')
    return "\r\n".join([
        "BEGIN:VCALENDAR", "VERSION:2.0", "PRODID:-//tabimate//travel plan//JA",
        "CALSCALE:GREGORIAN", "BEGIN:VEVENT",
        f"UID:tabimate-plan-{plan.get('id')}@kabu-app",
        f"DTSTAMP:{dtstamp}",
        f"DTSTART;VALUE=DATE:{start.strftime('%Y%m%d')}",
        f"DTEND;VALUE=DATE:{end.strftime('%Y%m%d')}",
        f"SUMMARY:{esc(summary)}",
        f"DESCRIPTION:{esc(chr(10).join(lines))}",
        "END:VEVENT", "END:VCALENDAR", "",
    ])


@planner.route('/export_plan_ics/<int:plan_id>')
@login_required
def export_plan_ics(plan_id):
    """保存プランを .ics（iCalendar）でダウンロードする（本人のプランのみ）。"""
    from db import get_travel_plan_by_id
    plan = get_travel_plan_by_id(plan_id)
    if not plan:
        return json.dumps({'status': 'ERROR', 'message': 'プランが見つかりません'}), 404, {'Content-Type': 'application/json'}
    if plan.get('google_user_id') != session.get('user_id'):
        return json.dumps({'status': 'ERROR', 'message': 'このプランを書き出す権限がありません'}), 403, {'Content-Type': 'application/json'}
    ics = _build_plan_ics(plan)
    return Response(ics, mimetype='text/calendar; charset=utf-8', headers={
        'Content-Disposition': f'attachment; filename="tabimate_plan_{plan_id}.ics"',
    })


@planner.route('/api/plan_weather/<int:plan_id>')
@login_required
def plan_weather(plan_id):
    """保存プランの目的地・旅行日の天気予報を返す（Open-Meteo・APIキー不要・本人のみ）。"""
    from db import get_travel_plan_by_id
    import weather

    plan = get_travel_plan_by_id(plan_id)
    if not plan or plan.get('google_user_id') != session.get('user_id'):
        return json.dumps({'status': 'OK', 'days': []}), 200, {'Content-Type': 'application/json'}
    if _geo_rate_limited(session.get('user_id')):
        return json.dumps({'status': 'OK', 'days': []}), 200, {'Content-Type': 'application/json'}

    days = weather.plan_forecast(plan)
    return json.dumps({'status': 'OK', 'days': days}, ensure_ascii=False), 200, {'Content-Type': 'application/json'}


@planner.route('/save_plan_pins/<int:plan_id>', methods=['POST'])
@login_required
def save_plan_pins(plan_id):
    """ユーザーが地図上に手動設置したカスタムピンを保存する（本人のプランのみ）。"""
    from db import update_plan_custom_pins
    data = request.get_json(silent=True) or {}
    raw = data.get('pins')
    if not isinstance(raw, list):
        return json.dumps({'status': 'ERROR', 'message': 'ピンの形式が不正です'}), 400, {'Content-Type': 'application/json'}
    # 値域を検証して安全な形だけ保存する（名前60字・種類ホワイトリスト・色は#rrggbb）
    import re as _re
    _PIN_TYPES = {'memo', 'spot', 'restaurant', 'accommodation'}
    pins = []
    for p in raw[:50]:
        try:
            lat = float(p['lat']); lng = float(p['lng'])
        except (KeyError, TypeError, ValueError):
            continue
        if not (-90 <= lat <= 90 and -180 <= lng <= 180):
            continue
        name = str(p.get('name') or '').strip()[:60]
        ptype = str(p.get('type') or 'memo')
        if ptype not in _PIN_TYPES:
            ptype = 'memo'
        pin = {'name': name, 'lat': lat, 'lng': lng, 'type': ptype}
        color = p.get('color')
        if color and _re.match(r'^#[0-9a-fA-F]{6}$', str(color)):
            pin['color'] = str(color)
        pins.append(pin)
    ok = update_plan_custom_pins(plan_id, session.get('user_id'), pins)
    if not ok:
        return json.dumps({'status': 'ERROR', 'message': 'プランが見つかりません'}), 404, {'Content-Type': 'application/json'}
    return json.dumps({'status': 'OK', 'pins': pins}, ensure_ascii=False), 200, {'Content-Type': 'application/json'}


@planner.route('/plan/<int:plan_id>/print')
@login_required
def plan_print(plan_id):
    """プランを「旅のしおり」として印刷／PDF保存できる専用ページ（本人のみ）。"""
    from db import get_travel_plan_by_id
    import weather
    plan = get_travel_plan_by_id(plan_id)
    if not plan or plan.get('google_user_id') != session.get('user_id'):
        abort(404)
    weather_days = weather.plan_forecast(plan)
    return render_template('shiori.html', plan=plan, weather_days=weather_days)


@planner.route('/api/plan_geo/<int:plan_id>')
@login_required
def plan_geo(plan_id):
    """プランの地図座標（観光/グルメ/宿）を返す。未取得なら今ここで取得しキャッシュする。

    保存をブロックしないため、地図を初めて開いたこのリクエスト中に1回だけ
    ジオコーディングする（以後はDBキャッシュを返すので即時）。本人のプランのみ。
    """
    from db import get_travel_plan_by_id
    from geocoding import ensure_plan_coords
    empty = {'spot_coords': [], 'restaurant_coords': [], 'accommodation_coords': []}
    plan = get_travel_plan_by_id(plan_id)
    if not plan or plan.get('google_user_id') != session.get('user_id'):
        return json.dumps(empty), 200, {'Content-Type': 'application/json'}
    # 既にジオコーディング済みなら制限対象外（座標を返すだけ）。未処理のみ throttle。
    if not plan.get('geo_done') and _geo_rate_limited(session.get('user_id')):
        return json.dumps({**empty, 'reason': 'rate_limited',
                           'spot_coords': plan.get('spot_coords') or [],
                           'restaurant_coords': plan.get('restaurant_coords') or [],
                           'accommodation_coords': plan.get('accommodation_coords') or []}), 200, {'Content-Type': 'application/json'}
    ensure_plan_coords(plan)
    return json.dumps({
        'spot_coords': plan.get('spot_coords') or [],
        'restaurant_coords': plan.get('restaurant_coords') or [],
        'accommodation_coords': plan.get('accommodation_coords') or [],
    }, ensure_ascii=False), 200, {'Content-Type': 'application/json'}


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


@planner.route('/api/geocode')
@login_required
def geocode():
    """スポット名を緯度経度に変換するプロキシ（座標未保存の旧プラン用フォールバック）。

    生成・編集時に座標を保存する方式に移行したため、新規プランは通常これを使わない。
    返り値はクライアント側の後方互換のため [{"lat","lon"}] 形式にする。
    """
    from geocoding import geocode_one
    q = request.args.get('q', '').strip()
    if not q or _geo_rate_limited(session.get('user_id')):
        return json.dumps([]), 200, {'Content-Type': 'application/json'}
    coords = geocode_one(q)
    if coords:
        return json.dumps([{'lat': coords['lat'], 'lon': coords['lng']}]), 200, {'Content-Type': 'application/json'}
    return json.dumps([]), 200, {'Content-Type': 'application/json'}


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
