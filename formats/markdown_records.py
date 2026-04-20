from __future__ import annotations

import re
from dataclasses import dataclass

from .frontmatter import parse_frontmatter_with_mode


def normalize_markdown_key(value: str) -> str:
    return re.sub(r"[^a-z0-9]+", "_", value.strip().lower()).strip("_")


def _strip_inline_wrappers(value: str) -> str:
    stripped = value.strip()
    if stripped.startswith(("'", '"', "`")) and stripped.endswith(("'", '"', "`")) and len(stripped) >= 2:
        return stripped[1:-1]
    return stripped


def extract_markdown_prose_snippet(
    text: str,
    *,
    max_chars: int = 240,
) -> str:
    """Return the first prose-like paragraph from markdown body text.

    This deliberately uses only structural markdown cues:
    headings, bullet lines, tables, and fenced code blocks are ignored.
    The goal is to surface narrative body evidence for closed-set selectors
    without inventing language-specific query heuristics.
    """

    paragraphs: list[str] = []
    current_lines: list[str] = []
    in_fence = False

    def flush() -> None:
        if not current_lines:
            return
        paragraph = " ".join(line.strip() for line in current_lines if line.strip())
        paragraph = re.sub(r"\s+", " ", paragraph).strip()
        current_lines.clear()
        if paragraph:
            paragraphs.append(paragraph)

    for raw_line in text.splitlines():
        stripped = raw_line.strip()
        if stripped.startswith("```"):
            in_fence = not in_fence
            continue
        if in_fence:
            continue
        if not stripped:
            flush()
            continue
        if stripped.startswith(("#", "-", "|", "`")):
            flush()
            continue
        current_lines.append(stripped)

    flush()
    if not paragraphs:
        return ""
    return paragraphs[0][:max_chars].strip()


def extract_markdown_bullet_values(text: str, key: str) -> tuple[str, ...]:
    values: list[str] = []
    pattern = f"- {key.lower()}:"
    lines = text.splitlines()
    index = 0
    while index < len(lines):
        raw_line = lines[index]
        stripped = raw_line.strip()
        if not stripped.lower().startswith(pattern):
            index += 1
            continue
        _, raw_value = stripped.split(":", 1)
        value = _strip_inline_wrappers(raw_value)
        if value:
            values.append(value)
            index += 1
            continue

        current_indent = len(raw_line) - len(raw_line.lstrip(" \t"))
        look_ahead = index + 1
        while look_ahead < len(lines):
            nested_line = lines[look_ahead]
            stripped_nested = nested_line.strip()
            if not stripped_nested:
                look_ahead += 1
                continue
            nested_indent = len(nested_line) - len(nested_line.lstrip(" \t"))
            if nested_indent <= current_indent:
                break
            if stripped_nested.startswith("- "):
                item_value = _strip_inline_wrappers(stripped_nested[2:])
                if item_value:
                    values.append(item_value)
                look_ahead += 1
                continue
            break
        index = look_ahead
    return tuple(dict.fromkeys(values))


@dataclass(frozen=True, slots=True)
class MarkdownSectionRecord:
    heading: str
    section_index: int
    fields: tuple[tuple[str, str], ...]

    def get(self, key: str, default: str = "") -> str:
        normalized_key = normalize_markdown_key(key)
        for field_key, field_value in self.fields:
            if field_key == normalized_key:
                return field_value
        return default


@dataclass(frozen=True, slots=True)
class MarkdownRecordFields:
    fields: dict[str, object]
    body: str
    record_format: str  # "yaml_frontmatter" | "markdown_bullets"


def parse_markdown_record_fields(
    text: str,
    *,
    lowercase_keys: bool = True,
    allow_invalid_frontmatter: bool = True,
) -> MarkdownRecordFields:
    parsed = parse_frontmatter_with_mode(
        text,
        lowercase_keys=lowercase_keys,
        allow_invalid=allow_invalid_frontmatter,
    )
    if parsed.mode != "none" and parsed.fields:
        return MarkdownRecordFields(
            fields=parsed.fields,
            body=parsed.body,
            record_format="yaml_frontmatter",
        )
    return MarkdownRecordFields(fields={}, body=text, record_format="markdown_bullets")


def parse_sectioned_bullet_records(text: str, *, heading_prefix: str = "### ") -> tuple[MarkdownSectionRecord, ...]:
    records: list[MarkdownSectionRecord] = []
    current_heading = ""
    current_section_index = 0
    current_fields: dict[str, str] = {}

    def flush_current() -> None:
        if not current_heading:
            return
        records.append(
            MarkdownSectionRecord(
                heading=current_heading,
                section_index=current_section_index,
                fields=tuple(current_fields.items()),
            )
        )

    for raw_line in text.splitlines():
        stripped = raw_line.strip()
        if stripped.startswith(heading_prefix):
            flush_current()
            current_section_index += 1
            current_heading = stripped[len(heading_prefix) :].strip()
            current_fields = {}
            continue
        if not current_heading or not stripped.startswith("- ") or ":" not in stripped:
            continue
        key, raw_value = stripped[2:].split(":", 1)
        normalized_key = normalize_markdown_key(key)
        if not normalized_key:
            continue
        current_fields[normalized_key] = _strip_inline_wrappers(raw_value)

    flush_current()
    return tuple(records)
