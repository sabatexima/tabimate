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

from typing import List, Optional
from pydantic import BaseModel, Field
from langchain_core.messages import HumanMessage, AIMessage, SystemMessage
from chat.llm import llm, invoke_with_retry
from chat.graph import generate_travel_plan
from chat.formatter import _format_plan
from chat.logger import get_logger

logger = get_logger("chat")

_SYSTEM_PROMPT = SystemMessage(content="""あなたは旅行プランナーのアシスタントです。
会話履歴から旅行の条件を読み取ってください。

【必須項目（7つ）】: 旅行先、旅行日程（いつ）、期間（何泊何日）、参加人数、1人あたりの予算上限、出発地、旅行テーマ
【任意項目】: 交通手段の希望（新幹線・飛行機・車・高速バス・おまかせ）、特別条件（アレルギー・バリアフリー等）

ルール:
・必須7項目がすべて揃っている場合のみ is_complete=true にしてください
・揃っていない場合は is_complete=false にして、まだ聞いていない必須項目を1つだけ next_question に設定してください
・質問は自然な日本語で、丁寧かつ簡潔に（1文）
・すでにアシスタントが聞いた項目は再度聞かないこと
・会話が始まったばかり or 旅行と無関係な発言には「どちらへのご旅行をお考えですか？」と聞いてください
・任意項目（交通手段の希望・特別条件）は、他の必須項目が揃ってから最後に確認すること
・交通手段は会話から読み取り、ユーザーが「車で」「高速バスで」等と希望すればその手段を、こだわりがなければ「おまかせ」を transport_mode に設定すること
""")

_PLAN_PLACEHOLDER = "[旅行プランを生成しました]"


class ConversationState(BaseModel):
    destination: Optional[str] = Field(None, description="旅行先（例：京都）。会話から読み取れない場合はNull")
    travel_date: Optional[str] = Field(None, description="旅行日程（例：2025年8月13日〜14日）。読み取れない場合はNull")
    duration: Optional[str] = Field(None, description="期間（例：1泊2日）。読み取れない場合はNull")
    themes: Optional[List[str]] = Field(None, description="旅行テーマ。読み取れない場合はNull")
    num_people: Optional[int] = Field(None, description="参加人数。読み取れない場合はNull")
    budget_limit: Optional[int] = Field(None, description="1人あたりの予算上限（円）。読み取れない場合はNull")
    departure_location: Optional[str] = Field(None, description="出発地。読み取れない場合はNull")
    transport_mode: Optional[str] = Field(None, description="交通手段の希望（新幹線・飛行機・車・高速バス など）。こだわりがなければ「おまかせ」。確認済みでなければNull")
    special_requirements: Optional[List[str]] = Field(None, description="特別条件（アレルギー・バリアフリー等）。確認済みでなければNull")
    is_complete: bool = Field(False, description="必須7項目がすべて揃っていればTrue")
    next_question: str = Field("", description="次にユーザーへ聞くべき質問文。is_complete=Trueなら空文字")


def _build_lc_messages(messages_history: list) -> list:
    """会話履歴をLangChainのメッセージリストに変換する。
    プランHTMLはトークン節約のためプレースホルダーに置き換える。"""
    lc_messages = [_SYSTEM_PROMPT]
    for m in messages_history:
        content = m["content"]
        if m["role"] == "ai" and content.startswith("<div"):
            content = _PLAN_PLACEHOLDER
        if m["role"] == "user":
            lc_messages.append(HumanMessage(content=content))
        else:
            lc_messages.append(AIMessage(content=content))
    return lc_messages


def chat(user_message: str, messages_history=None, request_id=None, active_requests=None) -> str | None:
    """1回のユーザー発話を処理し、応答テキストまたはプランHTMLを返す。

    Args:
        user_message: 今回のユーザー発話（履歴にも含まれる想定）。
        messages_history: これまでの会話履歴（role/content の辞書リスト）。
        request_id: リクエスト識別子。キャンセル判定に使う。
        active_requests: 現在処理中のリクエストIDの集合。ここに request_id が
            なくなっていればキャンセルされたとみなし None を返す。

    Returns:
        - 条件が未充足: 次にユーザーへ聞く質問文（str）
        - 条件が充足  : 整形済みプランHTML（str）
        - キャンセル時: None
    """
    lc_messages = _build_lc_messages(messages_history or [])

    try:
        state = invoke_with_retry(llm.with_structured_output(ConversationState), lc_messages)
    except Exception as e:
        logger.exception("会話状態の解析に失敗しました: request_id=%s", request_id)
        return f"申し訳ありません、処理中にエラーが発生しました: {e}"

    logger.debug("会話状態を解析しました: is_complete=%s, next_question=%s", state.is_complete, state.next_question)

    if not state.is_complete:
        return state.next_question

    if request_id and active_requests and request_id not in active_requests:
        logger.info("リクエストがキャンセルされました: request_id=%s", request_id)
        return None

    inputs = {
        "destination":          state.destination,
        "travel_date":          state.travel_date,
        "duration":             state.duration,
        "themes":               state.themes,
        "num_people":           state.num_people,
        "budget_limit":         state.budget_limit,
        "departure_location":   state.departure_location,
        "transport_mode":       state.transport_mode or "おまかせ",
        "special_requirements": state.special_requirements or [],
    }

    try:
        final_state = generate_travel_plan(inputs)
    except ValueError as e:
        logger.error("プラン生成で値域エラー: request_id=%s, error=%s", request_id, e)
        return str(e)

    if request_id and active_requests and request_id not in active_requests:
        logger.info("プラン生成後にリクエストがキャンセルされました: request_id=%s", request_id)
        return None

    formatted = _format_plan(final_state)
    logger.info("プラン生成が完了しました: request_id=%s, status=%s", request_id, final_state.get("status"))
    return formatted
