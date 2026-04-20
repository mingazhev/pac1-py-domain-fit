from __future__ import annotations

from collections.abc import Mapping
from dataclasses import dataclass
from typing import Any

import yaml


class _IndentedSafeDumper(yaml.SafeDumper):
    def increase_indent(self, flow: bool = False, indentless: bool = False):  # type: ignore[override]
        return super().increase_indent(flow, False)


@dataclass(frozen=True, slots=True)
class FrontmatterParseResult:
    fields: dict[str, Any]
    body: str
    mode: str  # "none" | "strict" | "legacy"


def _split_frontmatter_block(text: str) -> tuple[str | None, str]:
    lines = text.splitlines()
    if not lines or lines[0].strip() != "---":
        return None, text
    try:
        close_index = lines[1:].index("---") + 1
    except ValueError:
        return None, text
    frontmatter_text = "\n".join(lines[1:close_index])
    body = "\n".join(lines[close_index + 1 :])
    if text.endswith("\n"):
        body += "\n"
    return frontmatter_text, body


def _legacy_parse_frontmatter(frontmatter_text: str) -> dict[str, Any]:
    frontmatter: dict[str, Any] = {}
    lines = frontmatter_text.splitlines()
    index = 0
    while index < len(lines):
        raw_line = lines[index]
        if ":" not in raw_line:
            index += 1
            continue
        key, raw_value = raw_line.split(":", 1)
        key = key.strip()
        value = raw_value.strip()
        if not key:
            index += 1
            continue
        if not value:
            list_values: list[str] = []
            look_ahead = index + 1
            while look_ahead < len(lines):
                nested_line = lines[look_ahead]
                stripped_nested = nested_line.strip()
                if not stripped_nested:
                    look_ahead += 1
                    continue
                if nested_line.startswith((" ", "\t")) and stripped_nested.startswith("- "):
                    item_value = stripped_nested[2:].strip()
                    if item_value.startswith(("'", '"', "`")) and item_value.endswith(("'", '"', "`")) and len(item_value) >= 2:
                        item_value = item_value[1:-1]
                    list_values.append(item_value)
                    look_ahead += 1
                    continue
                break
            if list_values:
                frontmatter[key] = list_values
                index = look_ahead
                continue
        if value.startswith(("'", '"', "`")) and value.endswith(("'", '"', "`")) and len(value) >= 2:
            value = value[1:-1]
        frontmatter[key] = value
        index += 1
    return frontmatter


def _normalize_mapping_keys(value: Mapping[str, Any], *, lowercase_keys: bool) -> dict[str, Any]:
    normalized: dict[str, Any] = {}
    for raw_key, raw_value in value.items():
        key = str(raw_key).lower() if lowercase_keys else str(raw_key)
        if isinstance(raw_value, Mapping):
            normalized[key] = _normalize_mapping_keys(raw_value, lowercase_keys=lowercase_keys)
        elif isinstance(raw_value, list):
            normalized[key] = [
                _normalize_mapping_keys(item, lowercase_keys=lowercase_keys) if isinstance(item, Mapping) else item
                for item in raw_value
            ]
        else:
            normalized[key] = raw_value
    return normalized


def parse_frontmatter(
    text: str,
    *,
    lowercase_keys: bool = False,
    allow_invalid: bool = False,
) -> tuple[dict[str, Any], str]:
    parsed = parse_frontmatter_with_mode(
        text,
        lowercase_keys=lowercase_keys,
        allow_invalid=allow_invalid,
    )
    return parsed.fields, parsed.body


def parse_frontmatter_with_mode(
    text: str,
    *,
    lowercase_keys: bool = False,
    allow_invalid: bool = False,
) -> FrontmatterParseResult:
    frontmatter_text, body = _split_frontmatter_block(text)
    if frontmatter_text is None:
        return FrontmatterParseResult(fields={}, body=text, mode="none")
    mode = "strict"
    try:
        loaded = yaml.load(frontmatter_text, Loader=yaml.BaseLoader)
    except yaml.YAMLError:
        if not allow_invalid:
            raise ValueError("invalid yaml frontmatter") from None
        loaded = _legacy_parse_frontmatter(frontmatter_text)
        mode = "legacy"
    if loaded is None:
        return FrontmatterParseResult(fields={}, body=body, mode=mode)
    if not isinstance(loaded, Mapping):
        if allow_invalid:
            loaded = {}
        else:
            raise ValueError("frontmatter must parse to a mapping")
    return FrontmatterParseResult(
        fields=_normalize_mapping_keys(loaded, lowercase_keys=lowercase_keys),
        body=body,
        mode=mode,
    )


def render_frontmatter(fields: Mapping[str, Any]) -> str:
    payload = dict(fields)
    rendered = yaml.dump(
        payload,
        allow_unicode=True,
        default_flow_style=False,
        sort_keys=False,
        Dumper=_IndentedSafeDumper,
    ).strip()
    if not rendered:
        return "---\n---\n"
    return f"---\n{rendered}\n---\n"


def strip_frontmatter(text: str) -> str:
    _, body = _split_frontmatter_block(text)
    return body if body != text else text


def replace_frontmatter(text: str, fields: Mapping[str, Any]) -> str:
    body = strip_frontmatter(text).lstrip("\n")
    return render_frontmatter(fields) + body


def merge_frontmatter_fields(text: str, updates: Mapping[str, Any]) -> str:
    parsed = parse_frontmatter_with_mode(text, allow_invalid=True)
    existing, body = parsed.fields, parsed.body
    merged = dict(existing)
    merged.update(dict(updates))
    return render_frontmatter(merged) + body.lstrip("\n")
