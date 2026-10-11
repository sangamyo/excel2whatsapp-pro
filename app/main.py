from fastapi import FastAPI, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse
from slowapi import Limiter
from slowapi.errors import RateLimitExceeded
from slowapi.middleware import SlowAPIMiddleware
from slowapi.util import get_remote_address

from app.config.settings import settings
from app.database import Base, engine
import logging
from sqlalchemy import inspect, text
from sqlalchemy.exc import OperationalError
from app.middleware.plan import PlanLimitMiddleware
from app.routes import auth, upload, campaigns, dashboard, webhook

logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(name)s: %(message)s")

# Columns added after the first release. create_all() never alters existing tables, so
# add them here until proper Alembic migrations exist.
_ADDED_COLUMNS = {
    "messages": {
        "wa_message_id": "VARCHAR",
        "status_updated_at": "TIMESTAMP WITH TIME ZONE",
    },
}


def _add_missing_columns() -> None:
    inspector = inspect(engine)
    for table, columns in _ADDED_COLUMNS.items():
        if not inspector.has_table(table):
            continue
        existing = {c["name"] for c in inspector.get_columns(table)}
        with engine.begin() as conn:
            for name, ddl_type in columns.items():
                if name not in existing:
                    logging.info("Adding missing column %s.%s", table, name)
                    conn.execute(text(f"ALTER TABLE {table} ADD COLUMN {name} {ddl_type}"))
                    if name == "wa_message_id":
                        conn.execute(text(f"CREATE INDEX IF NOT EXISTS ix_{table}_{name} ON {table} ({name})"))


try:
    Base.metadata.create_all(bind=engine)
    _add_missing_columns()
except OperationalError as exc:
    logging.warning("Database not available at startup, skipping auto-create: %s", exc)
except Exception as exc:  # pragma: no cover - defensive
    logging.exception("Unexpected error when creating database tables: %s", exc)

limiter = Limiter(key_func=get_remote_address, default_limits=["120/minute"])

app = FastAPI(title="Excel2WhatsApp Pro", version="1.0.0", description="Send WhatsApp campaigns from Excel uploads")
app.state.limiter = limiter


@app.exception_handler(RateLimitExceeded)
async def rate_limit_handler(request: Request, exc: RateLimitExceeded):
    return JSONResponse(status_code=429, content={"detail": "Too many requests"})


app.add_middleware(SlowAPIMiddleware)
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)
app.add_middleware(PlanLimitMiddleware)


@app.get("/health")
async def health():
    return {"status": "ok", "environment": settings.ENV}


app.include_router(auth.router)
app.include_router(upload.router)
app.include_router(campaigns.router)
app.include_router(dashboard.router)
app.include_router(webhook.router)

# Meta can deliver many status webhooks per minute from the same IPs.
limiter.exempt(webhook.receive)


if __name__ == "__main__":
    import uvicorn

    # `python -m app.main` honours $HOST / $PORT (Railway sets PORT).
    uvicorn.run("app.main:app", host=settings.HOST, port=settings.PORT)
