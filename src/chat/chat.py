"""チャットの司令塔モジュール。

ユーザーの会話履歴から旅行条件（必須7項目）を構造化抽出し、
  - 条件が揃っていなければ「次に聞く質問」を返す
  - 揃っていれば LangGraph のプラン生成ワークフロー
    （chat.graph.generate_travel_plan）を呼び出し、結果をHTMLに整形して返す
という制御を担う。実際のプラン作成ロジックは agents / graph 側にある。
"""

import nest_asyncio
# Flask(同期) から LangChain/LangGraph の非同期処理を呼ぶため、
# 既存イベントループのネストを許可する
nest_asyncio.apply()

import re
from typing import List, Optional
from pydantic import BaseModel, Field
from langchain_core.messages import HumanMessage, AIMessage, SystemMessage
from chat.llm import llm, invoke_with_retry
from chat.graph import generate_travel_plan
from chat.formatter import _format_plan, plan_payload
from chat.logger import get_logger

logger = get_logger("chat")

# システムプロンプトの雛形。{today} に本日の日付を差し込んで使う（相対日付の換算用）。
_SYSTEM_PROMPT_TEMPLATE = """あなたは旅行プランナーのアシスタントです。本日の日付は {today} です。
会話履歴から旅行の条件を読み取り、状況に応じて次のいずれかを行ってください。

【必須項目（7つ）】: 旅行先、旅行日程（いつ）、期間（何泊何日）、参加人数、1人あたりの予算上限、出発地、旅行テーマ
【任意項目】: 交通手段の希望（新幹線・飛行機・車・高速バス・おまかせ）、特別条件（アレルギー・バリアフリー等）

※会話履歴に「[旅行プランを生成しました]」がある場合、すでにプランを提示済みです。

判定ルール:
A) 必須7項目がまだ揃っていない
   → is_complete=false。まだ聞いていない必須項目を1つだけ next_question に質問として設定。

B) 必須7項目が揃っていて、まだプラン未提示、またはユーザーが新しいプランの作成を求めている
   → is_complete=true、plan_change_request=null（新規プランを生成する）。

C) すでにプラン提示済みで、ユーザーがそのプランの【変更・調整】を求めている
   （例:「2日目をもっとゆっくり」「予算を抑えて」「宿を変えて」「観光をもう1つ増やして」「車で行きたい」など）
   → is_complete=true、plan_change_request にその具体的な変更指示を設定（プランを作り直す）。
     人数・予算・日程・交通手段など条件自体が変わる要望なら、該当フィールドも更新すること。
     さらに edit_targets に「変更が必要な領域」だけを列挙すること（指定外は前回のまま保持される）:
       sightseeing=観光地, gourmet=飲食店, accommodation=宿泊, schedule=スケジュール, budget=費用, transport=交通手段。
     例:「2日目をゆっくり」→["schedule"]、「宿を変えて」→["accommodation"]、「ご飯を変えて」→["gourmet"]、
       「予算を抑えて」→["accommodation","gourmet"]、全体的に作り直したい→["all"]。

D) すでにプラン提示済みで、変更要望ではない雑談・お礼・質問
   （例:「ありがとう」「いい感じ」「このお店は何時から？」など）
   → is_complete=false。next_question に、プランを作り直さずに返す自然な返答文を設定。
     必要に応じて「プランのどこを変えたいか教えてください」と案内してよい。

その他ルール:
・質問・返答は自然な日本語で、丁寧かつ簡潔に。
・すでにアシスタントが聞いた必須項目は再度聞かないこと。
・会話が始まったばかり or 旅行と無関係な発言には「どちらへのご旅行をお考えですか？」と聞くこと。
・任意項目（交通手段の希望・特別条件）は、必須7項目が揃ってから最後に確認すること。
・交通手段は会話から読み取り、希望があればその手段を、こだわりがなければ「おまかせ」を transport_mode に設定すること。
・「運転免許がない」「運転できない」「ペーパードライバー」「公共交通機関で行きたい」などの発言があれば no_car=true を設定すること。その場合は車・レンタカーを選ばないこと（transport_mode は新幹線/電車/バス等または「おまかせ」にする）。
・「夕方までに帰りたい」「早めに帰りたい」「朝はゆっくり」「◯時には出発したい」などの時間に関する希望があれば、その内容を schedule_pref に設定すること（スケジュールの帰宅・出発時刻に反映される）。
・旅行日程が「明日」「今週末」「来週の土曜」などの相対表現の場合は、本日の日付から換算して「YYYY年M月D日」の絶対日付（範囲なら「YYYY年M月D日〜D日」）に正規化して travel_date に設定すること。年を省略しないこと。
"""


