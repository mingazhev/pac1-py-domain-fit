from __future__ import annotations

from collections.abc import Mapping, Sequence
from dataclasses import dataclass
from typing import Literal

from application.ports import RecordResolutionPort
from domain.accounts import Account, Contact, resolve_account_relationship


@dataclass(frozen=True, slots=True)
class ContactLookupQueryResult:
    status: Literal["resolved", "clarify_missing"]
    message: str
    summary: str
    grounding_refs: tuple[str, ...]


def _account_row(account: Account) -> dict[str, str]:
    return {
        "account_id": str(account.account_id or "").strip(),
        "legal_name": str(account.legal_name or "").strip(),
        "display_name": str(account.display_name or "").strip(),
        "name": str(account.display_name or account.legal_name or "").strip(),
        "industry": str(account.industry or "").strip(),
        "country": str(account.country or "").strip(),
        "city": str(account.city or "").strip(),
    }


def _contact_row(contact: Contact) -> dict[str, str]:
    return {
        "contact_id": str(contact.contact_id or "").strip(),
        "full_name": str(contact.full_name or "").strip(),
        "display_name": str(contact.full_name or "").strip(),
        "name": str(contact.full_name or "").strip(),
        "email": str(contact.email or "").strip(),
        "title": str(contact.title or "").strip(),
        "account_id": str(contact.account_id or "").strip(),
    }


def _extract_contact_answer(record: Mapping[str, object], output_field: str) -> str:
    if output_field == "title":
        return str(record.get("title") or "").strip()
    if output_field == "full_name":
        return str(
            record.get("full_name")
            or record.get("display_name")
            or record.get("name")
            or ""
        ).strip()
    return str(record.get("email") or "").strip()


def resolve_contact_lookup_query(
    accounts: Sequence[Account],
    contacts: Sequence[Contact],
    *,
    query: str,
    relationship_role: Literal[
        "direct", "primary_contact", "account_manager"
    ] = "direct",
    output_field: Literal["email", "full_name", "title"] = "email",
    notes: Sequence[str] = (),
    fallback_refs: Sequence[str] = (),
    record_resolution_port: RecordResolutionPort | None = None,
) -> ContactLookupQueryResult | None:
    if not str(query or "").strip() or (relationship_role == "direct" and not contacts):
        return None

    candidate: Mapping[str, object] | None = None
    summary = "resolved CRM contact deterministically"

    if relationship_role == "direct":
        contact_rows = tuple(_contact_row(contact) for contact in contacts)
        if len(contact_rows) == 1:
            candidate = contact_rows[0]
            status = "resolved"
        else:
            resolver = (
                record_resolution_port.resolve_contact_candidate
                if record_resolution_port is not None
                else None
            )
            if resolver is None:
                return None
            resolution = resolver(contact_rows, query, notes)
            candidate = resolution.candidate
            status = resolution.status
        if status != "resolved" or candidate is None:
            return ContactLookupQueryResult(
                status="clarify_missing",
                message=(
                    "Multiple contacts matched the request; clarification is required."
                    if status == "clarify_multiple"
                    else "Could not identify a unique contact from the structured CRM records."
                ),
                summary="contact lookup requires clarification",
                grounding_refs=tuple(
                    dict.fromkeys(
                        str(ref) for ref in fallback_refs if str(ref or "").strip()
                    )
                ),
            )
        candidate = resolution.candidate
    else:
        if not accounts or not contacts:
            return None
        account_rows = tuple(_account_row(account) for account in accounts)
        if len(account_rows) == 1:
            account_candidate = account_rows[0]
            account_status = "resolved"
        else:
            resolver = (
                record_resolution_port.resolve_account_candidate
                if record_resolution_port is not None
                else None
            )
            if resolver is None:
                return None
            account_resolution = resolver(account_rows, query, notes)
            account_candidate = account_resolution.candidate
            account_status = account_resolution.status
        if account_status != "resolved" or account_candidate is None:
            return ContactLookupQueryResult(
                status="clarify_missing",
                message=(
                    "Multiple accounts matched the request; clarification is required."
                    if account_status == "clarify_multiple"
                    else "Could not identify a unique account from the structured CRM records."
                ),
                summary="relationship contact lookup requires account clarification",
                grounding_refs=tuple(
                    dict.fromkeys(
                        str(ref) for ref in fallback_refs if str(ref or "").strip()
                    )
                ),
            )
        typed_account = _typed_account_for_candidate(accounts, account_candidate)
        if typed_account is not None:
            relationship_decision = (
                resolve_account_relationship(
                    typed_account, contacts, role="primary_contact"
                )
                if relationship_role == "primary_contact"
                else resolve_account_relationship(
                    typed_account, contacts, role="account_manager"
                )
            )
            if (
                relationship_decision.status == "resolved"
                and relationship_decision.contact is not None
            ):
                candidate = _contact_row(relationship_decision.contact)
            if candidate is None:
                return ContactLookupQueryResult(
                    status="clarify_missing",
                    message=(
                        "Could not identify a unique primary contact from the structured CRM records."
                        if relationship_role == "primary_contact"
                        else "Could not identify a unique account manager from the structured CRM records."
                    ),
                    summary="relationship contact lookup requires clarification",
                    grounding_refs=tuple(
                        dict.fromkeys(
                            str(ref) for ref in fallback_refs if str(ref or "").strip()
                        )
                    ),
                )
        summary = (
            "resolved primary contact deterministically"
            if relationship_role == "primary_contact"
            else "resolved account manager deterministically"
        )

    answer = _extract_contact_answer(candidate or {}, output_field)
    if not answer:
        return ContactLookupQueryResult(
            status="clarify_missing",
            message="The structured CRM contact record did not contain the requested output field.",
            summary="contact lookup output field missing",
            grounding_refs=tuple(
                dict.fromkeys(
                    str(ref) for ref in fallback_refs if str(ref or "").strip()
                )
            ),
        )
    return ContactLookupQueryResult(
        status="resolved",
        message=answer,
        summary=summary,
        grounding_refs=tuple(
            dict.fromkeys(str(ref) for ref in fallback_refs if str(ref or "").strip())
        ),
    )


def render_contact_lookup_result(
    candidate: Mapping[str, object],
    *,
    output_field: Literal["email", "full_name", "title"] = "email",
    fallback_refs: Sequence[str] = (),
    summary: str = "resolved CRM contact via closed-set candidate selection",
) -> ContactLookupQueryResult:
    answer = _extract_contact_answer(candidate, output_field)
    grounding_refs = tuple(
        dict.fromkeys(str(ref) for ref in fallback_refs if str(ref or "").strip())
    )
    if not answer:
        return ContactLookupQueryResult(
            status="clarify_missing",
            message="The structured CRM contact record did not contain the requested output field.",
            summary="contact lookup output field missing",
            grounding_refs=grounding_refs,
        )
    return ContactLookupQueryResult(
        status="resolved",
        message=answer,
        summary=summary,
        grounding_refs=grounding_refs,
    )


def _typed_account_for_candidate(
    accounts: Sequence[Account],
    candidate: Mapping[str, object],
) -> Account | None:
    account_id = str(candidate.get("account_id") or "").strip()
    legal_name = str(candidate.get("legal_name") or "").strip().lower()
    display_name = str(candidate.get("display_name") or "").strip().lower()
    for account in accounts:
        if account_id and str(account.account_id or "").strip() == account_id:
            return account
        if legal_name and str(account.legal_name or "").strip().lower() == legal_name:
            return account
        if display_name and str(account.display_name or "").strip().lower() == display_name:
            return account
    return None
