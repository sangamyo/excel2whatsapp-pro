# Excel2WhatsApp Pro

Excel2WhatsApp Pro is a FastAPI backend that turns spreadsheet uploads into WhatsApp broadcast campaigns. It has plan-aware quotas, Celery-powered delivery (with an in-process fallback), delivery receipts via webhooks, and Docker-first deployment.

## Features

- **FastAPI + PostgreSQL** with SQLAlchemy ORM models (`User`, `Campaign`, `Message`). SQLite works for local development.
- **JWT authentication** (registration/login) with passlib hashing and the OAuth2 password flow.
- **Plan enforcement middleware** for Free/Pro/Enterprise tiers with automatic daily usage resets.
- **Excel/CSV ingestion** via pandas with strict column and phone validation.
- **Template engine** with placeholder validation (`{{Name}}`, `{{CustomField}}`).
- **WhatsApp Cloud API integration** (Meta Graph v18) with error propagation.
- **Celery + Redis queue** with 1 msg/sec rate limiting and retries. **Without Redis, campaigns are sent from in-process background threads**, so a single web service works.
- **Delivery receipts**: the WhatsApp webhook updates each message to `sent` → `delivered` → `read` (or `failed`, with the error reason) by WhatsApp message id, and keeps campaign success/failure counts in sync. Requests are verified with `X-Hub-Signature-256` when `APP_SECRET` is set.
- **Campaign and dashboard APIs** for analytics (success rate, daily usage, pending counts).
- **Docker + docker-compose** for API, worker, Postgres and Redis, plus a single-container Railway deploy.

## Prerequisites

- Python 3.11+
- Docker & Docker Compose (optional)
- Meta WhatsApp Cloud API credentials (access token, phone number ID, verify token, app secret)

## Environment variables

Copy `.env.example` to `.env` and fill in the values:

```bash
cp .env.example .env
```

| Variable | Required | Default | Description |
|---|---|---|---|
| `SECRET_KEY` | yes | | Secret for signing JWTs. Use a long random string. |
| `ACCESS_TOKEN` | yes | | Meta Graph API access token for the WhatsApp Cloud API. |
| `PHONE_NUMBER_ID` | yes | | WhatsApp Business phone number ID to send from. |
| `VERIFY_TOKEN` | yes | | Token you choose; Meta echoes it during webhook verification (`GET /webhook/whatsapp`). |
| `APP_SECRET` | recommended | empty | Meta app secret. When set, `POST /webhook/whatsapp` rejects requests without a valid `X-Hub-Signature-256`. |
| `DATABASE_URL` | no | empty | Full database URL. `postgres://` (Railway/Heroku style), `postgresql://` and `sqlite:///./dev.db` are accepted. Takes precedence over `POSTGRES_*`. |
| `POSTGRES_USER` / `POSTGRES_PASSWORD` / `POSTGRES_DB` | no | `postgres` / `postgres` / `excel2whatsapp` | Used to build the Postgres URL when `DATABASE_URL` is empty. |
| `POSTGRES_HOST` / `POSTGRES_PORT` | no | `localhost` / `5432` | Postgres host and port. |
| `REDIS_URL` | no | empty | Redis URL for Celery. If empty or unreachable, campaigns are sent in-process. |
| `CELERY_BROKER_URL` / `CELERY_RESULT_BACKEND` | no | `REDIS_URL` | Override the Celery broker/result backend. |
| `ACCESS_TOKEN_EXPIRE_MINUTES` | no | `1440` | JWT lifetime. |
| `HOST` / `PORT` | no | `0.0.0.0` / `8000` | Bind address for `python -m app.main` and the Docker image (Railway sets `PORT`). |
| `ENV` | no | `development` | Reported by `/health`. |

## Local development (venv)

```bash
python -m venv .venv
source .venv/bin/activate
pip install -r requirements-dev.txt
echo "DATABASE_URL=sqlite:///./dev.db" >> .env   # optional: skip Postgres locally
uvicorn app.main:app --reload                    # or: python -m app.main
```

Optional Celery worker (needs `REDIS_URL`):

```bash
celery -A app.tasks.send_message.celery_app worker --loglevel=info
```

## Docker Compose

```bash
docker compose up --build
```

Services started:
- `api`: FastAPI app on `http://localhost:8000`
- `worker`: Celery worker
- `db`: Postgres
- `redis`: Redis broker/result backend

## Deploy to Railway

The Dockerfile listens on `$PORT`, so Railway can run it directly.

