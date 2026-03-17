import uuid
from datetime import datetime
from sqlalchemy import Column, String, Boolean, DateTime, Integer, Float, Text, ForeignKey, Date
from sqlalchemy.dialects.postgresql import UUID, JSONB
from sqlalchemy.orm import DeclarativeBase, relationship


class Base(DeclarativeBase):
    pass


class User(Base):
    __tablename__ = "users"

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    telegram_id = Column(String, unique=True, nullable=True)  # opt-in only
    personality = Column(String(50), nullable=True)  # 'disciplined' or 'compassionate'
    coaching_style = Column(String(50), nullable=True)
    motivation = Column(String(200), nullable=True)
    health_scores = Column(JSONB, default=dict)  # {sleep, energy, nutrition, movement, stress, overall}
    assessment_data = Column(JSONB, default=dict)  # raw deep assessment answers
    timezone_offset = Column(Integer, default=0)  # UTC offset in hours
    timezone_name = Column(String(50), default="UTC")
    fsm_state = Column(String(100), nullable=True)
    fsm_phase = Column(Integer, default=0)  # 0=onboarding, 1=assessment, 2/3=daily, 4=monthly
    is_active = Column(Boolean, default=True)
    last_monthly_audit = Column(DateTime, nullable=True)
    nudge_plan = Column(JSONB, default=list)
    nudge_plan_start = Column(Date, nullable=True)
    block_count = Column(Integer, default=0)
    block_reset_at = Column(DateTime, nullable=True)
    message_count = Column(Integer, default=0)
    message_window_start = Column(DateTime, nullable=True)
    created_at = Column(DateTime, default=datetime.utcnow)
    updated_at = Column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)

    interactions = relationship("Interaction", back_populates="user")


class Interaction(Base):
    __tablename__ = "interactions"

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    user_id = Column(UUID(as_uuid=True), ForeignKey("users.id"), nullable=False)
    nudge_text = Column(Text, nullable=True)
    response_text = Column(Text, nullable=True)
    completed = Column(Boolean, default=False)
    category = Column(String(50), nullable=True)  # sleep, nutrition, movement, stress
    delivery_time = Column(String(10), nullable=True)  # MORNING or EVENING
    scheduled_time = Column(DateTime, nullable=True)
    responded_at = Column(DateTime, nullable=True)
    is_medical_request = Column(Boolean, default=False, nullable=False, server_default="false")
    created_at = Column(DateTime, default=datetime.utcnow)

    user = relationship("User", back_populates="interactions")
