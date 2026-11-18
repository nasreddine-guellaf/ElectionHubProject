from datetime import datetime
from typing import Literal
from uuid import UUID

from pydantic import BaseModel, ConfigDict


class PollingStationRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: UUID
    code: str
    name: str
    registered_voters: int
    created_at: datetime


class PollingStationPage(BaseModel):
    items: list[PollingStationRead]
    total: int
    limit: int
    offset: int
    data_kind: Literal["synthetic"] = "synthetic"


class HealthRead(BaseModel):
    status: Literal["ok"] = "ok"
    database: Literal["ok"] = "ok"
    schema_version: str
    environment: Literal["local", "test"]
