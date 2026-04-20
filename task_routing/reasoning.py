from __future__ import annotations

import os

from .gateway import ReasoningEffort


PAC1_WORKFLOW_CLASSIFIER_REASONING_EFFORT = (
    "PAC1_WORKFLOW_CLASSIFIER_REASONING_EFFORT"
)
PAC1_ROUTE_DISCLOSURE_REASONING_EFFORT = (
    "PAC1_ROUTE_DISCLOSURE_REASONING_EFFORT"
)
PAC1_FINANCE_LOOKUP_FALLBACK_REASONING_EFFORT = (
    "PAC1_FINANCE_LOOKUP_FALLBACK_REASONING_EFFORT"
)
PAC1_MUTATION_FALLBACK_REASONING_EFFORT = (
    "PAC1_MUTATION_FALLBACK_REASONING_EFFORT"
)

_ALLOWED: set[str] = {"none", "minimal", "low", "medium", "high", "xhigh"}
_STAGE_DEFAULTS: dict[str, ReasoningEffort | None] = {
    "workflow_classifier": None,
    "route_disclosure": None,
    "finance_lookup_fallback": "high",
    "mutation_fallback": "high",
}
_STAGE_ENVS = {
    "workflow_classifier": PAC1_WORKFLOW_CLASSIFIER_REASONING_EFFORT,
    "route_disclosure": PAC1_ROUTE_DISCLOSURE_REASONING_EFFORT,
    "finance_lookup_fallback": PAC1_FINANCE_LOOKUP_FALLBACK_REASONING_EFFORT,
    "mutation_fallback": PAC1_MUTATION_FALLBACK_REASONING_EFFORT,
}
_DISABLED = {"", "default", "off", "false", "no", "0"}


def reasoning_effort_for_stage(stage: str) -> ReasoningEffort | None:
    env_name = _STAGE_ENVS.get(stage)
    if env_name:
        raw = os.environ.get(env_name, "").strip().lower()
        if raw in _DISABLED:
            return _STAGE_DEFAULTS.get(stage)
        if raw in _ALLOWED:
            return raw  # type: ignore[return-value]
    return _STAGE_DEFAULTS.get(stage)
