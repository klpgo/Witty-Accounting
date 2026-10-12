from datetime import datetime

from sqlalchemy import DateTime, String
from sqlalchemy.orm import Mapped, mapped_column

from app.database import Base
from app.utils.utc import utc_now


class DeletedChargingSession(Base):
    """
    Merkmale eines gelöschten Ladevorgangs (z. B. nach Löschung eines
    Benutzers), damit Import und Hager-Abgleich ihn nicht erneut anlegen.

    Enthält bewusst keine Energie- oder Kartendaten, sondern nur die
    Merkmale der Dublettenprüfung.
    """

    __tablename__ = "deleted_charging_sessions"

    id: Mapped[int] = mapped_column(
        primary_key=True,
    )

    hager_session_id: Mapped[str | None] = mapped_column(
        String(100),
        nullable=True,
        index=True,
    )

    import_hash: Mapped[str | None] = mapped_column(
        String(64),
        nullable=True,
        index=True,
    )

    start_time: Mapped[datetime] = mapped_column(
        DateTime,
        nullable=False,
        index=True,
    )

    wallbox_id: Mapped[str | None] = mapped_column(
        String(64),
        nullable=True,
    )

    station_id: Mapped[str | None] = mapped_column(
        String(100),
        nullable=True,
    )

    deleted_at: Mapped[datetime] = mapped_column(
        DateTime,
        nullable=False,
        default=utc_now,
    )
