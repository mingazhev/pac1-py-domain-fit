from __future__ import annotations

import re
from collections.abc import Sequence
from pathlib import PurePosixPath

from .outbox_completion_normalization import OutboxCompletionNormalization


class OutboxPayloadContractError(ValueError):
    """Payload shape violates the outbox contract."""


class OutboxPayloadUnsupportedError(ValueError):
    """Payload requests a transport the runtime does not support."""


def _normalize_repo_ref(value: str) -> str:
    text = str(value or "").replace("\\", "/").strip()
    if not text:
        return ""
    while text.startswith("./"):
        text = text[2:]
    while "//" in text:
        text = text.replace("//", "/")
    normalized = PurePosixPath(text).as_posix()
    if normalized == ".":
        return ""
    return f"/{normalized.lstrip('/')}"


def _normalize_inline_text(value: object) -> str:
    return re.sub(r"\s+", " ", str(value or "").strip()).lower()


def canonical_outbox_success_message(
    task_text: str,
    message: str,
    *,
    canonical_success_message: str = "",
) -> str:
    stripped = str(message or "").strip()
    if re.fullmatch(r"Prepared [A-Za-z /-]+ draft\.", stripped):
        return stripped
    if canonical_success_message:
        return canonical_success_message

    normalized_context = _normalize_inline_text(
        " ".join(part for part in (task_text, stripped) if part)
    )
    if "invoice" in normalized_context and any(
        token in normalized_context for token in ("bundle", "oldest", "latest", "invoices")
    ):
        return "Prepared invoice bundle draft."
    if "invoice" in normalized_context or "resend" in normalized_context:
        return "Prepared invoice resend draft."
    return "Prepared outbound email draft."


def normalize_outbox_completion(
    *,
    task_text: str,
    message: str,
    outbox_path: str,
    grounding_refs: Sequence[str],
    canonical_success_message: str = "",
) -> OutboxCompletionNormalization:
    normalized_refs = tuple(
        dict.fromkeys(
            ref
            for ref in (
                _normalize_repo_ref(outbox_path),
                *(_normalize_repo_ref(raw_ref) for raw_ref in grounding_refs),
            )
            if ref
        )
    )
    return OutboxCompletionNormalization(
        canonical_message=canonical_outbox_success_message(
            task_text,
            message,
            canonical_success_message=canonical_success_message,
        ),
        grounding_refs=normalized_refs,
    )


__all__ = [
    "OutboxPayloadContractError",
    "OutboxPayloadUnsupportedError",
    "canonical_outbox_success_message",
    "normalize_outbox_completion",
]
