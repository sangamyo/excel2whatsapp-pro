from pydantic import BaseModel, ConfigDict
from typing import Optional
from datetime import datetime

class MessageCreate(BaseModel):
    phone: str
    message: str

class MessageOut(BaseModel):
    id: int
    campaign_id: int
    phone: str
    message: str
    context: dict
    status: str
    error_reason: Optional[str]
    sent_at: Optional[datetime]
    wa_message_id: Optional[str] = None
    status_updated_at: Optional[datetime] = None

    model_config = ConfigDict(from_attributes=True)