def _system_prompt() -> SystemMessage:
    """本日の日付を差し込んだシステムプロンプトを返す（相対日付の換算に必要）。"""
    from datetime import date
    return SystemMessage(content=_SYSTEM_PROMPT_TEMPLATE.format(today=date.today().strftime('%Y年%m月%d日')))


_PLAN_PLACEHOLDER = "[旅行プランを生成しました]"

# 「あと◯つで完成！ 🍀…・」進捗プレフィックス（_with_progress が付与する行）。
# これがLLMへの履歴に混ざると、LLMが真似て自分の返答にも付け、二重表示になる。
# そのため LLM入力からは剥がし、生成された質問文にも紛れ込んでいれば剥がす。
# 改行はコード付与時は2つだが、LLMが模倣した行は1つのことがあるため \n+ で許容する。
_PROGRESS_PREFIX_RE = re.compile(r'^あと\d+つで完成[！!][^\n]*\n+')


def _strip_progress(text):
    """先頭の進捗プレフィックス（1つでも重なっていても）を取り除く。"""
    if not isinstance(text, str):
        return text
    while True:
        stripped = _PROGRESS_PREFIX_RE.sub('', text, count=1)
        if stripped == text:
            return stripped
        text = stripped


class ConversationState(BaseModel):
    destination: Optional[str] = Field(None, description="旅行先（例：京都）。会話から読み取れない場合はNull")
    travel_date: Optional[str] = Field(None, description="旅行日程。「明日」「来週末」等の相対表現は本日の日付から換算し、必ず年を含む絶対日付（例：2025年8月13日〜14日）にする。読み取れない場合はNull")
    duration: Optional[str] = Field(None, description="期間（例：1泊2日）。読み取れない場合はNull")
    themes: Optional[List[str]] = Field(None, description="旅行テーマ。読み取れない場合はNull")
    num_people: Optional[int] = Field(None, description="参加人数。読み取れない場合はNull")
    budget_limit: Optional[int] = Field(None, description="1人あたりの予算上限（円）。読み取れない場合はNull")
    departure_location: Optional[str] = Field(None, description="出発地。読み取れない場合はNull")
    transport_mode: Optional[str] = Field(None, description="交通手段の希望（新幹線・飛行機・車・高速バス など）。こだわりがなければ「おまかせ」。確認済みでなければNull")
    no_car: Optional[bool] = Field(None, description="運転免許がない/運転できない/公共交通機関を希望、ならTrue。車・レンタカーを使わず公共交通で組む。該当しなければFalse、未確認ならNull")
    schedule_pref: Optional[str] = Field(None, description="時間の希望（例『夕方までに帰りたい』『早めに帰りたい』『朝はゆっくり』『◯時には現地を出たい』）。会話から読み取れればその文、無ければNull")
    special_requirements: Optional[List[str]] = Field(None, description="特別条件（アレルギー・バリアフリー等）。確認済みでなければNull")
    is_complete: bool = Field(False, description="プランを生成/再生成すべきならTrue（新規作成 or 既存プランの変更要望）。雑談や条件不足ならFalse")
    plan_change_request: Optional[str] = Field(None, description="既にプラン提示済みで、ユーザーがそのプランの変更を求めている場合の具体的な変更指示。新規作成や雑談の場合はNull")
    edit_targets: Optional[List[str]] = Field(None, description="既存プランの変更時、変更が必要な領域だけを列挙（sightseeing/gourmet/accommodation/schedule/budget/transport、全体なら['all']）。新規作成や雑談はNull")
    next_question: str = Field("", description="is_complete=Falseのときにユーザーへ返す文（次に聞く質問、または雑談への自然な返答）。is_complete=Trueなら空文字")


