import uuid
from datetime import datetime

from sqlalchemy import CheckConstraint, DateTime, Integer, String, Uuid, func
from sqlalchemy.orm import Mapped, mapped_column

from app.database import Base


class PollingStation(Base):
    __tablename__ = "polling_stations"
    __table_args__ = (
        CheckConstraint("registered_voters >= 0", name="ck_station_registered_nonnegative"),
        CheckConstraint("length(trim(code)) > 0", name="ck_station_code_nonempty"),
        CheckConstraint("length(trim(name)) > 0", name="ck_station_name_nonempty"),
    )

    id: Mapped[uuid.UUID] = mapped_column(Uuid, primary_key=True, default=uuid.uuid4)
    code: Mapped[str] = mapped_column(String(40), unique=True, nullable=False)
    name: Mapped[str] = mapped_column(String(200), nullable=False)
    registered_voters: Mapped[int] = mapped_column(Integer, nullable=False)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=func.now()
    )
