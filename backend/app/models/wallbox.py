from datetime import datetime

from sqlalchemy import DateTime, String
from sqlalchemy.orm import Mapped, mapped_column

from app.database import Base
from app.utils.utc import utc_now


class Wallbox(Base):
    """
    Name einer Wallbox für Ladevorgänge und Rechnungen. Vorrang hat der
    eigene Name, sonst gilt der Name aus der Hager Cloud, sonst eine
    Kurzform der technischen ID ("ID: ..XXXXX").
    """

    __tablename__ = "wallboxes"

    id: Mapped[int] = mapped_column(primary_key=True)

    # technische ID beim Hersteller (ändert sich bei Gerätetausch)
    wallbox_id: Mapped[str] = mapped_column(
        String(64),
        nullable=False,
        unique=True,
    )

    # Name laut Hager Cloud (beim Abruf aktualisiert)
    hager_name: Mapped[str | None] = mapped_column(
        String(100),
        nullable=True,
    )

    # eigener Name, vom Administrator vergeben
    custom_name: Mapped[str | None] = mapped_column(
        String(100),
        nullable=True,
    )

    created_at: Mapped[datetime] = mapped_column(
        DateTime,
        nullable=False,
        default=utc_now,
    )

    updated_at: Mapped[datetime] = mapped_column(
        DateTime,
        nullable=False,
        default=utc_now,
        onupdate=utc_now,
    )
