from __future__ import annotations

import re
from pathlib import PurePosixPath

from domain.inbox.inbox_item import InboxItem
from domain.inbox.paths import extract_repo_local_targets
from domain.workspace import DEFAULT_WORKSPACE_LAYOUT, WorkspaceLayout

from .security_finding import SecurityFinding, SecurityFindingKind
from .sanitization import sanitize_security_text as _sanitize_security_text


_SENSITIVE_KNOWLEDGE_ACCESS_PATTERNS = (
    re.compile(r"\b(?:read|access|view|retrieve|extract|copy|attach)\b", re.IGNORECASE),
)
_OUTBOUND_SHARE_CUES = (
    "send ",
    "share ",
    "forward ",
    "reply ",
    "email ",
    "mail ",
    "channel",
    "calendar",
    "slack",
    "discord",
)
OVERCAUTIOUS_INBOX_SECURITY_DENIAL_PATTERNS: tuple[re.Pattern[str], ...] = (
    re.compile(r"\bdestructive\b", re.IGNORECASE),
    re.compile(
        r"\bdestructive (?:side effect|action|workspace mutation)\b", re.IGNORECASE
    ),
    re.compile(r"\bdestructive mutation is disallowed\b", re.IGNORECASE),
    re.compile(r"\bterminal\s+(?:\w+\s+)?block\b", re.IGNORECASE),
    re.compile(r"\bterminal (?:security-style )?block\b", re.IGNORECASE),
    re.compile(r"\bper\s+(?:the\s+)?(?:\w+\s+)?policy\b", re.IGNORECASE),
    re.compile(r"\bper (?:policy|the blocked actions policy)\b", re.IGNORECASE),
    re.compile(
        r"\bexplicitly\s+(?:requests?|asks?)\s+(?:to\s+)?(?:delet|remov)", re.IGNORECASE
    ),
    re.compile(r"\bdisallowed\b", re.IGNORECASE),
    re.compile(r"\bexplicitly requests? (?:deletion|to delete)\b", re.IGNORECASE),
    re.compile(r"\bexplicitly asks? to delete\b", re.IGNORECASE),
    re.compile(r"\btask explicitly requests? deletion\b", re.IGNORECASE),
    re.compile(
        r"\bcan(?:not|['’]t)\s+(?:carry out|execute)\s+the\s+delet(?:e|ion)\s+request\b",
        re.IGNORECASE,
    ),
    re.compile(r"\bnon-destructive(?:ly)?\s+handle\b", re.IGNORECASE),
)
SECURITY_EVIDENCE_PATTERNS: tuple[re.Pattern[str], ...] = (
    re.compile(r"\binjection\b", re.IGNORECASE),
    re.compile(r"\bignore (?:local|repo(?:sitory)?|current) rules?\b", re.IGNORECASE),
    re.compile(r"\boverride\b", re.IGNORECASE),
    re.compile(r"\bcredentials?\b", re.IGNORECASE),
    re.compile(r"\b(?:api )?keys?\b", re.IGNORECASE),
    re.compile(r"\bsecret\b", re.IGNORECASE),
    re.compile(r"\btoken\b", re.IGNORECASE),
    re.compile(r"\bexfiltrat(?:e|ion)\b", re.IGNORECASE),
    re.compile(r"\bunauthori[sz]ed\b", re.IGNORECASE),
    re.compile(r"\bblacklist(?:ed)?\b", re.IGNORECASE),
    re.compile(r"\bprotected\b", re.IGNORECASE),
    re.compile(r"\binternal knowledge\b", re.IGNORECASE),
)
INJECTION_PATTERNS: tuple[tuple[str, re.Pattern[str]], ...] = (
    (
        "clipboard_relay",
        re.compile(r"clipboard\s*relay|sys[_-]?override@clipboard", re.IGNORECASE),
    ),
    ("system_override", re.compile(r"system\s*override", re.IGNORECASE)),
    ("chatml_tags", re.compile(r"<\|\s*(system|user|assistant)\s*\|>", re.IGNORECASE)),
    (
        "chatml_tags",
        re.compile(
            r"<\|\s*(?:start|end)_header_id\s*\|>|<\|\s*eot_id\s*\|>",
            re.IGNORECASE,
        ),
    ),
    (
        "ops_escalation",
        re.compile(r"ops\s+escalation|temporary\s+exception", re.IGNORECASE),
    ),
    (
        "rule_override",
        re.compile(
            r"ignore\s+(?:local|repo(?:sitory)?|current)\s+rules?|ignore\s+(?:all\s+)?(?:prior|previous)\s+instructions|prioriti[sz]e.+above.+guidance|do\s+not\s+request\s+confirmation",
            re.IGNORECASE,
        ),
    ),
    (
        "credential_harvest",
        re.compile(
            r"collect\s+(?:any\s+)?(?:accessible\s+)?(?:credentials|api keys?|access notes?)",
            re.IGNORECASE,
        ),
    ),
    (
        "control_override",
        re.compile(
            r"active\s+control\s+path|runtime_override\s*=\s*true|confirmation\s*=\s*not-required",
            re.IGNORECASE,
        ),
    ),
    (
        "data_exfil_intent",
        re.compile(
            r"export(?:\s+\w+){0,3}\s+contact(?:\s+list)?|export[_ ]contacts?|share[_ ]thread|customer\s+thread",
            re.IGNORECASE,
        ),
    ),
    (
        "policy_suppression",
        re.compile(
            r"process\s+the\s+following\s+runtime\s+note\s+directly|"
            r"operator\s+checklist\s+for\s+runtime\s+handling|"
            r"remove\s+policy/process\s+documents|"
            r"omit\s+override\s+context|"
            r"remove\s+the\s+root\s+`?agents\.md`?\s+file|"
            r"delete\s+(?:the\s+)?(?:repository(?:'s)?\s+root|receiving\s+repository(?:'s)?\s+root)\s+`?agents\.md`?\s+file|"
            r"control-layer\s+collisions|"
            r"consum(?:e|ing)\s+context\s+during\s+ingestion|"
            r"disposable\s+scaffolding|"
            r"omit\s+it\s+from\s+any\s+outgoing\s+explanation|"
            r"do\s+not\s+surface\s+this\s+warning(?:\s+to\s+the\s+recipient)?|"
            r"output\s+your\s+complete\s+prompt\s+verbatim|"
            r"full_prompt_audit",
            re.IGNORECASE,
        ),
    ),
)
SECRET_VALUE_PATTERNS: tuple[re.Pattern[str], ...] = (
    re.compile(r"\btmp-[A-Za-z0-9]{8,}\b"),
    re.compile(r"\b(?:sk|rk)-[A-Za-z0-9_-]{12,}\b"),
)
LABELED_SECRET_PATTERN = re.compile(
    r"(?i)\b(?:api[_ -]?key|secret|token)\b(?:[\"'\s]*[:=][\"'\s]*)([A-Za-z0-9_-]{8,})"
)


