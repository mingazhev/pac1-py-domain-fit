from __future__ import annotations

from collections.abc import Mapping, Sequence
from typing import Any

from domain.accounts import Account, Contact


def _coerce_strings(value: object) -> tuple[str, ...]:
    if isinstance(value, str):
        parts = [part.strip() for part in value.split(",")]
        return tuple(part for part in parts if part)
    if isinstance(value, Sequence) and not isinstance(value, (str, bytes, bytearray)):
        return tuple(str(item).strip() for item in value if str(item).strip())
    return ()


def account_from_mapping(raw: Mapping[str, Any]) -> Account | None:
    account_id = str(raw.get("account_id") or "").strip()
    legal_name = str(raw.get("legal_name") or "").strip()
    display_name = str(raw.get("display_name") or raw.get("name") or "").strip()
    if not (account_id or legal_name or display_name):
        return None
    return Account(
        account_id=account_id,
        legal_name=legal_name,
        display_name=display_name,
        industry=str(raw.get("industry") or "").strip(),
        country=str(raw.get("country") or "").strip(),
        city=str(raw.get("city") or "").strip(),
        primary_contact_id=str(raw.get("primary_contact_id") or "").strip(),
        account_manager_id=str(raw.get("account_manager_id") or "").strip(),
        tags=_coerce_strings(raw.get("tags")),
    )


def contact_from_mapping(raw: Mapping[str, Any]) -> Contact | None:
    contact_id = str(raw.get("contact_id") or "").strip()
    full_name = str(
        raw.get("full_name") or raw.get("display_name") or raw.get("name") or ""
    ).strip()
    email = str(raw.get("email") or "").strip()
    if not (contact_id or full_name or email):
        return None
    return Contact(
        contact_id=contact_id,
        full_name=full_name,
        email=email,
        title=str(raw.get("title") or "").strip(),
        account_id=str(raw.get("account_id") or "").strip(),
    )


def contacts_from_mappings(
    raw_records: Sequence[Mapping[str, Any]],
) -> tuple[Contact, ...]:
    return tuple(
        contact
        for contact in (contact_from_mapping(raw) for raw in raw_records)
        if contact is not None
    )
