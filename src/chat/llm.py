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



def web_search(query: str, min_score: float = 0.3) -> str:
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
