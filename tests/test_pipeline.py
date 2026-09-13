"""プラン生成を、AI の返事だけ偽物にして丸ごと通す検査。

ここまでの単体テストは、関数を1つずつ切り出して見ていた。それだと
「プロンプトにこの文字列が入る」ことは分かっても、条件の組み合わせで
プロンプトが壊れることには気づけない（実際、日帰りのときグルメ選定に
空の「選定済みの宿泊施設:」が出ていたのは、この通し検査で初めて見つかった）。

差し替えるのは3つだけ:
  ・LLM の呼び出し（invoke_with_retry と with_structured_output）
  ・ウェブ検索
  ・座標と天気
プロンプトの組み立て・日数の検証・予算ガード・差し戻しループ・整形は本物が動く。
APIキーは要らず、ネットワークにも出ない。

実行: pytest tests/test_pipeline.py
"""
import itertools
import os
import re
import sys
from pathlib import Path

import pytest

os.environ.setdefault("GOOGLE_API_KEY", "dummy")
os.environ.setdefault("TAVILY_API_KEY", "dummy")
os.environ.setdefault("SECRET_KEY", "dummy")
sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "src"))

from services.weather import parse_duration  # noqa: E402


class _Bound:
    """with_structured_output() の戻り。どのスキーマを求められたかを覚えるだけ。"""

    def __init__(self, schema):
        self.schema = schema


class _FakeLLM:
    """本物の ChatGoogleGenerativeAI の代わり。呼ばれても外へは出ない。"""

    def with_structured_output(self, schema):
        return _Bound(schema)


def _requested_days(prompt):
    """タイムキーパーのプロンプトが「何日ぶん」を求めているか読み取る。

    期間から勝手に日数を決めてしまうと、プロンプトが壊れていても偽物が
    正しい日数を返してしまい、検査が自分の偽物を見るだけになる。
    本物の LLM と同じように、指示された数に従う。
    """
    if "日帰りタイムスケジュール" in prompt:
        return 1
    m = re.search(r"「1日目」〜「(\d+)日目」", prompt)
    assert m, "タイムキーパーのプロンプトに日数の指示が無い"
    return int(m.group(1))


def _answer(name, days):
    """スキーマごとに、形の正しい返事をでっち上げる。"""
    one = lambda **kw: type("R", (), kw)()      # noqa: E731
    if name == "TransportOutput":
        return one(transport_cost=12000)
    if name == "SightseeingCandidatesOutput":
        return one(candidates=[f"観光候補{i}" for i in range(1, 7)])
    if name == "SightseeingOutput":
        return one(spots=["観光候補1", "観光候補2", "観光候補3"])
    if name == "AccommodationCandidatesOutput":
        return one(accommodation=[f"宿候補{i}" for i in range(1, 4)])
    if name == "AccommodationOutput":
        return one(accommodation=["宿候補1"])
    if name == "GourmetCandidatesOutput":
        return one(restaurants=[f"食候補{i}" for i in range(1, 5)])
    if name == "GourmetOutput":
        return one(restaurants=["食候補1", "食候補2"])
    if name == "TimekeeperOutput":
        # 本物のプロンプトに合わせる。日別の見出しを求めるのは複数日のときだけで、
        # 日帰りは時刻の並びだけを返させている
        body = ["09:00 観光候補1", "12:00 食候補1で昼食",
                "15:00 観光候補2", "18:00 宿候補1にチェックイン"]
        if days < 2:
            return one(schedule=body)
        schedule = []
        for n in range(1, days + 1):
            schedule += [f"{n}日目"] + body
        return one(schedule=schedule)
    if name == "CostOutput":
        return one(budget_estimate=["交通費 12,000円", "合計 40,000円"], total_per_person=40000)
    raise AssertionError(f"未知のスキーマ: {name}")


