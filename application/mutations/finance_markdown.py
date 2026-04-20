from __future__ import annotations

import re
from collections.abc import Sequence
from dataclasses import dataclass

from domain.finance import FinanceRecord
from domain.finance.aggregate import FinanceRecordAggregate, FinanceRecordDraft
from domain.finance.line_item import LineItem
from domain.finance.money import money_to_number
from domain.finance.settlement import payment_state_text, settlement_channel_text
from formats.frontmatter import strip_frontmatter
from formats.markdown_tables import render_ascii_table, render_key_value_table


@dataclass(frozen=True, slots=True)
class FinanceMarkdownSection:
    heading: str
    body: str


def render_finance_markdown(
    finance: FinanceRecord | FinanceRecordDraft | FinanceRecordAggregate,
    *,
    notes: str | None = None,
    leading_text: str | None = None,
    preserved_sections: Sequence[FinanceMarkdownSection] = (),
) -> str:
    record = _coerce_record(finance)
    record_type = _record_type_text(record)
    alias = str(record.alias or "").strip()
    title = f"# {_display_title(record.counterparty, record_type, alias)}"
    metadata_rows: list[tuple[str, str]] = [("record_type", record_type)]
    if record_type == "invoice" and str(record.reference_number or "").strip():
        metadata_rows.append(
            ("invoice_number", str(record.reference_number).upper().replace("_", "-"))
        )
    if record_type == "bill":
        bill_id = str(record.reference_number or "").strip() or f"bill.{alias}"
        metadata_rows.append(("bill_id", bill_id))
    metadata_rows.append(("alias", alias))
    metadata_rows.append(
        ("issued_on" if record_type == "invoice" else "purchased_on", record.date)
    )
    metadata_rows.append(("total_eur", format_finance_amount(record.total_eur or 0)))
    if record.counterparty:
        metadata_rows.append(("counterparty", record.counterparty.strip()))
    if record.project:
        metadata_rows.append(("project", record.project.strip()))
    if record.related_entity:
        metadata_rows.append(("related_entity", record.related_entity.strip()))
    payment_state = payment_state_text(record.payment_state)
    if payment_state:
        metadata_rows.append(("payment_state", payment_state))
    if str(record.settlement_reference or "").strip():
        metadata_rows.append(
            ("settlement_reference", str(record.settlement_reference).strip())
        )
    settlement_channel = settlement_channel_text(record.settlement_channel)
    if settlement_channel:
        metadata_rows.append(("settlement_channel", settlement_channel))
    if str(record.settlement_date or "").strip():
        metadata_rows.append(("settlement_date", str(record.settlement_date).strip()))

    metadata_block = render_key_value_table(metadata_rows)
    sections: list[str] = [title, "", metadata_block]
    if leading_text and leading_text.strip():
        sections.extend(["", leading_text.strip()])
    if record.line_items:
        sections.extend(
            [
                "",
                "## Line Items",
                "",
                _render_line_items(record.line_items, float(record.total_eur or 0)),
            ]
        )
    if notes and notes.strip():
        sections.extend(["", "## Notes", "", notes.strip()])
    for section in preserved_sections:
        heading = str(section.heading or "").strip()
        if not heading:
            continue
        normalized_heading = _normalize_section_heading(heading)
        if normalized_heading in {"line items", "notes"}:
            continue
        sections.extend(["", f"## {heading}"])
        body = str(section.body or "").strip()
        if body:
            sections.extend(["", body])
    return "\n".join(sections) + "\n"


def extract_finance_notes(note_text: str | None) -> str | None:
    for section in extract_finance_sections(note_text):
        if _normalize_section_heading(section.heading) == "notes":
            notes = str(section.body or "").strip()
            return notes or None
    return None


def extract_finance_preserved_sections(
    note_text: str | None,
) -> tuple[FinanceMarkdownSection, ...]:
    return tuple(
        section
        for section in extract_finance_sections(note_text)
        if _normalize_section_heading(section.heading) not in {"notes", "line items"}
    )


