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
  <img src="https://img.shields.io/badge/Code-MIT-4fa83a" alt="Code: MIT">
  <img src="https://img.shields.io/badge/Artwork-CC%20BY--NC%204.0-f08ba0" alt="Artwork: CC BY-NC 4.0">
</p>

<p align="center">
  <img src="https://raw.githubusercontent.com/sabatexima/tabimate/main/docs/img/readme-screens-en.png" alt="Trip journal, saved plans, plan detail" width="760">
</p>

<p align="center"><sub>The app UI is Japanese; screenshots are English-localized mockups of the same screens.</sub></p>

---

## What is TabiMate?

**A web app that hands the two hardest parts of a trip — planning it, and remembering it — to an AI and a mascot named Chamu.**

- 🗺️ **Just talk** — say "Kanazawa, two nights, two of us" and you get a full itinerary: sights, restaurants, a place to stay, a timetable and a cost estimate
- 📸 **Just drop in photos** — when you're back, the AI reads them and pins short sticky-note memories into an album
- 🤝 **Share with one link** — plans and memories alike, with family or friends

Plenty of apps help you book. TabiMate cares about the **before** and the **after** — the parts booking sites leave to you — inside a soft, picture-book interface. It installs as a PWA on your phone, and there is a native SwiftUI app for iOS.

> _From "where should we go?" to "that was fun."_<br>
> _Chamu is there for every part of the trip._

<p align="center">
  <img src="https://raw.githubusercontent.com/sabatexima/tabimate/main/docs/presentation/img/02-journey.png" alt="chat → itinerary → trip → look back" width="760"><br>
  <sub>Four steps: chat, get the itinerary, travel, look back when you're home. (Figure text is Japanese.)</sub>
</p>

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

<p align="center">
  <img src="https://raw.githubusercontent.com/sabatexima/tabimate/main/docs/img/readme-chat-en.png" alt="Just talk → the itinerary appears" width="760"><br>
  <sub>The real screen. "Kanazawa, two nights, two of us" — Chamu asks only about the budget, then the itinerary arrives.</sub>
</p>

| | |
|---|---|
| 💬 **Plan by conversation** | Destination, days and budget are read from natural chat; missing pieces are asked one at a time. Then a team of AI agents (LangGraph) builds the plan together. |
| 🌤️ **Weather-aware** | Reads the forecast for your dates — more indoor spots on rainy days, warmer picks when it's cold, and shops likely closed that weekday are skipped. |
| 🍽️ **Real places only** | Candidates are verified against Google Places, so plausible-sounding but invented shops get dropped. |
| 🗾 **Watercolor map** | Sights / food / stays as color-coded pins, connected **in visiting order**. Multi-day trips can be viewed **one day at a time**. Tap a pin for navigation. |
| 🌏 **Overseas too** | Say "Paris, 3 nights" and the plan comes with flights, local time and yen-converted costs; place names carry their local spelling so the map can find them. |
| 🎒 **Packing list** | Suggested from your destination and the weather. Check an item and a clover blooms. |
| 🍀 **Countdown** | "12 days to go." A little thrill every time you open the shelf. |
| 📅 **Calendar export** | Download the schedule as `.ics`; the itinerary also prints to PDF. |
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

## How it works

A plan is not written by one model in one go. **Ten agents with separate jobs** take turns on it, and a final reviewer sends the plan back — only to the node that caused the problem — when it isn't satisfied.

<p align="center">
  <img src="https://raw.githubusercontent.com/sabatexima/tabimate/main/docs/presentation/img/03-agents.png" alt="ten agents" width="760"><br>
  <sub>Transport and sightseeing candidates run first, in parallel. Then sights → stay → food → timetable → costs, and a reviewer decides.</sub>
</p>

The server is a single Flask app on Cloud Run. The browser and the iOS app talk to the same server, the same account and the same plans.

