import logging
import socket
from concurrent.futures import Future, ThreadPoolExecutor
from urllib.parse import urlparse

from app.config.settings import settings

logger = logging.getLogger(__name__)

executor = ThreadPoolExecutor(max_workers=2, thread_name_prefix="campaign")


def _can_connect_redis(url: str, timeout: float = 1.0) -> bool:
    parsed = urlparse(url)
    host = parsed.hostname or parsed.path.split(':')[0]
    port = parsed.port or 6379
    try:
        with socket.create_connection((host, port), timeout=timeout):
            return True
    except Exception as exc:
        logger.warning("Celery broker at %s:%s is unreachable (%s); using in-process sending", host, port, exc)
        return False


def _log_background_failure(future: Future, campaign_id: int) -> None:
    exc = future.exception()
    if exc is not None:
        logger.error(
            "Background processing of campaign %s failed", campaign_id,
            exc_info=(type(exc), exc, exc.__traceback__),
        )


def enqueue_campaign(campaign_id: int) -> str:
    """Start sending a campaign.

    Uses Celery when a broker URL (CELERY_BROKER_URL or REDIS_URL) is configured and
    reachable; otherwise sends from an in-process background thread, so a single
    web service works without Redis. Returns the mode used.
    """
    broker = settings.CELERY_BROKER_URL or settings.REDIS_URL
    if broker and _can_connect_redis(broker):
        try:
            from app.tasks.send_message import process_campaign_task

            process_campaign_task.delay(campaign_id)
            return "celery"
        except Exception:
            logger.exception("Could not enqueue campaign %s on Celery; falling back to a background thread", campaign_id)
    elif not broker:
        logger.info("No broker configured; sending campaign %s in-process", campaign_id)

    from app.tasks.send_message import process_campaign_sync

    try:
        future = executor.submit(process_campaign_sync, campaign_id, False)
    except RuntimeError:
        # Executor already shut down (interpreter exit): run inline as a last resort.
        logger.exception("Background executor unavailable; processing campaign %s inline", campaign_id)
        process_campaign_sync(campaign_id, False)
        return "inline"
    future.add_done_callback(lambda f: _log_background_failure(f, campaign_id))
    return "background"
