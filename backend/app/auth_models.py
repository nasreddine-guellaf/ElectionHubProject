import uuid
from datetime import datetime

from sqlalchemy import Boolean, CheckConstraint, DateTime, ForeignKey, Integer, String, func
from sqlalchemy.orm import Mapped, mapped_column

from app.database import Base
from app.domain_models import IdentityMixin


class Account(Base):
    __tablename__ = "accounts"
    __table_args__ = (CheckConstraint("username = lower(username)", name="ck_account_username"),)
    user_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("user_references.id"), primary_key=True)
    username: Mapped[str] = mapped_column(String(80), unique=True)
    password_hash: Mapped[str] = mapped_column(String(300))
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())


class AuthSession(Base):
    __tablename__ = "auth_sessions"
    token_hash: Mapped[str] = mapped_column(String(64), primary_key=True)
    user_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("user_references.id"), index=True)
    expires_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), index=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())


class AuthAudit(IdentityMixin, Base):
    __tablename__ = "auth_audit"
    actor_id: Mapped[uuid.UUID | None] = mapped_column(ForeignKey("user_references.id"))
    target_id: Mapped[uuid.UUID | None] = mapped_column(ForeignKey("user_references.id"))
    action: Mapped[str] = mapped_column(String(50))
    resource: Mapped[str | None] = mapped_column(String(300))


class RateLimit(Base):
    __tablename__ = "auth_rate_limits"
    key: Mapped[str] = mapped_column(String(64), primary_key=True)
    attempts: Mapped[int] = mapped_column(Integer)
    expires_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), index=True)


class Citizen(Base):
    __tablename__ = "citizens"
    __table_args__ = (CheckConstraint("synthetic_cin LIKE 'DEMO-CIN-%'", name="ck_citizen_demo"),)
    user_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("user_references.id"), primary_key=True)
    synthetic_cin: Mapped[str] = mapped_column(String(50), unique=True)
    polling_station_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("polling_stations.id"))
    mock_recipient: Mapped[str] = mapped_column(String(80))


class OtpChallenge(IdentityMixin, Base):
    __tablename__ = "otp_challenges"
    __table_args__ = (CheckConstraint("attempts >= 0 AND attempts <= 5", name="ck_otp_attempts"),)
    user_id: Mapped[uuid.UUID | None] = mapped_column(ForeignKey("user_references.id"), index=True)
    code_digest: Mapped[str] = mapped_column(String(64))
    expires_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), index=True)
    attempts: Mapped[int] = mapped_column(Integer, default=0)
    consumed: Mapped[bool] = mapped_column(Boolean, default=False)
