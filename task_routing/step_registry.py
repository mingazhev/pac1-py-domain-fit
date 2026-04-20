from __future__ import annotations

from .model import (
    AccountLookupRequest,
    CaptureLookupRequest,
    ContactLookupRequest,
    EntityQueryRequest,
    FinanceLookupRequest,
    FinanceMutationRequest,
    FollowUpRescheduleRequest,
    FollowUpSendRequest,
    InboxEmailLookupRequest,
    InboxProcessNextRequest,
    MessageQueryRequest,
    OutboundEmailLookupRequest,
    OutboxDraftRequest,
    ProjectMutationRequest,
    ProjectQueryRequest,
    QueueMutationRequest,
    QueueStateLookupRequest,
    TypedTaskRequest,
)
from .step_contract import (
    StepContract,
    StepPolicyClass,
    StepResultShape,
    StepSideEffectClass,
)


_READ_OPEN_SCALAR = StepContract(
    side_effect_class=StepSideEffectClass.READ,
    policy_class=StepPolicyClass.OPEN,
    result_shape=StepResultShape.SCALAR,
    grounding_required=True,
    continuation_allowed=False,
)

_READ_OPEN_COLLECTION = StepContract(
    side_effect_class=StepSideEffectClass.READ,
    policy_class=StepPolicyClass.OPEN,
    result_shape=StepResultShape.COLLECTION,
    grounding_required=True,
    continuation_allowed=False,
)

_READ_OPEN_AGGREGATE = StepContract(
    side_effect_class=StepSideEffectClass.READ,
    policy_class=StepPolicyClass.OPEN,
    result_shape=StepResultShape.AGGREGATE,
    grounding_required=True,
    continuation_allowed=False,
)

_MUTATE_AUTHZ = StepContract(
    side_effect_class=StepSideEffectClass.MUTATE,
    policy_class=StepPolicyClass.AUTHZ_REQUIRED,
    result_shape=StepResultShape.ACTION_RESULT,
    grounding_required=True,
    continuation_allowed=False,
)

_WORKFLOW_AUTHZ = StepContract(
    side_effect_class=StepSideEffectClass.WORKFLOW,
    policy_class=StepPolicyClass.AUTHZ_REQUIRED,
    result_shape=StepResultShape.DECISION,
    grounding_required=True,
    continuation_allowed=True,
)


_CONTRACTS: dict[type, StepContract] = {
    AccountLookupRequest: _READ_OPEN_SCALAR,
    ContactLookupRequest: _READ_OPEN_SCALAR,
    CaptureLookupRequest: _READ_OPEN_SCALAR,
    ProjectQueryRequest: _READ_OPEN_SCALAR,
    EntityQueryRequest: _READ_OPEN_SCALAR,
    MessageQueryRequest: _READ_OPEN_SCALAR,
    FinanceLookupRequest: _READ_OPEN_AGGREGATE,
    OutboundEmailLookupRequest: _READ_OPEN_COLLECTION,
    QueueStateLookupRequest: _READ_OPEN_SCALAR,
    InboxEmailLookupRequest: _READ_OPEN_COLLECTION,
    FinanceMutationRequest: _MUTATE_AUTHZ,
    OutboxDraftRequest: _MUTATE_AUTHZ,
    ProjectMutationRequest: _MUTATE_AUTHZ,
    QueueMutationRequest: _MUTATE_AUTHZ,
    FollowUpSendRequest: _WORKFLOW_AUTHZ,
    FollowUpRescheduleRequest: _WORKFLOW_AUTHZ,
    InboxProcessNextRequest: _WORKFLOW_AUTHZ,
}


class UnregisteredStepError(KeyError):
    """Raised when a typed step has no declared StepContract."""


def contract_for_command(command: TypedTaskRequest) -> StepContract:
    try:
        return _CONTRACTS[type(command)]
    except KeyError as exc:
        raise UnregisteredStepError(
            f"No StepContract registered for {type(command).__name__}; "
            "every typed step must declare its side-effect/policy/result contract"
        ) from exc


def registered_step_types() -> tuple[type, ...]:
    return tuple(_CONTRACTS.keys())


def update_contract(command_type: type, contract: StepContract) -> None:
    """Explicit override used by higher-level refactors (e.g. when a step
    type gains an aggregate variant). Not for runtime use."""

    _CONTRACTS[command_type] = contract


__all__ = [
    "UnregisteredStepError",
    "contract_for_command",
    "registered_step_types",
    "update_contract",
]
