from __future__ import annotations

from dataclasses import dataclass
from enum import Enum


class StepSideEffectClass(str, Enum):
    READ = "read"
    MUTATE = "mutate"
    WORKFLOW = "workflow"


class StepPolicyClass(str, Enum):
    OPEN = "open"
    AUTHZ_REQUIRED = "authz_required"


class StepResultShape(str, Enum):
    SCALAR = "scalar"
    COLLECTION = "collection"
    AGGREGATE = "aggregate"
    ACTION_RESULT = "action_result"
    DECISION = "decision"


@dataclass(frozen=True, slots=True)
class StepContract:
    """Static metadata every typed step declares up front.

    Each registered step type owns a ``StepContract`` so the machine can
    reason about it without hard-coding per-step knowledge in the
    dispatcher. The contract is read before execution (authorization,
    continuation, postcheck shaping) and must not change per request.
    """

    side_effect_class: StepSideEffectClass
    policy_class: StepPolicyClass
    result_shape: StepResultShape
    grounding_required: bool
    continuation_allowed: bool


__all__ = [
    "StepContract",
    "StepPolicyClass",
    "StepResultShape",
    "StepSideEffectClass",
]