1. Push the repo to GitHub, then in Railway choose **New Project → Deploy from GitHub repo**. Railway builds the `Dockerfile`.
2. Add a **PostgreSQL** database to the project, and in the API service's **Variables** reference it with `DATABASE_URL=${{Postgres.DATABASE_URL}}`. The `postgres://` scheme is converted automatically.
3. Set `SECRET_KEY`, `ACCESS_TOKEN`, `PHONE_NUMBER_ID`, `VERIFY_TOKEN` and `APP_SECRET`.
4. Optional: add a **Redis** service, set `REDIS_URL=${{Redis.REDIS_URL}}`, and create a second service from the same repo with the start command `celery -A app.tasks.send_message.celery_app worker --loglevel=info`. Without Redis, the single API service sends campaigns from background threads. In that mode, a campaign that is mid-send during a redeploy stops, and its remaining messages stay `pending`.
5. Under **Settings → Networking**, generate a public domain and check `https://<domain>/health`.
6. In the Meta developer dashboard (WhatsApp → Configuration), set the callback URL to `https://<domain>/webhook/whatsapp` with your `VERIFY_TOKEN`, and subscribe to the `messages` field to receive delivery statuses.

## Database migrations

Tables are created automatically on startup with SQLAlchemy metadata. Columns added after the first release (`messages.wa_message_id`, `messages.status_updated_at`) are also added on startup if they are missing. Alembic is included for future migrations:

```bash
alembic init migrations  # once
alembic revision --autogenerate -m "init"
alembic upgrade head
```

(Configure `alembic.ini` to point at `DATABASE_URL`.)

## API overview

| Endpoint | Method | Description |
|----------|--------|-------------|
| `/auth/register` | POST | Create account (name, email, password, plan) |
| `/auth/token` | POST (form) | Obtain JWT access token |
| `/auth/me` | GET | Retrieve current user |
| `/upload/campaign` | POST (multipart) | Upload Excel/CSV + template to create a campaign |
| `/campaigns/` | GET | List user campaigns |
| `/campaigns/{id}` | GET | Campaign detail |
| `/campaigns/{id}/messages` | GET | Messages for a campaign, including delivery status |
| `/dashboard/stats` | GET | Summary analytics |
| `/webhook/whatsapp` | GET | Meta webhook verification handshake |
| `/webhook/whatsapp` | POST | WhatsApp status updates (sent/delivered/read/failed) |
| `/health` | GET | Liveness probe |

### Upload contract

- File must be `.xlsx` or `.csv` with columns `Name`, `Phone`, `CustomField` (see `samples/contacts.csv`).
- Phone numbers must include the leading `+` (E.164).
- Template placeholders allowed: `{{Name}}`, `{{CustomField}}`.

### Message status lifecycle

`pending` → `sent` (accepted by the Cloud API, WhatsApp message id stored) → `delivered` → `read`. Any step can become `failed`. Webhooks can arrive out of order, so a status never moves backwards. A `failed` webhook for a message previously counted as sent moves it from the campaign's `success_count` to its `failed_count`.

## Plan limits

| Plan | Daily messages |
|------|----------------|
| Free | 50 |
| Pro | 5,000 |
| Enterprise | 100,000 (soft limit) |

The middleware enforces quotas per request, and usage is incremented when a campaign is created.

## Testing

```bash
pip install -r requirements-dev.txt
pytest -q                      # webhook, signature, DB URL and fallback tests (SQLite, no network)
```

End-to-end smoke test against a running server on port 8000:

```bash
DATABASE_URL=sqlite:///./dev.db uvicorn app.main:app &
python run_smoke.py            # register → token → upload samples/contacts.csv
```

`run_smoke.py` uploads a real campaign, so with real WhatsApp credentials it sends real messages to the sample numbers. Use dummy credentials when smoke testing.

## Postman collection

See `postman/Excel2WhatsApp-Pro.postman_collection.json` for ready-to-import requests covering the key flows.

## Deployment notes

- Behind a reverse proxy, terminate HTTPS and forward to Uvicorn. The Docker image already trusts `X-Forwarded-*` headers.
- Scale Celery by running more worker containers if throughput grows.
- Schedule a nightly job (or Celery beat) to reset `daily_usage_count`, beyond the middleware's automatic reset.

## Future enhancements

- Alembic migration scripts.
- Persist template name/description for UI selection.
- Handle inbound (user-sent) WhatsApp messages.
- UI dashboard.
