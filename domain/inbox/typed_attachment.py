from __future__ import annotations

import re
from dataclasses import dataclass
from pathlib import PurePosixPath
from typing import Literal


AttachmentKind = Literal["invoice", "document", "image", "archive", "unknown"]


@dataclass(frozen=True, slots=True)
class TypedAttachment:
    path: str
    kind: AttachmentKind = "unknown"
    workspace_relative: bool = True

    def __post_init__(self) -> None:
        if self.path and self.workspace_relative:
            normalized = _normalize_attachment_path(self.path)
            if normalized != self.path:
                object.__setattr__(self, "path", normalized)


_EXTENSION_KIND_MAP: dict[str, AttachmentKind] = {
    ".pdf": "invoice",
    ".xlsx": "document",
    ".xls": "document",
    ".csv": "document",
    ".doc": "document",
    ".docx": "document",
    ".png": "image",
    ".jpg": "image",
    ".jpeg": "image",
    ".gif": "image",
    ".zip": "archive",
    ".tar": "archive",
    ".gz": "archive",
}

_EXTERNAL_RE = re.compile(r"^[a-z][a-z0-9+.-]*://", re.IGNORECASE)


def _normalize_attachment_path(path: str) -> str:
    text = str(path or "").replace("\\", "/").strip()
    if not text:
        return ""
    while text.startswith("./"):
        text = text[2:]
    while "//" in text:
        text = text.replace("//", "/")
    return text.lstrip("/")


def classify_attachment_kind(path: str) -> AttachmentKind:
    if not path:
        return "unknown"
    suffix = PurePosixPath(path).suffix.lower()
    return _EXTENSION_KIND_MAP.get(suffix, "unknown")


def typed_attachment_from_path(path: str) -> TypedAttachment:
    normalized = _normalize_attachment_path(path)
    kind = classify_attachment_kind(normalized)
    return TypedAttachment(path=normalized, kind=kind)


def validate_attachment_boundary(attachment: TypedAttachment) -> tuple[bool, str]:
    if not attachment.path:
        return False, "attachment path must not be empty"

    text = attachment.path
    if text.startswith("/"):
        return False, f"attachment must be workspace-relative: '{text}'"
    if text.startswith("./") or text.startswith("../"):
        return False, f"attachment must stay inside workspace root: '{text}'"
    if "/../" in text or text == "..":
        return False, f"attachment must stay inside workspace root: '{text}'"
    if _EXTERNAL_RE.match(text):
        return False, f"attachment must be workspace-relative, not external URL: '{text}'"

    return True, ""
