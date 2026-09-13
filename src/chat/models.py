"""プラン生成ワークフローで使うデータ構造の定義。

  - TravelPlanState : LangGraph の各エージェント間で受け渡す状態（TypedDict）。
                      旅行条件・中間成果物・最終プランをまとめて保持する。
  - 各 *Output      : LLM の構造化出力（with_structured_output）用スキーマ。
                      これにより LLM 応答を型付きオブジェクトとして受け取れる。
"""

from typing import TypedDict, List, Literal
from pydantic import BaseModel, Field


class TravelPlanState(TypedDict):
    """エージェント間で受け渡す旅行プランの全状態。

    前半は入力条件、中盤は各エージェントの成果物（交通費・候補・確定リスト等）、
    status / feedback / retry_count は balancer による審査と差し戻し制御に使う。
    """
    destination: str
    travel_date: str
    duration: str
    themes: List[str]
    num_people: int
    budget_limit: int
    departure_location: str
    transport_mode: str
    no_car: bool  # 運転免許なし/運転不可。Trueなら車を使わず公共交通機関で組む
    schedule_pref: str  # 時間の希望（「夕方までに帰りたい」「朝はゆっくり」等）。無ければ空
    weather: str  # 旅行日の天気予報ヒント（屋内/屋外の調整用）。取得できなければ空
    # 行き先の国。生成の前に目的地をジオコーディングして決める（services.weather.dest_center）。
    # 海外なら費用の円換算・現地語名・フライトの指示を各エージェントに足す。
    dest_country: str  # ISO 3166-1 小文字（"jp","fr"…）。不明なら ""（＝国内扱い）
    is_overseas: bool
    user_preferences: str  # 過去の★評価から得た好み（参考）。無ければ空
    special_requirements: List[str]
    transport_cost: int
    remaining_budget: int
    spots: List[str]
    restaurants: List[str]
    schedule: List[str]
    accommodation: List[str]
    budget_estimate: List[str]
    total_per_person: int
    feedback: str
    status: Literal[
        "approved",
        "fix_sightseeing",
        "fix_gourmet",
        "fix_accommodation",
        "fix_budget",
        "fix_time",
        "budget_infeasible",
    ]
    prev_status: str
    retry_count: int
    user_feedback: str
    # 部分編集の対象領域（sightseeing/gourmet/accommodation/schedule/budget/transport）。
    # 空ならフル生成。対象外の領域は前回プランの成果物をそのまま引き継ぐ。
    edit_targets: List[str]
    spot_candidates: List[str]
    accommodation_candidates: List[str]
    restaurant_candidates: List[str]


class TransportOutput(BaseModel):
    """交通エージェントの出力。往復交通費（1人あたり・円）だけを受け取る。

    金額1つに絞ってあるのは、残予算＝予算上限−交通費 をコード側で確実に計算するため。
    """
    transport_cost: int = Field(
        description="出発地から目的地までの往復交通費の1人あたり概算金額（円）。0以上999999以下の整数"
    )


class SightseeingCandidatesOutput(BaseModel):
    """観光候補の抽出（1段目）の出力。名前だけを多めに集める。

    ここでは絞り込まない。選ぶのは SightseeingOutput の段で、差し戻しのときも
    この候補プールから選び直す。
    """
    candidates: List[str] = Field(
        description="厳密に5個以上8個以下の名称のみ。説明なし。"
    )


class SightseeingOutput(BaseModel):
    """観光スポット選定（2段目）の出力。候補から実際に回る分だけを選ぶ。"""
    spots: List[str] = Field(
        description="2個以上6個以下の観光スポット名称のみのリスト。説明なし。重複なし。日帰りでも1日を充実させられる件数を選ぶこと。"
    )


class GourmetCandidatesOutput(BaseModel):
    """飲食店候補の抽出（1段目）の出力。名前だけを多めに集める。"""
    restaurants: List[str] = Field(
        description="厳密に4個以上6個以下の飲食店名のみのリスト。説明なし。重複なし。"
    )


class GourmetOutput(BaseModel):
    """飲食店選定（2段目）の出力。候補から食事回数分だけを選ぶ。"""
    restaurants: List[str] = Field(
        description="厳密に2個以上3個以下の飲食店名のみのリスト。説明なし。重複なし。"
    )


class AccommodationCandidatesOutput(BaseModel):
    """宿泊候補の抽出（1段目）の出力。価格帯の違う宿を混ぜて集める。"""
    accommodation: List[str] = Field(
        description="厳密に3個以上5個以下の宿泊施設名のみのリスト。説明なし。重複なし。"
    )


class AccommodationOutput(BaseModel):
    """宿泊施設選定（2段目）の出力。実際に泊まる1軒だけを受け取る。

    「A旅館かBホテル」と併記されると費用も行程も二重になるので、
    スキーマの説明文の側でも1個に絞るよう強く指示している。
    """
    accommodation: List[str] = Field(
        description="実際に宿泊する施設名のみ。原則1個（全員同一施設）。宿泊エリアが変わる連泊のときだけ最大2個。代替候補の併記は禁止。説明なし。重複なし。"
    )


class TimekeeperOutput(BaseModel):
    """タイムキーパーの出力。時系列のスケジュール行。

    複数日なら「N日目」の見出し行を挟む。この見出しは後段でも使う
    （agents._days_in の日数検証、地図の日ごとの絞り込み）。
    """
    schedule: List[str] = Field(
        description="時系列の行動指示。各要素は先頭に時刻を付け、1行1予定。重複なし。"
    )


class CostOutput(BaseModel):
    """費用マネージャーの出力。内訳の行と、1人あたり合計。

    合計を別項目として持たせるのは、コード側の予算ガードが数値で比較するため
    （文章から金額を読み取らずに済む）。
    """
    budget_estimate: List[str] = Field(
        description="各費用項目と金額を箇条書きにしたリスト。日別に分けて記載し、最後に合計行を含めること。"
    )
    total_per_person: int = Field(
        description="往復交通費を含む1人あたりの合計金額（円）。budget_estimateの合計と必ず一致させること。"
    )


class BalancerOutput(BaseModel):
    """バランサーの審査結果。差し戻し先はこの status から決まる
    （agents.route_after_balancer）。
    """
    status: Literal[
        "approved",
        "fix_sightseeing",
        "fix_gourmet",
        "fix_accommodation",
        "fix_budget",
        "fix_time",
        "budget_infeasible",
    ] = Field(
        description=(
            "プラン審査結果。"
            "全観点をパスしたら approved、"
            "観光スポットの選定に問題があれば fix_sightseeing、"
            "飲食店の選定に問題（アレルギー非対応など）があれば fix_gourmet、"
            "宿泊施設の選定に問題（バリアフリー非対応・人数不足など）があれば fix_accommodation、"
            "宿泊費と食費の両方が予算を圧迫しており両方見直しが必要な場合は fix_budget、"
            "スケジュールの詰め込みや移動時間に問題があれば fix_time、"
            "費用見積もりの合計が予算上限を大幅に超えており、どう選び直しても構造的に実現不可能と判断される場合は budget_infeasible を返す。"
            "初回審査では budget_infeasible を選ばず、fix_* で差し戻す。"
        )
    )
    feedback: str = Field(description="審査の理由や、修正が必要なエージェントへの具体的なアドバイス")
