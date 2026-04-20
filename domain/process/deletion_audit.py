from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True, slots=True)
class DeletionAudit:
    workflow_name: str
    deleted_paths: tuple[str, ...]
    evidence_refs: tuple[str, ...] = ()
    requested_by_path: str = ""
    rationale: str = ""

    def as_payload(self) -> dict[str, object]:
        return {
            "workflow_name": self.workflow_name,
            "deleted_paths": self.deleted_paths,
            "evidence_refs": self.evidence_refs,
            "requested_by_path": self.requested_by_path,
            "rationale": self.rationale,
        }
