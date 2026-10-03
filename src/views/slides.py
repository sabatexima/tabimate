"""Google スライドへの書き出し（保存プランの「旅のしおり」と、思い出の「アルバム」）。

流れ:
  /plan/<id>/slides（しおり）・/trip/<id>/slides（アルバム）
  → Google の許可画面（ドライブにファイルを作る権限だけ）
  → /auth/callback に戻る → スライドを作って、そのURLへ移る

アルバムは写真を何十枚も整えて貼るので、数十秒かかる。待っている間に白い画面のまま
にしないよう、進み具合を書き足していくページを返し（ストリーミング）、できたら移る。

戻り先はログインと同じ /auth/callback にしている。Google Cloud の
「承認済みのリダイレクト URI」を増やさずに済むため。どちらの戻りかは、
Authlib がセッションに残した state の持ち主（クライアント名）で見分ける
（is_slides_callback）。合言葉の取り違えが起きないので、ログイン中に
書き出しを途中でやめても、次のログインを邪魔しない。

アクセストークンはその場で使い切り、保存しない。書き出すたびに Google を
通るが、一度許可していれば画面は出ずにすぐ戻ってくる。
"""

import json
import queue
import threading

from flask import (Blueprint, Response, redirect, render_template, request, session,
                   stream_with_context, url_for)

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


def _viewable_trip(trip_id):
    """この旅を見られる人（持ち主・メールで共有された人）なら旅を返す。それ以外は None。"""
    import db_reflection as repo
    from views.sharing import _resolve_permission
    if _resolve_permission("trip", trip_id, token=None) is None:
        return None
    return repo.get_trip_by_id(trip_id)


def _not_found(message):
    return render_template("error.html", code=404, heading="ページが見つかりません",
                           message=message), 404


@slides.route("/plan/<int:plan_id>/slides")
@login_required
def export_slides(plan_id):
    """Google の許可画面へ送る。戻ってきたら finish_slides_export が続きをやる。"""
    if not _own_plan(plan_id):
        return _not_found("このプランは見つかりませんでした。")
    session["slides_target"] = ["plan", plan_id]
    logger.info("スライド書き出し開始: plan_id=%s", plan_id)
    return _authorize()


@slides.route("/trip/<int:trip_id>/slides")
@login_required
def export_album(trip_id):
    """思い出の写真を、写真が主役のアルバムのスライドにする（許可画面へ送る）。"""
    if not _viewable_trip(trip_id):
        return _not_found("この旅は見つかりませんでした。")
    session["slides_target"] = ["trip", trip_id]
    logger.info("アルバムのスライド書き出し開始: trip_id=%s", trip_id)
    return _authorize()


def _authorize():
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


def _trip_page(trip_id):
    """旅のページ（持ち主は自分の旅のページ、共有された人は共有のページ）。"""
    import db_reflection as repo
    if repo.get_trip(trip_id, session.get("user_id")):
        return url_for("reflection.trip_detail", trip_id=trip_id)
    return url_for("sharing.shared_view", resource_type="trip", resource_id=trip_id)


def finish_slides_export():
    """Google から戻ってきたところ。スライドを作り、そのURLへ移る。"""
    target = session.pop("slides_target", None)
    legacy = session.pop("slides_plan_id", None)   # 以前の形（更新の前に許可画面へ行った人）
    kind, target_id = target if target else ("plan", legacy)
    if request.args.get("error"):
        # 許可画面で「キャンセル」を押した
        logger.info("スライド書き出し: 許可されませんでした (%s)", request.args.get("error"))
        if kind == "trip" and target_id:
            return redirect(_trip_page(target_id))
        if target_id:
            return redirect(url_for("planner.plan_detail", plan_id=target_id))
        return redirect(url_for("planner.saved_plans"))
    try:
        token = getattr(oauth, CLIENT_NAME).authorize_access_token()
    except Exception:
        logger.exception("スライド書き出し: トークンを受け取れませんでした")
        return _sorry("Google との連携がうまくいきませんでした。もう一度お試しください。")
    if kind == "trip":
        return _finish_album(token["access_token"], target_id)
    return _finish_plan(token, target_id)


