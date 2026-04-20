"""YAML rendering utilities extracted from agent.py."""
from __future__ import annotations

import json
import re

from formats.frontmatter import render_frontmatter as _strict_render_frontmatter


def _yaml_scalar(value: object) -> str:
    if isinstance(value, bool):
        return "true" if value else "false"
    if isinstance(value, float) and value.is_integer():
        return str(int(value))
    if isinstance(value, (int, float)):
        return str(value)
    text = str(value)
    if not text:
        return '""'
    lowered = text.lower()
    if lowered in {"true", "false", "null", "~"}:
        return json.dumps(text, ensure_ascii=False)
    if (
        text[0] in {'"', "'", "{", "}", "[", "]", ",", "&", "*", "!", "|", ">", "@", "`"}
        or text.endswith(":")
        or ": " in text
        or " #" in text
        or "\n" in text
        or "\t" in text
    ):
        return json.dumps(text, ensure_ascii=False)
    if re.fullmatch(r"[A-Za-z0-9_./@:+-]+(?: [A-Za-z0-9_./@:+-]+)*", text):
        return text
    return json.dumps(text, ensure_ascii=False)


def _render_yaml_field_lines(key: str, value: object, *, indent: int = 0) -> list[str]:
    prefix = " " * indent
    if isinstance(value, dict):
        lines = [f"{prefix}{key}:"]
        for child_key, child_value in value.items():
            lines.extend(_render_yaml_field_lines(str(child_key), child_value, indent=indent + 2))
        return lines
    if isinstance(value, (list, tuple)):
        if not value:
            return [f"{prefix}{key}: []"]
        lines = [f"{prefix}{key}:"]
        for item in value:
            if isinstance(item, dict):
                item_entries = list(item.items())
                if not item_entries:
                    lines.append(f"{prefix}  - {{}}")
                    continue
                first_key, first_value = item_entries[0]
                if isinstance(first_value, (dict, list, tuple)):
                    lines.append(f"{prefix}  - {first_key}:")
                    if isinstance(first_value, dict):
                        for child_key, child_value in first_value.items():
                            lines.extend(_render_yaml_field_lines(str(child_key), child_value, indent=indent + 6))
                    else:
                        for nested_value in first_value:
                            lines.extend(_render_yaml_list_item_lines(nested_value, indent=indent + 4))
                else:
                    lines.append(f"{prefix}  - {first_key}: {_yaml_scalar(first_value)}")
                for child_key, child_value in item_entries[1:]:
                    lines.extend(_render_yaml_field_lines(str(child_key), child_value, indent=indent + 4))
                continue
            lines.extend(_render_yaml_list_item_lines(item, indent=indent + 2))
        return lines
    return [f"{prefix}{key}: {_yaml_scalar(value)}"]


def _render_yaml_list_item_lines(value: object, *, indent: int = 0) -> list[str]:
    prefix = " " * indent
    if isinstance(value, dict):
        item_entries = list(value.items())
        if not item_entries:
            return [f"{prefix}- {{}}"]
        first_key, first_value = item_entries[0]
        if isinstance(first_value, (dict, list, tuple)):
            lines = [f"{prefix}- {first_key}:"]
            if isinstance(first_value, dict):
                for child_key, child_value in first_value.items():
                    lines.extend(_render_yaml_field_lines(str(child_key), child_value, indent=indent + 4))
            else:
                for nested_value in first_value:
                    lines.extend(_render_yaml_list_item_lines(nested_value, indent=indent + 2))
        else:
            lines = [f"{prefix}- {first_key}: {_yaml_scalar(first_value)}"]
        for child_key, child_value in item_entries[1:]:
            lines.extend(_render_yaml_field_lines(str(child_key), child_value, indent=indent + 2))
        return lines
    return [f"{prefix}- {_yaml_scalar(value)}"]


def _render_yaml_frontmatter(fields: dict[str, object]) -> str:
    return _strict_render_frontmatter(fields)
