"""旅の「解釈」エンジン。

アプリの主役は「付箋（sticker）」。旅の写真から、旅全体の空気感を
少しズラして切り取った短い言葉（例:「曇り空が同行者」「気づけば出雲」）を生成する。

入力は services/features.py が集計した特徴量（メタデータ要約）＋代表写真。
付箋は写真の中身に根ざす必要があるため画像送付が前提（呼び出し側で収集）。
安価な Gemini モデル（環境変数で差替可能）を使い、全呼び出しで
input/output トークン数をログ出力して推定コストを算出する。
"""
import base64
import io
import json
import os
from typing import List, Optional

from langchain_core.messages import HumanMessage
from langchain_google_genai import ChatGoogleGenerativeAI
from pydantic import BaseModel, Field

from chat.llm import invoke_with_retry
from chat.logger import get_logger

logger = get_logger("services.trip_interpreter")

# --- モデル設定（環境変数で差替可能）---
# 付箋生成は短文の創作タスク（旅ごとに1回だけ）なので軽量モデルで十分。
_MODEL = os.getenv("INTERPRETER_MODEL", "gemini-3.1-flash-lite")
_SEND_IMAGES_DEFAULT = os.getenv("INTERPRETER_SEND_IMAGES", "false").lower() == "true"

# 画像送付（任意機能）のコスト保護: 送る最大枚数と縮小後の最大辺(px)。
_MAX_IMAGES = int(os.getenv("INTERPRETER_MAX_IMAGES", "4"))
_IMAGE_MAX_EDGE = int(os.getenv("INTERPRETER_IMAGE_MAX_EDGE", "512"))
# 付箋生成は画像が主役。称号・レポートより多めに送る（コストは枚数で調整）。
_STICKER_MAX_IMAGES = int(os.getenv("STICKER_MAX_IMAGES", "6"))


def send_images_enabled() -> bool:
    """画像送付オプションが有効か（既定オフ）。呼び出し側の判定用。"""
    return _SEND_IMAGES_DEFAULT


def _prepare_image_blocks(images: Optional[list], max_images: Optional[int] = None) -> list:
    """生画像バイト列を縮小・JPEG化し、Gemini用の image_url ブロックに変換する。

    images: bytes のリスト。コスト保護のため最大 max_images 枚に制限し
    （未指定なら _MAX_IMAGES）、各画像は長辺 _IMAGE_MAX_EDGE px 以内へ縮小する。
    失敗画像はスキップ。
    """
    if not images:
        return []
    cap = max_images if max_images is not None else _MAX_IMAGES
    blocks = []
    for data in images[:cap]:
        if not data:
            continue
        try:
            from PIL import Image
            img = Image.open(io.BytesIO(data))
            img = img.convert("RGB")
            img.thumbnail((_IMAGE_MAX_EDGE, _IMAGE_MAX_EDGE))
            buf = io.BytesIO()
            img.save(buf, format="JPEG", quality=80)
            b64 = base64.b64encode(buf.getvalue()).decode("ascii")
            blocks.append({"type": "image_url", "image_url": f"data:image/jpeg;base64,{b64}"})
        except Exception:
            logger.debug("画像の前処理に失敗（スキップ）", exc_info=True)
    return blocks

# 推定コスト（USD / 100万トークン）。既定は gemini-3.1-flash-lite の価格。
# 実価格・モデル変更時は環境変数で上書き可。
_PRICE_IN = float(os.getenv("INTERPRETER_PRICE_INPUT_PER_M", "0.25"))
_PRICE_OUT = float(os.getenv("INTERPRETER_PRICE_OUTPUT_PER_M", "1.50"))

_llm = ChatGoogleGenerativeAI(
    model=_MODEL,
    temperature=0.8,   # 解釈・大喜利なので多少ゆらぎを持たせる
    timeout=120,
    max_retries=2,
)


# ----------------------------------------------------------------------
# 出力スキーマ
# ----------------------------------------------------------------------
class StickerItem(BaseModel):
    text: str = Field(
        description="短い付箋の言葉（目安6〜14字）。説明文・旅レポートの見出しにしないこと。"
    )
    basis: str = Field(
        description="根拠：写真の何から来たか（内部用・ユーザー非表示）。"
    )


class StickersOutput(BaseModel):
    stickers: List[StickerItem] = Field(
        description="3〜6枚。旅全体の空気感を少しズラして切り取る付箋。"
    )


# ----------------------------------------------------------------------
# 共通呼び出し（トークンログ付き）
# ----------------------------------------------------------------------
def _invoke(schema, prompt, tag: str):
    """structured_output を include_raw=True で呼び、parsed と usage を返す。

    prompt は文字列、または HumanMessage を含むメッセージ列（画像送付時）。
    """
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
    """集計済み特徴量を、プロンプトに埋め込む読みやすいJSON文字列に整形する。"""
    return json.dumps(features, ensure_ascii=False, indent=2)


