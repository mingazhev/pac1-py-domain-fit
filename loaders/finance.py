from __future__ import annotations

from collections.abc import Mapping
from pathlib import PurePosixPath

from domain.finance import Bill, FinanceRecord, Invoice
from domain.finance.line_item import LineItem
from domain.finance.money import Money
from domain.finance.record_type import RecordType
from formats.frontmatter import parse_frontmatter_with_mode, strip_frontmatter
from formats.markdown_tables import coerce_markdown_number, extract_markdown_tables

_LINE_ITEM_NAME_KEYS = (
    "item",
    "item_name",
    "line_item",
    "description",
    "product",
    "service",
    "name",
    "label",
)
_LINE_ITEM_QUANTITY_KEYS = (
    "qty",
    "quantity",
    "count",
    "units",
    "pcs",
    "pieces",
    "piece",
    "x",
)
_LINE_ITEM_UNIT_KEYS = (
    "unit_eur",
    "unit_price",
    "unit_price_eur",
    "unit_cost",
    "unit_cost_eur",
    "unit",
    "price",
    "price_eur",
    "price_per_unit",
    "price_per_unit_eur",
    "each",
    "each_eur",
    "per_unit",
    "per_unit_eur",
    "eur",
)
_LINE_ITEM_TOTAL_KEYS = (
    "line_eur",
    "line_total",
    "line_total_eur",
    "line_amount",
    "line_amount_eur",
    "amount",
    "amount_eur",
    "total",
    "total_eur",
    "extended",
    "extended_eur",
    "ext",
    "ext_eur",
    "sum",
    "sum_eur",
    "subtotal",
)


def _first_present(raw: Mapping[str, object], keys: tuple[str, ...]) -> object:
    for key in keys:
        if key in raw and raw.get(key) not in (None, ""):
            return raw.get(key)
    return None


def _coerce_finance_number(value: object) -> int | float | None:
    text = str(value or "").strip()
    if not text:
        return None
    normalized = text.replace("€", "").replace("EUR", "").replace("eur", "").strip()
    return coerce_markdown_number(normalized)


def _coerce_quantity_number(value: object) -> int | float | None:
    parsed = _coerce_finance_number(value)
    if parsed is not None:
        return parsed
    text = str(value or "").strip().lower()
    if not text:
        return None
    for prefix, suffix in (("", "x"), ("x", "")):
        if prefix and not text.startswith(prefix):
            continue
        if suffix and not text.endswith(suffix):
            continue
        inner = text[len(prefix) : len(text) - len(suffix) if suffix else None].strip()
        parsed_inner = _coerce_finance_number(inner)
        if parsed_inner is not None:
            return parsed_inner
    return None


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
        has_item = any(header in headers for header in _LINE_ITEM_NAME_KEYS)
        has_amount = any(header in headers for header in (*_LINE_ITEM_UNIT_KEYS, *_LINE_ITEM_TOTAL_KEYS))
        if not has_item or not has_amount:
            continue
        items: list[dict[str, object]] = []
        for row in table.rows_as_dicts(normalized_headers=True):
            item_name = str(_first_present(row, _LINE_ITEM_NAME_KEYS) or "").strip()
            if not item_name or item_name.upper() == "TOTAL":
                continue
            parsed_row: dict[str, object] = {"item": item_name}
            quantity_value = _first_present(row, _LINE_ITEM_QUANTITY_KEYS)
            unit_value = _first_present(row, _LINE_ITEM_UNIT_KEYS)
            total_value = _first_present(row, _LINE_ITEM_TOTAL_KEYS)
            if quantity_value not in (None, ""):
                parsed_row["quantity"] = _coerce_quantity_number(quantity_value)
            if unit_value not in (None, ""):
                parsed_row["unit_eur"] = coerce_markdown_number(unit_value)
            if total_value not in (None, ""):
                parsed_row["line_eur"] = coerce_markdown_number(total_value)
            items.append(parsed_row)
        if items:
            return tuple(items)
    return ()


def _normalize_path(path: object) -> str:
    normalized = str(path or "").strip().replace("\\", "/")
    if not normalized:
        return ""
    if normalized.startswith("/"):
        return normalized
    return f"/{normalized}"


