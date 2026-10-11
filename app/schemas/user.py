from pydantic import BaseModel, EmailStr, field_validator, ConfigDict
from datetime import datetime

class UserCreate(BaseModel):
    name: str
    email: EmailStr
    password: str
    plan: str = "Free"

    @field_validator("plan")
    @classmethod
    def validate_plan(cls, value):
        allowed = {"Free", "Pro", "Enterprise"}
        if value not in allowed:
            raise ValueError("Invalid plan type")
        return value

class UserOut(BaseModel):
    id: int
    name: str
    email: EmailStr
    plan: str
    daily_usage_count: int
    last_usage_reset: datetime
    created_at: datetime

    model_config = ConfigDict(from_attributes=True)

class Token(BaseModel):
    access_token: str
    token_type: str = "bearer"

class TokenData(BaseModel):
    user_id: int | None = None


class UserLogin(BaseModel):
    email: EmailStr
    password: str
