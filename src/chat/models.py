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
        "candidates_ready",
        "accommodation_candidates_ready",
        "gourmet_candidates_ready",
    ]
    prev_status: str
    retry_count: int
    user_feedback: str
    # 部分編集の対象領域（sightseeing/gourmet/accommodation/schedule/budget/transport）。
    # 空ならフル生成。対象外の領域は前回プランの成果物をそのまま引き継ぐ。
    edit_targets: List[str]
    search_context: str
    spot_candidates: List[str]
    accommodation_candidates: List[str]
    restaurant_candidates: List[str]


class TransportOutput(BaseModel):
    transport_cost: int = Field(
        description="出発地から目的地までの往復交通費の1人あたり概算金額（円）。0以上999999以下の整数"
    )


class SightseeingCandidatesOutput(BaseModel):
    candidates: List[str] = Field(
        description="厳密に5個以上8個以下の名称のみ。説明なし。"
    )


class SightseeingOutput(BaseModel):
    spots: List[str] = Field(
        description="厳密に2個以上3個以下の候補スポット名称のみのリスト。説明なし。重複なし。"
    )


class GourmetCandidatesOutput(BaseModel):
    restaurants: List[str] = Field(
        description="厳密に4個以上6個以下の飲食店名のみのリスト。説明なし。重複なし。"
    )


class GourmetOutput(BaseModel):
    restaurants: List[str] = Field(
        description="厳密に2個以上3個以下の飲食店名のみのリスト。説明なし。重複なし。"
    )


class AccommodationCandidatesOutput(BaseModel):
    accommodation: List[str] = Field(
        description="厳密に3個以上5個以下の宿泊施設名のみのリスト。説明なし。重複なし。"
    )


class AccommodationOutput(BaseModel):
    accommodation: List[str] = Field(
        description="厳密に1個以上2個以下の宿泊施設名のみのリスト。説明なし。重複なし。"
    )


class TimekeeperOutput(BaseModel):
    schedule: List[str] = Field(
        description="時系列の行動指示。各要素は先頭に時刻を付け、1行1予定。重複なし。"
    )


class CostOutput(BaseModel):
    budget_estimate: List[str] = Field(
        description="各費用項目と金額を箇条書きにしたリスト。日別に分けて記載し、最後に合計行を含めること。"
    )
    total_per_person: int = Field(
        description="往復交通費を含む1人あたりの合計金額（円）。budget_estimateの合計と必ず一致させること。"
    )


class BalancerOutput(BaseModel):
    status: Literal[
        "approved",
        "fix_sightseeing",
        "fix_gourmet",
        "fix_accommodation",
        "fix_budget",
        "fix_time",
        "budget_infeasible",
        "candidates_ready",
        "accommodation_candidates_ready",
        "gourmet_candidates_ready",
        "fallback_sightseeing",
        "fallback_accommodation",
        "fallback_gourmet",
    ] = Field(
        description=(
            "プラン審査結果。"
            "完璧なら approved、"
            "観光スポットの選定に問題があれば fix_sightseeing、"
            "飲食店の選定に問題（アレルギー非対応など）があれば fix_gourmet、"
            "宿泊施設の選定に問題（バリアフリー非対応・人数不足など）があれば fix_accommodation、"
            "宿泊費と食費の両方が予算を圧迫しており両方見直しが必要な場合は fix_budget、"
            "スケジュールの詰め込みや移動時間に問題があれば fix_time、"
            "費用見積もりの合計が予算上限を大幅に超えており、どう選び直しても構造的に実現不可能と判断される場合は budget_infeasible、"
            "候補抽出チェックで問題がなくなったら intermediate status を返す。"
            "初回審査では budget_infeasible を選ばず、fix_* で差し戻す。"
            "候補抽出でGPTが失敗した場合は fallback_* で救済する。"
        )
    )
    feedback: str = Field(description="審査の理由や、修正が必要なエージェントへの具体的なアドバイス")
