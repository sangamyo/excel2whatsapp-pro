import hashlib
import hmac
import json
import logging
from datetime import datetime, timezone

from fastapi import APIRouter, Request, HTTPException
from fastapi.concurrency import run_in_threadpool
from fastapi.responses import PlainTextResponse

from app.config.settings import settings
from app.database import SessionLocal
from app.models.message import Message

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/webhook", tags=["webhook"])

# Delivery progress only moves forward; webhooks can arrive out of order.
STATUS_RANK = {"pending": 0, "sent": 1, "delivered": 2, "read": 3}
SUCCESS_STATUSES = {"sent", "delivered", "read"}


@router.get("/whatsapp", response_class=PlainTextResponse)
async def verify(request: Request):
    mode = request.query_params.get("hub.mode")
    token = request.query_params.get("hub.verify_token")
    challenge = request.query_params.get("hub.challenge")

    if mode == "subscribe" and settings.VERIFY_TOKEN and token == settings.VERIFY_TOKEN:
        return challenge or ""
    raise HTTPException(status_code=403, detail="Verification failed")


def verify_signature(body: bytes, header: str | None, app_secret: str) -> bool:
    """Check Meta's X-Hub-Signature-256 header ("sha256=<hex HMAC of the raw body>")."""
    if not header or not header.startswith("sha256="):
        return False
    expected = hmac.new(app_secret.encode("utf-8"), body, hashlib.sha256).hexdigest()
    return hmac.compare_digest(expected, header.removeprefix("sha256="))


def _iter_statuses(payload: dict):
    for entry in payload.get("entry") or []:
        for change in entry.get("changes") or []:
            value = change.get("value") or {}
            for status in value.get("statuses") or []:
                yield status


def _error_reason(status: dict) -> str:
    parts = []
    for err in status.get("errors") or []:
        details = (err.get("error_data") or {}).get("details")
        text = err.get("message") or err.get("title") or "unknown error"
        parts.append(f"{err.get('code', '')} {text}".strip() + (f": {details}" if details else ""))
    return "; ".join(parts) or "WhatsApp reported the message as failed"


def apply_status_updates(payload: dict) -> int:
    """Apply WhatsApp delivery status webhooks to Message rows. Returns rows updated."""
    updated = 0
    db = SessionLocal()
    try:
        for status in _iter_statuses(payload):
            wa_id = status.get("id")
            new_status = status.get("status")
            if not wa_id or new_status not in SUCCESS_STATUSES | {"failed"}:
                continue

            message = db.query(Message).filter(Message.wa_message_id == wa_id).first()
            if message is None:
                logger.info("Status %r for unknown WhatsApp message id %s ignored", new_status, wa_id)
                continue

            current = message.status or "pending"
            campaign = message.campaign

            if new_status == "failed":
                if current == "failed":
                    continue
                if current in SUCCESS_STATUSES and campaign and campaign.success_count:
                    campaign.success_count -= 1
                if campaign:
                    campaign.failed_count += 1
                message.status = "failed"
                message.error_reason = _error_reason(status)
            else:
                if current == "failed" or STATUS_RANK[new_status] <= STATUS_RANK.get(current, 0):
                    continue
                message.status = new_status

            ts = status.get("timestamp")
            message.status_updated_at = (
                datetime.fromtimestamp(int(ts), tz=timezone.utc) if str(ts or "").isdigit()
                else datetime.now(timezone.utc)
            )
            updated += 1
        db.commit()
    except Exception:
        db.rollback()
        raise
    finally:
        db.close()
    return updated


@router.post("/whatsapp")
async def receive(request: Request):
    body = await request.body()

    if settings.APP_SECRET:
        if not verify_signature(body, request.headers.get("X-Hub-Signature-256"), settings.APP_SECRET):
            raise HTTPException(status_code=403, detail="Invalid signature")

    try:
        payload = json.loads(body or b"{}")
    except json.JSONDecodeError:
        raise HTTPException(status_code=400, detail="Invalid JSON")
    if not isinstance(payload, dict):
        raise HTTPException(status_code=400, detail="Invalid payload")

    try:
        updated = await run_in_threadpool(apply_status_updates, payload)
    except Exception:
        # A non-2xx response makes Meta redeliver the webhook later.
        logger.exception("Failed to process WhatsApp webhook payload")
        raise HTTPException(status_code=500, detail="Webhook processing failed")

    return {"received": True, "updated": updated}