def _resolve_document_title(
    path: str,
    body_text: str,
    *,
    frontmatter: Mapping[str, object],
    document: Mapping[str, object],
) -> str:
    title = str(
        document.get("title")
        or frontmatter.get("title")
        or frontmatter.get("name")
        or frontmatter.get("project_name")
        or ""
    ).strip()
    if title:
        return title

    for raw_line in body_text.splitlines():
        stripped = raw_line.strip()
        if stripped.startswith("#"):
            return stripped.lstrip("#").strip()

    stem = PurePosixPath(path).stem
    return stem.split("__", 1)[-1].replace("-", " ").replace("_", " ").strip().title()


def line_item_from_mapping(raw: Mapping[str, object]) -> LineItem | None:
    item = str(_first_present(raw, _LINE_ITEM_NAME_KEYS) or "").strip()
    if not item:
        return None
    quantity = _first_present(raw, _LINE_ITEM_QUANTITY_KEYS)
    if not isinstance(quantity, int | float):
        quantity = _coerce_quantity_number(quantity)
    unit_eur = _coerce_finance_number(_first_present(raw, _LINE_ITEM_UNIT_KEYS))
    line_eur = _coerce_finance_number(_first_present(raw, _LINE_ITEM_TOTAL_KEYS))
    return LineItem(
        item=item,
        quantity=quantity if isinstance(quantity, int | float) else None,
        unit_eur=Money.from_number(unit_eur),
        line_eur=Money.from_number(line_eur),
    )


def _finance_identifier(raw: Mapping[str, object], record_type: RecordType) -> str:
    """Pick the reference number from raw YAML.

    The workspace schema keys it as `invoice_number` on invoices and `bill_id`
    on bills. Both carry the same semantic — a reference identifier issued by
    one side of the transaction — so we normalize onto the neutral
    `reference_number` column on `FinanceRecord` and surface side-specific
    property accessors (`Invoice.invoice_number`, `Bill.bill_id`) at the
    subclass boundary.
    """

    if record_type is RecordType.INVOICE:
        return str(raw.get("invoice_number") or raw.get("reference_number") or "").strip()
    return str(
        raw.get("bill_id")
        or raw.get("reference_number")
        or raw.get("invoice_number")
        or ""
    ).strip()


def finance_record_from_mapping(raw: Mapping[str, object]) -> FinanceRecord | None:
    path = str(raw.get("path") or "").strip()
    record_type = RecordType.parse(raw.get("record_type"))
    if record_type is None:
        normalized_path = path.lower()
        if "/invoices/" in normalized_path or "__inv_" in normalized_path:
            record_type = RecordType.INVOICE
        elif "/purchases/" in normalized_path or "__bill__" in normalized_path:
            record_type = RecordType.BILL
    if record_type is None:
        return None
    raw_line_items = raw.get("line_items")
    if not isinstance(raw_line_items, (list, tuple)):
        raw_line_items = raw.get("lines")
    if not isinstance(raw_line_items, (list, tuple)):
        raw_line_items = raw.get("items")
    line_items = tuple(
        item
        for item in (
            line_item_from_mapping(candidate)
            for candidate in (raw_line_items or ())
            if isinstance(candidate, Mapping)
        )
        if item is not None
    )
    payload = dict(
        path=path,
        date=str(raw.get("date") or "").strip(),
        counterparty=str(raw.get("counterparty") or "").strip(),
        total_eur=Money.from_number(_coerce_finance_number(raw.get("total_eur"))),
        related_entity=str(raw.get("related_entity") or "").strip(),
        project=str(raw.get("project") or "").strip(),
        reference_number=_finance_identifier(raw, record_type),
        alias=str(raw.get("alias") or "").strip(),
        title=str(raw.get("title") or "").strip(),
        line_items=line_items,
        payment_state=str(raw.get("payment_state") or "").strip(),
        settlement_reference=str(raw.get("settlement_reference") or "").strip(),
        settlement_channel=str(raw.get("settlement_channel") or "").strip(),
        settlement_date=str(raw.get("settlement_date") or "").strip(),
    )
    if record_type is RecordType.INVOICE:
        return Invoice(**payload)
    return Bill(**payload)


