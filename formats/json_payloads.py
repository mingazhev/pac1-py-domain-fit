from __future__ import annotations

import json
from typing import Any

def parse_json_value(text: str) -> Any:
    try:
        return json.loads(text)
    except json.JSONDecodeError as exc:
        raise ValueError("invalid json payload") from exc


def parse_json_object(text: str) -> dict[str, Any]:
    payload = parse_json_value(text)
    if not isinstance(payload, dict):
        raise ValueError("expected JSON object")
    return payload


def parse_json_array(text: str) -> list[Any]:
    payload = parse_json_value(text)
    if not isinstance(payload, list):
        raise ValueError("expected JSON array")
    return payload


def render_json(
    payload: Any,
    *,
    indent: int | None = None,
    sort_keys: bool = False,
    ensure_ascii: bool = False,
) -> str:
    return json.dumps(payload, indent=indent, sort_keys=sort_keys, ensure_ascii=ensure_ascii)
