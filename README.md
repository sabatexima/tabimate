<p align="center">
  <img src="https://raw.githubusercontent.com/sabatexima/tabimate/main/src/static/img/mate-head.png" alt="Chamu" width="130">
</p>

<h1 align="center">TabiMate&nbsp;🍀</h1>

<p align="center">
  <b>Your travel plan? The AI writes it.</b><br>
  Come home, and your photos quietly become sticky notes.
</p>

<p align="center"><i>A gentle, picture-book-styled travel companion.</i></p>

<p align="center">
  <a href="README_jp.md">🇯🇵&nbsp;日本語</a>
  &nbsp;·&nbsp;
  <a href="https://github.com/sabatexima/tabimate/actions/workflows/ci.yml"><img src="https://github.com/sabatexima/tabimate/actions/workflows/ci.yml/badge.svg" alt="CI"></a>
</p>

<p align="center">
  <img src="https://img.shields.io/badge/Python-3.13-3776AB?logo=python&logoColor=white" alt="Python 3.13">
  <img src="https://img.shields.io/badge/Flask-3.1-000000?logo=flask&logoColor=white" alt="Flask 3.1">
  <img src="https://img.shields.io/badge/LangGraph-1.2-1C3C3C" alt="LangGraph 1.2">
  <img src="https://img.shields.io/badge/Gemini-3.6%20Flash-4285F4?logo=googlegemini&logoColor=white" alt="Gemini">
  <img src="https://img.shields.io/badge/Cloud%20Run-deployed-4285F4?logo=googlecloud&logoColor=white" alt="Cloud Run">
</p>

<p align="center">
  <img src="https://raw.githubusercontent.com/sabatexima/tabimate/main/docs/img/screen-journal-en.png" alt="Trip journal" width="240">
  <img src="https://raw.githubusercontent.com/sabatexima/tabimate/main/docs/img/screen-bookshelf-en.png" alt="Saved plans" width="240">
  <img src="https://raw.githubusercontent.com/sabatexima/tabimate/main/docs/img/screen-plan-detail-en.png" alt="Plan detail" width="240">
</p>

<p align="center"><sub>The app UI is Japanese; screenshots are English-localized mockups of the same screens.</sub></p>

---

## What is TabiMate?

> _From "where should we go?" to "that was fun."_<br>
> _Chamu is there for every part of the trip._

Plenty of apps help you book a trip. TabiMate cares about the **before** and the **after**.

Chat your way to an itinerary. Come home and drop in your photos. **Chamu**, the mascot, binds the itinerary, turns memories into sticky notes, and quietly frames your best shot.

<table>
<tr>
<td width="33%" align="center"><br>🗺️<br><b>Before</b><br><sub>Chat, and your<br>itinerary appears</sub><br><br></td>
<td width="33%" align="center"><br>📸<br><b>After</b><br><sub>Photos become<br>sticky-note memories</sub><br><br></td>
<td width="33%" align="center"><br>🤝<br><b>Together</b><br><sub>Share plans and<br>memories, gently</sub><br><br></td>
</tr>
</table>

---

## Features

### 🗺️ Before — just chat, and the itinerary appears

> _Chamu: "Where to? How many nights? …Got it, leave it to me."_

| | |
|---|---|
| 💬 **Plan by conversation** | Destination, days and budget are read from natural chat; missing pieces are asked one at a time. Then a team of AI agents (LangGraph) builds the plan together. |
| 🌤️ **Weather-aware** | Reads the forecast for your dates — more indoor spots on rainy days, warmer picks when it's cold, and shops likely closed that weekday are skipped. |
| 🍽️ **Real places only** | Candidates are verified against Google Places, so plausible-sounding but invented shops get dropped. |
| 🗾 **Watercolor map** | Sights / food / stays as color-coded pins, connected **in visiting order**. Tap a pin for navigation. |
| 🎒 **Packing list** | Suggested from your destination and the weather. Check an item and a clover blooms. |
| 🍀 **Countdown** | "12 days to go." A little thrill every time you open the shelf. |
| 📅 **Calendar export** | Download the schedule as `.ics`. |
| ✏️ **Tweak later** | "Make Day 2 relaxed," "change the hotel" — all by chat. Rate with ★ and future suggestions quietly adapt. |