def _build_user_preferences(user_id: str) -> str:
    """過去の★評価＋コメントから、生成時に参照する「好み」テキストを作る。"""
    if not user_id:
        return ""
    try:
        from db import get_rated_plans
        rated = get_rated_plans(user_id, limit=8)
    except Exception:
        logger.debug("評価の取得に失敗", exc_info=True)
        return ""
    likes, dislikes = [], []
    for p in rated:
        r = p.get("rating") or 0
        themes = "・".join(p.get("themes") or [])
        comment = (p.get("rating_comment") or "").strip()
        entry = f"{p.get('destination')}（{themes}）" + (f"：{comment}" if comment else "")
        if r >= 4:
            likes.append(entry)
        elif r <= 2:
            dislikes.append(entry)
    parts = []
    if likes:
        parts.append("高評価だった旅: " + " / ".join(likes[:4]))
    if dislikes:
        parts.append("低評価だった旅: " + " / ".join(dislikes[:4]))
    return "\n".join(parts)


# LLMに渡す会話履歴の上限（件数）。通常は「新しいチャット」でリセットされるため
# ここまで溜まらないが、同じ会話を延々続けた場合の送信トークン増に上限を設ける保険。
# 直近だけ残すので、これより古い発言の条件は忘れられる（実用上はプラン保存後に
# 編集する流れのため影響はほぼない）。
_MAX_HISTORY_MESSAGES = 40


def _build_lc_messages(messages_history: list) -> list:
    """会話履歴をLangChainのメッセージリストに変換する。
    プランHTMLはトークン節約のためプレースホルダーに置き換える。
    履歴は直近 _MAX_HISTORY_MESSAGES 件までに絞る。"""
    lc_messages = [_system_prompt()]
    for m in messages_history[-_MAX_HISTORY_MESSAGES:]:
        content = m["content"]
        if m["role"] == "ai" and content.startswith("<div"):
            content = _PLAN_PLACEHOLDER
        elif m["role"] == "ai":
            # 進捗プレフィックスはLLMに見せない（真似て二重に付けるのを防ぐ）
            content = _strip_progress(content)
        if m["role"] == "user":
            lc_messages.append(HumanMessage(content=content))
        else:
            lc_messages.append(AIMessage(content=content))
    return lc_messages