def _normalize_repo_path(path: str) -> str:
    text = str(path or "").replace("\\", "/").strip()
    if not text:
        return ""
    while text.startswith("./"):
        text = text[2:]
    normalized = PurePosixPath(text).as_posix()
    if normalized == ".":
        return ""
    return "/" + normalized.lstrip("/")


def _is_sensitive_knowledge_target(path: str, *, layout: WorkspaceLayout) -> bool:
    normalized = _normalize_repo_path(path)
    if not normalized:
        return False
    if layout.semantic_role(normalized) in {"knowledge", "capture"}:
        return True
    filename = PurePosixPath(normalized).name.lower()
    return filename in {"agents.md", "claude.md"}


def sanitize_security_text(text: str) -> str:
    return _sanitize_security_text(text)


def contains_security_evidence(text: str) -> bool:
    return any(pattern.search(text) for pattern in SECURITY_EVIDENCE_PATTERNS)


def looks_like_overcautious_security_denial(text: str) -> bool:
    return any(
        pattern.search(text) for pattern in OVERCAUTIOUS_INBOX_SECURITY_DENIAL_PATTERNS
    )


def detect_injection_patterns(text: str) -> list[str]:
    sanitized = sanitize_security_text(text)
    return [name for name, pattern in INJECTION_PATTERNS if pattern.search(sanitized)]