### 📸 After — photos turn into words on their own

> _Chamu: "Welcome back. Show me the photos… what a trip."_

| | |
|---|---|
| 🏷️ **Sticky notes from photos** | The AI reads your uploads and captures the mood in short phrases. |
| 📖 **Travel journal** | Polaroids and pastel sticky notes on craft paper. Search and favorite to look back. |
| 🏅 **Chamu's best shot** | Picks the one to frame, and frames it in gold. |
| 💰 **Trip ledger** | Estimate vs. what you actually spent. Under budget? "◯ yen saved 🍀." |
| 🐾 **Footprints map** | Plots your path from photo GPS. Overlay the plan to compare planned vs. actual. |
| 📔 **Yearly digest** | "Your year in travel," recapping the year's trips and sticky notes at a glance. |

### 🤝 Share

- 🔗 **Public link** — login-free, view-only.
- ✉️ **Email grants** — let a specific person view or edit.
- 📱 **PWA** — add to your home screen and launch it from Chamu's icon.

---

## 📱 The iOS app

A native SwiftUI client lives in [`ios/`](ios/) — same server, same account, same trips.

It talks to the endpoints under `/auth/app/*` and `/api/*` listed below, authenticating with a Bearer token instead of a session cookie (`src/api_auth.py`). Setup and build steps are in [`ios/README.md`](ios/README.md); CI builds it and runs its tests on every push.

---

## Built with

| | |
|---|---|
| 🧠 **AI** | LangGraph 1.2 · LangChain · Gemini 3.6 Flash / 3.1 Flash-Lite · Tavily Search |
| ⚙️ **Backend** | Flask 3.1 · SQLAlchemy 2.0 · MySQL 8.0 / TiDB · gunicorn |
| 🗺️ **Maps & Geo** | Leaflet · Stadia Maps (watercolor) · Google Places · OSM Nominatim · GSI |
| ☁️ **Infra** | Cloud Run · Docker · Cloud Storage · Secret Manager · Google OAuth 2.0 · GitHub Actions |
| 🎨 **Frontend** | Jinja2 · vanilla JS · PWA · Zen Maru Gothic |
| 📱 **iOS** | SwiftUI (iOS 17+) · Swift 6 · XcodeGen |

---

## Quick start

```bash
git clone https://github.com/sabatexima/tabimate && cd tabimate

cp src/.env.example src/.env      # fill in API keys, OAuth and DB

cd src
python3 -m venv .venv && source .venv/bin/activate
pip install -r ../requirements.txt
python3 app.py
```

Open **http://localhost:5007**. Tables are created on first access (`CREATE TABLE IF NOT EXISTS`).

```bash
./deploy.sh    # one command to Cloud Run — Secrets, GCS bucket and IAM included
```

---

<details>
<summary><b>📖 Deep dive — developer docs</b></summary>

<br>

### Environment variables

Set in `src/.env` (local) or Cloud Run env / Secret Manager. `src/.env` is Git-ignored.

| Variable | Required | Purpose |
|---|---|---|
| `SECRET_KEY` | prod | Flask session signing key |
| `GOOGLE_API_KEY` | ✓ | Gemini API key |
| `TAVILY_API_KEY` | ✓ | Tavily web search |
| `GOOGLE_CLIENT_ID` / `GOOGLE_CLIENT_SECRET` | ✓ | Google OAuth (web sign-in) |
| `DB_USER` / `DB_PASS` / `DB_NAME` / `DB_HOST` / `DB_PORT` | ✓ | Database connection |
| `GOOGLE_IOS_CLIENT_ID` | app | Audience for verifying ID tokens from the iOS app. Falls back to `GOOGLE_CLIENT_ID`; **sign-in is refused when neither is set**, because an unset audience makes the library skip `aud` validation entirely |
| `APP_TOKEN_MAX_AGE_SEC` | | Lifetime of app tokens (default 30 days) |
| `STADIA_API_KEY` | | Watercolor tiles (falls back to standard OSM). ⚠️ Reaches the browser by design, so **set a domain restriction on the Stadia side** |
| `GOOGLE_MAPS_API_KEY` | | Google Places-powered geocoding. Unset = free stack (Nominatim + GSI) only |
| `DB_SSL` / `DB_SSL_CA` | cond. | TLS connection (`DB_SSL=true` required for TiDB Cloud) |
| `CLOUD_SQL_INSTANCE` | cond. | Connect via Cloud SQL Connector when set |
| `GCS_BUCKET` | cond. | Uses GCS when set, else the local filesystem |
| `LOCAL_UPLOAD_DIR` / `SIGNED_URL_TTL_SECONDS` / `GCS_SIGNER_SA` | | Local dir · signed-URL TTL · signer SA |
| `REDIS_URL` | | Share in-flight generation state across instances |
| `GEMINI_MODEL_STRONG` / `GEMINI_MODEL_LITE` | | Override models (defaults `gemini-3.6-flash` / `gemini-3.1-flash-lite`) — roll back a new model with one line |
| `STICKER_MAX_IMAGES` / `INTERPRETER_IMAGE_MAX_EDGE` | | Sticker-generation image count / resize |

