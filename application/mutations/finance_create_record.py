from __future__ import annotations

import re
from collections.abc import Sequence
from pathlib import PurePosixPath
from typing import Protocol

from domain.finance import FinanceRecord
from domain.finance.line_item import LineItem
from domain.workspace import DEFAULT_WORKSPACE_LAYOUT

from .finance_markdown import render_finance_markdown
from .result import MutationStepResult


_SLUG_RE = re.compile(r"[^a-z0-9]+")


class FinanceLineItemLike(Protocol):
    item: str
    qty: float
    unit_eur: float


def resolve_finance_create_record(
    finance_records: Sequence[FinanceRecord],
    *,
    action: str,
    record_type: str,
    counterparty: str | None,
    amount: float | None,
    alias: str | None,
    invoice_number: str | None,
    date: str | None,
    project: str | None,
    related_entity: str | None,
    notes: str | None,
    line_items: Sequence[object],
    currency: str,
    finance_root: str | None = None,
) -> tuple[MutationStepResult, str | None, str | None]:
    """Compose a canonical finance record draft. Returns (result, path, content).

    The mutation pipeline writes ``content`` at ``path`` when the
    result is resolved. This keeps the composer pure for testing.
    """

    if action not in {"create_invoice", "create_bill"}:
        return (
            MutationStepResult(
                status="unsupported",
                message=f"finance_create_record does not handle action={action}",
                grounding_refs=(),
                reason_code="finance_create_action_unsupported",
            ),
            None,
            None,
        )

    resolved_record_type = _resolved_record_type(action, record_type)
    resolved_date = _clean_iso_date(date)
    resolved_amount = _compute_amount(amount, line_items)
    resolved_alias = _resolve_alias(alias, counterparty, project)
    resolved_currency = (currency or "eur").strip().lower() or "eur"

    if not resolved_date:
        return _clarify(
            "Finance create requires an explicit ISO date (YYYY-MM-DD).",
            reason_code="finance_create_requires_date",
        )
    if resolved_amount is None:
        return _clarify(
            "Finance create requires an amount (either top-level or via line items).",
            reason_code="finance_create_requires_amount",
        )
    if not resolved_alias:
        return _clarify(
            "Finance create requires a short alias slug for the canonical path.",
            reason_code="finance_create_requires_alias",
        )

    date_slug = resolved_date.replace("-", "_")
    amount_slug = f"{int(round(resolved_amount)):06d}"

    if resolved_record_type == "invoice":
        resolved_number = _resolve_invoice_number(
            invoice_number, finance_records, alias=resolved_alias
        )
        number_slug = resolved_number.lower().replace("-", "_")
        directory = "invoices"
        filename = (
            f"{date_slug}__{resolved_currency}_{amount_slug}__{number_slug}__"
            f"{resolved_alias}.md"
        )
    else:
        resolved_number = None
        directory = "purchases"
        filename = (
            f"{date_slug}__{resolved_currency}_{amount_slug}__bill__"
            f"{resolved_alias}.md"
        )
    resolved_finance_root = _normalize_root(
        finance_root or DEFAULT_WORKSPACE_LAYOUT.primary_finance_root() or "/finance"
    )
    path = f"{resolved_finance_root}/{directory}/{filename}"

    content = _compose_markdown(
        record_type=resolved_record_type,
        invoice_number=resolved_number,
        alias=resolved_alias,
        date=resolved_date,
        total_eur=resolved_amount,
        counterparty=counterparty,
        project=project,
        related_entity=related_entity,
        line_items=line_items,
        notes=notes,
    )

    return (
        MutationStepResult(
            status="resolved",
            message=path,
            grounding_refs=(path,),
            reason_code=(
                "finance_create_invoice_resolved"
                if resolved_record_type == "invoice"
                else "finance_create_bill_resolved"
            ),
        ),
        path,
        content,
    )


def _clarify(message: str, *, reason_code: str) -> tuple[MutationStepResult, None, None]:
    return (
        MutationStepResult(
            status="clarify_missing",
            message=message,
            grounding_refs=(),
            reason_code=reason_code,
        ),
        None,
        None,
    )