def finance_record_from_document(document: Mapping[str, object]) -> FinanceRecord | None:
    path = _normalize_path(document.get("path"))
    if not path:
        return None

    note_text = str(document.get("body") or "")
    parsed = parse_frontmatter_with_mode(note_text, allow_invalid=True)
    frontmatter, body_text = parsed.fields, parsed.body
    body = body_text.strip()
    metadata = extract_finance_metadata(body)
    line_items = extract_finance_line_items(body)
    if not line_items:
        raw_frontmatter_lines = frontmatter.get("lines")
        if isinstance(raw_frontmatter_lines, (list, tuple)):
            line_items = tuple(
                candidate
                for candidate in raw_frontmatter_lines
                if isinstance(candidate, Mapping)
            )
    if not line_items:
        raw_document_lines = document.get("lines")
        if isinstance(raw_document_lines, (list, tuple)):
            line_items = tuple(
                candidate
                for candidate in raw_document_lines
                if isinstance(candidate, Mapping)
            )
    inferred_record_type = "invoice" if "/invoices/" in path.lower() else "bill"

    record = finance_record_from_mapping(
        {
            "path": path,
            "record_type": metadata.get("record_type")
            or frontmatter.get("record_type")
            or document.get("record_type")
            or inferred_record_type,
            "date": metadata.get("issued_on")
            or metadata.get("purchased_on")
            or frontmatter.get("issued_on")
            or frontmatter.get("purchased_on")
            or document.get("issued_on")
            or document.get("purchased_on")
            or document.get("date"),
            "counterparty": metadata.get("counterparty")
            or frontmatter.get("counterparty")
            or document.get("counterparty")
            or "",
            "total_eur": _coerce_finance_number(
                metadata.get("total_eur")
                or frontmatter.get("total_eur")
                or document.get("total_eur")
            ),
            "related_entity": metadata.get("related_entity")
            or frontmatter.get("related_entity")
            or document.get("related_entity")
            or "",
            "project": metadata.get("project") or frontmatter.get("project") or document.get("project") or "",
            "invoice_number": metadata.get("invoice_number")
            or frontmatter.get("invoice_number")
            or document.get("invoice_number")
            or "",
            "bill_id": metadata.get("bill_id")
            or frontmatter.get("bill_id")
            or document.get("bill_id")
            or "",
            "alias": metadata.get("alias") or frontmatter.get("alias") or document.get("alias") or "",
            "title": _resolve_document_title(path, body_text, frontmatter=frontmatter, document=document),
            "line_items": line_items,
            "payment_state": metadata.get("payment_state")
            or frontmatter.get("payment_state")
            or document.get("payment_state")
            or "",
            "settlement_reference": metadata.get("settlement_reference")
            or frontmatter.get("settlement_reference")
            or document.get("settlement_reference")
            or "",
            "settlement_channel": metadata.get("settlement_channel")
            or frontmatter.get("settlement_channel")
            or document.get("settlement_channel")
            or "",
            "settlement_date": metadata.get("settlement_date")
            or frontmatter.get("settlement_date")
            or document.get("settlement_date")
            or "",
        }
    )
    return record


def finance_records_from_mappings(raw_records: Mapping[str, object] | list[Mapping[str, object]] | tuple[Mapping[str, object], ...]) -> tuple[FinanceRecord, ...]:
    if isinstance(raw_records, Mapping):
        candidates = (raw_records,)
    else:
        candidates = raw_records
    return tuple(
        record
        for record in (finance_record_from_mapping(raw) for raw in candidates if isinstance(raw, Mapping))
        if record is not None
    )


def build_finance_frontmatter_updates(note_text: str, note_path: str) -> dict[str, object] | None:
    note_body = strip_frontmatter(note_text)
    metadata = extract_finance_metadata(note_body)
    line_items = extract_finance_line_items(note_body)
    normalized_path = str(note_path or "").strip().replace("\\", "/").lower()
    record_type = str(
        metadata.get("record_type") or ("invoice" if "/invoices/" in normalized_path else "bill")
    ).strip().lower()
    if record_type not in {"invoice", "bill"}:
        return None

    identifier_key = "invoice_number" if record_type == "invoice" else "bill_id"
    date_key = "issued_on" if record_type == "invoice" else "purchased_on"
    required_metadata_keys = (identifier_key, "alias", date_key, "counterparty", "project")
    if any(not str(metadata.get(key) or "").strip() for key in required_metadata_keys):
        return None

    total_eur = coerce_markdown_number(metadata.get("total_eur"))
    if total_eur is None or not line_items:
        return None

    rendered_line_items: list[dict[str, object]] = []
    for item in line_items:
        quantity = _first_present(item, _LINE_ITEM_QUANTITY_KEYS)
        unit_eur = _first_present(item, _LINE_ITEM_UNIT_KEYS)
        line_eur = _first_present(item, _LINE_ITEM_TOTAL_KEYS)
        item_name = str(_first_present(item, _LINE_ITEM_NAME_KEYS) or "").strip()
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