<p align="center">
  <img src="https://raw.githubusercontent.com/sabatexima/tabimate/main/docs/presentation/img/04-architecture.png" alt="architecture" width="760"><br>
  <sub>Clients (browser, iOS) → one Flask app on Cloud Run → the services it leans on (Gemini, search, maps, DB, storage).</sub>
</p>

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
| 🗺️ **Maps & Geo** | Leaflet · Stadia Maps (watercolor) · Google Places · OSM Nominatim · GSI (domestic only) |
| ☁️ **Infra** | Cloud Run · Docker · Cloud Storage · Secret Manager · Google OAuth 2.0 · GitHub Actions |
| 🎨 **Frontend** | Jinja2 · vanilla JS · PWA · Zen Maru Gothic · OpenMoji |
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

The container and CI both run Python 3.13. Locally 3.11 is also known to work — no dependency asks for more than 3.10.

`deploy.sh` runs `gcloud run deploy --source .`, so Cloud Build picks up the
`Dockerfile` in the repository root. The file has to be named exactly that —
it was `dockerfile` for a while, and a lowercase name is not what Cloud Build
looks for, which quietly falls back to Buildpacks instead. If you change how
the image is built, check the build log says `FROM python:3.13-slim`.

### Changing dependencies

`requirements.txt` is generated, not edited. Add or bump what you need in
`requirements.in`, then resolve it in a clean environment on the same Python
the container uses:

```bash
python3.13 -m venv /tmp/resolve && /tmp/resolve/bin/pip install -r requirements.in
/tmp/resolve/bin/pip freeze | sort -f > /tmp/pins && cat /tmp/pins   # → requirements.txt
```

Then regenerate the dependency table in `THIRD_PARTY_NOTICES.md` — the script
for it is in that file.

---

<details>
<summary><b>📖 Deep dive — developer docs</b></summary>

<br>

### Design

Three layers. **Upper layers call lower ones; lower layers know nothing about the ones above.**

```
  views/        The entrance. HTTP only (authorization, input shaping, responses). No SQL here
    │
    ├── chat/       AI (the LangGraph agents, prompts, model calls)
    ├── services/   Logic (photos, EXIF, storage, weather, geocoding, packing, sticky notes)
    │
  db*.py        Persistence (SQLAlchemy Core, plain SQL). Knows nothing about Flask
```

| Rule | What it means |
|---|---|
| **One Blueprint per feature** | `planner` (chat and plans) · `auth` · `reflection` (trip journal) · `sharing`. URL prefixes and permission boundaries line up |
| **Persistence split by table owner** | `db.py` (plans, chat) · `db_reflection.py` (trips, photos, stickers) · `db_sharing.py` (sharing). All share the single engine from `db.get_engine()` |
| **External services are swappable** | Storage is GCS or the local filesystem depending on `GCS_BUCKET` (`services/storage.py`). Geocoding falls through Google Places → Nominatim → GSI (`services/geocoding.py`; the country to search comes from the destination, and GSI is Japan-only). AI, search and the DB are stubbed wholesale in tests |
| **One session, two doors** | The browser uses a session cookie; the app sends `Authorization: Bearer …`, which `api_auth.py` translates into the same session for that single request, so `login_required` needs no special case |
| **Cross-cutting code sits at `src/`** | `logger.py` (the one logger factory) · `api_auth.py` (tokens) |
| **Frontend has no build step** | One CSS and one JS file per page. Color/radius/shadow tokens and shared parts (page headings, back links, share banner) live in `layout.css`; parts used by more than one page live once, in `trip-detail.css` / `plan-card.css` |
| **Tests never leave the machine** | AI, DB, storage and weather are stubbed; everything runs without API keys. The chat screen is additionally driven in a real Chromium |
| **iOS is organized by feature** | `Features/` (a View and ViewModel per screen) · `Networking/` (APIClient, services, models) · `Design/` (theme, components). UI tests stub the network with `URLProtocol` |

