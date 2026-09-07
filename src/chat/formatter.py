"""完成した旅行プラン状態を、チャットに表示するHTMLカードへ整形するモジュール。"""

import json
import urllib.parse
from chat.logger import get_logger


logger = get_logger("formatter")


def booking_url(destination: str) -> str:
    """目的地の宿を Google マップで探すURL（公式の Maps URLs 形式・スマホはアプリが開く）。

    以前は楽天トラベルの検索URLだったが、非公開のURL形式だったため常にエラーページに
    着地していた。地図ピンの経路リンクとも揃う Google マップ検索に統一する。
    """
    return ("https://www.google.com/maps/search/?api=1&query="
            + urllib.parse.quote((destination or "") + " 宿"))


# プラン状態のうち、保存・再編集に必要なフィールドだけを取り出した辞書を作る。
# 用途は2つで、両方がこの同じ関数を使うことで定義が1か所に集約される:
#   1) data-plan 埋め込み（フロントの「保存する」ボタンが読む）
#   2) チャット編集時の「前回プラン」としてDBへ保存（chat.py）
def plan_payload(state: dict) -> dict:
    return {
        "destination":          state.get("destination"),
        "travel_date":          state.get("travel_date"),
        "duration":             state.get("duration"),
        "num_people":           state.get("num_people"),
        "budget_limit":         state.get("budget_limit"),
        "departure_location":   state.get("departure_location"),
        "transport_cost":       state.get("transport_cost"),
        "remaining_budget":     state.get("remaining_budget"),
        "total_per_person":     state.get("total_per_person"),
        "status":               state.get("status"),
        "feedback":             state.get("feedback"),
        "themes":               state.get("themes", []),
        "special_requirements": state.get("special_requirements", []),
        "spots":                state.get("spots", []),
        "restaurants":          state.get("restaurants", []),
        "schedule":             state.get("schedule", []),
        "accommodation":        state.get("accommodation", []),
        "budget_estimate":      state.get("budget_estimate", []),
    }


def _no_blank_lines(html: str) -> str:
    """空行（空白だけの行を含む）を落とす。プランカードを返す前の最後の一手。

    このHTMLは画面側で marked.parse() を通ってから表示される。Markdown は
    空行を見つけると「HTMLはここまで」と判断してMarkdownの解釈に戻るので、
    その次に来る4字下げの行を**コードブロック**とみなしてしまう。

    実際これで、日帰りプラン（宿泊が空）のスケジュールが壊れていた:
    空の宿泊セクションが空白だけの行を残す → 次の `    <details>` が
    コードブロックになり、`<details>` という文字がそのまま表示され、
    スケジュールは折りたためないまま中身が開きっぱなしになる。

    行の形に依存しないよう、空行を持たせないことで防ぐ。
    """
    return "\n".join(line for line in html.splitlines() if line.strip())


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
        """項目リストを <details> 折りたたみブロックのHTMLにする。空なら出さない（日帰りの宿泊等）。

        改行も字下げも入れずに1行で返すこと。このHTMLは画面側で
        marked.parse() を通るので、行の形がそのまま表示に効いてしまう
        （詳しくは _no_blank_lines の説明）。
        """
        if not items:
            return ""
        items_html = "".join(f"<li>{esc(i)}</li>" for i in items)
        open_attr = " open" if open else ""
        return (f"<details{open_attr}>"
                f"<summary>{icon} {label}</summary>"
                f'<div class="plan-accordion-body"><ul>{items_html}</ul></div>'
                f"</details>")

    status = state.get("status")
    logger.debug("フォーマット開始: destination=%s, status=%s", state.get("destination"), status)

    # 金額と「円/人」は途中で改行されると読みにくい（「…円/」＋「人」の泣き別れ）ため分割禁止にする
    _total = state.get("total_per_person")
    _cost_line = (f'💴 費用の目安: <span style="white-space:nowrap">{_total:,}円/人</span>'
                  if _total else f'💴 予算上限: <span style="white-space:nowrap">{state["budget_limit"]:,}円/人</span>')
    header = f"""<div class="plan-card">
  <div class="plan-summary-block">
    <div class="plan-title">🗾 旅行プラン：{esc(state['destination'])}</div>
    <div class="plan-summary-grid">
      <span>📍 出発地: {esc(state['departure_location'])}</span>
      <span>⏱️ 期間: {esc(state['duration'])}</span>
      <span>👥 人数: {esc(state['num_people'])}人</span>
      <span>{_cost_line}</span>
    </div>
  </div>"""

    if status == "budget_infeasible":
        logger.warning("予算不足でプラン生成を中断: destination=%s", state.get("destination"))
        return _no_blank_lines(header + f"""
  <div class="plan-error">
    <strong>❌ 予算不足により旅行プランの作成を断念しました</strong>
    <p>{esc(state.get('feedback', ''))}</p>
  </div>
</div>""")

    plan_json = json.dumps(plan_payload(state), ensure_ascii=False).replace("'", "&#39;").replace('"', "&quot;")

    save_button = f'<div class="plan-save-area"><button class="plan-save-btn" data-plan="{plan_json}">このプランを保存する</button></div>'

    # プランは「出して終わり」ではなく、チャットで調整できることを案内する
    edit_hint = ""
    if status == "approved":
        edit_hint = (
            '<div class="plan-edit-hint">'
            'このプランは<strong>チャットで調整</strong>できます。'
            '「2日目をゆっくりに」「もう少し予算を抑えて」「宿を変えて」のように送ってくださいね🍀'
            '</div>'
        )

    footer = ""
    if status == "approved":
        footer = f'<div class="plan-review"><strong>💬 総評</strong><br>{esc(state.get("feedback", ""))}</div>'
    elif status:
        footer = f'<div class="plan-warning"><strong>⚠️ 未承認終了（{esc(status)}）</strong><br>{esc(state.get("feedback", ""))}</div>'

    logger.info("フォーマット完了: status=%s", status)
    book = (
        f'<div class="plan-book"><a class="plan-book-btn" href="{booking_url(state.get("destination"))}" '
        f'target="_blank" rel="noopener">🏨 {esc(state.get("destination"))}の宿を探す</a></div>'
    )

    # 空のセクションは "" になる。行として並べると空白だけの行が残るので、
    # 連結してから埋める（_no_blank_lines の説明を参照）
    accordions = "".join([
        accordion("✨", "主要観光地", state.get("spots", [])),
        accordion("🍱", "グルメ", state.get("restaurants", [])),
        accordion("🏨", "宿泊施設", state.get("accommodation", [])),
        accordion("📅", "スケジュール", state.get("schedule", [])),
        accordion("💰", "費用見積もり", state.get("budget_estimate", [])),
    ])

    return _no_blank_lines(header + f"""
  <div class="plan-accordion">{accordions}</div>
  {book}
  {footer}
  {edit_hint}
  {save_button}
</div>""")
