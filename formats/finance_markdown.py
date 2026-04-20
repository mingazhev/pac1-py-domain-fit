from __future__ import annotations

from formats.frontmatter import strip_frontmatter
from formats.markdown_tables import coerce_markdown_number, extract_markdown_tables


def extract_finance_metadata(body: str) -> dict[str, str]:
    for table in extract_markdown_tables(body):
        headers = table.normalized_headers
        if headers[:2] != ("field", "value"):
            continue
        metadata: dict[str, str] = {}
        for row in table.rows_as_dicts(normalized_headers=True):
            key = str(row.get("field") or "").strip()
            value = str(row.get("value") or "").strip()
            if key and value:
                metadata[key] = value
        if metadata:
            return metadata
    return {}


def extract_finance_line_items(body: str) -> tuple[dict[str, object], ...]:
    for table in extract_markdown_tables(body):
        headers = table.normalized_headers
        if "item" not in headers or (
            "line_eur" not in headers and "unit_eur" not in headers
        ):
            continue
        items: list[dict[str, object]] = []
        for row in table.rows_as_dicts(normalized_headers=True):
            item_name = str(row.get("item") or "").strip()
            if not item_name or item_name.upper() == "TOTAL":
                continue
            parsed_row: dict[str, object] = {**row, "item": item_name}
            for field_name in ("qty", "quantity", "unit_eur", "line_eur"):
                if field_name in parsed_row:
                    parsed_row[field_name] = coerce_markdown_number(
                        parsed_row[field_name]
                    )
            items.append(parsed_row)
        if items:
            return tuple(items)
    return ()


def build_finance_frontmatter_updates(
    note_text: str,
    note_path: str,
) -> dict[str, object] | None:
    note_body = strip_frontmatter(note_text)
    metadata = extract_finance_metadata(note_body)
    line_items = extract_finance_line_items(note_body)
    normalized_path = str(note_path or "").strip().replace("\\", "/").lower()
    record_type = str(
        metadata.get("record_type")
        or ("invoice" if "/invoices/" in normalized_path else "bill")
    ).strip().lower()
    if record_type not in {"invoice", "bill"}:
        return None

    identifier_key = "invoice_number" if record_type == "invoice" else "bill_id"
    date_key = "issued_on" if record_type == "invoice" else "purchased_on"
    required_metadata_keys = (
        identifier_key,
        "alias",
        date_key,
        "counterparty",
        "project",
    )
    if any(not str(metadata.get(key) or "").strip() for key in required_metadata_keys):
        return None

    total_eur = coerce_markdown_number(metadata.get("total_eur"))
    if total_eur is None or not line_items:
        return None

    rendered_line_items: list[dict[str, object]] = []
    for item in line_items:
        quantity = item.get("quantity")
        if quantity is None:
            quantity = item.get("qty")
        unit_eur = item.get("unit_eur")
        line_eur = item.get("line_eur")
        item_name = str(item.get("item") or "").strip()
        if not item_name or quantity is None or unit_eur is None or line_eur is None:
            return None
        rendered_line_items.append(
            {
                "item": item_name,
                "quantity": quantity,
                "unit_eur": unit_eur,
                "line_eur": line_eur,
            }
        )

    updates: dict[str, object] = {
        "record_type": record_type,
        identifier_key: str(metadata[identifier_key]).strip(),
        "alias": str(metadata["alias"]).strip(),
        date_key: str(metadata[date_key]).strip(),
        "total_eur": total_eur,
        "counterparty": str(metadata["counterparty"]).strip(),
        "project": str(metadata["project"]).strip(),
        "lines": rendered_line_items,
    }
    related_entity = str(metadata.get("related_entity") or "").strip()
    if related_entity:
        updates["related_entity"] = related_entity
    return updates


__all__ = [
    "build_finance_frontmatter_updates",
    "extract_finance_line_items",
    "extract_finance_metadata",
]
