from datetime import datetime

from pydantic import BaseModel, Field, field_validator


class WallboxResponse(BaseModel):
    id: int
    wallbox_id: str
    hager_name: str | None
    custom_name: str | None
    # eigener Name, sonst Name aus der Hager Cloud, sonst "ID: ..XXXXX"
    display_name: str
    session_count: int
    last_session_at: datetime | None


class WallboxUpdate(BaseModel):
    # leer oder null = keinen eigenen Namen verwenden
    custom_name: str | None = Field(default=None, max_length=100)

    @field_validator("custom_name", mode="before")
    @classmethod
    def normalize(cls, value: object) -> object:
        if isinstance(value, str):
            value = value.strip()
            return value or None
        return value


class WallboxUpdateResult(WallboxResponse):
    # Zahl der nicht abgerechneten Ladevorgänge, die den Namen übernommen haben
    updated_sessions: int
