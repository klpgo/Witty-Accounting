"""
Schutz vor einem Wechsel der Zeitzone nach dem ersten Import.

Ladevorgänge, Leistungszeiträume und Tarifbeginne werden als Ortszeit
ohne Zeitzonenangabe gespeichert. Würde die Zeitzone der Installation
(Umgebungsvariable TZ) später geändert, verschöbe sich die Bedeutung
aller bestehenden Daten stillschweigend. Jeder Mandant hält deshalb beim
ersten Import fest, in welcher Zone seine Daten liegen; weicht die
eingestellte Zone davon ab, werden Importe abgelehnt.
"""
from __future__ import annotations

from sqlalchemy import update
from sqlalchemy.orm import Session

from app.models.global_settings import GlobalSettings
from app.utils.local_time import TIMEZONE_NAME


class DataTimezoneMismatchError(RuntimeError):
    """Die eingestellte Zeitzone passt nicht zu den gespeicherten Daten."""


def ensure_data_timezone(
    db: Session,
    timezone_name: str = TIMEZONE_NAME,
) -> None:
    settings = db.get(GlobalSettings, 1)

    if settings is None:
        return

    stored = settings.data_timezone

    if stored is None:
        # erster Import: aktuelle Zone festhalten (gezieltes UPDATE in
        # eigener Transaktion, siehe MariaDB-Snapshot-Isolation)
        db.commit()
        db.execute(
            update(GlobalSettings)
            .where(GlobalSettings.id == 1, GlobalSettings.data_timezone.is_(None))
            .values(data_timezone=timezone_name)
        )
        db.commit()
        db.expire_all()
        return

    if stored != timezone_name:
        raise DataTimezoneMismatchError(
            f"Die Daten dieses Mandanten liegen in der Zeitzone {stored}, "
            f"eingestellt ist aber {timezone_name}. Bitte beim Container "
            f"TZ wieder auf {stored} setzen – ein Wechsel der "
            "Zeitzone würde alle gespeicherten Zeiten verschieben."
        )