### Layout

```
tabimate/
├── deploy.sh                    # Cloud Run deploy (Secrets / GCS / IAM)
├── dockerfile                   # gunicorn, 1 worker × 20 threads
├── .github/workflows/ci.yml     # two jobs: ubuntu (server + logic) / macOS (iOS)
├── scripts/
│   ├── check_home_js.sh         # drives the chat UI in a real browser
│   ├── check_ios_logic.sh       # type-checks the iOS logic on Linux Swift
│   ├── backfill_thumbnails.py
│   └── setup_alerts.sh
├── tests/                       # see "Tests & CI"
├── ios/                         # SwiftUI app (XcodeGen; see ios/README.md)
└── src/
    ├── app.py                   # Flask app · Blueprints · security headers
    ├── api_auth.py              # Bearer tokens for the native app
    ├── db.py                    # travel_plans / chat_messages
    ├── db_reflection.py         # trips / photos / stickers
    ├── db_sharing.py            # share links / email grants
    ├── geocoding.py             # spot name → lat/lng (multi-provider, cached)
    ├── weather.py               # forecast for the travel dates (Open-Meteo)
    ├── chat/                    # plan generation (LangGraph agents)
    ├── services/                # exif · features · storage · interpreter · packing
    ├── views/                   # planner · auth · reflection · sharing
    ├── templates/               # Jinja2
    └── static/                  # css / js / img
```

### Architecture

```
          ┌─────────── Flask app (app.py) ────────────┐
 Browser  │  ProxyFix · security headers               │
 ─────────┤  planner("/")        auth("/auth")         │
 iOS app  │  reflection("/reflection")  sharing("/share")
 ─────────┤                                            │
  Bearer  └────┬───────────────┬──────────────┬────────┘
               │               │              │
        chat/ (LangGraph)   db*.py        services/
        multi-agent flow  (SQLAlchemy)   exif · storage ·
               │               │         interpreter
               ▼               ▼              ▼
      Gemini + Tavily     MySQL / TiDB       GCS
```

- **One engine, shared** — `get_engine()` (QueuePool) in `db.py` is reused by `db_reflection` / `db_sharing`. Tables are created lazily.
- **Storage is swappable** — `services/storage.py` picks GCS or the local filesystem by `GCS_BUCKET`. Signed URLs are cached and generated in parallel.
- **One session, two doors** — the browser uses a session cookie; the app sends `Authorization: Bearer …`, which `api_auth.authenticate_app_token` translates into the same session for that single request. `login_required` therefore needs no special case.

### Plan-generation agents

`chat/graph.py` defines a `StateGraph` chaining functions from `chat/agents.py`, with `TravelPlanState` (a TypedDict) flowing between them.

```
START
  → transport                  round-trip cost · remaining budget
  → sightseeing_candidates → sightseeing       2–3 spots
  → accommodation_candidates → accommodation   ~40% of remaining (skipped for day trips)
  → gourmet_candidates → gourmet               ~25% of remaining
  → timekeeper                 chronological schedule
  → cost_manager               budget breakdown
  → balancer                   whole-plan review
        ├─ approved / budget_infeasible → END
        └─ fix_* → back to the relevant node   (cap: MAX_BALANCER_RETRIES = 5)
```