Good next steps, if you keep going:

- `views/planner.py` (~970 lines) holds chat, plans and the plan APIs together; splitting it into `chat` / `plans` / `plan_api` would help
- `chat/formatter.py` renders the plan to HTML — presentation work sitting in the AI layer. Cleaner for `chat/` to return state and `views/` to format it
- `db.py` / `db_reflection.py` / `db_sharing.py` could become a `db/` package

### Layout

```
tabimate/
├── LICENSE                      # code: MIT
├── LICENSE-ARTWORK              # Chamu and images: CC BY-NC 4.0
├── THIRD_PARTY_NOTICES.md       # dependency licenses and map attribution
├── requirements.in              # direct dependencies (edit this one)
├── requirements.txt             # the resolved, pinned result (generated)
├── deploy.sh                    # Cloud Run deploy (Secrets / GCS / IAM)
├── Dockerfile                   # python:3.13-slim · gunicorn, 1 worker × 20 threads
├── .github/workflows/ci.yml     # two jobs: ubuntu (server + logic) / macOS (iOS)
├── docs/
│   ├── img/                     # screenshots for the README
│   └── presentation/            # slide figures and the AI brief (PROMPT.md)
├── scripts/
│   ├── check_home_js.sh         # drives the chat UI in a real browser
│   ├── check_ios_logic.sh       # type-checks the iOS logic on Linux Swift
│   ├── backfill_thumbnails.py
│   └── setup_alerts.sh
├── tests/                       # see "Tests & CI"
├── ios/                         # SwiftUI app (XcodeGen; see ios/README.md)
└── src/
    ├── app.py                   # Flask app · Blueprint registration · security headers · template filters
    ├── api_auth.py              # Bearer tokens for the native app
    ├── logger.py                # the one logger factory
    ├── db.py                    # travel_plans / chat_messages
    ├── db_reflection.py         # trips / photos / stickers
    ├── db_sharing.py            # share links / email grants
    ├── views/                   # planner · auth · reflection · sharing (Blueprints)
    ├── chat/                    # plan generation: agents · graph · chat · llm · models · formatter
    ├── services/                # exif · features · images · storage · packing
    │                            #   · trip_interpreter (sticky notes) · weather · geocoding
    ├── templates/               # Jinja2 (extends layout.html; partial: _share_modal.html)
    └── static/
        ├── css/                 # layout.css (tokens, shared parts) + one per page
        │                        #   shared parts: trip-detail.css · plan-card.css · plan-map.css · share-modal.css
        ├── js/                  # one per page + layout.js · openmoji.js · plan-map.js · footprint-map.js
        └── img/                 # Chamu · PWA icons
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
               │               │         interpreter · weather
               ▼               ▼              ▼
      Gemini + Tavily     MySQL / TiDB    GCS · Open-Meteo · Places
```

### Plan-generation agents

`chat/graph.py` defines a `StateGraph` chaining functions from `chat/agents.py`, with `TravelPlanState` (a TypedDict) flowing between them.

```
(before generating) look up the destination's country and centre once — overseas adds instructions to every agent
(in parallel, ahead of the graph) transport · sightseeing_candidates · weather
START
  → sightseeing               2–3 spots
  → accommodation_candidates → accommodation   ~40% of remaining (skipped for day trips)
  → gourmet_candidates → gourmet               ~25% of remaining
  → timekeeper                 chronological schedule
  → cost_manager               budget breakdown
  → balancer                   whole-plan review
        ├─ approved / budget_infeasible → END
        └─ fix_* → back to the relevant node   (cap: MAX_BALANCER_RETRIES = 5)
             1st re-picks (cheap); repeated verdict or 3rd rejection refetches candidates (costly)
```

