"""Typed value objects for finance record references.

`FinanceRecord` historically stored `related_entity`, `project`, and the
reference identifier as raw strings. These value objects provide explicit
domain-level identity for those fields without forcing a loader rewrite —
loaders still populate the string columns, but domain consumers can request
typed references instead of re-normalizing strings at every call site.
"""
from __future__ import annotations

from dataclasses import dataclass
from typing import Literal


@dataclass(frozen=True, slots=True)
class ReferenceNumber:
    """Typed reference identifier for a finance record.

    Bills and invoices both carry a reference number. The underlying value is
    the same string, but the role differs: an invoice reference is issued by
    the workspace, a bill reference is issued by the counterparty. This value
    object preserves that distinction so callers do not conflate them.
    """

    value: str
    role: Literal["invoice_number", "bill_id"]

    def __post_init__(self) -> None:
        normalized = self.value.strip()
        object.__setattr__(self, "value", normalized)

    def is_present(self) -> bool:
        return bool(self.value)

    @classmethod
    def for_invoice(cls, value: str | None) -> ReferenceNumber | None:
        text = str(value or "").strip()
        if not text:
            return None
        return cls(value=text, role="invoice_number")

    @classmethod
    def for_bill(cls, value: str | None) -> ReferenceNumber | None:
        text = str(value or "").strip()
        if not text:
            return None
        return cls(value=text, role="bill_id")


@dataclass(frozen=True, slots=True)
class EntityReference:
    """Typed display-name reference for a `related_entity` column.

    Finance frontmatter records `related_entity` as a display name (e.g.
    "Nina Schreiber"), not a canonical cast id. This value object surfaces the
    display form as domain data while recording that it is not yet reconciled
    to a canonical entity. Reconciliation belongs to `PartyReference` (see
    `identity.py`); this type is deliberately the weaker, display-only rung.
    """

    display_name: str

    def __post_init__(self) -> None:
        object.__setattr__(self, "display_name", self.display_name.strip())

    def is_present(self) -> bool:
        return bool(self.display_name)

    @classmethod
    def from_raw(cls, value: object) -> EntityReference | None:
        text = str(value or "").strip()
        if not text:
            return None
        return cls(display_name=text)


@dataclass(frozen=True, slots=True)
class ProjectReference:
    """Typed project-name reference for the `project` column on a finance record.

    Finance records attach a project by display name. Canonical project
    identity lives in `domain/projects/`. This value object is the typed
    hand-off — callers take it as a typed reference and reconcile to a
    canonical project id elsewhere, instead of re-normalizing raw strings at
    every selector call site.
    """

    name: str

    def __post_init__(self) -> None:
        object.__setattr__(self, "name", self.name.strip())

    def is_present(self) -> bool:
        return bool(self.name)

    @classmethod
    def from_raw(cls, value: object) -> ProjectReference | None:
        text = str(value or "").strip()
        if not text:
            return None
        return cls(name=text)
