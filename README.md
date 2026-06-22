<p align="center">
  <img src="src/static/img/mate-head.png" alt="Chamu — TabiMate mascot" width="120">
</p>

<h1 align="center">TabiMate 🍀</h1>

<p align="center">
  A gentle, picture-book-styled AI travel companion that stays with you <em>before</em> and <em>after</em> your trip.<br>
  Plan creation, trip reflection (sticky notes), and sharing in a single Flask app.
</p>

<p align="center"><a href="README_jp.md">日本語版</a></p>

## Tech Stack

![Flask](https://img.shields.io/badge/Flask-3.1-000000.svg?logo=flask&logoColor=white)
![LangChain](https://img.shields.io/badge/LangChain-1.3-1DA1F2.svg?logo=langchain)
![LangGraph](https://img.shields.io/badge/LangGraph-1.2-1DA1F2.svg?logo=langgraph&logoColor=white)
![Google%20Gemini](https://img.shields.io/badge/Gemini-3.5_Flash_%2F_3.1_Flash--Lite-4285F4.svg?logo=google%20gemini&logoColor=white)
![Tavily](https://img.shields.io/badge/Tavily-Search-F97316.svg?logo=tavily&logoColor=white)
![MySQL](https://img.shields.io/badge/MySQL-8.0-4479A1.svg?logo=mysql&logoColor=white)
![Google%20Cloud%20Run](https://img.shields.io/badge/Cloud_Run-Cloud-4285F4.svg?logo=google%20cloud&logoColor=white)
![Docker](https://img.shields.io/badge/Docker-Build-2496ED.svg?logo=docker&logoColor=white)
![Google%20OAuth](https://img.shields.io/badge/Google_OAuth-2.0-4285F4.svg?logo=google&logoColor=white)

## Key Features

### 1. Travel Plan Creation Chat (Main Feature)
- Structured extraction of travel conditions (7 required items) from natural conversations, asking clarifying questions one by one for missing items.
- A multi-agent system powered by LangGraph workflows generates plans once all conditions are met.
- Users can specify preferred transportation (Shinkansen, flight, car, highway bus, or "leave it to AI"). Estimation methods and schedule compilation adapt to the chosen transportation (defaults to "leave it to AI" for optimal selection).
- A "no driver's license / public transport only" preference is detected from the conversation; when set, cars/rental cars are avoided and only public-transport-accessible spots and routes are used.
- **Time preferences** (e.g., "I want to be home by evening", "take it easy in the morning") are detected from the conversation and applied to the schedule with top priority.
- **Day trips make full use of the day**: the number of spots scales with the trip length, and the schedule is built by working *backward from a reasonable return-home time* (departure time = home time − return travel time) instead of ending in the early afternoon.
- A Balancer (reviewer) detects budget overruns, schedule conflicts, theme mismatches, etc., and automatically rejects & triggers regeneration (with a capped number of retries).
- **Hybrid models**: a fast, low-cost model (`gemini-3.1-flash-lite`) for most steps, and a stronger model (`gemini-3.5-flash`) for cost estimation and review. A numeric budget guard prevents over-budget plans (and clearly reports when a budget is structurally infeasible). Per-generation token usage and estimated cost are logged.
- SSE (Server-Sent Events) streaming for responses. Sends "thinking" indicators during generation, allowing users to cancel mid-way. Notifies users of errors or disconnections in the chat to prevent silent hanging.
- Generated plans can be saved, viewed, and deleted from the saved plans list.
- Post-generation adjustments are supported via chat (e.g., "make Day 2 more relaxing", "reduce the budget", "change the accommodation"). Supports **partial editing**, which regenerates only specified areas while keeping the rest unchanged.
- **Saved plans can also be edited via chat** directly on the card. The result is shown as a preview first and is only persisted when the user confirms ("update").
- **Rating-based personalization**: users can rate a saved plan with ★1–5 plus a short comment (one rating per plan; locked once submitted). Highly-rated (★4+) and poorly-rated (★2−) plans and their comments are summarized into a preference hint that is softly applied to future plan generation (explicit requests still take priority; disliked tendencies are avoided).
- Tavily Web search reinforces real-time accuracy and information freshness.

### 2. Trip Reflection (Sticky Notes)
- Create trips and upload multiple photos (saved to GCS or local storage). HEIC/HEIF photos are converted to JPEG on upload, and lightweight thumbnails are generated (lists show thumbnails; the lightbox shows the original).
- Extract shoot time and GPS coordinates from photo EXIF metadata, summarizing them into features (time-of-day bias, travel distance, activity range, etc.) on the backend.
- Feed summarized features and representative photos to Gemini to generate 3 to 6 virtual sticky notes. Notes are re-pinned upon regeneration.
- SNS-style feed on the home page. Each trip card features a large thumbnail and sticky note badges.
- In trip details, tap photos to open in a lightbox. Supports navigation (prev/next buttons, arrow keys, and swipe gestures).
- Trip titles can be edited later. Deleting a trip or photo cleans up the underlying storage to prevent orphaned files.

### 3. Sharing
- Public Link: Accessible via a tokenized URL (`/s/<token>`) without requiring login.
- Email Grants: Access restricted to logged-in users with authorized emails (`/shared/...`).
- Permissions can be set to `view` (read-only) or `edit` (can modify). For trips, `edit` allows adding photos and generating sticky notes. For plans, an `edit` email grant lets the recipient co-edit the plan via chat (changes overwrite the owner's plan). Public links remain view-only for safety.
- The owner always retains full permissions, and can revoke links or delete grants.
- Recipients of a shared item can remove it from their shared list (the owner's original data remains intact, and it will reappear if shared again).
- Shared trips and plans are integrated into the recipient's "Shared List", album, and saved plans views.

---

## Environment Variables

Configured in `src/.env` (local) or via Cloud Run environment variables / Secret Manager. Sensitive information must be passed via environment variables and never hardcoded. `src/.env` is excluded from Git.

| Variable | Required | Purpose |
|------|------|------|
| `SECRET_KEY` | Production | Flask session signature key |
| `GOOGLE_API_KEY` | Yes | Gemini API Key |
| `TAVILY_API_KEY` | Yes | Tavily Web Search API Key |
| `GOOGLE_CLIENT_ID` / `GOOGLE_CLIENT_SECRET` | Yes | Google OAuth Credentials |
| `DB_USER` / `DB_PASS` / `DB_NAME` / `DB_HOST` / `DB_PORT` | Yes | Database connection details |
| `DB_SSL` | Conditional | Set to `true` for TLS connections (required for TiDB Cloud) |
| `DB_SSL_CA` | | Path to CA bundle (defaults to `/etc/ssl/certs/ca-certificates.crt`) |
| `CLOUD_SQL_INSTANCE` | Conditional | Connects via Cloud SQL Connector when set |
| `GCS_BUCKET` | Conditional | Uses GCS when set, otherwise falls back to local FS |
| `LOCAL_UPLOAD_DIR` | | Local storage directory (defaults to `src/uploads`) |
| `SIGNED_URL_TTL_SECONDS` | | Expiration time for signed URLs in seconds (defaults to 3600) |
| `GCS_SIGNER_SA` | | SA used explicitly for signing URLs (if applicable) |
| `REDIS_URL` | | Uses Redis to share generation request states when set |
| `STICKER_MAX_IMAGES` / `INTERPRETER_IMAGE_MAX_EDGE` etc. | | Configuration for sticker generation image counts/resize limits |

---

## Directory Structure

```
tabimate/
├── README.md                 # Project description (English)
├── README_jp.md              # Project description (Japanese)
├── requirements.txt          # Python dependencies
├── dockerfile                # ubuntu22.04 + python3.10 + gunicorn
├── deploy.sh                 # Cloud Run deployment (includes Secret/GCS/IAM setup)
├── tests/
│   └── test_smoke.py         # End-to-end smoke test for plan generation
└── src/
    ├── .env                  # Environment variables (excluded from Git)
    ├── app.py                # Flask app initialization & Blueprint registration
    ├── db.py                 # DAO for travel_plans / chat_messages + shared engine
    ├── db_reflection.py      # DAO for trips / photos / stickers etc.
    ├── db_sharing.py         # DAO for sharing links / email grants
    ├── chat/                 # Travel plan generation (LLM/Agents)
    │   ├── chat.py           #  Orchestrates conversation (extract conditions -> question or plan)
    │   ├── graph.py          #  LangGraph workflow definitions & execution
    │   ├── agents.py         #  Agent (node) implementations
    │   ├── models.py         #  TravelPlanState and structured output schemas
    │   ├── llm.py            #  Gemini/Tavily client & retries
    │   ├── formatter.py      #  Formats generated plan to HTML cards
    │   └── logger.py         #  Logger configuration
    ├── services/             # Reflection feature modules
    │   ├── exif.py           #  EXIF metadata extraction (timestamp, GPS)
    │   ├── features.py       #  Summarizes photo metadata into features
    │   ├── storage.py        #  Abstraction for GCS / Local FS
    │   └── trip_interpreter.py #  Generates sticky notes via Gemini (with token logging)
    ├── views/                # Blueprints (Routing)
    │   ├── planner.py        #  Chat, SSE, and saved plans
    │   ├── auth.py           #  Google OAuth authentication
    │   ├── reflection.py     #  APIs & views for trips, photos, and sticky notes
    │   └── sharing.py        #  Sharing links, email sharing, & permission controls
    ├── templates/            # Jinja2 Templates
    │   ├── layout.html, home.html, saved_plans.html, sidebar.html
    │   ├── _share_modal.html
    │   └── reflection/
    │       ├── index.html    #  Trip list (feed-style, sticky note badges)
    │       └── trip.html     #  Trip details (hero section, photos, edit/delete)
    │   └── shared/
    │       ├── index.html    #  List of items shared with me
    │       ├── trip.html     #  Shared trip details (editable)
    │       └── plan.html     #  Shared plan details (view-only)
    └── static/               # CSS / JS / Images
        ├── css/
        ├── js/
        └── img/
```

---

## Architecture

```
         ┌──────────── Flask app (app.py) ────────────┐
         │  ProxyFix + 4 Blueprints                   │
         │                                             │
 Browser─┤  planner      ("/")         Travel plan generation chat
         │  auth         ("/auth")    Google OAuth        │
         │  reflection   ("/reflection") Trip reflection (sticky notes)
         │  sharing      ("/share")   Sharing management  │
         └──────┬───────────────┬──────────┬──────────┘
                │               │          │
        chat/ (LangGraph)   db.py /   services/
        Multi-agent workflow db_reflection.py  exif, features,
                │           （SQLAlchemy） storage,
                ▼               │       trip_interpreter
        Gemini + Tavily         ▼
                          MySQL/TiDB
```

- **Entry Point**: `src/app.py`. Loads `.env`, registers 4 Blueprints, and initializes OAuth.
- **Shared DB Engine**: The SQLAlchemy engine (QueuePool) generated by `get_engine()` in `db.py` is shared by `db_reflection.py` / `db_sharing.py`. Tables are lazily created using `CREATE TABLE IF NOT EXISTS`.
- **Storage Abstraction**: `services/storage.py` dynamically switches between GCS and local FS (based on the presence of `GCS_BUCKET`). GCS signed URLs are generated using **caching & parallel generation** (`get_urls()`) to accelerate loading for pages with many photos.
- **Two Sharing Methods**: `views/sharing.py` manages both public links (tokens) and email grants, controlling access permissions for owners, editors, and viewers.

---

## Getting Started (Development Setup)

### Prerequisites
- Python 3.10+
- MySQL 8.0 (Local, TiDB Cloud, or Cloud SQL)
- Docker (Optional: used to test local storage as an alternative to GCS)

### Setup Steps

```bash
# 1. Clone the repository
git clone <repo-url> && cd tabimate/tabimate

# 2. Create the environment variable file
cp src/.env.example src/.env
# Set the following in src/.env: SECRET_KEY, GOOGLE_API_KEY, TAVILY_API_KEY,
#   GOOGLE_CLIENT_ID, GOOGLE_CLIENT_SECRET,
#   DB_USER, DB_PASS, DB_NAME, DB_HOST, DB_PORT

# 3. Create a virtual environment (Python 3.10+ recommended)
cd src
python3 -m venv .venv
source .venv/bin/activate

# 4. Install dependencies
pip install -r ../requirements.txt

# 5. Start the application
python3 app.py
```

After starting, access `http://localhost:5007` (Flask development server).

> **Note**: Database tables are automatically created on first access via `CREATE TABLE IF NOT EXISTS` (using `utf8mb4`).

### Production Deployment (Cloud Run)

The `deploy.sh` script automates the entire deployment process (reads variables from `src/.env`). Ensure you are authenticated with your GCP project beforehand.

```bash
./deploy.sh
```

What the script does:
1. Enables necessary GCP APIs (run, artifactregistry, cloudbuild, secretmanager, storage, iamcredentials).
2. Registers/updates secrets (`GOOGLE_API_KEY`, `TAVILY_API_KEY`, `GOOGLE_CLIENT_SECRET`, `DB_PASS`, `SECRET_KEY`) in Secret Manager and grants access to the Cloud Run service account.
3. Creates a GCS bucket for photos and grants `objectAdmin` permissions to the service account.
4. Grants `serviceAccountTokenCreator` (IAM signBlob) to the service account for generating signed URLs.
5. Deploys the application via `gcloud run deploy --source .` (specifies region `asia-northeast1`, service name, and project).

> Because the default Cloud Run SA does not have a private key, GCS signed URLs are generated via the **IAM signBlob method** (`service_account_email` + `access_token`).

### Common Commands

```bash
# Run tests
python tests/test_smoke.py          # E2E smoke test for plan generation
pytest tests/                       # Run all tests

# Verify DB connection (if MySQL client is installed)
mysql -h $DB_HOST -u $DB_USER -p $DB_NAME

# Check Cloud Run logs
gcloud run services logs tail <service-name> --region asia-northeast1

# Clean up local storage
rm -rf src/uploads/*               # Delete all locally saved photos
```

---

## Database Schema

| Table | Purpose |
|----------|------|
| `travel_plans` | Saved travel plans (conditions and results stored in a JSON column) |
| `chat_messages` | Chat history (role/content/request_id) |
| `trips` | Trips (title, dates, owner user) |
| `photos` | Uploaded photos (storage_path, shoot time, GPS) |
| `stickers` | Virtual sticky notes (text = display text, basis = internal logic generation basis) |
| `share_links` | Public sharing links (token/resource_type/resource_id/permission) |
| `share_grants` | Email-based sharing (grantee_email/resource_type/resource_id/permission) |
| `achievements` | Legacy "achievements" table (currently unused in the UI, kept for backward compatibility) |
| `trip_reports` | Legacy "AI Trip Report" table (currently unused, kept) |

- Ownership is verified against the `user_id` (Google's OAuth `sub`), preventing unauthorized data access.
- Deleting a trip cascades to delete `photos` / `stickers` / `achievements` / `trip_reports`, and deletes physical photos via `storage.delete()`.
- For TiDB compatibility, sticky note previews are fetched via scalar subqueries instead of `GROUP_CONCAT`.

---

## HTTP Endpoints

### planner (`/`) — `views/planner.py`

| Method | Path | Description |
|----------|------|------|
| GET | `/` | Home (Chat Interface) |
| GET | `/saved_plans` | Saved Plans page (login required) |
| POST | `/send_message` | Submits message & streams AI response via SSE (login required, rate limit: 5 requests / 60 seconds) |
| POST | `/abort_request` | Cancels the active generation request |
| POST | `/reset_chat` | Resets chat history |
| GET | `/get_messages` | Retrieves chat history |
| POST | `/save_plan` | Saves a travel plan |
| DELETE | `/delete_plan/<id>` | Deletes a travel plan |
| GET | `/get_my_plans` | JSON list of personal saved plans |
| GET | `/get_shared_plans` | JSON list of plans shared with the user (integrated into the saved plans view) |
| POST | `/edit_saved_plan/<id>` | Chat-edits a saved plan and streams the proposed result via SSE (no save yet; owner or edit-grant recipient) |
| POST | `/apply_saved_plan/<id>` | Persists the previewed edit (overwrites the owner's plan) |
| POST | `/rate_plan/<id>` | Records a ★1–5 rating and comment for the user's own plan (used to personalize future generation) |

### auth (`/auth`) — `views/auth.py`

| Method | Path | Description |
|----------|------|------|
| GET | `/auth/login` | Starts Google OAuth flow |
| GET | `/auth/callback` | OAuth Callback (stores user_id/email/name in session) |
| GET | `/auth/logout` | Logs out (clears session) |

### reflection (`/reflection`) — `views/reflection.py`

| Method | Path | Description |
|----------|------|------|
| GET | `/reflection/` | List of trips (feed-style layout) |
| GET | `/reflection/trips/<id>` | Trip details (sticky notes & photos) |
| POST | `/reflection/trips` | Creates a new trip |
| PATCH | `/reflection/trips/<id>` | Renames a trip title |
| DELETE | `/reflection/trips/<id>` | Deletes a trip (removes physical photos & related records) |
| POST | `/reflection/trips/<id>/photos` | Uploads photos (max 50 photos) |
| GET | `/reflection/photo/<path>` | Serves locally saved photos (GCS uses signed URLs directly) |
| POST | `/reflection/trips/<id>/stickers/generate` | Generates sticky notes (photos required) |
| GET | `/reflection/trips/<id>/stickers` | Lists sticky notes |
| DELETE | `/reflection/trips/<id>/stickers/<sid>` | Deletes a sticky note |

### sharing (`/share`) — `views/sharing.py`

| Method | Path | Description |
|----------|------|------|
| GET | `/share/trip\|plan/<id>` | List of active shares (JSON for modal) |
| POST | `/share/trip\|plan/<id>/link` | Generates a public share link |
| DELETE | `/share/link/<id>` | Deletes a public share link |
| POST | `/share/trip\|plan/<id>/grant` | Adds email-based share grant |
| DELETE | `/share/grant/<id>` | Deletes email-based share grant (revoked by owner) |
| DELETE | `/shared/grant/<id>` | Removes shared item from recipient's list (grantee only) |
| GET | `/s/<token>` | Accesses public share link (no login required) |
| GET | `/shared` | List of items shared with me |
| GET | `/shared/trip\|plan/<id>` | Accesses email-shared item |
| POST | `/shared/trip/<id>/photos` | Adds photos to a shared trip |
| DELETE | `/shared/trip/<id>/photos/<photo_id>` | Deletes a photo from a shared trip |
| POST | `/shared/trip/<id>/stickers/generate` | Generates sticky notes for a shared trip |
| DELETE | `/shared/trip/<id>/stickers/<sticker_id>` | Deletes a sticky note from a shared trip |
| DELETE | `/shared/trip/<id>` | Deletes a shared trip |

`reflection`, `sharing`, and plan saving features are protected by the `@login_required` decorator.

---

## Plan Generation Agent Architecture

`chat/graph.py` defines the LangGraph `StateGraph` which chains functions from `chat/agents.py` as nodes. The state is passed as a `TravelPlanState` (TypedDict) defined in `chat/models.py`.

### Flow

```
START
  → transport (estimates round-trip costs and remaining budget. Splits costs for car options, etc. Defaults to AI selection)
  → sightseeing_candidates (5 to 8 sightseeing candidates)
  → sightseeing (selects 2 to 3 spots from candidates)
  → accommodation_candidates (3 to 5 lodging candidates / empty for day trips)
  → accommodation (selects 1 to 2 places / target max: 40% of remaining budget)
  → gourmet_candidates (4 to 6 dining candidates)
  → gourmet (selects 2 to 3 dining spots / target max: 25% of remaining budget)
  → timekeeper (compiles chronological timeline)
  → cost_manager (calculates daily and total expense breakdown)
  → balancer (inspects the overall plan)
        └─ branches at route_after_balancer:
             approved / budget_infeasible → END
             fix_sightseeing → goes back to sightseeing
             fix_gourmet / fix_accommodation / fix_budget → goes back to accommodation
             fix_time → goes back to timekeeper
             (repeating issues trigger fallback to sightseeing selection)
```

- **Validation Criteria**: Budget constraints, schedule feasibility, fatigue levels, theme consistency, and (if overnight) special lodging requirements.
- **Rejection Limit**: `MAX_BALANCER_RETRIES = 5`. `recursion_limit = 60` prevents infinite loops.
- **Budget Allocation**: Target cap is 40% of remaining budget for accommodation, and 25% for dining.
- **Out of Budget**: If transportation costs exceed the total budget, `transport_agent` throws a `ValueError` to abort and notify the user.
- **Day Trip Check**: `is_day_trip()` inspects the duration string to skip accommodation nodes.
- **User Feedback Priority**: During planning adjustments, `user_feedback` is prioritized in prompts for all agents.
- **Time Preference**: `schedule_pref` (e.g., "home by evening") is injected into the timekeeper as a top-priority constraint; the day-trip schedule is computed by back-calculating from the return-home time.
- **Rating-based Preferences**: `user_preferences` is built from the user's past ★ ratings/comments (`get_rated_plans`) and softly injected into the sightseeing, accommodation, gourmet, and timekeeper agents.
- **Partial Editing**: Automatically detects edit targets (`edit_targets`) based on adjustment requests, regenerating only targeted nodes (previous outputs are preserved for other nodes). Previous plans are restored via the `data-plan` attribute on the save button. Edits affecting budget (lodging, dining, transport, cost) verify budget/feasibility and return warnings rather than triggering a balancer rejection if exceeded.
- **Web Search Integration**: `build_search_context()` in `chat/llm.py` uses Tavily to fetch official guidelines and reviews to back up candidates (filter score threshold: 0.3).
- **Retries**: `invoke_with_retry()` retries API requests up to 5 times using exponential/linear backoff to handle rate limits (429/503) and network failures.

---

## Testing

```bash
python tests/test_smoke.py          # E2E smoke test for plan generation
pytest tests/                       # Runs all tests
```

`tests/test_smoke.py` executes the full planning workflow to verify that destinations are preserved and `spots` are returned as a list (requires Gemini/Tavily API keys).

`tests/test_units.py` runs **offline (no API keys/DB)** and checks pure helpers — thumbnail key derivation, local URL generation/dedup, and path-traversal protection. Fast to run in CI.

---

## Security Policy

- **No Hardcoded Secrets**: Secrets are fed via environment variables / Secret Manager. `src/.env` is excluded from Git.
- **Session Hardening**: Fails to start in production if `SECRET_KEY` is not set (prevents session hijacking via default keys). Cookies are configured with `HttpOnly` and `SameSite=Lax` (and `Secure` in production).
- **OAuth Email Verification**: Requires `email_verified` during login to prevent spoofing, since email addresses are used for sharing grants.
- **Access Control**: Trips, photos, stickers, plans, and sharing links are validated against `user_id` to block cross-user data access.
- **XSS Protection**: HTML formatting for travel plans escapes user-controlled strings.
- **Path Traversal Protection**: Directory boundary checks for local photo serving/deletion prevent access outside the upload directory.
- **Rate Limiting**: Plan generation is limited to 5 requests / 60 seconds per user.
- **Upload Restrictions**: Max 50 files per request, validated against an extension whitelist.
- **Proxy Trust**: Uses `ProxyFix` to parse headers forwarded by Cloud Run, ensuring correct scheme/host formatting for OAuth callbacks.
- **Unpredictable Token Keys**: Sharing links use sufficiently long random tokens.

---

## Troubleshooting

### `.env` is Missing
Create `src/.env` in the root directory and populate it based on the environment variables guide above.

### Docker Daemon is Not Running
```bash
open -a Docker   # macOS
# Verify Docker Desktop is running before retrying.
```

### Cannot Connect to MySQL
- Double-check `DB_HOST`. If connecting to Cloud SQL (`CLOUD_SQL_INSTANCE` specified), use the Instance Connection Name rather than the local MySQL host.
- For SSL-enforced environments like TiDB Cloud, ensure `DB_SSL=true` and `DB_SSL_CA` are properly configured.

### Plan generation times out (504)
- Cloud Run's default request timeout is 300s (5 min), which can be shorter than a full multi-agent generation. `deploy.sh` sets `--timeout=600` (matching gunicorn's 600s); the effective cap is `min(Cloud Run timeout, gunicorn timeout)`.
- To apply without redeploying: `gcloud run services update <service-name> --region asia-northeast1 --timeout=600`.
- To allow even longer, raise both the gunicorn `--timeout` (dockerfile) and Cloud Run `--timeout` (Cloud Run gen2 max is 3600s).
- Expected timeouts are handled on the client side via the `abort_request` endpoint to cancel operations explicitly.

### Photo Loading is Slow
GCS signed URLs call IAM signBlob per photo, which slows down as the photo count increases (increasing CPU/memory won't resolve this). `services/storage.py`'s `get_urls()` implements **caching & parallel generation**, and **thumbnails** are served in lists (originals only in the lightbox). For photos uploaded before thumbnails existed, run `scripts/backfill_thumbnails.py`. To further reduce cold starts, consider a minimum instance of 1 on Cloud Run.

### Tavily Search Returns "String Instead of List" Error
Tavily's search result types can occasionally be unstable (returning a `str` instead of a `list`). Check that `build_search_context()` in `chat/llm.py` includes the `if not isinstance(results, list)` guard, as previous issues have shown `AttributeError` from using `.get()` on strings.
