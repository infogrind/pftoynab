"""Interactive prompts: the YNAB Memo field, and names for TWINT contacts.

The Memo that ``parser.py`` derives from PostFinance's "Label" and
"Kategorie" columns is often not useful (the auto-assigned "Kategorie" in
particular). ``run_interactive_memo`` lets the user type their own Memo for
each transaction instead, one at a time in date order, discarding whatever
was derived from the input.

TWINT person-to-person transfers only carry the counterparty's phone
number, which YNAB strips from payees on import. ``ask_twint_contact_names``
asks for a name for each number not yet in the config.
"""

from __future__ import annotations

from collections.abc import Callable

from .errors import PftoynabError
from .parser import MAX_MEMO_LEN, Transaction, sanitize_field, signed_amount


def run_interactive_memo(transactions: list[Transaction]) -> list[str]:
    warnings: list[str] = []
    total = len(transactions)
    print(f"Interactive memo entry for {total} transaction(s); press Enter to leave one empty.")

    for i, t in enumerate(transactions, start=1):
        amount = signed_amount(t)
        print(f"[{i}/{total}] {t.txn_date.isoformat()}  {t.payee}  {amount:.2f}")
        try:
            raw = input("> ")
        except EOFError as e:
            raise PftoynabError("interactive memo entry aborted (end of input)") from e
        except KeyboardInterrupt as e:
            raise PftoynabError("interactive memo entry aborted") from e
        t.memo = sanitize_field(raw, MAX_MEMO_LEN, "memo", i, warnings)

    return warnings


def ask_twint_contact_names(
    transactions: list[Transaction],
    contacts: dict[str, str],
    save_contact: Callable[[str, str], None],
) -> dict[str, str]:
    """Ask for a name for each TWINT P2P number not in ``contacts``.

    Numbers are asked about once each, in order of first appearance, listing
    every transaction with that number so it can be looked up in online
    banking. Each entered name is passed to ``save_contact`` right away, so
    names already entered survive if the run is aborted later. Pressing
    Enter skips a number, leaving its payee as parsed. Returns the newly
    named numbers.
    """
    by_number: dict[str, list[Transaction]] = {}
    for t in transactions:
        if t.twint_number is not None and t.twint_number not in contacts:
            by_number.setdefault(t.twint_number, []).append(t)
    if not by_number:
        return {}

    total = len(by_number)
    print(
        f"{total} TWINT phone number(s) without a name in the config; enter a name for "
        "each (Enter to skip). YNAB drops numbers from payees on import."
    )
    new_contacts: dict[str, str] = {}
    for i, (number, group) in enumerate(by_number.items(), start=1):
        print(f"[{i}/{total}] {number}")
        for t in group:
            print(f"    {t.txn_date.isoformat()}  {t.payee}  {signed_amount(t):.2f}")
        try:
            raw = input("Name> ")
        except EOFError as e:
            raise PftoynabError("TWINT contact entry aborted (end of input)") from e
        except KeyboardInterrupt as e:
            raise PftoynabError("TWINT contact entry aborted") from e
        name = " ".join(raw.split())
        if not name:
            continue
        save_contact(number, name)
        new_contacts[number] = name

    return new_contacts
