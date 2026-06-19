"""完成した旅行プラン状態を、チャットに表示するHTMLカードへ整形するモジュール。"""

import json
from chat.logger import get_logger


logger = get_logger("formatter")


def _format_plan(state: dict) -> str:
    """TravelPlanState をプランカードのHTML文字列に変換する。

    予算不足（budget_infeasible）の場合はエラーカードを返す。通常時は
    概要ヘッダ＋アコーディオン（観光/グルメ/宿泊/スケジュール/費用）＋総評＋
    保存ボタンを組み立てる。保存ボタンには再保存用のプランJSONを埋め込む。
    ユーザー由来の文字列はすべて esc() でHTMLエスケープしてXSSを防ぐ。
    """
    def esc(text: str) -> str:
        """HTML特殊文字をエスケープする（XSS対策）。"""
        return str(text).replace("&", "&amp;").replace("<", "&lt;").replace(">", "&gt;")

    def accordion(icon: str, label: str, items: list, open: bool = False) -> str:
        """項目リストを <details> 折りたたみブロックのHTMLにする。"""
        items_html = "".join(f"<li>{esc(i)}</li>" for i in items)
        open_attr = " open" if open else ""
        return f"""<details{open_attr}>
  <summary>{icon} {label}</summary>
  <div class="plan-accordion-body"><ul>{items_html}</ul></div>
</details>"""

    status = state.get("status")
    logger.debug("フォーマット開始: destination=%s, status=%s", state.get("destination"), status)

    header = f"""<div class="plan-card">
  <div class="plan-summary-block">
    <div class="plan-title">🗾 旅行プラン：{esc(state['destination'])}</div>
    <div class="plan-summary-grid">
      <span>📍 出発地: {esc(state['departure_location'])}</span>
      <span>⏱️ 期間: {esc(state['duration'])}</span>
      <span>👥 人数: {esc(state['num_people'])}人</span>
      <span>💴 予算上限: {state['budget_limit']:,}円/人</span>
      <span>🚄 交通費: {state.get('transport_cost', 0):,}円/人</span>
      <span>💰 残り予算: {state.get('remaining_budget', 0):,}円/人</span>
    </div>
  </div>"""

    if status == "budget_infeasible":
        logger.warning("予算不足でプラン生成を中断: destination=%s", state.get("destination"))
        return header + f"""
  <div class="plan-error">
    <strong>❌ 予算不足により旅行プランの作成を断念しました</strong>
    <p>{esc(state.get('feedback', ''))}</p>
  </div>
</div>"""

    plan_json = json.dumps({
        "destination":          state.get("destination"),
        "travel_date":          state.get("travel_date"),
        "duration":             state.get("duration"),
        "num_people":           state.get("num_people"),
        "budget_limit":         state.get("budget_limit"),
        "departure_location":   state.get("departure_location"),
        "transport_cost":       state.get("transport_cost"),
        "remaining_budget":     state.get("remaining_budget"),
        "status":               state.get("status"),
        "feedback":             state.get("feedback"),
        "themes":               state.get("themes", []),
        "special_requirements": state.get("special_requirements", []),
        "spots":                state.get("spots", []),
        "restaurants":          state.get("restaurants", []),
        "schedule":             state.get("schedule", []),
        "accommodation":        state.get("accommodation", []),
        "budget_estimate":      state.get("budget_estimate", []),
    }, ensure_ascii=False).replace("'", "&#39;").replace('"', "&quot;")

    save_button = f'<div class="plan-save-area"><button class="plan-save-btn" data-plan="{plan_json}">このプランを保存する</button></div>'

    footer = ""
    if status == "approved":
        footer = f'<div class="plan-review"><strong>💬 総評</strong><br>{esc(state.get("feedback", ""))}</div>'
    elif status:
        footer = f'<div class="plan-warning"><strong>⚠️ 未承認終了（{esc(status)}）</strong><br>{esc(state.get("feedback", ""))}</div>'

    logger.info("フォーマット完了: status=%s", status)
    return header + f"""
  <div class="plan-accordion">
    {accordion("✨", "主要観光地", state.get("spots", []))}
    {accordion("🍱", "グルメ", state.get("restaurants", []))}
    {accordion("🏨", "宿泊施設", state.get("accommodation", []))}
    {accordion("📅", "スケジュール", state.get("schedule", []))}
    {accordion("💰", "費用見積もり", state.get("budget_estimate", []))}
  </div>
  {footer}
  {save_button}
</div>"""
