from datetime import datetime

from fastapi import APIRouter, Depends
from sqlalchemy.orm import Session
from sqlalchemy import func

from app.database import get_db
from app.models.campaign import Campaign
from app.models.message import Message
from app.utils.security import get_current_user
from app.models.user import User

router = APIRouter(prefix="/dashboard", tags=["dashboard"])


@router.get("/stats")
def stats(current_user: User = Depends(get_current_user), db: Session = Depends(get_db)):
    base = db.query(Campaign).filter(Campaign.user_id == current_user.id)
    total_campaigns = base.count()

    success = db.query(func.sum(Campaign.success_count)).filter(Campaign.user_id == current_user.id).scalar() or 0
    failed = db.query(func.sum(Campaign.failed_count)).filter(Campaign.user_id == current_user.id).scalar() or 0

    success_rate = 0.0
    if success + failed > 0:
        success_rate = round(success / (success + failed), 4)

    today = datetime.utcnow().date()
    today_start = datetime.combine(today, datetime.min.time())

    daily_usage = current_user.daily_usage_count
    daily_sent = (
        db.query(func.count(Message.id))
        .join(Campaign, Message.campaign_id == Campaign.id)
        .filter(Campaign.user_id == current_user.id, Message.sent_at >= today_start)
        .scalar()
        or 0
    )

    pending_campaigns = base.filter(Campaign.status == "pending").count()

    return {
        "total_campaigns": total_campaigns,
        "success_count": success,
        "failed_count": failed,
        "success_rate": success_rate,
        "daily_usage_count": daily_usage,
        "daily_messages_sent": daily_sent,
        "pending_campaigns": pending_campaigns,
    }