- **Lodging-free check** — `parse_duration()` yields (nights, days); zero nights skips the lodging nodes, which covers overnight-transit trips.
- **Existence check** — with `GOOGLE_MAPS_API_KEY`, candidates are verified against Google Places and invented names are dropped.
- **Overseas destinations** — the country is resolved before generation; abroad, every agent gains instructions: costs converted to yen with the rate stated, flights for the round trip, local time with the offset and border-crossing waits, insurance and connectivity in the budget, a passport in the packing list. Place names are written as "Japanese name (local name)", and the map searches on that local name.
- **Preference learning** — past ★ ratings and comments become `user_preferences`, softly injected into the agents.
- **Day-by-day map** — the `N日目` headings in the schedule decide which day each pin belongs to, so multi-day trips can be filtered one day at a time (a hotel belongs to both surrounding days). If fewer than half the pins could be dated, the filter is withheld — picking a day would make pins vanish and look broken.
- **Partial editing** — an edit request regenerates only the nodes it touches.
- **Escalating retries** — the first rejection re-picks from the same candidate pool (cheap). On a repeated verdict, or from the third rejection onwards, the graph returns to candidate gathering and changes the lineup (costly: search + LLM). The retry-count trigger matters: with verdicts alternating between areas, the repeat trigger never fires and the pool would go untouched to the cap. Candidate agents receive the review notes and the rejected lineup — without them, temperature 0 just rebuilds the identical list. The search queries stay the same, so a refreshed pool is drawn from the same evidence plus the exclusion.
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

The plan card shown in the chat goes through `marked.parse()` in the browser. Markdown ends an HTML block at a blank line, so `chat/formatter.py` returns HTML **with no blank lines** (otherwise a literal `<details>` shows up on screen).

### Database

| Table | Purpose |
|---|---|
| `travel_plans` | Saved plans (conditions and results as JSON) plus stated preferences (transport, whether they drive, timing), coordinate cache, custom pins, packing list, actual cost, ★ rating |
| `chat_messages` | Chat history; plan rows also carry `plan_json` (the "previous plan" used when editing) |
| `trips` | Trips (title, dates), cover photo, best shots, linked plan |
| `photos` / `stickers` | Photos (path, shoot time, GPS) / sticky notes (display text + internal basis) |
| `share_links` / `share_grants` | Public links / email-based sharing |

Ownership is always checked against `user_id` (the Google `sub`). Deleting a trip cascades to its rows and its physical photos.

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
| `MAX_CONTENT_LENGTH_MB` | | Upload size cap per request (default 100) |
| `SEARCH_SNIPPET_CHARS` / `SEARCH_QUERY_CHARS` | | How much of each web-search result is kept, and the cap per query (600 / 2400) — trims what reaches the model |
| `INTERPRETER_MODEL` | | Model used for sticky notes and best-shot picking (default `gemini-3.1-flash-lite`) |
| `STICKER_MAX_IMAGES` / `INTERPRETER_IMAGE_MAX_EDGE` | | Photos sent for sticky notes (6) and the longest edge each is resized to before sending (512 px) — the cost dial for that call |
| `INTERPRETER_MAX_IMAGES` | | Fallback cap (4) for callers that don't set their own. Both current callers do — sticky notes use `STICKER_MAX_IMAGES`, best-shot picking sends every sampled photo (up to 12) — so changing this alone does nothing today |
| `INTERPRETER_PRICE_INPUT_PER_M` / `INTERPRETER_PRICE_OUTPUT_PER_M` | | Prices per million tokens used only to log an estimated cost (0.25 / 1.50) |

`K_SERVICE` is set by Cloud Run itself and is read to detect production (secure
cookies, refusing to start without `SECRET_KEY`). Do not set it by hand.

### HTTP endpoints

**Pages** — `/` (welcome) · `/chat` · `/saved_plans` · `/plan/<id>` · `/plan/<id>/print` · `/reflection/` · `/reflection/digest` · `/reflection/trips/<id>` · `/shared` · `/s/<token>` · `/terms` · `/privacy`