def _build_input(prompt_text: str, images: Optional[list], tag: str,
                 max_images: Optional[int] = None):
    """画像があればマルチモーダルのメッセージ列を、なければ文字列をそのまま返す。"""
    cap = max_images if max_images is not None else _MAX_IMAGES
    blocks = _prepare_image_blocks(images, max_images=cap)
    if not blocks:
        return prompt_text
    logger.info("[画像送付] task=%s images=%d（最大%d, 長辺%dpxに縮小）",
                tag, len(blocks), cap, _IMAGE_MAX_EDGE)
    content = [{"type": "text", "text": prompt_text}] + blocks
    return [HumanMessage(content=content)]


# ----------------------------------------------------------------------
# 付箋（sticker）生成 ― アプリの主役
# ----------------------------------------------------------------------
def interpret_stickers(features: dict, images: Optional[list] = None):
    """写真＋特徴量から付箋を3〜6枚生成。戻り値: (items: list[dict], usage: dict)。

    items は [{"text": ..., "basis": ...}]。basis は内部用（生成根拠）。
    付箋は写真の中身に根ざすため、images（代表写真のbytes列）が前提。
    """
    prompt = f"""あなたは旅の写真から「付箋」を作る人です。
付箋とは、旅の空気感を“少しだけズラして”切り取った短い言葉です。

参考（補助情報・あくまで補足。主役は写真そのもの）:
{_features_block(features)}

# お手本（このトーン・長さ・ズラし方を真似る）
・「曇り空が同行者」
・「雨との交渉継続中」
・「気づけば出雲」
・「駅ホームが渋い」

# 付箋の作り方（厳守）
・写真の事実から大きく逸脱しない（完全な創作は禁止）。
・旅行全体の特徴を反映する。
・少し詩的でよい／擬人化してよい／少し大喜利的でよい。
・写真を見返した時に「確かに」と思えること。
・「説明文」にしないこと。「旅行レポートの見出し」にしないこと。
・目安6〜14字。短く。句点（。）で終わる説明にしない。

各付箋について basis（根拠：写真の何から来たか）も必ず書くこと。
basis はユーザーには見せない内部メモなので、率直に書いてよい。

付箋を3〜6枚作ってください。"""
    model_input = _build_input(prompt, images, tag="stickers",
                               max_images=_STICKER_MAX_IMAGES)
    parsed, usage = _invoke(StickersOutput, model_input, tag="stickers")
    items = []
    if parsed and getattr(parsed, "stickers", None):
        items = [{"text": s.text, "basis": s.basis} for s in parsed.stickers]
    return items, usage


# ----------------------------------------------------------------------
# ベストショット選出 ― 旅の写真から「飾りたい一枚」を選ぶ
# ----------------------------------------------------------------------
class _BestShot(BaseModel):
    index: int = Field(description="選んだ写真の番号（0から始まる）")
    reason: str = Field(description="その写真を選んだ理由（15〜35字のあたたかい一言）")


class _BestShotsOutput(BaseModel):
    best: list = Field(default_factory=list, description="ベストショット（最大3枚）")


def select_best_photos(images: list, count: int = 3):
    """旅の写真（bytes列）から、飾りたいベストショットを選ぶ。

    戻り値: (picks: list[{"index": int, "reason": str}], usage: dict)。
    index は入力 images の並び順（0始まり）。範囲外・重複は呼び出し側で弾く前提だが
    ここでも軽く整える。
    """
    n = len(images or [])
    if n == 0:
        return [], {"input_tokens": 0, "output_tokens": 0}

    class _Item(BaseModel):
        index: int = Field(description=f"選んだ写真の番号（0〜{n - 1}）")
        reason: str = Field(description="選んだ理由（15〜35字のあたたかい一言）")

    class _Out(BaseModel):
        best: list[_Item] = Field(default_factory=list)

    prompt = f"""あなたは旅の思い出を一緒に振り返るやさしい相棒「ちゃむ」です。
以下は、ある旅で撮られた {n} 枚の写真です（0番から {n - 1} 番の順に並んでいます）。
この中から「思い出として飾りたいベストショット」を最大 {count} 枚選んでください。

# 選び方
・景色・表情・その場の空気が伝わる、心に残る一枚を選ぶ。
・似た写真が続くときは、いちばん良い一枚だけを選ぶ。
・番号は 0〜{n - 1} の範囲で、重複させないこと。
・それぞれに、選んだ理由を 15〜35字のあたたかい一言で添える
  （例:「光の入り方がやわらかくて、その場の静けさが伝わる一枚」）。
"""
    model_input = _build_input(prompt, images, tag="best_shots", max_images=n)
    parsed, usage = _invoke(_Out, model_input, tag="best_shots")
    picks, seen = [], set()
    if parsed and getattr(parsed, "best", None):
        for b in parsed.best:
            i = getattr(b, "index", None)
            if isinstance(i, int) and 0 <= i < n and i not in seen:
                seen.add(i)
                picks.append({"index": i, "reason": (getattr(b, "reason", "") or "").strip()})
            if len(picks) >= count:
                break
    return picks, usage