def run_pipeline(monkeypatch, inputs, verdicts=("approved",), country="jp"):
    """本物の generate_travel_plan を1本流し、(最終状態, 渡ったプロンプト) を返す。"""
    import chat.agents as A
    import chat.graph as G
    from services import geocoding as GC, weather as WX

    days = parse_duration(inputs["duration"])[1]
    prompts = []
    verdict_iter = iter(verdicts)

    def invoke(bound, prompt):
        name = bound.schema.__name__
        prompts.append((name, prompt))
        if name == "BalancerOutput":
            return type("R", (), {"status": next(verdict_iter, "approved"),
                                  "feedback": "位置が離れすぎています"})()
        # 行程だけは、期間ではなくプロンプトが求めた日数に従う（本物と同じ振る舞い）
        return _answer(name, _requested_days(prompt) if name == "TimekeeperOutput" else days)

    fake = _FakeLLM()
    monkeypatch.setattr(A, "llm", fake)
    monkeypatch.setattr(A, "llm_strong", fake)
    monkeypatch.setattr(A, "invoke_with_retry", invoke)
    monkeypatch.setattr(A, "build_search_context", lambda qs: "【参考】検索結果")
    monkeypatch.setattr(GC, "verify_place_exists", lambda n, c=None, **kw: True)
    monkeypatch.setattr(GC, "geocode_center",
                        lambda q: {"lat": 36.0, "lng": 137.0, "radius_km": 80.0,
                                   "country_code": country})
    monkeypatch.setattr(GC, "geocode_one", lambda q, **kw: {"lat": 36.0, "lng": 137.0})
    monkeypatch.setattr(WX, "forecast", lambda *a, **kw: [
        {"date": "2099-08-01", "label": "晴れ", "tmin": 20, "tmax": 30, "code": 0}])
    WX._DEST_CACHE.clear()
    return G.generate_travel_plan(dict(inputs)), prompts


def _inputs(duration, country, **over):
    base = dict(destination="パリ" if country == "fr" else "金沢",
                travel_date="2099年8月1日", duration=duration, themes=["食", "街歩き"],
                num_people=3, budget_limit=400000, departure_location="東京",
                special_requirements=[])
    base.update(over)
    return base


# 「見出し:」の形の行を見分ける。時刻（09:00）を見出しと取り違えないよう、
# 行頭が数字のものは除く。■ は審査プロンプトの見出し記号。
_LABEL = r"^\s*■?\s*[^\d\s:：][^:：]{0,19}[:：]"


def _label_only(line):
    """見出しだけで、その行に中身が無いか。"""
    return bool(re.match(_LABEL + r"\s*$", line))


def _starts_with_label(line):
    """行頭が「見出し:」の形か（中身が続いていてもよい）。"""
    return bool(re.match(_LABEL, line))


DURATIONS = ["日帰り", "0泊2日", "1泊2日", "2泊3日", "5泊6日"]
SHAPES = list(itertools.product(DURATIONS, ["jp", "fr"], [False, True]))


@pytest.mark.parametrize("duration,country,no_car", SHAPES)
def test_pipeline_produces_a_coherent_plan(monkeypatch, duration, country, no_car):
    """どの形の旅でも、最後まで通って結果が揃うこと。"""
    nights, days = parse_duration(duration)
    state, _ = run_pipeline(monkeypatch, _inputs(duration, country, no_car=no_car),
                            country=country)

    assert state["status"] == "approved"
    for key in ("spots", "restaurants", "schedule", "budget_estimate", "total_per_person"):
        assert state.get(key), f"{key} が空"
    # 宿は泊数で決まる（0泊2日の夜行では取らない）
    assert bool(state.get("accommodation")) == (nights > 0)
    # スケジュールの日数が期間と一致すること
    found = {int(m.group(1)) for m in
             (re.match(r"[【\[]?\s*(\d+)\s*日目", str(line).strip())
              for line in state["schedule"]) if m}
    assert found == (set(range(1, days + 1)) if days >= 2 else set())


@pytest.mark.parametrize("duration,country,no_car", SHAPES)
def test_prompts_have_no_holes(monkeypatch, duration, country, no_car):
    """どのエージェントのプロンプトにも、埋め残しや空欄が無いこと。

    条件の組み合わせでしか出ない穴を探す。f-string の埋め残し、値が None の行、
    「見出しだけあって中身が無い行」の3つを見る。
    """
    nights = parse_duration(duration)[0]
    _, prompts = run_pipeline(monkeypatch, _inputs(duration, country, no_car=no_car),
                              country=country)

    # 呼ばれた顔ぶれが、旅の形どおりであること。宿を取らない行程で宿の
    # エージェントを呼ぶと、返事を捨てるだけの LLM 代がかかる
    expected = {"TransportOutput", "SightseeingCandidatesOutput", "SightseeingOutput",
                "GourmetCandidatesOutput", "GourmetOutput", "TimekeeperOutput",
                "CostOutput", "BalancerOutput"}
    if nights > 0:
        expected |= {"AccommodationCandidatesOutput", "AccommodationOutput"}
    assert {n for n, _ in prompts} == expected, f"呼ばれたエージェントが想定と違う（{nights}泊）"

    for name, prompt in prompts:
        assert not re.search(r"\{[a-z_]+[\[\]'\"a-z_ ]*\}", prompt), \
            f"{name}: f-string の埋め残し"
        assert not re.search(r"^(.{0,24}?): *None *$", prompt, re.M), f"{name}: None が露出"
        lines = prompt.split("\n")
        for i, line in enumerate(lines):
            if not _label_only(line):
                continue
            nxt = lines[i + 1].strip() if i + 1 < len(lines) else ""
            # 見出しだけの行は、次の行に中身が続いていれば正常
            # （「スケジュール:」→「09:00 …」の形）。次も見出しなら中身が無い
            assert nxt and not _starts_with_label(nxt) and not nxt.startswith("【"), \
                f"{name}: 中身の無い行「{line.strip()}」"


