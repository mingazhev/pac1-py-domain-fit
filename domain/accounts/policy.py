from __future__ import annotations

from dataclasses import dataclass
from typing import Literal, Sequence

from .account import Account
from .contact import Contact


RelationshipRole = Literal["primary_contact", "account_manager"]


@dataclass(frozen=True, slots=True)
class RelationshipLookupDecision:
    status: Literal["resolved", "missing", "ambiguous"]
    contact: Contact | None = None


@dataclass(frozen=True, slots=True)
class PrimaryContact:
    account: Account
    contact: Contact


@dataclass(frozen=True, slots=True)
class AccountManager:
    account: Account
    contact: Contact


@dataclass(frozen=True, slots=True)
class CanonicalContactGateDecision:
    status: Literal["resolved", "missing", "ambiguous"]
    contact: Contact | None = None
    email: str = ""


def resolve_account_relationship(
    account: Account,
    contacts: Sequence[Contact],
    *,
    role: RelationshipRole,
) -> RelationshipLookupDecision:
    target_id = (
        account.primary_contact_id
        if role == "primary_contact"
        else account.account_manager_id
    )
    if not str(target_id or "").strip():
        return RelationshipLookupDecision(status="missing")
    matches = [contact for contact in contacts if contact.contact_id == target_id]
    if not matches:
        return RelationshipLookupDecision(status="missing")
    if len(matches) > 1:
        return RelationshipLookupDecision(status="ambiguous")
    return RelationshipLookupDecision(status="resolved", contact=matches[0])


def resolve_primary_contact(
    account: Account, contacts: Sequence[Contact]
) -> PrimaryContact | None:
    decision = resolve_account_relationship(account, contacts, role="primary_contact")
    if decision.status != "resolved" or decision.contact is None:
        return None
    return PrimaryContact(account=account, contact=decision.contact)


def resolve_account_manager(
    account: Account, contacts: Sequence[Contact]
) -> AccountManager | None:
    decision = resolve_account_relationship(account, contacts, role="account_manager")
    if decision.status != "resolved" or decision.contact is None:
        return None
    return AccountManager(account=account, contact=decision.contact)


def resolve_canonical_contact_email(
    contacts: Sequence[Contact],
    sender_email: str,
) -> CanonicalContactGateDecision:
    normalized_email = str(sender_email or "").strip().lower()
    if not normalized_email:
        return CanonicalContactGateDecision(status="missing")

    matches = [
        contact
        for contact in contacts
        if str(contact.email or "").strip().lower() == normalized_email
    ]
    if not matches:
        return CanonicalContactGateDecision(status="missing")

    unique_contact_ids = {
        str(contact.contact_id or "").strip().lower() for contact in matches
    }
    unique_emails = {
        str(contact.email or "").strip()
        for contact in matches
        if str(contact.email or "").strip()
    }
    if len(unique_contact_ids) != 1 or len(unique_emails) != 1:
        return CanonicalContactGateDecision(status="ambiguous")

    matched = matches[0]
    return CanonicalContactGateDecision(
        status="resolved",
        contact=matched,
        email=str(matched.email or "").strip(),
    )
