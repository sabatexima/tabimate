<p align="center">
  <img src="https://raw.githubusercontent.com/sabatexima/tabimate/main/src/static/img/mate-head.png" alt="Chamu" width="130">
</p>

<h1 align="center">TabiMate&nbsp;🍀</h1>

<p align="center">
  <b>Your travel plan? The AI writes it.</b><br>
  Come home, and your photos quietly become sticky notes.
</p>

<p align="center">
  <i>A gentle, picture-book-styled travel companion.</i>
</p>

<p align="center">
  <a href="README_jp.md">🇯🇵&nbsp;日本語</a>&nbsp;&nbsp;·&nbsp;&nbsp;
  <a href="https://github.com/sabatexima/tabimate/actions/workflows/ci.yml"><img src="https://github.com/sabatexima/tabimate/actions/workflows/ci.yml/badge.svg" alt="CI"></a>
</p>

<p align="center">
  <img src="https://raw.githubusercontent.com/sabatexima/tabimate/main/docs/img/screen-journal-en.png" alt="Trip journal" width="240">
  <img src="https://raw.githubusercontent.com/sabatexima/tabimate/main/docs/img/screen-bookshelf-en.png" alt="Saved plans" width="240">
  <img src="https://raw.githubusercontent.com/sabatexima/tabimate/main/docs/img/screen-plan-detail-en.png" alt="Plan detail" width="240">
</p>

<p align="center"><sub>The app UI is Japanese; screenshots are English-localized mockups of the same screens.</sub></p>

---

## 🍀 What is TabiMate?

> _From "where should we go?" to "that was fun."<br>
> Chamu is there for every part of the trip._

There are plenty of travel apps &mdash; but TabiMate cares about the **before** and **after** of a trip.

Plan by simply chatting with the AI. Come home and just drop in your photos.
The rest is handled by **Chamu**, the mascot, who binds your itinerary, turns memories into sticky notes, and quietly frames your best shots.

<table>
<tr>
<td width="33%" align="center"><br>🗺️<br><b>Before</b><br><sub>Chat, and your<br>itinerary appears</sub><br><br></td>
<td width="33%" align="center"><br>📸<br><b>After</b><br><sub>Photos become<br>sticky-note memories</sub><br><br></td>
<td width="33%" align="center"><br>🤝<br><b>Together</b><br><sub>Share plans and<br>memories, gently</sub><br><br></td>
</tr>
</table>

---

## ✨ Features

### 🗺️ Before &mdash; just chat, and the itinerary appears

> _Chamu: "Where to? How many nights? …Got it, leave it to me."_

- 💬 **Plan by conversation** &mdash; destination, days, budget and more are read from natural chat; missing pieces are asked one at a time. Once everything's set, a team of AI agents (LangGraph) builds the plan together.
- 🌤️ **Weather-aware** &mdash; reads the forecast for your travel dates: more indoor spots on rainy days, warmer picks when it's cold. It even avoids shops likely closed that weekday.
- 🍽️ **Real places only** &mdash; candidates are verified against Google Places, so "plausible-sounding but invented" shops get dropped.
- 🗾 **Watercolor map** &mdash; sights / food / stays as color-coded pins, connected **in visiting order**. Tap a pin for turn-by-turn navigation.
- 🎒 **Packing list** &mdash; Chamu suggests what to bring from your destination and weather. Check an item and a clover blooms.
- 🍀 **Departure countdown** &mdash; "12 days to go." A little thrill every time you open the shelf.
- 📅 **Calendar export** &mdash; export the schedule as `.ics`, straight into Google Calendar and friends.
- ✏️ **Tweak later** &mdash; "make Day 2 relaxed," "change the hotel" &mdash; all by chat. Rate a plan with ★ and future suggestions quietly adapt.

### 📸 After &mdash; photos turn into words on their own

> _Chamu: "Welcome back. Show me the photos… what a trip."_

- 🏷️ **Sticky notes from photos** &mdash; the AI reads your uploads and captures the mood in short "sticky note" phrases.
- 📖 **Travel journal** &mdash; polaroids and pastel sticky notes on craft paper. Search and favorite to look back.
- 🏅 **Chamu's best shots** &mdash; picks the "one to frame" from many photos, set in a golden frame.
- 💰 **Trip ledger** &mdash; record estimate vs. what you actually spent. Under budget? "◯ yen saved 🍀."
- 🐾 **Footprints map** &mdash; plots your path from photo GPS. Overlay the plan to compare "planned vs. actual."
- 📔 **Yearly digest** &mdash; "Your year in travel," recapping the year's trips and sticky notes at a glance.

### 🤝 Share

- 🔗 **Public link** for login-free sharing (view-only).
- ✉️ **Email grants** to allow a specific person to view or edit.
- 📱 **PWA** &mdash; add to your home screen and launch it as an app from Chamu's icon.

---

## 🛠️ Built with