@pytest.mark.parametrize("country", ["jp", "fr"])
@pytest.mark.parametrize("no_car", [False, True])
def test_conditional_instructions_appear_only_when_they_apply(monkeypatch, country, no_car):
    """海外・運転しないの指示が、条件どおりに出入りすること。

    条件を見ないエージェントが1つでもあると、そこだけ配慮が抜ける。
    """
    _, prompts = run_pipeline(monkeypatch, _inputs("2泊3日", country, no_car=no_car),
                              country=country)
    # 行き先を選ぶ・経路を組むエージェント（費用は値付けだけなので対象外）
    chooses_places = {"SightseeingCandidatesOutput", "SightseeingOutput",
                      "AccommodationCandidatesOutput", "AccommodationOutput",
                      "GourmetCandidatesOutput", "GourmetOutput", "TimekeeperOutput"}
    for name, prompt in prompts:
        if name != "TransportOutput":
            assert ("日本円に換算して書き" in prompt) == (country == "fr"), f"{name}: 海外の指示"
        if name in chooses_places:
            has = "運転免許がない" in prompt or "運転しない前提" in prompt
            assert has == no_car, f"{name}: 運転しないの指示"


@pytest.mark.parametrize("verdicts", [
    ["fix_sightseeing", "fix_sightseeing", "fix_sightseeing", "approved"],
    ["fix_sightseeing", "fix_gourmet", "fix_sightseeing", "fix_gourmet", "approved"],
    ["fix_accommodation", "fix_budget", "fix_budget", "approved"],
    ["fix_time"] * 6,
])
def test_retries_hand_the_review_notes_to_the_candidate_agents(monkeypatch, verdicts):
    """差し戻しで候補を集め直すとき、必ず審査の指摘が載っていること。

    載っていなければ temperature=0 なので同じ候補が返り、検索とLLMが無駄になる。
    """
    _, prompts = run_pipeline(monkeypatch, _inputs("2泊3日", "jp"), verdicts=verdicts)
    refreshed = 0
    for schema in ("SightseeingCandidatesOutput", "GourmetCandidatesOutput",
                   "AccommodationCandidatesOutput"):
        again = [p for n, p in prompts if n == schema][1:]   # 2回目以降＝集め直し
        refreshed += len(again)
        for prompt in again:
            assert "前回の審査での指摘" in prompt, f"{schema} に指摘が載っていない"
    assert refreshed, "この並びでは候補集めに戻っていない（テストが効いていない）"


@pytest.mark.parametrize("duration", DURATIONS)
def test_generated_plan_survives_formatting(monkeypatch, duration):
    """出来たプランが、そのまま画面に出せる形になっていること。

    プランカードは marked.parse() を通るので、空行が1つでもあると
    そこで HTML の解釈が打ち切られる（実際に `<details>` が文字で出た）。
    """
    from chat.formatter import _format_plan, plan_payload

    state, _ = run_pipeline(monkeypatch, _inputs(duration, "jp"))
    html = _format_plan(state)
    assert not [l for l in html.split("\n") if not l.strip()], "空行がある"
    for tag in ("div", "details"):
        assert html.count(f"<{tag}") == html.count(f"</{tag}>"), f"<{tag}> の開閉が合わない"
    assert "None" not in html
    payload = plan_payload(state)
    for key in ("destination", "duration", "spots", "schedule"):
        assert payload.get(key), f"控えに {key} が無い"