**Chat** — `/send_message` (SSE) · `/get_messages` · `/reset_chat` · `/abort_request` · `/generation_status`

**Plans** — `/save_plan` · `/get_my_plans` · `/get_shared_plans` · `/edit_saved_plan/<id>` · `/apply_saved_plan/<id>` · `/delete_plan/<id>` · `/rate_plan/<id>` · `/save_actual_total/<id>` · `/save_plan_pins/<id>` · `/export_plan_ics/<id>` · `/api/packing_list/<id>` · `/api/plan_geo/<id>` · `/api/plan_weather/<id>` · `/api/geocode`

**Memories** — `/reflection/trips` (POST) · `/reflection/trips/<id>` (GET / PATCH / DELETE) · `…/photos` · `…/stickers` · `…/stickers/generate` · `…/best_shots` · `…/favorite` · `…/linked-plan` · `/reflection/photo/<path>`

**Sharing** — `/share/<type>/<id>` (state) · `…/link` · `…/grant` · `/share/link/<id>` · `/share/grant/<id>` · `/shared/<type>/<id>` · `/shared/trip/<id>/…` (photo & sticker operations for editors) · `/shared/plan/<id>/ics`

**For the native app** — `/auth/app/signin` · `/auth/app/me` · `/api/ideas` · `/api/chat_messages` · `/reflection/api/trips` · `/reflection/api/trips/<id>` · `/reflection/api/digest`

**Auth** — `/auth/login` · `/auth/callback` · `/auth/logout`

Everything except `/`, `/terms`, `/privacy`, `/api/ideas`, `/auth/*` and the public `/s/<token>` view sits behind `@login_required`, which answers `401 JSON` to API clients and redirects browsers to the login page. 67 routes in total.

### Tests & CI

```bash
pytest tests/ -k "not smoke"    # 185 offline tests — no API keys, no DB
scripts/check_home_js.sh        # drives the chat UI in a real browser
scripts/check_ios_logic.sh      # type-checks the iOS logic on Linux Swift
python tests/test_smoke.py      # end-to-end plan generation (needs API keys)
```

| Suite | What it guards |
|---|---|
| `test_units.py` (38) | Thumbnail keys, URL generation, path traversal, geocoding variants, destination-country resolution, app-token issue/verify |
| `test_ios_routes.py` (44) | Every URL the iOS app calls exists on the server, with the right method |
| `test_regression.py` (56) | Bugs that came back once already — every template `url_for` resolves, plan cards contain no blank lines, public-link trips wrap every photo, "I don't drive" survives a save-and-edit round trip, … |
| `test_generation_status.py` (18) | Reload restore — the pending/done/gone decision, and what the page carries |
| `test_app_api.py` (16) | Authorization and JSON shape for the native-app endpoints |
| `test_send_message_survives_disconnect.py` (7) | A generation is not thrown away when the browser goes |
| `test_static_js.py` (6) | The JS and the template still fit together (names, element ids), and which day the map assigns each pin to |
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

**Code: MIT** — see [LICENSE](LICENSE). Use it, change it, redistribute it,
sell it; the only condition is keeping the copyright notice.

**Chamu and the images: CC BY-NC 4.0** — see [LICENSE-ARTWORK](LICENSE-ARTWORK).
Free to use with credit for non-commercial purposes; commercial use of the
artwork needs separate permission. If you run this commercially, swap the
images for your own — the code does not depend on them.

The libraries, map data and fonts it stands on keep their own licenses and
attribution, listed in [THIRD_PARTY_NOTICES.md](THIRD_PARTY_NOTICES.md).

---

<p align="center">
  <img src="https://raw.githubusercontent.com/sabatexima/tabimate/main/src/static/img/mate.png" alt="Chamu" width="90"><br>
  <sub><i>Whenever you feel like traveling again, just call Chamu. 🍀</i></sub>
</p>
