import os
import time
from concurrent.futures import ThreadPoolExecutor
from dotenv import load_dotenv
from langchain_google_genai import ChatGoogleGenerativeAI
from langchain_tavily import TavilySearch
from chat.logger import get_logger

load_dotenv(os.path.join(os.path.dirname(os.path.abspath(__file__)), '..', '.env'))

llm = ChatGoogleGenerativeAI(
    model="gemini-3.1-flash-lite",
    temperature=0,
    max_tokens=None,
    timeout=120,
    max_retries=2,
)

# 推論・数値判断が重要なノード（審査=balancer、費用=cost_manager）用の上位モデル。
# 大半は軽量な lite を使い、品質の効きどころだけ上位モデルに上げてコスト増を抑える。
# gemini-3.5-flash は Flash 価格帯で Pro 近い性能（2026年時点の最新Flash）。
llm_strong = ChatGoogleGenerativeAI(
    model="gemini-3.5-flash",
    temperature=0,
    max_tokens=None,
    timeout=120,
    max_retries=2,
)

_search = TavilySearch(max_results=8)
log = get_logger("llm")

# モデル別の概算料金（USD / 100万トークン, 入力, 出力）。未知モデルは lite 相当で概算。
MODEL_PRICING_USD_PER_M = {
    "gemini-3.1-flash-lite": (0.25, 1.50),
    "gemini-3.5-flash": (1.50, 9.00),
}
USD_TO_JPY = 150  # 概算用の固定レート


def estimate_cost(usage_by_model: dict):
    """モデル別トークン使用量から (入力tok合計, 出力tok合計, 推定USD) を返す。

    usage_by_model は UsageMetadataCallbackHandler.usage_metadata の形式
    （{モデル名: {"input_tokens":int, "output_tokens":int, ...}}）を想定。
    """
    in_tok = out_tok = 0
    usd = 0.0
    for model, u in (usage_by_model or {}).items():
        i = int(u.get("input_tokens", 0) or 0)
        o = int(u.get("output_tokens", 0) or 0)
        in_tok += i
        out_tok += o
        p_in, p_out = MODEL_PRICING_USD_PER_M.get(model, (0.25, 1.50))
        usd += i / 1_000_000 * p_in + o / 1_000_000 * p_out
    return in_tok, out_tok, usd



def web_search(query: str, min_score: float = 0.3) -> str:
    """Tavily でウェブ検索し、スコアが min_score 以上の本文を改行連結して返す。

    エージェントが実在スポット選定の根拠にする参考テキスト。失敗時・該当なしは空文字。
    """
    log.debug("web_search start query=%s min_score=%s", query, min_score)
    try:
        results = _search.invoke(query) or []
    except Exception:
        log.debug("web_search failed query=%s", query, exc_info=True)
        return ""

    if isinstance(results, str):
        return results.strip()
    if not isinstance(results, list):
        return ""

    filtered = [r for r in results if isinstance(r, dict) and r.get("score", 0) >= min_score]
    log.debug("web_search result_count=%s for query=%s", len(filtered), query)
    return "\n".join((r.get("content") or "").strip() for r in filtered if (r.get("content") or "").strip())


def build_search_context(queries: list[str], min_score: float = 0.3) -> str:
    """複数クエリの検索結果を1つの「参考情報」プロンプト断片にまとめて返す。

    各クエリを並列検索し、結果のある分だけを見出し付きで連結する。全滅なら空文字。
    エージェントのプロンプト末尾に添えて、実在確認の根拠として使う。
    """
    # 複数の検索クエリは互いに独立なので並列実行して待ち時間を短縮する（順序は維持）
    if not queries:
        return ""
    with ThreadPoolExecutor(max_workers=min(4, len(queries))) as ex:
        results = list(ex.map(lambda q: web_search(q, min_score=min_score), queries))
    sections = [f"[検索: {q}]\n{r}" for q, r in zip(queries, results) if r]
    if not sections:
        log.debug("build_search_context empty for queries=%s", queries)
        return ""
    log.debug("build_search_context generated for queries=%s", queries)
    return "\n\n【ウェブ検索による参考情報（上位の信頼できる情報を抽出）】\n" + "\n\n".join(sections) + "\n上記の公式・ガイド情報に基づいて、実在が確認できる候補を選定してください。"


def invoke_with_retry(structured_llm, prompt: str):
    """LLM 呼び出しを最大5回までリトライする。

    レート制限(429/503/quota等)は指数バックオフ、接続エラーは線形バックオフで待機。
    それ以外のエラー、または上限到達時は最後の例外を送出する。
    """
    for attempt in range(5):
        try:
            return structured_llm.invoke(prompt)
        except Exception as e:
            err = str(e).lower()
            is_rate_limit = "429" in str(e) or "503" in str(e) or "rate" in err or "quota" in err or "unavailable" in err
            is_connection_err = "disconnected" in err or "remoteprotocol" in err or "connection" in err or "reset" in err or "timeout" in err
            if (is_rate_limit or is_connection_err) and attempt < 4:
                wait = 10 * (2 ** attempt) if is_rate_limit else 5 * (attempt + 1)
                reason = "レート制限" if is_rate_limit else "接続エラー"
                log.warning("%sのため%s秒待機中... (試行%s/5)", reason, wait, attempt + 1)
                time.sleep(wait)
            else:
                log.error("invoke_with_retry failed attempt=%s err=%s", attempt + 1, e, exc_info=True)
                raise
