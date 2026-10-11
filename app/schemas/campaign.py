from pydantic import BaseModel, ConfigDict
from typing import Optional
from datetime import datetime

class CampaignCreate(BaseModel):
    name: Optional[str]

class CampaignOut(BaseModel):
    id: int
    user_id: int
    name: str | None
    total_messages: int
    success_count: int
    failed_count: int
    status: str
    template: str
    created_at: datetime

    model_config = ConfigDict(from_attributes=True)
