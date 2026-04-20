from __future__ import annotations

from dataclasses import dataclass
from enum import Enum


class HumanDecisionRequired(str, Enum):
    """Reasons why a human decision is required before an action proceeds."""

    COMMITMENT = "commitment"
    PURCHASE = "purchase"
    RELATIONSHIP_JUDGMENT = "relationship_judgment"
    VALUE_TRADEOFF = "value_tradeoff"
    EXTERNAL_AUTOMATION = "external_automation"
    CONSENT_REQUIRED = "consent_required"
    DATA_EXPORT = "data_export"


class ExportIntent(str, Enum):
    """The kind of export action taking place."""

    LOCAL_REPORT = "local_report"
    OUTBOUND_PUBLISH = "outbound_publish"
    EXTERNAL_SYNC = "external_sync"
    DATA_EXPORT = "data_export"


class DataResidency(str, Enum):
    LOCAL_ONLY = "local_only"
    WORKSPACE = "workspace"
    EXTERNAL_EXPORT_ALLOWED = "external_export_allowed"


@dataclass(frozen=True, slots=True)
class DelegationBoundary:
    """Records whether an action requires explicit human delegation before proceeding."""

    requires_human_decision: bool
    reason: HumanDecisionRequired | None = None
    description: str = ""


@dataclass(frozen=True, slots=True)
class CommitmentGuard:
    """Policy gate for actions that commit to financial, relationship, or external consequences.

    Use ``to_delegation_boundary()`` to surface as a typed
    ``DelegationBoundary`` for downstream routing and audit.
    """

    is_commitment: bool
    commitment_reason: HumanDecisionRequired | None = None

    def to_delegation_boundary(self) -> DelegationBoundary:
        return DelegationBoundary(
            requires_human_decision=self.is_commitment,
            reason=self.commitment_reason,
        )


@dataclass(frozen=True, slots=True)
class DataResidencyPolicy:
    """Declares where data produced or consumed by an action is allowed to live."""

    residency: DataResidency
    justification: str = ""

    @classmethod
    def workspace(cls, justification: str = "") -> DataResidencyPolicy:
        return cls(residency=DataResidency.WORKSPACE, justification=justification)

    @classmethod
    def external_export_allowed(cls, justification: str = "") -> DataResidencyPolicy:
        return cls(
            residency=DataResidency.EXTERNAL_EXPORT_ALLOWED,
            justification=justification,
        )

    def allows_external_export(self) -> bool:
        return self.residency == DataResidency.EXTERNAL_EXPORT_ALLOWED


@dataclass(frozen=True, slots=True)
class ConsentBoundary:
    """Records whether an action requires explicit consent before execution."""

    requires_consent: bool
    consent_reason: str = ""
    export_intent: ExportIntent | None = None

    @classmethod
    def required(
        cls,
        reason: str,
        export_intent: ExportIntent | None = None,
    ) -> ConsentBoundary:
        return cls(
            requires_consent=True,
            consent_reason=reason,
            export_intent=export_intent,
        )

    @classmethod
    def not_required(cls) -> ConsentBoundary:
        return cls(requires_consent=False)


# ---------------------------------------------------------------------------
# Classification helpers
# ---------------------------------------------------------------------------

_EXTERNAL_COMMITMENT_ACTIONS: dict[str, HumanDecisionRequired] = {
    "purchase": HumanDecisionRequired.PURCHASE,
    "bank_transfer": HumanDecisionRequired.COMMITMENT,
    "payment_authorization": HumanDecisionRequired.COMMITMENT,
    "contact_sync": HumanDecisionRequired.EXTERNAL_AUTOMATION,
    "report_publish": HumanDecisionRequired.EXTERNAL_AUTOMATION,
    "calendar_event_create": HumanDecisionRequired.EXTERNAL_AUTOMATION,
    "data_export": HumanDecisionRequired.DATA_EXPORT,
}


def classify_commitment(action_kind: str) -> CommitmentGuard:
    """Classify whether an action requires human decision before proceeding.

    Returns a ``CommitmentGuard`` with ``is_commitment=True`` and the matching
    reason for any action that crosses a delegation boundary.
    """
    reason = _EXTERNAL_COMMITMENT_ACTIONS.get(action_kind)
    if reason is not None:
        return CommitmentGuard(is_commitment=True, commitment_reason=reason)
    return CommitmentGuard(is_commitment=False)


def consent_boundary_for_external_mutation(action_kind: str) -> ConsentBoundary:
    """Return the consent boundary that applies to an external mutation action."""
    if action_kind in {"contact_sync", "report_publish", "calendar_event_create"}:
        return ConsentBoundary.required(
            reason=f"external mutation '{action_kind}' requires explicit consent",
            export_intent=ExportIntent.EXTERNAL_SYNC,
        )
    if action_kind == "data_export":
        return ConsentBoundary.required(
            reason="data export to external system requires explicit consent",
            export_intent=ExportIntent.DATA_EXPORT,
        )
    return ConsentBoundary.not_required()


__all__ = [
    "HumanDecisionRequired",
    "ExportIntent",
    "DataResidency",
    "DelegationBoundary",
    "CommitmentGuard",
    "DataResidencyPolicy",
    "ConsentBoundary",
    "classify_commitment",
    "consent_boundary_for_external_mutation",
]
