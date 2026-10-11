from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session
from typing import List

from app.database import get_db
from app.models.campaign import Campaign
from app.models.message import Message
from app.schemas.campaign import CampaignOut
from app.schemas.message import MessageOut
from app.utils.security import get_current_user
from app.models.user import User

router = APIRouter(prefix="/campaigns", tags=["campaigns"])


@router.get("/", response_model=List[CampaignOut])
def list_campaigns(current_user: User = Depends(get_current_user), db: Session = Depends(get_db)):
    return (
        db.query(Campaign)
        .filter(Campaign.user_id == current_user.id)
        .order_by(Campaign.created_at.desc())
        .all()
    )


@router.get("/{campaign_id}", response_model=CampaignOut)
def get_campaign(campaign_id: int, current_user: User = Depends(get_current_user), db: Session = Depends(get_db)):
    campaign = (
        db.query(Campaign)
        .filter(Campaign.id == campaign_id, Campaign.user_id == current_user.id)
        .first()
    )
    if not campaign:
        raise HTTPException(status_code=404, detail="Campaign not found")
    return campaign


@router.get("/{campaign_id}/messages", response_model=List[MessageOut])
def list_campaign_messages(
    campaign_id: int,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    campaign = (
        db.query(Campaign)
        .filter(Campaign.id == campaign_id, Campaign.user_id == current_user.id)
        .first()
    )
    if not campaign:
        raise HTTPException(status_code=404, detail="Campaign not found")
    return (
        db.query(Message)
        .filter(Message.campaign_id == campaign.id)
        .order_by(Message.id.asc())
        .all()
    )
