from __future__ import annotations

import re
from collections.abc import Mapping
from pathlib import PurePosixPath

from domain.messages import (
    ChannelDefinition,
    ChannelTransportKind,
    MessageRecord,
    MessageSurfaceKind,
    ThreadRecord,
)
from domain.workspace import WorkspaceLayout
from formats.markdown_records import (
    extract_markdown_bullet_values,
    parse_sectioned_bullet_records,
)


def message_record_from_mapping(
    raw: Mapping[str, object],
    *,
    layout: WorkspaceLayout | None = None,
) -> MessageRecord | None:
    path = str(raw.get("path") or "").strip()
    message = str(raw.get("message") or "").strip()
    author = str(raw.get("author") or raw.get("from") or "").strip()
    author_id = str(raw.get("author_id") or raw.get("from_id") or "").strip()
    if not path or not message or not (author or author_id):
        return None
    section_index = raw.get("section_index")
    return MessageRecord(
        path=path,
        recorded_on=str(raw.get("recorded_on") or "").strip(),
        section_index=section_index if isinstance(section_index, int) else 0,
        author=author,
        author_id=author_id,
        message=message,
        surface_kind=MessageSurfaceKind.from_path(path, layout=layout),
    )


def message_records_from_mappings(
    raw_records: list[dict[str, object]] | tuple[dict[str, object], ...],
    *,
    layout: WorkspaceLayout | None = None,
) -> tuple[MessageRecord, ...]:
    return tuple(
        record
        for record in (message_record_from_mapping(raw, layout=layout) for raw in raw_records)
        if record is not None
    )


def message_records_from_document(
    document: Mapping[str, object],
    *,
    layout: WorkspaceLayout | None = None,
) -> tuple[MessageRecord, ...]:
    path = str(document.get("path") or "").strip()
    body = str(document.get("body") or "")
    if not path or not body.strip():
        return ()

    raw_records: list[dict[str, object]] = []
    for section in parse_sectioned_bullet_records(body):
        date_match = re.search(r"\d{4}-\d{2}-\d{2}", section.heading)
        record = message_record_from_mapping(
            {
                "path": path,
                "recorded_on": date_match.group(0) if date_match is not None else "",
                "section_index": section.section_index,
                "author": section.get("author"),
                "author_id": section.get("author_id"),
                "message": section.get("message"),
            },
            layout=layout,
        )
        if record is None:
            continue
        raw_records.append(
            {
                "path": record.path,
                "recorded_on": record.recorded_on,
                "section_index": record.section_index,
                "author": record.author,
                "author_id": record.author_id,
                "message": record.message,
            }
        )
    return message_records_from_mappings(raw_records, layout=layout)


def _first_heading(text: str) -> str:
    for line in text.splitlines():
        stripped = line.strip()
        if stripped.startswith("# "):
            return stripped[2:].strip()
    return ""


def _first_bullet_value(text: str, *keys: str) -> str:
    for key in keys:
        values = extract_markdown_bullet_values(text, key)
        if values:
            return values[0]
    return ""


def channel_definition_from_document(
    document: Mapping[str, object],
) -> ChannelDefinition | None:
    path = str(document.get("path") or "").strip()
    body = str(document.get("body") or "")
    if not path or not body.strip():
        return None
    return ChannelDefinition(
        path=path,
        title=_first_heading(body) or PurePosixPath(path).stem.replace("_", " ").strip(),
        alias=_first_bullet_value(body, "alias"),
        transport_kind=ChannelTransportKind.from_value(_first_bullet_value(body, "kind")),
        address=_first_bullet_value(body, "address"),
        created_on=_first_bullet_value(body, "created_on"),
        participants=extract_markdown_bullet_values(body, "participants"),
        authority_trust_class=_first_bullet_value(
            body, "authority_trust_class", "trust_class", "channel_trust"
        ),
        lane_anchor=_first_bullet_value(body, "lane_anchor", "lane"),
    )


def build_thread_record(
    document: Mapping[str, object],
    *,
    layout: WorkspaceLayout | None = None,
) -> ThreadRecord | None:
    path = str(document.get("path") or "").strip()
    body = str(document.get("body") or "")
    if not path or not body.strip():
        return None
    title = _first_heading(body) or PurePosixPath(path).stem.replace("_", " ").strip()
    return ThreadRecord(
        path=path,
        title=title,
        body=body.strip(),
        messages=message_records_from_document(document, layout=layout),
    )


__all__ = [
    "build_thread_record",
    "channel_definition_from_document",
    "message_record_from_mapping",
    "message_records_from_document",
    "message_records_from_mappings",
]
