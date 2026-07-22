from datetime import datetime

from sqlalchemy import DateTime, Integer
from sqlalchemy.orm import Mapped, mapped_column

from app.database import Base

from app.utils.utc import utc_now


class ImportState(Base):

    __tablename__ = "import_state"

    id: Mapped[int] = mapped_column(
        Integer,
        primary_key=True
    )

    last_successful_import: Mapped[datetime | None] = mapped_column(
        DateTime,
        nullable=True
    )

    created_at: Mapped[datetime] = mapped_column(
        DateTime,
        default=utc_now
    )

    updated_at: Mapped[datetime] = mapped_column(
        DateTime,
        default=utc_now,
        onupdate=utc_now
    )
