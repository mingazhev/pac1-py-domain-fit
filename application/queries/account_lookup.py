from __future__ import annotations

from collections.abc import Mapping, Sequence
from dataclasses import dataclass
from typing import Literal

from application.ports import RecordResolutionPort
from domain.accounts import Account


@dataclass(frozen=True, slots=True)
class AccountLookupQueryResult:
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


def _extract_account_answer(record: Mapping[str, object], output_field: str) -> str:
    if output_field == "account_id":
        return str(record.get("account_id") or "").strip()
    if output_field == "display_name":
        return str(
            record.get("display_name")
            or record.get("name")
            or record.get("legal_name")
            or ""
        ).strip()
    return str(
        record.get("legal_name")
        or record.get("display_name")
        or record.get("name")
        or ""
    ).strip()


def resolve_account_lookup_query(
    accounts: Sequence[Account],
    *,
    query: str,
    output_field: Literal["legal_name", "display_name", "account_id"] = "legal_name",
    notes: Sequence[str] = (),
    fallback_refs: Sequence[str] = (),
    record_resolution_port: RecordResolutionPort | None = None,
) -> AccountLookupQueryResult | None:
    if not accounts or not str(query or "").strip():
        return None
    rows = tuple(_account_row(account) for account in accounts)
    if len(rows) == 1:
        candidate = rows[0]
        status = "resolved"
    else:
        resolver = (
            record_resolution_port.resolve_account_candidate
            if record_resolution_port is not None
            else None
        )
        if resolver is None:
            return None
        resolution = resolver(rows, query, notes)
        candidate = resolution.candidate
        status = resolution.status
    if status != "resolved" or candidate is None:
        return AccountLookupQueryResult(
            status="clarify_missing",
            message=(
                "Multiple accounts matched the request; clarification is required."
                if status == "clarify_multiple"
                else "Could not identify a unique account from the structured CRM records."
            ),
            summary="account lookup requires clarification",
            grounding_refs=tuple(
                dict.fromkeys(
                    str(ref) for ref in fallback_refs if str(ref or "").strip()
                )
            ),
        )
    answer = _extract_account_answer(candidate, output_field)
    if not answer:
        return AccountLookupQueryResult(
            status="clarify_missing",
            message="The structured CRM account record did not contain the requested output field.",
            summary="account lookup output field missing",
            grounding_refs=tuple(
                dict.fromkeys(
                    str(ref) for ref in fallback_refs if str(ref or "").strip()
                )
            ),
        )
    return AccountLookupQueryResult(
        status="resolved",
        message=answer,
        summary="resolved CRM account deterministically",
        grounding_refs=tuple(
            dict.fromkeys(str(ref) for ref in fallback_refs if str(ref or "").strip())
        ),
    )


def render_account_lookup_result(
    candidate: Mapping[str, Any],
    *,
    output_field: Literal["legal_name", "display_name", "account_id"] = "legal_name",
    fallback_refs: Sequence[str] = (),
    summary: str = "resolved CRM account via closed-set candidate selection",
) -> AccountLookupQueryResult:
    answer = _extract_account_answer(candidate, output_field)
    grounding_refs = tuple(
        dict.fromkeys(str(ref) for ref in fallback_refs if str(ref or "").strip())
    )
    if not answer:
        return AccountLookupQueryResult(
            status="clarify_missing",
            message="The structured CRM account record did not contain the requested output field.",
            summary="account lookup output field missing",
            grounding_refs=grounding_refs,
        )
    return AccountLookupQueryResult(
        status="resolved",
        message=answer,
        summary=summary,
        grounding_refs=grounding_refs,
    )