|  |  |
|---|---|
| 🧠 **AI** | LangGraph · LangChain · Gemini 3.5 Flash / 3.1 Flash-Lite · Tavily Search |
| ⚙️ **Backend** | Flask 3.1 · SQLAlchemy · MySQL 8.0 / TiDB · gunicorn |
| 🗺️ **Maps & Geo** | Leaflet · Stadia Maps (watercolor) · Google Places · OSM Nominatim · GSI |
| ☁️ **Infra** | Google Cloud Run · Docker · Cloud Storage · Secret Manager · Google OAuth 2.0 · GitHub Actions |
| 🎨 **Frontend** | Jinja2 · Vanilla JS · PWA · Zen Maru Gothic |

---

## 🚀 Run it

```bash
# 1. Clone
git clone <repo-url> && cd tabimate

# 2. Prepare env vars (at least: API keys, OAuth, DB)
cp src/.env.example src/.env   # → fill it in

# 3. Install & run
cd src
python3 -m venv .venv && source .venv/bin/activate
pip install -r ../requirements.txt
python3 app.py
```

Open **http://localhost:5007**. Tables are created on first access (`CREATE TABLE IF NOT EXISTS`).

> 🍀 **One command to production** &mdash; `./deploy.sh` handles the whole Cloud Run deploy (Secrets, GCS bucket, IAM roles included).

---

<details>
<summary><b>📖 Deep dive (developer docs)</b></summary>

<br>

### Environment variables

Set in `src/.env` (local) or Cloud Run env / Secret Manager. `src/.env` is Git-ignored.

| Variable | Required | Purpose |
|------|------|------|
| `SECRET_KEY` | prod | Flask session signing key |
| `GOOGLE_API_KEY` | ✓ | Gemini API key |
| `TAVILY_API_KEY` | ✓ | Tavily web search |
| `GOOGLE_CLIENT_ID` / `GOOGLE_CLIENT_SECRET` | ✓ | Google OAuth |
| `DB_USER` / `DB_PASS` / `DB_NAME` / `DB_HOST` / `DB_PORT` | ✓ | Database connection |
| `STADIA_API_KEY` | | Watercolor map tiles (falls back to standard OSM tiles) |
| `GOOGLE_MAPS_API_KEY` | | Google Places-powered geocoding. Unset = free stack (Nominatim + GSI) only |
| `DB_SSL` / `DB_SSL_CA` | cond. | TLS connection (`DB_SSL=true` required for TiDB Cloud) |
| `CLOUD_SQL_INSTANCE` | cond. | Connect via Cloud SQL Connector when set |
| `GCS_BUCKET` | cond. | Uses GCS when set, else local FS |
| `LOCAL_UPLOAD_DIR` / `SIGNED_URL_TTL_SECONDS` / `GCS_SIGNER_SA` | | Local dir · signed-URL TTL · signer SA |
| `REDIS_URL` | | Share in-flight generation state via Redis |
| `STICKER_MAX_IMAGES` / `INTERPRETER_IMAGE_MAX_EDGE` etc. | | Sticker-generation image count/resize |

### Directory layout

```
tabimate/
├── deploy.sh                 # Cloud Run deploy (Secret/GCS/IAM)
├── .github/workflows/ci.yml  # CI on push/PR
├── scripts/                  # backfill_thumbnails.py / setup_alerts.sh
├── tests/                    # test_smoke.py (E2E) / test_units.py (offline)
└── src/
    ├── app.py                # Flask app · Blueprint registration
    ├── db.py                 # DAO for travel_plans / chat_messages
    ├── db_reflection.py      # DAO for trips / photos / stickers
    ├── db_sharing.py         # DAO for share links / email grants
    ├── geocoding.py          # spot name → lat/lng (multi-provider, lazy cache)
    ├── weather.py            # travel-date forecast (Open-Meteo)
    ├── chat/                 # plan generation (LangGraph / agents)
    │   └── chat.py graph.py agents.py models.py llm.py formatter.py logger.py
    ├── services/             # exif · features · storage · trip_interpreter · packing
    ├── views/                # planner · auth · reflection · sharing (Blueprints)
    ├── templates/            # Jinja2 (layout / home / welcome / reflection / shared …)
    └── static/               # css / js / img
```

### Architecture

```
         ┌──────────── Flask app (app.py) ────────────┐
         │  ProxyFix + 4 Blueprints                    │
 Browser ┤  planner("/")  auth("/auth")               │
         │  reflection("/reflection")  sharing("/share")│
         └──────┬───────────────┬──────────┬──────────┘
                │               │          │
        chat/ (LangGraph)   db.py /     services/
        multi-agent flow    db_reflection  exif·features·
                │           (SQLAlchemy)  storage·interpreter
                ▼               │
        Gemini + Tavily         ▼
                          MySQL / TiDB
```

- **Shared DB engine**: `get_engine()` (QueuePool) in `db.py` is reused by `db_reflection` / `db_sharing`. Tables are lazily created with `CREATE TABLE IF NOT EXISTS`.
- **Storage abstraction**: `services/storage.py` switches between GCS and local FS (by `GCS_BUCKET`). GCS signed URLs use caching + parallel generation.
- **Two sharing methods**: public links (tokens) and email grants, managed in `views/sharing.py` with owner/edit/view control.