def chat(user_message: str, messages_history=None, request_id=None, active_requests=None, user_id=None) -> tuple:
    """1回のユーザー発話を処理し、(応答, プラン構造化データ) のタプルを返す。

    Args:
        user_message: 今回のユーザー発話（履歴にも含まれる想定）。
        messages_history: これまでの会話履歴（role/content の辞書リスト）。
        request_id: リクエスト識別子。キャンセル判定に使う。
        active_requests: 現在処理中のリクエストIDの集合。ここに request_id が
            なくなっていればキャンセルされたとみなし (None, None) を返す。

    Returns:
        (response, plan) のタプル。
        - response: 質問文 or 整形済みプランHTML（str）。キャンセル時は None
        - plan: プランを生成したときだけ、その構造化データ（dict）。それ以外は None
          呼び出し側はこれをメッセージ行と一緒にDB保存し、次回の部分編集で読み戻す。
    """
    lc_messages = _build_lc_messages(messages_history or [])

    try:
        state = invoke_with_retry(llm.with_structured_output(ConversationState), lc_messages)
    except Exception as e:
        logger.exception("会話状態の解析に失敗しました: request_id=%s", request_id)
        return f"申し訳ありません、処理中にエラーが発生しました: {e}", None

    logger.debug("会話状態を解析しました: is_complete=%s, next_question=%s", state.is_complete, state.next_question)

    # 必須7項目の充足状況。進捗表示（ゴール感）と、取りこぼし防止の両方に共用する。
    _required = {
        "旅行先": state.destination,
        "旅行日程": state.travel_date,
        "期間": state.duration,
        "参加人数": state.num_people,
        "1人あたりの予算上限": state.budget_limit,
        "出発地": state.departure_location,
        "旅行テーマ": state.themes,
    }
    _missing = [label for label, val in _required.items() if val in (None, "", [])]
    _filled = len(_required) - len(_missing)

    def _with_progress(q: str) -> str:
        """必須項目を集めている間だけ「あと◯つで完成」を質問に添えてゴール感を出す。"""
        q = _strip_progress(q)  # LLMが自発的に付けた進捗行があれば除去してから付け直す（保険）
        if _missing and q:
            dots = "🍀" * _filled + "・" * len(_missing)
            return f"あと{len(_missing)}つで完成！ {dots}\n\n{q}"
        return q

    if not state.is_complete:
        return _with_progress(state.next_question), None

    # is_complete=true でも必須項目が欠けている場合（LLMの取りこぼし）は、生成に進まず聞き直す。
    # 欠けたまま生成するとエージェント側で None 参照のエラーになるため、ここで防ぐ。
    if _missing:
        logger.warning("is_complete=trueだが必須項目が不足のため聞き直し: %s", _missing)
        return _with_progress(f"恐れ入りますが、{_missing[0]}を教えていただけますか？"), None

    if request_id and active_requests and request_id not in active_requests:
        logger.info("リクエストがキャンセルされました: request_id=%s", request_id)
        return None, None

    inputs = {
        "destination":          state.destination,
        "travel_date":          state.travel_date,
        "duration":             state.duration,
        "themes":               state.themes,
        "num_people":           state.num_people,
        "budget_limit":         state.budget_limit,
        "departure_location":   state.departure_location,
        "transport_mode":       state.transport_mode or "おまかせ",
        "no_car":               bool(state.no_car),
        "schedule_pref":        state.schedule_pref or "",
        "special_requirements": state.special_requirements or [],
        # 既存プランへの変更要望は user_feedback として各エージェントに最優先で反映させる
        "user_feedback":        state.plan_change_request or "",
        # 過去の★評価から得た好み（参考としてやんわり反映）
        "user_preferences":     _build_user_preferences(user_id),
    }

    # 部分編集: 変更要望があり、前回プランが復元でき、対象領域が限定されている場合は、
    # 前回の成果物を引き継いで対象領域だけを再生成する（指定外はそのまま保持）。
    # 変更要望はあるが対象が空の場合は、全体作り直し(["all"])として扱う。
    targets = state.edit_targets or (["all"] if state.plan_change_request else [])
    # 前回プランは、HTMLを正規表現で読み戻す代わりにDBの構造化データから取得する
    # （直近のAIプランメッセージと一緒に保存した plan_json）。
    from db import get_last_plan
    prev = get_last_plan(user_id) if (state.plan_change_request and user_id) else None
    if state.plan_change_request and prev and targets and "all" not in targets:
        for key in ("spots", "restaurants", "accommodation", "schedule", "budget_estimate"):
            inputs[key] = prev.get(key, [])
        inputs["transport_cost"] = prev.get("transport_cost") or 0
        inputs["remaining_budget"] = prev.get("remaining_budget") or 0
        inputs["edit_targets"] = targets
        logger.info("部分編集: targets=%s request=%s", targets, state.plan_change_request)

    try:
        final_state = generate_travel_plan(inputs)
    except ValueError as e:
        logger.error("プラン生成で値域エラー: request_id=%s, error=%s", request_id, e)
        return str(e), None

    if request_id and active_requests and request_id not in active_requests:
        logger.info("プラン生成後にリクエストがキャンセルされました: request_id=%s", request_id)
        return None, None

    formatted = _format_plan(final_state)
    logger.info("プラン生成が完了しました: request_id=%s, status=%s", request_id, final_state.get("status"))
    # プランの構造化データも返し、呼び出し側でメッセージ行と一緒にDB保存させる
    return formatted, plan_payload(final_state)


