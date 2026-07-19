from datetime import datetime

from sqlalchemy import DateTime, Numeric
from sqlalchemy.orm import Mapped, mapped_column

from app.database import Base


class EnergyPrice(Base):

    __tablename__ = "energy_prices"

    id: Mapped[int] = mapped_column(
        primary_key=True
    )

    # Zeitpunkt, ab dem dieser Tarif gilt
    valid_from: Mapped[datetime] = mapped_column(
        DateTime,
        nullable=False
    )

    # Netto-Preis je kWh Netzbezug
    grid_price_net: Mapped[float] = mapped_column(
        Numeric(10, 4),
        nullable=False
    )

    # Netto-Preis je kWh PV-Strom
    pv_price_net: Mapped[float] = mapped_column(
        Numeric(10, 4),
        nullable=False
    )

    # Umsatzsteuer als Prozentwert, z.B. 19.0
    vat_rate: Mapped[float] = mapped_column(
        Numeric(5, 2),
        nullable=False
    )

    created_at: Mapped[datetime] = mapped_column(
        DateTime,
        default=datetime.utcnow
    )

    updated_at: Mapped[datetime] = mapped_column(
        DateTime,
        default=datetime.utcnow,
        onupdate=datetime.utcnow
    )
