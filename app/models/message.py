from sqlalchemy import Column, Integer, String, ForeignKey, DateTime, Text
from sqlalchemy.types import JSON
from sqlalchemy.sql import func
from sqlalchemy.orm import relationship
from app.database import Base

class Message(Base):
    __tablename__ = "messages"

    id = Column(Integer, primary_key=True, index=True)
    campaign_id = Column(Integer, ForeignKey("campaigns.id"), nullable=False)
    phone = Column(String, nullable=False)
    message = Column(Text, nullable=False)
    context = Column(JSON, nullable=False)
    status = Column(String, default="pending")  # pending, sent, delivered, read, failed
    error_reason = Column(Text, nullable=True)
    sent_at = Column(DateTime(timezone=True), nullable=True)
    # WhatsApp message id ("wamid...") returned by the Cloud API; used to match status webhooks.
    wa_message_id = Column(String, nullable=True, index=True)
    status_updated_at = Column(DateTime(timezone=True), nullable=True)

    campaign = relationship("Campaign", back_populates="messages")
