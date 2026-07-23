"""旅の「持ち物リスト」を LLM で生成する（旅行プランの情報＋天気から）。

プラン生成の LangGraph フローとは独立した単発呼び出し。プラン詳細ページで
「持ちものリストを作る」を押したときにだけ実行し、結果は DB に保存して再利用する。
"""
from typing import List

from pydantic import BaseModel, Field

from chat.llm import llm, invoke_with_retry
from chat.logger import get_logger

logger = get_logger("packing")


class PackingListOutput(BaseModel):
    items: List[str] = Field(description="持ち物の名前のリスト（10〜16個・短い名詞）")


def generate_packing_list(plan: dict) -> list:
    """プラン情報と天気から持ち物リストを作って返す（重複除去・上限20）。"""
    dest = plan.get("destination") or ""
    duration = plan.get("duration") or ""
    themes = plan.get("themes") or []
    spots = plan.get("spots") or []

    # 天気ヒント（取得できない環境・日付では空文字。持ち物生成は続行する）
    wx = ""
    try:
        import weather
        wx = weather.generation_hint(dest, plan.get("travel_date"), duration) or ""
    except Exception:
        logger.info("持ち物生成: 天気ヒントの取得をスキップ")

    prompt = f"""あなたは旅の準備を手伝うやさしいアシスタントです。
以下の旅行に必要な「持ち物リスト」を作ってください。

行き先: {dest}
期間: {duration}
テーマ: {', '.join(themes) if themes else '指定なし'}
主な立ち寄り先: {', '.join(spots[:5]) if spots else '指定なし'}
{('天気の見込み: ' + wx) if wx else ''}

【方針】
・一般的な必需品（財布・スマホ・充電器・常備薬など）と、この旅ならではの持ち物
  （天気・行き先・アクティビティに応じたもの）を両方バランスよく入れる。
・天気が雨なら折りたたみ傘、寒いなら羽織るもの、海なら日焼け止め・水着…のように、
  条件に合わせて具体的に。
・各項目は短い名詞で（「折りたたみ傘」「モバイルバッテリー」など）。文や説明は書かない。
・10〜16個。多すぎず、抜け漏れなく。

【出力】
持ち物名のリストだけを返す。
"""
    structured = llm.with_structured_output(PackingListOutput)
    res = invoke_with_retry(structured, prompt)

    seen, out = set(), []
    for it in (res.items or []):
        it = (it or "").strip()
        if it and it not in seen:
            seen.add(it)
            out.append(it)
    return out[:20]