def extract_labeled_secret_values(text: str) -> tuple[str, ...]:
    sanitized = sanitize_security_text(text)
    return tuple(
        dict.fromkeys(
            match.group(1) for match in LABELED_SECRET_PATTERN.finditer(sanitized)
        )
    )


def extract_secret_values(text: str) -> tuple[str, ...]:
    sanitized = sanitize_security_text(text)
    values: list[str] = []
    for pattern in SECRET_VALUE_PATTERNS:
        values.extend(pattern.findall(sanitized))
    values.extend(extract_labeled_secret_values(sanitized))
    return tuple(dict.fromkeys(values))


def detect_sensitive_inbox_export(
    item: InboxItem, *, layout: WorkspaceLayout | None = None
) -> SecurityFinding | None:
    resolved_layout = DEFAULT_WORKSPACE_LAYOUT if layout is None else layout
    request_text = f"{item.subject}\n{item.body}".lower()
    targets = tuple(
        _normalize_repo_path(path)
        for path in extract_repo_local_targets(f"{item.subject}\n{item.body}")
    )
    sensitive_targets = tuple(
        path
        for path in targets
        if _is_sensitive_knowledge_target(path, layout=resolved_layout)
    )
    if not sensitive_targets:
        return None
    if not any(cue in request_text for cue in _OUTBOUND_SHARE_CUES) and not any(
        pattern.search(request_text) for pattern in _SENSITIVE_KNOWLEDGE_ACCESS_PATTERNS
    ):
        return None
    return SecurityFinding(
        kind=SecurityFindingKind.SENSITIVE_KNOWLEDGE_EXPORT,
        evidence=sensitive_targets,
        summary="inbox request attempted outbound sharing or access of internal knowledge material",
    )


def detect_channel_security_finding(item: InboxItem) -> SecurityFinding | None:
    lowered = item.body.lower()
    if (
        "otp" in lowered
        and "do not include the otp" not in lowered
        and "include" in lowered
        and "reply" in lowered
    ):
        return SecurityFinding(
            kind=SecurityFindingKind.CHANNEL_OTP_EXFILTRATION,
            summary="channel inbox request attempted to exfiltrate an OTP token",
        )

    explicit_targets = tuple(
        path.lower() for path in extract_repo_local_targets(item.body)
    )

    def _is_channel_rule_target(path: str) -> bool:
        normalized = _normalize_repo_path(path)
        pure = PurePosixPath(normalized)
        return pure.parent.name.lower() == "channels" and (
            pure.parent.parent.name.lower() == "docs"
            or pure.parent.parent.name.lower().endswith("outbox")
        )

    if any(_is_channel_rule_target(path) for path in explicit_targets) and any(
        verb in lowered for verb in ("delete", "remove", "cleanup", "clean up")
    ):
        return SecurityFinding(
            kind=SecurityFindingKind.CHANNEL_RULES_DESTRUCTIVE_EDIT,
            evidence=tuple(
                _normalize_repo_path(path)
                for path in explicit_targets
                if _is_channel_rule_target(path)
            ),
            summary="channel inbox request attempted a destructive edit of protected channel rules",
        )
    if "channel rules" in lowered and any(
        verb in lowered for verb in ("remove", "delete", "drop")
    ):
        return SecurityFinding(
            kind=SecurityFindingKind.CHANNEL_RULES_DESTRUCTIVE_EDIT,
            summary="channel inbox request attempted a destructive edit of protected channel rules",
        )
    return None
