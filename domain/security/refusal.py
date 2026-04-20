from __future__ import annotations

from collections.abc import Iterable, Sequence
from dataclasses import dataclass
from enum import Enum


class SecurityRefusalKind(str, Enum):
    """Typed denial causes that live in code, not prompt text.

    Every refusal surfaced to the model or recorded as an outcome must map to
    one of these kinds. Free-form refusal strings drift over time; a typed
    catalog keeps security wording auditable and prevents silent rewording.
    """

    INJECTION_IN_TASK_INSTRUCTION = "injection_in_task_instruction"
    INJECTION_IN_PREFLIGHT_CONTEXT = "injection_in_preflight_context"
    INJECTION_IN_INBOX_ITEM = "injection_in_inbox_item"
    INJECTION_IN_TOOL_RESULT = "injection_in_tool_result"
    PROTECTED_AUTHORITY_PATH = "protected_authority_path"
    SECRET_EXFILTRATION_OBSERVED_TOKEN = "secret_exfiltration_observed_token"
    SECRET_EXFILTRATION_LABELED_SECRET = "secret_exfiltration_labeled_secret"
    SENSITIVE_KNOWLEDGE_EXPORT = "sensitive_knowledge_export"


@dataclass(frozen=True, slots=True)
class SecurityRefusal:
    kind: SecurityRefusalKind
    reason: str
    summary: str = ""

    @property
    def outcome_name(self) -> str:
        return "OUTCOME_DENIED_SECURITY"


def _joined_findings(findings: Iterable[str]) -> str:
    return ", ".join(tuple(findings))


def refusal_for_injection_in_task_instruction(
    findings: Sequence[str],
) -> SecurityRefusal:
    findings_text = _joined_findings(findings)
    return SecurityRefusal(
        kind=SecurityRefusalKind.INJECTION_IN_TASK_INSTRUCTION,
        reason=f"injection content detected in task instruction: {findings_text}",
        summary="Task instruction contains known injection patterns and must be denied.",
    )


def refusal_for_injection_in_preflight_context(
    tool: str, findings: Sequence[str]
) -> SecurityRefusal:
    findings_text = _joined_findings(findings)
    return SecurityRefusal(
        kind=SecurityRefusalKind.INJECTION_IN_PREFLIGHT_CONTEXT,
        reason=(
            f"injection content detected in preflight context ({tool}): {findings_text}"
        ),
    )


def refusal_for_injection_in_inbox_item(
    inbox_path: str, findings: Sequence[str]
) -> SecurityRefusal:
    findings_text = _joined_findings(findings)
    return SecurityRefusal(
        kind=SecurityRefusalKind.INJECTION_IN_INBOX_ITEM,
        reason=f"injection content detected in inbox item: {findings_text}",
        summary=f"inbox gate denied injection content in {inbox_path}",
    )


def refusal_for_injection_in_tool_result(findings: Sequence[str]) -> SecurityRefusal:
    findings_text = _joined_findings(findings)
    return SecurityRefusal(
        kind=SecurityRefusalKind.INJECTION_IN_TOOL_RESULT,
        reason=f"injection content detected in tool result: {findings_text}",
    )


def refusal_for_protected_authority_path(path: str) -> SecurityRefusal:
    return SecurityRefusal(
        kind=SecurityRefusalKind.PROTECTED_AUTHORITY_PATH,
        reason=f"protected authority path blocked: {path}",
    )


def refusal_for_secret_exfiltration(finding: str) -> SecurityRefusal:
    if finding == "observed_secret_token":
        return SecurityRefusal(
            kind=SecurityRefusalKind.SECRET_EXFILTRATION_OBSERVED_TOKEN,
            reason=(
                "secret exfiltration blocked: observed secret token in outbound content"
            ),
        )
    if finding == "labeled_secret":
        return SecurityRefusal(
            kind=SecurityRefusalKind.SECRET_EXFILTRATION_LABELED_SECRET,
            reason=(
                "secret exfiltration blocked: outbound content contains labeled secret"
            ),
        )
    raise ValueError(f"unknown secret exfiltration finding: {finding!r}")


def refusal_for_sensitive_knowledge_export(
    inbox_path: str, targets: Sequence[str]
) -> SecurityRefusal:
    exported = ", ".join(tuple(targets)[:2])
    return SecurityRefusal(
        kind=SecurityRefusalKind.SENSITIVE_KNOWLEDGE_EXPORT,
        reason=(
            "inbox request attempted outbound sharing of internal knowledge material "
            f"from {exported}"
        ),
        summary=f"inbox gate denied sensitive knowledge export in {inbox_path}",
    )
