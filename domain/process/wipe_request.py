from __future__ import annotations

from dataclasses import dataclass
from enum import Enum


class WipeSafetyScope(str, Enum):
    EXACT_PATH = "exact_path"
    SUBTREE = "subtree"
    MIXED = "mixed"


@dataclass(frozen=True, slots=True)
class WipeRequest:
    workflow_name: str
    target_paths: tuple[str, ...]
    requested_by_path: str = ""
    requester_identity: str = ""
    requester_evidence: tuple[str, ...] = ()
    rationale: str = ""
    safety_scope: WipeSafetyScope = WipeSafetyScope.EXACT_PATH

    def as_payload(self) -> dict[str, object]:
        return {
            "workflow_name": self.workflow_name,
            "target_paths": self.target_paths,
            "requested_by_path": self.requested_by_path,
            "requester_identity": self.requester_identity,
            "requester_evidence": self.requester_evidence,
            "rationale": self.rationale,
            "safety_scope": self.safety_scope.value,
        }


__all__ = [
    "WipeRequest",
    "WipeSafetyScope",
]