def extract_finance_leading_text(note_text: str | None) -> str | None:
    text = str(note_text or "")
    if not text.strip():
        return None
    lines = strip_frontmatter(text).splitlines()
    index = 0
    if index < len(lines) and re.match(r"^\s*#\s+.+$", lines[index]):
        index += 1
    while index < len(lines) and not lines[index].strip():
        index += 1
    if index < len(lines) and lines[index].strip() == "```text":
        index += 1
        while index < len(lines) and lines[index].strip() != "```":
            index += 1
        if index < len(lines) and lines[index].strip() == "```":
            index += 1
    while index < len(lines) and not lines[index].strip():
        index += 1
    preserved: list[str] = []
    while index < len(lines):
        if re.match(r"^\s*##\s+.+$", lines[index]):
            break
        preserved.append(lines[index])
        index += 1
    leading = "\n".join(preserved).strip()
    return leading or None


def extract_finance_sections(
    note_text: str | None,
) -> tuple[FinanceMarkdownSection, ...]:
    text = str(note_text or "")
    if not text.strip():
        return ()
    body = strip_frontmatter(text)
    lines = body.splitlines()
    sections: list[FinanceMarkdownSection] = []
    current_heading: str | None = None
    current_lines: list[str] = []
    for line in lines:
        match = re.match(r"^\s*##\s+(.+?)\s*$", line)
        if match is not None:
            if current_heading is not None:
                sections.append(
                    FinanceMarkdownSection(
                        heading=current_heading,
                        body="\n".join(current_lines).strip(),
                    )
                )
            current_heading = match.group(1).strip()
            current_lines = []
            continue
        if current_heading is None:
            continue
        current_lines.append(line)
    if current_heading is not None:
        sections.append(
            FinanceMarkdownSection(
                heading=current_heading,
                body="\n".join(current_lines).strip(),
            )
        )
    return tuple(sections)


def format_finance_amount(value: float | int) -> str:
    numeric = float(value)
    if numeric.is_integer():
        return str(int(round(numeric)))
    return f"{numeric:.2f}".rstrip("0").rstrip(".")


def _coerce_record(
    finance: FinanceRecord | FinanceRecordDraft | FinanceRecordAggregate,
) -> FinanceRecordDraft:
    if isinstance(finance, FinanceRecordAggregate):
        return finance.draft
    if isinstance(finance, FinanceRecordDraft):
        return finance
    return FinanceRecordDraft.from_record(finance)


def _record_type_text(finance: FinanceRecord | FinanceRecordDraft) -> str:
    raw = getattr(finance, "record_type", None)
    return str(getattr(raw, "value", raw) or "").strip().lower() or "invoice"


def _display_title(
    counterparty: str | None, record_type: str, alias: str
) -> str:
    if counterparty:
        suffix = "invoice" if record_type == "invoice" else "bill"
        return f"{counterparty.strip()} {suffix}"
    readable = alias.replace("_", " ").strip().title()
    return readable or record_type.title()


def _render_line_items(
    items: Sequence[LineItem], total_eur: float
) -> str:
    rows: list[tuple[str, str, str, str, str]] = []
    for index, item in enumerate(items, start=1):
        qty = float(getattr(item, "quantity", None) or getattr(item, "qty", 1) or 1)
        unit = float(money_to_number(getattr(item, "unit_eur", None)) or 0)
        line_total = qty * unit
        rows.append(
            (
                str(index),
                str(getattr(item, "item", "") or "").strip(),
                format_finance_amount(qty),
                format_finance_amount(unit),
                format_finance_amount(line_total),
            )
        )
    rows.append(("", "TOTAL", "", "", format_finance_amount(total_eur)))
    return render_ascii_table(
        ("#", "item", "qty", "unit_eur", "line_eur"),
        rows,
    )


def _normalize_section_heading(value: str) -> str:
    return re.sub(r"\s+", " ", str(value or "").strip()).lower()


__all__ = [
    "FinanceMarkdownSection",
    "extract_finance_leading_text",
    "extract_finance_preserved_sections",
    "extract_finance_sections",
    "extract_finance_notes",
    "format_finance_amount",
    "render_finance_markdown",
]
