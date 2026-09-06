DEFAULT_HEADER = "Datum;Avisierungstext;Gutschrift in CHF;Lastschrift in CHF;Label;Kategorie;Valuta;Saldo in CHF"


def build_export(data_rows: list[str], header: str = DEFAULT_HEADER, with_disclaimer: bool = True) -> str:
    """Assemble a synthetic PostFinance "Bewegungen" export around given data rows.

    Mirrors the real export's structure: a metadata preamble, a blank line,
    the header, another blank line, the data rows, a blank line, and a
    trailing disclaimer -- without embedding any real personal data.
    """
    lines = [
        'Datum von:;="01.01.2026"',
        'Datum bis:;="31.01.2026"',
        'Kategorie:;="Alle"',
        'Konto:;="CH0000000000000000000"',
        'Währung:;="CHF"',
        "",
        header,
        "",
        *data_rows,
    ]
    if with_disclaimer:
        lines += [
            "",
            "Disclaimer:",
            "Der Dokumentinhalt wurde durch Filtereinstellungen der Kund:innen generiert.",
        ]
    return "\r\n".join(lines) + "\r\n"


def row(
    date="15.01.2026",
    desc="TWINT Kauf/Dienstleistung Test Shop",
    credit="",
    debit="-10",
    label="",
    kategorie="Einkaufen // Supermärkte",
    valuta=None,
    saldo="1000",
) -> str:
    if valuta is None:
        valuta = date
    return f'{date};"{desc}";{credit};{debit};{label};{kategorie};{valuta};{saldo}'


CREDIT_CARD_HEADER = "Rechnungsperiode;Buchungsdatum;Einkaufsdatum;Buchungsdetails;Gutschrift in CHF;Lastschrift in CHF;Label;Kategorie"


def build_credit_card_export(
    data_rows: list[str], header: str = CREDIT_CARD_HEADER, with_disclaimer: bool = True
) -> str:
    """Assemble a synthetic PostFinance credit card statement ("Kreditkartenübersicht") export.

    Mirrors the real export's structure: a metadata preamble, a blank line,
    the header, another blank line, the data rows, a blank line, and a
    trailing disclaimer -- without embedding any real personal data.
    """
    lines = [
        "Kartenkonto:;0000 0000 0000 0000",
        "Karte:;XXXX XXXX XXXX 0000 PostFinance Mastercard Standard",
        "Karteninhaber:;TEST CARDHOLDER",
        'Kategorie:;="Alle"',
        "",
        header,
        "",
        *data_rows,
    ]
    if with_disclaimer:
        lines += [
            "",
            "Disclaimer:",
            "Der Dokumentinhalt wurde durch Filtereinstellungen der Kund:innen generiert.",
        ]
    return "\r\n".join(lines) + "\r\n"


def credit_card_row(
    rechnungsperiode="Aktuelle Rechnungsperiode",
    buchungsdatum="15.01.2026",
    einkaufsdatum="14.01.2026",
    desc="Apple Pay - Test Shop AG          Zuerich",
    credit="",
    debit="-10",
    label="",
    kategorie="Einkaufen // Sonstiges Einkaufen",
) -> str:
    return (
        f"{rechnungsperiode};{buchungsdatum};{einkaufsdatum};"
        f'"{desc}";{credit};{debit};{label};{kategorie}'
    )
