from __future__ import annotations

import csv
import re
from collections.abc import Sequence
from dataclasses import dataclass
from typing import Any


_DIVIDER_CELL_RE = re.compile(r"^:?-+:?$")


def normalize_markdown_table_header(value: str) -> str:
    stripped = value.strip().lower()
    if stripped == "#":
        return "index"
    return re.sub(r"[^a-z0-9]+", "_", stripped).strip("_")


def _parse_table_row(raw_line: str) -> tuple[str, ...]:
    stripped = raw_line.strip()
    if not stripped.startswith("|") or not stripped.endswith("|"):
        raise ValueError("markdown table row must start and end with pipe")
    inner = stripped[1:-1]
    reader = csv.reader([inner], delimiter="|", quotechar='"', escapechar="\\")
    row = next(reader, [])
    return tuple(cell.strip() for cell in row)


def _is_divider_row(cells: tuple[str, ...]) -> bool:
    return bool(cells) and all(_DIVIDER_CELL_RE.fullmatch(cell.replace(" ", "")) for cell in cells)


@dataclass(frozen=True, slots=True)
class MarkdownTable:
    headers: tuple[str, ...]
    rows: tuple[tuple[str, ...], ...]

    @property
    def normalized_headers(self) -> tuple[str, ...]:
        return tuple(normalize_markdown_table_header(header) for header in self.headers)

    def rows_as_dicts(self, *, normalized_headers: bool = False) -> tuple[dict[str, str], ...]:
        headers = self.normalized_headers if normalized_headers else self.headers
        return tuple(dict(zip(headers, row, strict=False)) for row in self.rows if len(row) == len(headers))


def extract_markdown_tables(text: str) -> tuple[MarkdownTable, ...]:
    tables: list[MarkdownTable] = []
    current_lines: list[str] = []

    def flush_current() -> None:
        if not current_lines:
            return
        parsed_rows = tuple(_parse_table_row(line) for line in current_lines)
        non_divider_rows = tuple(row for row in parsed_rows if not _is_divider_row(row))
        if not non_divider_rows:
            current_lines.clear()
            return
        headers = non_divider_rows[0]
        data_rows = tuple(row for row in non_divider_rows[1:] if len(row) == len(headers))
        tables.append(MarkdownTable(headers=headers, rows=data_rows))
        current_lines.clear()

    for raw_line in text.splitlines():
        stripped = raw_line.strip()
        if stripped.startswith("+") and stripped.endswith("+"):
            continue
        if stripped.startswith("|") and stripped.endswith("|"):
            current_lines.append(raw_line)
            continue
        flush_current()
    flush_current()
    return tuple(tables)


def render_ascii_table(
    headers: Sequence[str],
    rows: Sequence[Sequence[Any]],
    *,
    fenced: bool = True,
) -> str:
    """Render a canonical ASCII pipe/plus table.

    Produces the same ``+---+...+`` bordered table used by canonical
    finance records. When ``fenced`` is true the table is wrapped in a
    ```text fenced block so it renders verbatim inside markdown.
    """

    header_cells = tuple(str(h) for h in headers)
    row_cells = tuple(tuple(str(cell) for cell in row) for row in rows)
    column_count = len(header_cells)

    widths = [len(cell) for cell in header_cells]
    for row in row_cells:
        for column_index in range(column_count):
            if column_index >= len(row):
                continue
            widths[column_index] = max(widths[column_index], len(row[column_index]))

    border = "+" + "+".join("-" * (width + 2) for width in widths) + "+"

    def _format_row(cells: Sequence[str]) -> str:
        padded = []
        for column_index in range(column_count):
            cell = cells[column_index] if column_index < len(cells) else ""
            padded.append(f" {cell:<{widths[column_index]}} ")
        return "|" + "|".join(padded) + "|"

    lines = [border, _format_row(header_cells), border]
    for row in row_cells:
        lines.append(_format_row(row))
    lines.append(border)
    table = "\n".join(lines)
    if not fenced:
        return table
    return f"```text\n{table}\n```"


def render_key_value_table(rows: Sequence[tuple[str, str]], *, fenced: bool = True) -> str:
    """Render a two-column ``field | value`` ASCII table."""

    return render_ascii_table(
        ("field", "value"),
        tuple((key, value) for key, value in rows),
        fenced=fenced,
    )


def coerce_markdown_number(value: Any) -> int | float | None:
    text = str(value or "").strip()
    if not text:
        return None
    normalized = text.replace(",", "")
    if not re.fullmatch(r"-?\d+(?:\.\d+)?", normalized):
        return None
    number = float(normalized)
    if number.is_integer():
        return int(number)
    return number
