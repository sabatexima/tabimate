"""旅の「解釈」エンジン（共通モジュール）。

同じエンジンの出力長さ違いとして2機能を提供する:
- 短い解釈 → 機能A: 謎アチーブメント（称号 2〜4個）
- 長い解釈 → 機能B: 旅レポート（数百字の読み物）

入力は services/features.py が集計した特徴量（メタデータ要約）。
高度な推論は不要なため安価な Gemini モデル（環境変数で差替可能）を使う。
全呼び出しで input/output トークン数をログ出力し、推定コストを算出する。
"""
import json
import os
from typing import List, Optional

from langchain_google_genai import ChatGoogleGenerativeAI
from pydantic import BaseModel, Field

from chat.llm import invoke_with_retry
from chat.logger import get_logger

logger = get_logger("services.trip_interpreter")

# --- モデル設定（環境変数で差替可能）---
_MODEL = os.getenv("INTERPRETER_MODEL", "gemini-2.5-flash")
_SEND_IMAGES_DEFAULT = os.getenv("INTERPRETER_SEND_IMAGES", "false").lower() == "true"

# 推定コスト（USD / 100万トークン）。実価格に合わせて環境変数で上書き可。
_PRICE_IN = float(os.getenv("INTERPRETER_PRICE_INPUT_PER_M", "0.30"))
_PRICE_OUT = float(os.getenv("INTERPRETER_PRICE_OUTPUT_PER_M", "2.50"))

_llm = ChatGoogleGenerativeAI(
    model=_MODEL,
    temperature=0.8,   # 解釈・大喜利なので多少ゆらぎを持たせる
    timeout=120,
    max_retries=2,
)


# ----------------------------------------------------------------------
# 出力スキーマ
# ----------------------------------------------------------------------
class AchievementItem(BaseModel):
    title: str = Field(description="ふわっとした称号名。攻略条件は書かない。例:『水辺に呼ばれし者』")
    flavor_text: str = Field(description="一言フレーバー。観察・解釈のトーン。条件や根拠は書かない。")


class AchievementsOutput(BaseModel):
    achievements: List[AchievementItem] = Field(
        description="2個以上4個以下の称号。狙って取れないようあいまいに。"
    )


class ReportOutput(BaseModel):
    body: str = Field(
        description="数百字の読み物。やや盛って・ボケて・実況講評するトーン。改行可。"
    )


# ----------------------------------------------------------------------
# 共通呼び出し（トークンログ付き）
# ----------------------------------------------------------------------
def _invoke(schema, prompt: str, tag: str):
    """structured_output を include_raw=True で呼び、parsed と usage を返す。"""
    structured = _llm.with_structured_output(schema, include_raw=True)
    result = invoke_with_retry(structured, prompt)

    parsed = result.get("parsed") if isinstance(result, dict) else result
    raw = result.get("raw") if isinstance(result, dict) else None

    usage = {"input_tokens": 0, "output_tokens": 0, "total_tokens": 0}
    if raw is not None and getattr(raw, "usage_metadata", None):
        um = raw.usage_metadata
        usage["input_tokens"] = um.get("input_tokens", 0)
        usage["output_tokens"] = um.get("output_tokens", 0)
        usage["total_tokens"] = um.get("total_tokens", usage["input_tokens"] + usage["output_tokens"])

    est_cost = (usage["input_tokens"] / 1_000_000 * _PRICE_IN
                + usage["output_tokens"] / 1_000_000 * _PRICE_OUT)
    logger.info(
        "[トークン] task=%s model=%s input=%d output=%d total=%d 推定コスト=$%.6f",
        tag, _MODEL, usage["input_tokens"], usage["output_tokens"],
        usage["total_tokens"], est_cost,
    )
    return parsed, usage


def _features_block(features: dict) -> str:
    return json.dumps(features, ensure_ascii=False, indent=2)


# ----------------------------------------------------------------------
# 機能A: 謎アチーブメント（短い解釈）
# ----------------------------------------------------------------------
def interpret_achievements(features: dict, images: Optional[list] = None):
    """特徴量から称号 2〜4個を生成。戻り値: (items: list[dict], usage: dict)"""
    prompt = f"""あなたは旅の行動を面白く解釈する観察者です。
以下は、ある人の旅行中の写真から機械的に集計した特徴量です。

{_features_block(features)}

この特徴量から、その人の旅のクセや傾向を読み取り、ふわっとした「称号」を2〜4個付けてください。

【厳守】
・これは「達成バッジ」ではなく「観察・解釈」です。攻略可能な具体的条件は絶対に書かないこと。
・狙って取れないよう、あいまい・ちょっと面白い表現にすること。
・称号名の例:「迷子の達人」「水辺に呼ばれし者」「黄昏コレクター」「胃袋無限大」「結局そこ?」
・flavor_text は一言。データの数値をそのまま書かず、行動を面白く解釈すること。
・特徴量が乏しい場合でも、無難に2個はひねり出すこと。
"""
    parsed, usage = _invoke(AchievementsOutput, prompt, tag="achievements")
    items = []
    if parsed and getattr(parsed, "achievements", None):
        items = [{"title": a.title, "flavor_text": a.flavor_text} for a in parsed.achievements]
    return items, usage


# ----------------------------------------------------------------------
# 機能B: AI旅レポート（長い解釈）
# ----------------------------------------------------------------------
_TONE_GUIDE = {
    "playful": "陽気でちょっとボケる。ツッコミどころを楽しく拾う。",
    "roast": "ちょい辛口。愛のあるイジり。けなしすぎない。",
    "gentle": "やさしく寄り添う。じんわり良かったね、と振り返る。",
}


def interpret_report(features: dict, tone: str = "playful",
                     area: Optional[str] = None, images: Optional[list] = None):
    """特徴量から旅レポート本文を生成。戻り値: (body: str, usage: dict)"""
    tone = tone if tone in _TONE_GUIDE else "playful"
    tone_desc = _TONE_GUIDE[tone]
    area_line = f"\n対象エリア: {area}（このエリアに絞って講評すること）" if area else ""

    prompt = f"""あなたは旅の実況・講評をする相棒です。一人旅でも横で講評してくれる存在として書きます。

以下は、ある人の旅行中の写真から機械的に集計した特徴量です。{area_line}

{_features_block(features)}

この特徴量をもとに「こんな旅でしたね」という読み物を書いてください。

【トーン】{tone}: {tone_desc}
【厳守】
・真面目な要約にしないこと。やや盛って、ボケて、実況・講評すること。
・例:「この旅、8割が"とりあえず腹ごしらえ"でしたね」「写真の影の長さから察するに、完全に出遅れてます朝」
・数百字程度（200〜400字目安）。
・特徴量の数値を箇条書きで並べるのではなく、読み物として自然な文章にすること。
・データが乏しくても、その乏しさ自体をネタにして書くこと。
"""
    parsed, usage = _invoke(ReportOutput, prompt, tag="report")
    body = parsed.body if parsed and getattr(parsed, "body", None) else ""
    return body, usage