def _resolved_record_type(action: str, record_type: str) -> str:
    if action == "create_invoice":
        return "invoice"
    if action == "create_bill":
        return "bill"
    normalized = (record_type or "").strip().lower()
    if normalized in {"invoice", "bill"}:
        return normalized
    return "invoice"


_ISO_DATE_RE = re.compile(r"^\d{4}-\d{2}-\d{2}$")


def _clean_iso_date(date: str | None) -> str | None:
    text = str(date or "").strip()
    if not text:
        return None
    match = _ISO_DATE_RE.match(text[:10])
    return match.group(0) if match else None


def _compute_amount(
    amount: float | None, line_items: Sequence[object]
) -> float | None:
    if amount is not None:
        return float(amount)
    if not line_items:
        return None
    total = 0.0
    seen = False
    for item in line_items:
        qty = float(getattr(item, "qty", 1) or 1)
        unit = float(getattr(item, "unit_eur", 0) or 0)
        if unit <= 0:
            continue
        seen = True
        total += qty * unit
    return total if seen else None


def _slugify(text: str) -> str:
    lowered = str(text or "").strip().lower()
    normalized = _SLUG_RE.sub("_", lowered).strip("_")
    return normalized


def _resolve_alias(
    alias: str | None,
    counterparty: str | None,
    project: str | None,
) -> str:
    for candidate in (alias, project, counterparty):
        slug = _slugify(str(candidate or ""))
        if slug:
            return slug
    return ""


def _resolve_invoice_number(
    invoice_number: str | None,
    existing_records: Sequence[FinanceRecord],
    *,
    alias: str,
) -> str:
    explicit = str(invoice_number or "").strip()
    if explicit:
        normalized = explicit.lower().replace("-", "_")
        match = re.match(r"^(?:inv_?)?(\d+)$", normalized)
        if match:
            return f"inv_{int(match.group(1)):04d}"
        if normalized.startswith("inv_"):
            return normalized
    # Count existing invoice records whose filename slug matches this alias.
    count = 0
    target_alias = alias.lower()
    for record in existing_records:
        path = str(getattr(record, "path", "") or "").lower()
        if not path or "/invoices/" not in path:
            continue
        filename = PurePosixPath(path).name
        # Canonical filename shape: <date>__<cur>_<amt>__inv_NNNN__<alias>.md
        parts = filename.split("__")
        if len(parts) < 4:
            continue
        record_alias = parts[-1].rsplit(".md", 1)[0]
        if record_alias == target_alias:
            count += 1
    return f"inv_{count + 1:04d}"


def _compose_markdown(
    *,
    record_type: str,
    invoice_number: str | None,
    alias: str,
    date: str,
    total_eur: float,
    counterparty: str | None,
    project: str | None,
    related_entity: str | None,
    line_items: Sequence[FinanceLineItemLike],
    notes: str | None,
) -> str:
    from domain.finance import RecordType

    return render_finance_markdown(
        FinanceRecord(
            path="",
            record_type=RecordType.parse(record_type) or RecordType.INVOICE,
            date=date,
            counterparty=str(counterparty or "").strip(),
            total_eur=total_eur,
            related_entity=str(related_entity or "").strip(),
            project=str(project or "").strip(),
            reference_number=(
                invoice_number.upper().replace("-", "_") if invoice_number else f"bill.{alias}"
            ),
            alias=alias,
            title="",
            line_items=tuple(
                LineItem(item=item.item, quantity=item.qty, unit_eur=item.unit_eur)
                for item in line_items
            ),
        ),
        notes=notes,
    )


def _normalize_root(path: str) -> str:
    text = str(path or "").strip().replace("\\", "/")
    if not text:
        return DEFAULT_WORKSPACE_LAYOUT.primary_finance_root() or "/finance"
    if not text.startswith("/"):
        text = f"/{text}"
    text = text.rstrip("/")
    return text or (DEFAULT_WORKSPACE_LAYOUT.primary_finance_root() or "/finance")


__all__ = ["resolve_finance_create_record"]
