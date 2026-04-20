from __future__ import annotations

import re
from collections.abc import Sequence
from datetime import datetime, timezone
from typing import Mapping

from domain.workspace import DEFAULT_WORKSPACE_LAYOUT

from .result import MutationStepResult


_DEFAULT_OUTBOX_DIR = DEFAULT_WORKSPACE_LAYOUT.primary_outbox_sink_root() or "/outbox"
_TIMESTAMP_FORMAT = "%Y-%m-%dT%H-%M-%SZ"


def resolve_outbox_draft(
    *,
    to: Sequence[str],
    subject: str,
    body: str,
    attachments: Sequence[str],
    related_entities: Sequence[str],
    source_channel: str | None,
    created_at: str | None,
    send_state: str,
    context_payload: Mapping[str, object] | None,
    outbox_root: str | None = None,
) -> tuple[MutationStepResult, str | None, str | None]:
    """Compose a canonical outbox draft. Returns (result, path, content).

    The mutation pipeline writes ``content`` to ``path`` when the result
    is resolved; this handler stays pure so tests can exercise the
    composition separately from the VM write.
    """

    cleaned_to = tuple(dict.fromkeys(str(addr).strip() for addr in to if str(addr or "").strip()))
    if not cleaned_to:
        return (
            MutationStepResult(
                status="clarify_missing",
                message="Outbox draft requires at least one recipient in `to`.",
                grounding_refs=(),
                reason_code="outbox_draft_requires_recipient",
            ),
            None,
            None,
        )

    clean_subject = str(subject or "").strip()
    clean_body = str(body or "").rstrip()
    if not clean_subject or not clean_body:
        return (
            MutationStepResult(
                status="clarify_missing",
                message="Outbox draft requires a non-empty subject and body.",
                grounding_refs=(),
                reason_code="outbox_draft_requires_subject_and_body",
            ),
            None,
            None,
    )

    iso_timestamp = _resolve_iso_timestamp(created_at, context_payload)
    resolved_outbox_root = _normalize_root(outbox_root or _DEFAULT_OUTBOX_DIR)
    path = f"{resolved_outbox_root}/eml_{_path_timestamp(iso_timestamp)}.md"

    frontmatter = _compose_frontmatter(
        send_state=send_state,
        created_at=iso_timestamp,
        to=cleaned_to,
        subject=clean_subject,
        attachments=_clean_paths(attachments),
        related_entities=_clean_entity_refs(related_entities),
        source_channel=source_channel,
    )
    content = f"---\n{frontmatter}---\n{clean_body}\n"

    return (
        MutationStepResult(
            status="resolved",
            message=path,
            grounding_refs=_grounding_refs(path, frontmatter_attachments=attachments),
            reason_code="outbox_draft_resolved",
        ),
        path,
        content,
    )


def _resolve_iso_timestamp(
    created_at: str | None, context_payload: Mapping[str, object] | None
) -> str:
    explicit = str(created_at or "").strip()
    if explicit:
        parsed = _parse_iso(explicit)
        if parsed is not None:
            return _format_iso(parsed)
    if context_payload:
        raw = str(context_payload.get("time") or "").strip()
        if raw:
            parsed = _parse_iso(raw)
            if parsed is not None:
                return _format_iso(parsed)
    return _format_iso(datetime.now(timezone.utc))


def _parse_iso(value: str) -> datetime | None:
    normalized = value.strip().replace("Z", "+00:00")
    try:
        parsed = datetime.fromisoformat(normalized)
    except ValueError:
        return None
    if parsed.tzinfo is None:
        parsed = parsed.replace(tzinfo=timezone.utc)
    return parsed.astimezone(timezone.utc)


def _format_iso(value: datetime) -> str:
    return value.strftime("%Y-%m-%dT%H:%M:%SZ")


def _path_timestamp(iso_timestamp: str) -> str:
    parsed = _parse_iso(iso_timestamp) or datetime.now(timezone.utc)
    return parsed.strftime(_TIMESTAMP_FORMAT)


def _clean_paths(values: Sequence[str]) -> tuple[str, ...]:
    cleaned: list[str] = []
    for raw in values:
        text = str(raw or "").strip()
        if not text:
            continue
        text = text.replace("\\", "/")
        if not text.startswith("/"):
            text = f"{text}"
        text = re.sub(r"/+", "/", text)
        if text.startswith("/"):
            text = text[1:]
        cleaned.append(text)
    return tuple(dict.fromkeys(cleaned))


def _grounding_refs(
    draft_path: str,
    *,
    frontmatter_attachments: Sequence[str],
) -> tuple[str, ...]:
    refs: list[str] = [draft_path]
    for attachment in frontmatter_attachments:
        text = str(attachment or "").strip()
        if not text:
            continue
        refs.append(text if text.startswith("/") else f"/{text}")
    return tuple(dict.fromkeys(refs))


def _clean_entity_refs(values: Sequence[str]) -> tuple[str, ...]:
    cleaned = tuple(
        dict.fromkeys(str(v).strip() for v in values if str(v or "").strip())
    )
    return cleaned


def _normalize_root(path: str) -> str:
    text = str(path or "").strip().replace("\\", "/")
    if not text:
        return _DEFAULT_OUTBOX_DIR
    if not text.startswith("/"):
        text = f"/{text}"
    text = re.sub(r"/+", "/", text).rstrip("/")
    return text or _DEFAULT_OUTBOX_DIR


def _compose_frontmatter(
    *,
    send_state: str,
    created_at: str,
    to: Sequence[str],
    subject: str,
    attachments: Sequence[str],
    related_entities: Sequence[str],
    source_channel: str | None,
) -> str:
    lines: list[str] = ["record_type: outbound_email"]
    lines.append(f"created_at: '{created_at}'")
    lines.append(f"send_state: {send_state}")
    lines.append("to:")
    for address in to:
        lines.append(f"  - {address}")
    lines.append(f"subject: {_yaml_scalar(subject)}")
    if attachments:
        lines.append("attachments:")
        for item in attachments:
            lines.append(f"  - {item}")
    if related_entities:
        lines.append("related_entities:")
        for entity in related_entities:
            lines.append(f"  - {entity}")
    if source_channel and source_channel.strip():
        lines.append(f"source_channel: {source_channel.strip()}")
    return "\n".join(lines) + "\n"


def _yaml_scalar(value: str) -> str:
    text = str(value).strip().replace("\n", " ")
    if _needs_quoting(text):
        escaped = text.replace("'", "''")
        return f"'{escaped}'"
    return text


def _needs_quoting(text: str) -> bool:
    if not text:
        return True
    if text[0] in "&*!|>%@`[]{}#,?:-\"'":
        return True
    if any(ch in text for ch in ":#"):
        return True
    return False


__all__ = ["resolve_outbox_draft"]