def _finish_plan(token, plan_id):
    """しおりのスライドを作って、そのURLへ移る（数秒で終わるので、そのまま待たせる）。"""
    from services import weather
    from services.slides_export import SlidesError, create_presentation

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


def _album_data(trip: dict) -> dict:
    """アルバムの材料（旅・写真・付箋・ベストショット）を集める。"""
    import db_reflection as repo
    best = trip.get("best_shots")
    if isinstance(best, str):
        try:
            best = json.loads(best)
        except ValueError:
            best = []
    return {
        "id": trip["id"], "title": trip.get("title"),
        "start_date": trip.get("start_date"), "end_date": trip.get("end_date"),
        "cover_photo_id": trip.get("cover_photo_id"),
        "best": [b for b in (best or []) if isinstance(b, dict)],
        "stickers": [s.get("text") for s in repo.get_stickers(trip["id"])],
        "photos": [{"id": p["id"], "taken_at": p.get("taken_at"), "storage_path": p["storage_path"]}
                   for p in repo.get_photos(trip["id"])],
    }


def _js(value) -> str:
    """<script> の中に置く値（</script> で閉じられないよう < を逃がす）。"""
    return json.dumps(value, ensure_ascii=False).replace("<", "\\u003c")


def _finish_album(access_token, trip_id):
    """アルバムを作る。進み具合を書き足していくページを返し、できたらスライドへ移る。"""
    from services import storage
    from services.album_slides import SlidesError, create_album

    trip = _viewable_trip(trip_id) if trip_id else None
    if not trip:
        return _sorry("アルバムにする旅が見つかりませんでした。旅のページからもう一度お試しください。", 404)
    album = _album_data(trip)
    if not album["photos"]:
        return _sorry("この旅にはまだ写真がありません。写真を入れてから作ってください。")
    back = _trip_page(trip_id)
    page = render_template("slides_progress.html", back=back, title=album["title"] or "旅の思い出")
    head, tail = page.split("<!--progress-->", 1)
    events: queue.Queue = queue.Queue()
    result: dict = {}

    def work():
        host = storage.TempImages()
        try:
            try:
                storage.TempImages.sweep()
            except Exception:
                logger.warning("スライド用の一時ファイルを掃除できませんでした", exc_info=True)
            result["url"] = create_album(
                access_token, album, read_photo=lambda p: storage.read_bytes(p["storage_path"]),
                host=host, progress=lambda text, done, total: events.put((text, done, total)))
        except SlidesError as e:
            result["error"] = f"{e} 少し時間をおいて、もう一度お試しください。"
        except Exception:
            logger.exception("アルバムのスライド書き出しに失敗: trip_id=%s", trip_id)
            result["error"] = "少し時間をおいて、もう一度お試しください。"
        finally:
            events.put(None)

    def stream():
        # ブラウザがすぐ描き始めるよう、ページの頭を先に送る
        yield head + "<!--" + " " * 1024 + "-->\n"
        threading.Thread(target=work, daemon=True).start()
        last = None
        while True:
            try:
                item = events.get(timeout=10)
            except queue.Empty:
                yield "\n"   # 長く黙ると切られることがあるので、ときどき改行を送る
                continue
            if item is None:
                break
            # 同じ段階の細かな進みは間引く（1枚ごとに送ると多すぎる）
            text, done, total = item
            if last and last[0] == text and done not in (total,) and done - last[1] < max(1, total // 20):
                continue
            last = item
            yield f"<script>step({_js(text)},{int(done)},{int(total)})</script>\n"
        if result.get("url"):
            yield f"<script>finish({_js(result['url'])})</script>\n"
        else:
            yield f"<script>fail({_js(result.get('error') or '')})</script>\n"
        yield tail

    return Response(stream_with_context(stream()), mimetype="text/html",
                    headers={"Cache-Control": "no-store", "X-Accel-Buffering": "no"})