- **Lodging-free check** — `parse_duration()` yields (nights, days); zero nights skips the lodging nodes, which covers overnight-transit trips.
- **Existence check** — with `GOOGLE_MAPS_API_KEY`, candidates are verified against Google Places and invented names are dropped.
- **Preference learning** — past ★ ratings and comments become `user_preferences`, softly injected into the agents.
- **Partial editing** — an edit request regenerates only the nodes it touches.
- **Retries** — `invoke_with_retry()` backs off on 429 / 503 / network errors, up to 5 attempts.

### Generation outlives the connection

Plan generation runs in a background thread that **also writes the result to the database**. Nothing about it depends on the browser staying connected.

That matters because generation takes minutes. If the reply were saved by the SSE responder instead, reloading the page would kill the generator mid-flight and throw the whole generation away.

On page load, `/chat` reports whether a reply is still pending, so the "thinking" state comes back immediately after a reload. That state is derived from the rows in `chat_messages` rather than from process memory, so it stays correct across Cloud Run instances:

| Rows for that `request_id` | Meaning |
|---|---|
| an `ai` row exists | finished |
| only the `user` row, recent | still generating |
| only the `user` row, 20+ min old | gave up (the worker probably died) |
| no rows | failed or aborted — already cleaned up |

### Database

| Table | Purpose |
|---|---|
| `travel_plans` | Saved plans (conditions and results as JSON) plus coordinate cache, custom pins, packing list, actual cost, ★ rating |
| `chat_messages` | Chat history; plan rows also carry `plan_json` (the "previous plan" used when editing) |
| `trips` | Trips (title, dates), cover photo, best shots, linked plan |
| `photos` / `stickers` | Photos (path, shoot time, GPS) / sticky notes (display text + internal basis) |
| `share_links` / `share_grants` | Public links / email-based sharing |

Ownership is always checked against `user_id` (the Google `sub`). Deleting a trip cascades to its rows and its physical photos.

### HTTP endpoints

**Pages** — `/` (welcome) · `/chat` · `/saved_plans` · `/plan/<id>` · `/plan/<id>/print` · `/reflection/` · `/reflection/digest` · `/reflection/trips/<id>` · `/shared` · `/s/<token>` · `/terms` · `/privacy`

**Chat** — `/send_message` (SSE) · `/get_messages` · `/reset_chat` · `/abort_request` · `/generation_status`

**Plans** — `/save_plan` · `/get_my_plans` · `/get_shared_plans` · `/edit_saved_plan/<id>` · `/apply_saved_plan/<id>` · `/delete_plan/<id>` · `/rate_plan/<id>` · `/save_actual_total/<id>` · `/save_plan_pins/<id>` · `/export_plan_ics/<id>` · `/api/packing_list/<id>` · `/api/plan_geo/<id>` · `/api/plan_weather/<id>` · `/api/geocode`

**Memories** — `/reflection/trips` (POST) · `/reflection/trips/<id>` (GET / PATCH / DELETE) · `…/photos` · `…/stickers` · `…/stickers/generate` · `…/best_shots` · `…/favorite` · `…/linked-plan` · `/reflection/photo/<path>`

**Sharing** — `/share/<type>/<id>` (state) · `…/link` · `…/grant` · `/share/link/<id>` · `/share/grant/<id>` · `/shared/<type>/<id>` · `/shared/trip/<id>/…` (photo & sticker operations for editors) · `/shared/plan/<id>/ics`

**For the native app** — `/auth/app/signin` · `/auth/app/me` · `/api/ideas` · `/api/chat_messages` · `/reflection/api/trips` · `/reflection/api/trips/<id>` · `/reflection/api/digest`

**Auth** — `/auth/login` · `/auth/callback` · `/auth/logout`

Everything except `/`, `/terms`, `/privacy`, `/api/ideas`, `/auth/*` and the public `/s/<token>` view sits behind `@login_required`, which answers `401 JSON` to API clients and redirects browsers to the login page.

### Tests & CI

```bash
pytest tests/ -k "not smoke"    # 139 offline tests — no API keys, no DB
scripts/check_home_js.sh        # drives the chat UI in a real browser
scripts/check_ios_logic.sh      # type-checks the iOS logic on Linux Swift
python tests/test_smoke.py      # end-to-end plan generation (needs API keys)
```

