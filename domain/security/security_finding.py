from __future__ import annotations

from dataclasses import dataclass
from enum import Enum


class SecurityFindingKind(str, Enum):
    SENSITIVE_KNOWLEDGE_EXPORT = "sensitive_knowledge_export"
    CHANNEL_OTP_EXFILTRATION = "channel_otp_exfiltration"
    CHANNEL_RULES_DESTRUCTIVE_EDIT = "channel_rules_destructive_edit"


@dataclass(frozen=True, slots=True)
class SecurityFinding:
    kind: SecurityFindingKind
    evidence: tuple[str, ...] = ()
    summary: str = ""
