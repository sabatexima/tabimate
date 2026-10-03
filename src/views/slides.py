"""保存プランを Google スライドの「旅のしおり」に書き出す Blueprint。

流れ:
  /plan/<id>/slides → Google の許可画面（ドライブにファイルを作る権限だけ）
  → /auth/callback に戻る → スライドを作って、そのURLへ移る

戻り先はログインと同じ /auth/callback にしている。Google Cloud の
「承認済みのリダイレクト URI」を増やさずに済むため。どちらの戻りかは、
Authlib がセッションに残した state の持ち主（クライアント名）で見分ける
（is_slides_callback）。合言葉の取り違えが起きないので、ログイン中に
書き出しを途中でやめても、次のログインを邪魔しない。

アクセストークンはその場で使い切り、保存しない。書き出すたびに Google を
通るが、一度許可していれば画面は出ずにすぐ戻ってくる。
"""

from flask import Blueprint, redirect, render_template, request, session, url_for

from logger import get_logger
from views.auth import login_required, oauth

slides = Blueprint("slides", __name__)
logger = get_logger("views.slides")

# ドライブ全体ではなく「このアプリが作ったファイルだけ」に触れる、いちばん狭い権限
SLIDES_SCOPE = "openid email profile https://www.googleapis.com/auth/drive.file"
CLIENT_NAME = "google_slides"


def register_client(oauth_registry, client_id, client_secret):
    """ログイン用とは別に、書き出し用のクライアントを登録する（権限の範囲だけが違う）。"""
    oauth_registry.register(
        name=CLIENT_NAME,
        client_id=client_id,
        client_secret=client_secret,
        server_metadata_url="https://accounts.google.com/.well-known/openid-configuration",
        client_kwargs={"scope": SLIDES_SCOPE},
    )


def _own_plan(plan_id):
    """本人のプランだけ返す。他人のものや無いものは None。"""
    from db import get_travel_plan_by_id
    plan = get_travel_plan_by_id(plan_id)
    if not plan or plan.get("google_user_id") != session.get("user_id"):
        return None
    return plan


def _sorry(message, code=400):
    """世界観に合わせたエラーページで、書き出せなかった理由を伝える。"""
    return render_template(
        "error.html", code="", heading="スライドを作れませんでした", message=message,
    ), code


@slides.route("/plan/<int:plan_id>/slides")
@login_required
def export_slides(plan_id):
    """Google の許可画面へ送る。戻ってきたら finish_slides_export が続きをやる。"""
    if not _own_plan(plan_id):
        return render_template(
            "error.html", code=404, heading="ページが見つかりません",
            message="このプランは見つかりませんでした。",
        ), 404
    session["slides_plan_id"] = plan_id
    logger.info("スライド書き出し開始: plan_id=%s", plan_id)
    return getattr(oauth, CLIENT_NAME).authorize_redirect(
        url_for("auth.callback", _external=True),
        # 別のアカウントを選ばせない（ドライブはログイン中の人のものに作る）
        login_hint=session.get("user_email") or None,
        # ログインで許可済みの範囲も引き継ぐ（許可画面を必要以上に出さない）
        include_granted_scopes="true",
    )


def is_slides_callback() -> bool:
    """いまの /auth/callback が、スライド書き出しの戻りかどうか。"""
    state = request.args.get("state")
    return bool(state) and f"_state_{CLIENT_NAME}_{state}" in session


def finish_slides_export():
    """Google から戻ってきたところ。スライドを作り、そのURLへ移る。"""
    from services import weather
    from services.slides_export import SlidesError, create_presentation

    plan_id = session.pop("slides_plan_id", None)
    if request.args.get("error"):
        # 許可画面で「キャンセル」を押した
        logger.info("スライド書き出し: 許可されませんでした (%s)", request.args.get("error"))
        if plan_id:
            return redirect(url_for("planner.plan_detail", plan_id=plan_id))
        return redirect(url_for("planner.saved_plans"))
    try:
        token = getattr(oauth, CLIENT_NAME).authorize_access_token()
    except Exception:
        logger.exception("スライド書き出し: トークンを受け取れませんでした")
        return _sorry("Google との連携がうまくいきませんでした。もう一度お試しください。")

    plan = _own_plan(plan_id) if plan_id else None
    if not plan:
        return _sorry("書き出すプランが見つかりませんでした。保存プランの画面からもう一度お試しください。", 404)

    try:
        weather_days = weather.plan_forecast(plan)
    except Exception:
        weather_days = None  # 天気は飾り。取れなくてもしおりは作る

    def image_url(name):
        return url_for("static", filename=f"img/{name}", _external=True)

    try:
        url = create_presentation(token["access_token"], plan,
                                  image_url=image_url, weather_days=weather_days)
    except SlidesError as e:
        return _sorry(f"{e} 少し時間をおいて、もう一度お試しください。", 502)
    except Exception:
        logger.exception("スライド書き出しに失敗: plan_id=%s", plan_id)
        return _sorry("少し時間をおいて、もう一度お試しください。", 502)
    return redirect(url)