### Plan-generation agents (LangGraph)

`chat/graph.py` defines a `StateGraph` chaining functions from `chat/agents.py` as nodes. State flows as `TravelPlanState` (TypedDict).

```
START
  → transport (round-trip cost · remaining budget)
  → sightseeing_candidates → sightseeing (2–3 spots)
  → accommodation_candidates → accommodation (~40% of remaining · skipped for day trips)
  → gourmet_candidates → gourmet (~25% of remaining)
  → timekeeper (chronological schedule)
  → cost_manager (budget breakdown)
  → balancer (whole-plan review)
        └─ approved / budget_infeasible → END
           fix_* → route back to the relevant node (cap: MAX_BALANCER_RETRIES=5)
```

- **Lodging-free check**: `parse_duration()` parses the duration into (nights, days); nights = 0 skips lodging nodes (covers overnight-transit "0泊2日").
- **Existence check**: with `GOOGLE_MAPS_API_KEY`, sightseeing/food/lodging candidates are verified via Google Places and invented names are dropped.
- **Preference learning**: `user_preferences` is built from past ★ ratings/comments and softly injected into agents.
- **Partial editing**: only targeted nodes are regenerated from an edit request (others kept).
- **Retries**: `invoke_with_retry()` retries 429/503 and network errors up to 5× with backoff.

### Database

| Table | Purpose |
|----------|------|
| `travel_plans` | Saved plans (conditions/results as JSON). Also holds map-coord cache, custom pins, packing list, actual cost, ★ rating |
| `chat_messages` | Chat history; plan rows also store `plan_json` (the "previous plan" for edits) |
| `trips` | Trips (title, dates). Holds cover photo, best shots, linked plan |
| `photos` / `stickers` | Photos (path, shoot time, GPS) / sticky notes (display text + internal basis) |
| `share_links` / `share_grants` | Public links / email-based sharing |

- Ownership is always checked against `user_id` (Google `sub`). Deleting a trip cascades to related rows and physical photos.

### Key HTTP endpoints

**planner (`/`)** &mdash; `/` (chat) · `/saved_plans` · `/plan/<id>` · `/send_message` (SSE) · `/save_plan` · `/edit_saved_plan/<id>` · `/rate_plan/<id>` · `/save_actual_total/<id>` · `/api/packing_list/<id>` · `/api/plan_geo/<id>` · `/api/plan_weather/<id>` · `/export_plan_ics/<id>`

**reflection (`/reflection`)** &mdash; `/trips` · `/trips/<id>` · `/trips/<id>/photos` · `/trips/<id>/stickers/generate` · `/trips/<id>/best_shots` · `/trips/<id>/linked-plan`

**sharing (`/share`, `/shared`, `/s/<token>`)** &mdash; create/delete links · grant/revoke email shares · public view · photo & sticker ops on shared trips

**auth (`/auth`)** &mdash; `/login` · `/callback` · `/logout`

`reflection`, `sharing`, and plan-saving routes are protected by `@login_required`.

### Tests & CI

```bash
pytest tests/                # full suite
python tests/test_smoke.py   # E2E plan generation (needs API keys)
```

- `test_units.py` runs **offline (no API keys/DB)** — thumbnail-key derivation, URL generation, path-traversal, geocoding name-variant/candidate selection.
- **GitHub Actions** runs offline tests, a JS syntax check, and a template compile check on every push / PR.

### Security

- No hardcoded secrets — all via env / Secret Manager (`src/.env` never committed).
- Fails to start in prod if `SECRET_KEY` is unset. Cookies are HttpOnly / SameSite=Lax (Secure in prod).
- OAuth requires `email_verified`. Every resource is ownership-checked by `user_id`.
- Plan HTML escapes user strings (XSS); local photo serving is path-traversal-guarded.
- Rate limiting (chat 5/60s, external-API routes separate), upload limits (≤50 files, extension whitelist, size cap).
- `X-Content-Type-Options` / `X-Frame-Options` / `Referrer-Policy` on all responses. `ProxyFix` trusts Cloud Run forwarded headers.

### Troubleshooting

- **No `.env`** → create `src/.env` and fill in the variables.
- **Can't connect to MySQL** → check `DB_HOST`. Cloud SQL uses `CLOUD_SQL_INSTANCE`; TiDB needs `DB_SSL=true`.
- **Generation times out (504)** → `deploy.sh` sets `--timeout=3600`. For manual deploys: `gcloud run services update ... --timeout=3600`.
- **Slow photos** → signed URLs call IAM signBlob per photo. `storage.get_urls()` caches + parallelizes; lists serve thumbnails. Backfill old photos with `scripts/backfill_thumbnails.py`.
- **No pins on the map** → with `GOOGLE_MAPS_API_KEY`, you must enable **Places API (New)**. The startup log's "外部連携" line shows enabled/disabled.

</details>

---

<p align="center">
  <img src="https://raw.githubusercontent.com/sabatexima/tabimate/main/src/static/img/mate.png" alt="Chamu" width="90"><br>
  <sub><i>Whenever you feel like traveling again, just call Chamu. 🍀</i></sub>
</p>
