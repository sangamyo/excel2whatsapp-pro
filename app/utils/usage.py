from datetime import datetime, timezone
from fastapi import HTTPException

PLAN_LIMITS = {
    "Free": 50,
    "Pro": 5000,
    "Enterprise": 100000,
}


def reset_daily_usage_if_needed(user):
    now = datetime.now(timezone.utc)
    last_reset = user.last_usage_reset
    if not last_reset or last_reset.date() < now.date():
        user.daily_usage_count = 0
        user.last_usage_reset = now


def ensure_can_send(user, batch_size: int):
    limit = PLAN_LIMITS.get(user.plan, PLAN_LIMITS["Free"])
    if user.plan == "Enterprise":
        return
    if user.daily_usage_count + batch_size > limit:
        raise HTTPException(status_code=429, detail="Daily messaging limit exceeded for your plan")