| Suite | What it guards |
|---|---|
| `test_units.py` (29) | Thumbnail keys, URL generation, path traversal, geocoding variants, app-token issue/verify |
| `test_ios_routes.py` (44) | Every URL the iOS app calls exists on the server, with the right method |
| `test_regression.py` (23) | Bugs that came back once already |
| `test_generation_status.py` (18) | Reload restore — the pending/done/gone decision, and what the page carries |
| `test_app_api.py` (16) | Authorization and JSON shape for the native-app endpoints |
| `test_send_message_survives_disconnect.py` (7) | A generation is not thrown away when the browser goes |
| `test_static_js.py` (2) | The JS and the template still fit together (names, element ids) |
| `tests/js/home_chat.html` (11 scenarios) | The chat screen, driven in headless Chromium |

The browser suite exists because this code breaks in ways a linter cannot see. An inline script once declared a name that `home.js` already held; that killed the entire script silently, and the seasonal-idea chips simply did nothing.

**CI** runs two jobs on every push and PR — Ubuntu (server tests, JS syntax, the browser suite, Swift type-check, template compile) and macOS (build the iOS app, run its unit and UI tests, list any warnings).

### Security

- No hardcoded secrets — everything through env vars / Secret Manager. `src/.env` is never committed.
- Refuses to start in production without `SECRET_KEY`. Cookies are HttpOnly / SameSite=Lax, Secure in production.
- OAuth requires `email_verified`. App ID tokens are rejected outright when no audience is configured, because an unset audience makes the library skip `aud` validation entirely.
- Every resource is ownership-checked by `user_id`. Plan HTML escapes user strings; local photo serving is guarded against path traversal.
- Rate limiting (chat 20 requests / 60 s, geocoding 40 / 60 s) and upload limits (≤50 files, extension whitelist, size cap).
- `X-Content-Type-Options` / `X-Frame-Options` / `Referrer-Policy` on every response. `ProxyFix` trusts Cloud Run's forwarded headers.
- **External key restrictions**, set on the provider side:
  - `STADIA_API_KEY` reaches the browser for tile requests — set a **domain restriction** in the Stadia dashboard.
  - `GOOGLE_MAPS_API_KEY` is server-side only (sent as `X-Goog-Api-Key`, so it never lands in URLs or logs). In GCP use **no application restriction or an IP one** — a referrer restriction would block server calls — and **restrict it to Places API (New)**.
  - `GOOGLE_API_KEY` (Gemini) and `TAVILY_API_KEY` never reach the frontend.

### Troubleshooting

| Symptom | Likely cause |
|---|---|
| Startup fails on missing config | Create `src/.env` and fill it in |
| Cannot reach MySQL | Check `DB_HOST`. Cloud SQL uses `CLOUD_SQL_INSTANCE`; TiDB needs `DB_SSL=true` |
| Generation times out (504) | `deploy.sh` sets `--timeout=3600`; a manual deploy needs the same |
| Photos load slowly | Signed URLs call IAM signBlob per photo. `storage.get_urls()` caches and parallelizes; lists use thumbnails. Backfill old ones with `scripts/backfill_thumbnails.py` |
| No pins on the map | With `GOOGLE_MAPS_API_KEY` you must enable **Places API (New)**. The startup log's `外部連携` line shows what is active |
| The iOS app cannot sign in | `GOOGLE_IOS_CLIENT_ID` is not reaching the server — add it to `src/.env` and to `deploy.sh` |

</details>

---

## License

Published so it can be read, not to be reused — see [LICENSE](LICENSE).
All rights reserved; please get in touch before using any part of it.

The libraries, map data and fonts it stands on keep their own licenses and
attribution, listed in [THIRD_PARTY_NOTICES.md](THIRD_PARTY_NOTICES.md).

---

<p align="center">
  <img src="https://raw.githubusercontent.com/sabatexima/tabimate/main/src/static/img/mate.png" alt="Chamu" width="90"><br>
  <sub><i>Whenever you feel like traveling again, just call Chamu. 🍀</i></sub>
</p>
