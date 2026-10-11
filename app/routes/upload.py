from fastapi import APIRouter, UploadFile, File, Depends, Form, HTTPException
from sqlalchemy.orm import Session

from app.database import get_db
from app.models.campaign import Campaign
from app.models.message import Message
from app.tasks.runner import enqueue_campaign
from app.utils.excel import parse_excel_upload
from app.utils.security import get_current_user
from app.utils.usage import reset_daily_usage_if_needed, ensure_can_send
from app.services.template_engine import TemplateEngine
from app.schemas.campaign import CampaignOut
from app.models.user import User

router = APIRouter(prefix="/upload", tags=["upload"])


@router.post("/campaign", response_model=CampaignOut)
async def upload_campaign(
    file: UploadFile = File(...),
    template: str = Form(..., description="Message template including placeholders like {{Name}}"),
    campaign_name: str | None = Form(None),
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    rows = await parse_excel_upload(file)
    if not rows:
        raise HTTPException(status_code=400, detail="No rows detected in file")

    reset_daily_usage_if_needed(current_user)
    ensure_can_send(current_user, len(rows))

    placeholders = TemplateEngine.extract_placeholders(template)
    allowed = {"Name", "CustomField"}
    invalid = placeholders - allowed
    if invalid:
        raise HTTPException(status_code=400, detail=f"Unsupported placeholder(s): {', '.join(invalid)}")

    campaign = Campaign(
        user_id=current_user.id,
        name=campaign_name,
        total_messages=len(rows),
        status="pending",
        template=template,
    )
    db.add(campaign)
    db.flush()

    for r in rows:
        context = {"Name": r["Name"], "CustomField": r["CustomField"]}
        try:
            rendered = TemplateEngine.render(template, context)
        except ValueError as exc:
            raise HTTPException(status_code=400, detail=str(exc))
        message = Message(
            campaign_id=campaign.id,
            phone=r["Phone"],
            message=rendered,
            context=context,
        )
        db.add(message)

    current_user.daily_usage_count += len(rows)
    db.commit()
    db.refresh(campaign)

    # enqueue processing using Celery if available, otherwise background runner
    enqueue_campaign(campaign.id)

    return campaign
