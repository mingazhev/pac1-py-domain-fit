"""Finance identity, authorization, and settlement models.

These models cover party reconciliation, payment authorization gates,
settlement evidence, vendor first-class identity, and record series
semantics. They are policy-level objects — they do not replace the
canonical `10_entities/cast/` identity graph; they map finance display
names to that canonical layer.
"""
from __future__ import annotations

from dataclasses import dataclass, field
import re
from collections.abc import Mapping, Sequence
from typing import Literal

from .settlement import SettlementChannel

# ---------------------------------------------------------------------------
# Party reconciliation
# ---------------------------------------------------------------------------


@dataclass(frozen=True, slots=True)
class PurchaseIdPrefix:
    """Typed prefix for recurring purchase ids used by downstream emitters.

    Purchase ids such as ``prc-100277`` encode a stable prefix that downstream
    processing lanes are expected to mirror.  The prefix is domain data, not a
    runtime string trick, because the benchmark already relies on deterministic
    repair of mismatched emitter prefixes.
    """

    value: str

    @classmethod
    def from_purchase_id(cls, purchase_id: object) -> PurchaseIdPrefix | None:
        text = str(purchase_id or "").strip()
        if not text:
            return None
        match = re.match(r"^([A-Za-z][A-Za-z0-9_-]*-)\d", text)
        if match is None:
            return None
        return cls(value=match.group(1).lower())


def resolve_purchase_id_prefix(
    records: Sequence[Mapping[str, object]],
) -> PurchaseIdPrefix | None:
    """Resolve the oldest canonical purchase-id prefix from structured records."""

    for record in sorted(
        (record for record in records if isinstance(record, Mapping)),
        key=lambda record: str(record.get("created_at") or ""),
    ):
        prefix = PurchaseIdPrefix.from_purchase_id(record.get("purchase_id"))
        if prefix is not None:
            return prefix
    return None


@dataclass(frozen=True, slots=True)
class PartyReference:
    """Reconciles a finance display name with a canonical entity id.

    Finance records carry counterparty display names (e.g. "Helios BV") that
    may not be globally unique.  ``PartyReference`` is the explicit bridge from
    the display string to a canonical cast or account identity — so resolvers
    do not silently conflate "Helios" with an unrelated "Helios Logistics".
    """

    display_name: str
    canonical_entity_id: str = ""
    match_confidence: Literal["exact", "fuzzy", "unresolved"] = "unresolved"
    source: Literal["cast", "accounts", "manual"] = "manual"

    def is_exact(self) -> bool:
        return self.match_confidence == "exact" and bool(self.canonical_entity_id)


# ---------------------------------------------------------------------------
# Vendor
# ---------------------------------------------------------------------------


@dataclass(frozen=True, slots=True)
class Vendor:
    """First-class vendor entity for finance counterparties.

    Vendors are recurring expense-side counterparties (suppliers, service
    providers) that appear frequently enough in the finance corpus to deserve
    stable identity.  A Vendor is *not* a cast record replacement — it is a
    finance-domain adapter that anchors recurring bill counterparties to a
    canonical resolution path.
    """

    vendor_id: str
    canonical_name: str
    display_aliases: tuple[str, ...] = ()
    party_reference: PartyReference | None = None
    default_record_type: Literal["bill", "invoice", "any"] = "bill"
    notes: str = ""

    def matches_name(self, value: str) -> bool:
        normalized = value.strip().lower()
        if not normalized:
            return False
        if normalized == self.canonical_name.lower():
            return True
        return any(normalized == alias.lower() for alias in self.display_aliases)


# ---------------------------------------------------------------------------
# Finance record series (repeating identity)
# ---------------------------------------------------------------------------


@dataclass(frozen=True, slots=True)
class DocumentOccurrenceKey:
    """Unique occurrence key for a repeating finance document.

    ``invoice_number`` alone is not globally unique — the same number appears
    across different counterparties and time windows.  This key combines the
    minimal fields needed to distinguish one occurrence from another without
    fabricating a synthetic global id.
    """

    reference_number: str
    counterparty: str
    record_type: Literal["invoice", "bill"]
    occurrence_date: str = ""

    def as_tuple(self) -> tuple[str, str, str, str]:
        return (
            self.reference_number,
            self.counterparty.strip().lower(),
            self.record_type,
            self.occurrence_date,
        )


@dataclass(frozen=True, slots=True)
class FinanceRecordSeries:
    """Models a series of repeating finance documents (recurring invoices, etc.).

    Repeating ``invoice_number`` / ``bill_id`` values are treated as a series
    rather than as globally unique record identity.  Each member of the series
    is addressed by a ``DocumentOccurrenceKey``.
    """

    series_id: str
    counterparty: str
    record_type: Literal["invoice", "bill"]
    occurrence_keys: tuple[DocumentOccurrenceKey, ...] = ()
    recurrence_label: str = ""

# ---------------------------------------------------------------------------
# Payment authorization gate
# ---------------------------------------------------------------------------


@dataclass(frozen=True, slots=True)
class PaymentAuthorization:
    """Policy gate that must be satisfied before a bank-action mutation fires.

    Finance mutations that trigger real payment (bank transfer, card charge,
    settlement) must pass through an explicit authorization gate rather than
    proceeding on task wording alone.  This object encodes *what* authorized
    the action, *who* authorized it, and *which* finance record it covers.

    The gate result is either ``approved`` (all checks passed) or ``blocked``
    (one or more checks failed — reason is explicit, not buried in fallback).
    """

    record_path: str
    authorized_by: str
    authorization_kind: Literal[
        "explicit_user_confirmation",
        "workflow_policy",
        "pre_authorized_series",
    ]
    gate_result: Literal["approved", "blocked"] = "blocked"
    block_reason: str = ""
    requires_settlement_evidence: bool = True

    def is_approved(self) -> bool:
        return self.gate_result == "approved"

    @classmethod
    def blocked(cls, record_path: str, reason: str) -> PaymentAuthorization:
        return cls(
            record_path=record_path,
            authorized_by="",
            authorization_kind="explicit_user_confirmation",
            gate_result="blocked",
            block_reason=reason,
            requires_settlement_evidence=True,
        )


# ---------------------------------------------------------------------------
# Settlement evidence
# ---------------------------------------------------------------------------


@dataclass(frozen=True, slots=True)
class SettlementEvidence:
    """Evidence that a payment has actually settled.

    Finance mutations that mark a record as paid must carry settlement evidence
    rather than inferring completion from inbox preflight alone.  Settlement
    evidence comes from bank confirmation, payment reference, or explicit user
    attestation — not from the task wording.
    """

    record_path: str
    settled_date: str
    confirmation_reference: str = ""
    channel: SettlementChannel = SettlementChannel.MANUAL_ATTESTATION
    attested_by: str = ""
    notes: str = ""

    def is_bank_confirmed(self) -> bool:
        return self.channel == "bank_transfer" and bool(self.confirmation_reference)

    def is_attested_only(self) -> bool:
        return self.channel == "manual_attestation"
