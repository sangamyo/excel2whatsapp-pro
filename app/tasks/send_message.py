import logging
from datetime import datetime
from typing import Optional

from celery import Celery
from sqlalchemy.orm import Session

from app.config.settings import settings
from app.database import SessionLocal
from app.models.message import Message
from app.models.campaign import Campaign
from app.services.whatsapp import WhatsAppService

logger = logging.getLogger(__name__)

BROKER_URL = settings.CELERY_BROKER_URL or settings.REDIS_URL

# Without a broker URL the Celery app is still importable (so the worker module and
# task decorators work), but app.tasks.runner never dispatches to it.
celery_app = Celery(
    "excel2whatsapp",
    broker=BROKER_URL,
    backend=settings.CELERY_RESULT_BACKEND or settings.REDIS_URL,
)

celery_app.conf.beat_schedule = {}
celery_app.conf.task_routes = {"app.tasks.send_message.*": {"rate_limit": "1/s"}}
celery_app.conf.task_default_retry_delay = 10
celery_app.conf.task_annotations = {"app.tasks.send_message.send_message_task": {"rate_limit": "1/s"}}

# Statuses that mean the API accepted the message; never send these again.
ACCEPTED_STATUSES = {"sent", "delivered", "read"}


def _extract_wa_message_id(response: dict) -> Optional[str]:
    try:
        return response["messages"][0]["id"]
    except (KeyError, IndexError, TypeError):
        return None


def send_message_sync(message_id: int) -> None:
    """Send one message and record the outcome.

    Used directly by the in-process fallback and wrapped by the Celery task.
    """
    db: Session = SessionLocal()
    try:
        message = db.get(Message, message_id)
        if not message or message.status in ACCEPTED_STATUSES:
            return

        campaign = message.campaign

        try:
            response = WhatsAppService.send_text_message(message.phone, message.message)
            message.status = "sent"
            message.error_reason = None
            message.sent_at = datetime.utcnow()
            message.wa_message_id = _extract_wa_message_id(response)
            campaign.success_count += 1
            db.commit()
        except Exception as exc:
            logger.warning("Sending message %s (campaign %s) failed: %s", message_id, campaign.id, exc)
            db.rollback()
            message = db.get(Message, message_id)
            if message:
                message.status = "failed"
                message.error_reason = str(getattr(exc, "detail", exc))
                if message.campaign:
                    message.campaign.failed_count += 1
                db.commit()
            return

        pending = (
            db.query(Message)
            .filter(Message.campaign_id == campaign.id, Message.status == "pending")
            .count()
        )
        if pending == 0:
            campaign.status = "completed"
            db.commit()
    finally:
        db.close()


@celery_app.task(bind=True, max_retries=3)
def send_message_task(self, message_id: int):
    try:
        send_message_sync(message_id)
    except Exception as exc:
        # Allow Celery to retry
        raise self.retry(exc=exc, countdown=1)


def process_campaign_sync(campaign_id: int, send_via_celery: Optional[bool] = False):
    """Synchronous campaign processor. If `send_via_celery` is True it will try to
    enqueue Celery tasks for sending; otherwise it will send inline.
    """
    db: Session = SessionLocal()
    try:
        campaign = db.get(Campaign, campaign_id)
        if not campaign:
            logger.warning("Campaign %s not found; nothing to send", campaign_id)
            return
        campaign.status = "processing"
        db.commit()
        db.refresh(campaign)

        message_ids = [msg.id for msg in campaign.messages]
        for message_id in message_ids:
            if send_via_celery:
                try:
                    send_message_task.delay(message_id)
                except Exception:
                    logger.exception("Could not enqueue message %s; sending inline", message_id)
                    send_message_sync(message_id)
            else:
                send_message_sync(message_id)

        db.expire_all()
        campaign = db.get(Campaign, campaign_id)
        pending = (
            db.query(Message)
            .filter(Message.campaign_id == campaign.id, Message.status == "pending")
            .count()
        )
        if pending == 0:
            campaign.status = "completed"
            db.commit()
    finally:
        db.close()


@celery_app.task(bind=True)
def process_campaign_task(self, campaign_id: int):
    try:
        process_campaign_sync(campaign_id, send_via_celery=True)
    except Exception as exc:
        raise self.retry(exc=exc)
