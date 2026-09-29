import re

import pytest

from app.i18n import de, en, normalize_language, translate


PLACEHOLDER = re.compile(r"\{(\w+)\}")


def test_catalogs_have_the_same_keys() -> None:
    assert set(de.MESSAGES) == set(en.MESSAGES)


@pytest.mark.parametrize("key", sorted(de.MESSAGES))
def test_placeholders_match(key: str) -> None:
    assert set(PLACEHOLDER.findall(de.MESSAGES[key])) == set(
        PLACEHOLDER.findall(en.MESSAGES[key])
    )


def test_unknown_language_falls_back_to_german() -> None:
    assert normalize_language("fr") == "de"
    assert normalize_language(None) == "de"
    assert translate("fr", "item.postage") == "Briefporto"


def test_german_item_texts_are_unchanged() -> None:
    # Wortlaut wie vor der Mehrsprachigkeit (bestehende Rechnungen)
    assert translate(
        "de",
        "item.chargingSession",
        start="01.07.2026 07:45",
        station="WB2",
    ) == "Ladevorgang 01.07.2026 07:45 an WB2"
    assert translate(
        "de",
        "item.monthlyFee",
        card="Karte 1",
        month="Juli",
        year=2026,
        proration=translate("de", "item.proration", days="15,5", total=31),
    ) == "Monatsgebühr Ladekarte Karte 1 - Juli 2026 (anteilig 15,5/31 Tage)"