class _PlanEditIntent(BaseModel):
    edit_targets: List[str] = Field(
        default_factory=list,
        description=(
            "変更が必要な領域だけを列挙: sightseeing(観光地)/gourmet(飲食店)/"
            "accommodation(宿泊)/schedule(スケジュール)/budget(費用)/transport(交通手段)。"
            "全体的に作り直す場合は ['all']。"
        ),
    )


def _as_list(value) -> list:
    """値をリストに正規化する。None/空は []、リストはそのまま、単一値は1要素のリストに。

    保存プランのフィールドが文字列で入っている旧データにも備えるための保険。
    """
    if isinstance(value, list):
        return value
    if value in (None, ""):
        return []
    return [value]


def edit_saved_plan(plan: dict, message: str) -> dict:
    """保存済みプランに対するチャット修正を実行し、更新後の最終状態を返す。

    変更要望から対象領域を判定し、対象だけを再生成する（指定外は前回値を維持）。
    予算超過時は generate_travel_plan が ValueError を送出する。
    """
    intent_messages = [
        SystemMessage(content=(
            "あなたは旅行プラン編集の意図分類器です。ユーザーの変更指示から、変更が必要な領域だけを "
            "edit_targets に列挙してください。領域: sightseeing(観光地)/gourmet(飲食店)/"
            "accommodation(宿泊)/schedule(スケジュール)/budget(費用)/transport(交通手段)。"
            "全体的な作り直しは ['all']。"
        )),
        HumanMessage(content=(
            f"現在のプラン: 行き先={plan.get('destination')} / 期間={plan.get('duration')}。\n"
            f"変更指示: {message}"
        )),
    ]
    try:
        intent = invoke_with_retry(llm.with_structured_output(_PlanEditIntent), intent_messages)
        targets = intent.edit_targets or ["all"]
    except Exception:
        logger.warning("プラン編集の意図分類に失敗。全体作り直しにフォールバック", exc_info=True)
        targets = ["all"]

    # 旧い/不完全な保存プランは再生成に必要な条件が欠けていることがあるため、事前に弾く
    _required = {
        "destination": plan.get("destination"),
        "travel_date": plan.get("travel_date"),
        "duration": plan.get("duration"),
        "num_people": plan.get("num_people"),
        "budget_limit": plan.get("budget_limit"),
        "departure_location": plan.get("departure_location"),
        "themes": _as_list(plan.get("themes")),
    }
    if any(v in (None, "", []) for v in _required.values()):
        raise ValueError("このプランは保存情報が不足しているため、チャット修正に対応できません。お手数ですが新しく作り直してください。")

    inputs = {
        "destination":          plan.get("destination"),
        "travel_date":          plan.get("travel_date"),
        "duration":             plan.get("duration"),
        "themes":               _as_list(plan.get("themes")),
        "num_people":           plan.get("num_people"),
        "budget_limit":         plan.get("budget_limit"),
        "departure_location":   plan.get("departure_location"),
        "transport_mode":       "おまかせ",
        "no_car":               False,
        "special_requirements": _as_list(plan.get("special_requirements")),
        "user_feedback":        message,
    }
    # 対象が限定されていれば、前回プランの成果物を引き継いで対象だけ再生成（部分編集）
    if targets and "all" not in targets:
        for key in ("spots", "restaurants", "accommodation", "schedule", "budget_estimate"):
            inputs[key] = _as_list(plan.get(key))
        inputs["transport_cost"] = plan.get("transport_cost") or 0
        inputs["remaining_budget"] = plan.get("remaining_budget") or 0
        inputs["edit_targets"] = targets
    logger.info("保存プランのチャット修正: targets=%s request=%s", targets, message)
    return generate_travel_plan(inputs)
