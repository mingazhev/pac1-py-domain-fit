"""LLM fallback for mutation variants without a dedicated composer.

Keeps the architectural contract: LLM produces a typed, constrained
plan; deterministic code applies it through ``vm.write`` + the
canonical frontmatter merge helper. The LLM never writes free-form
markdown — it only supplies a flat dict of frontmatter updates.
"""
from __future__ import annotations

from typing import Literal

from pydantic import BaseModel, Field

from .gateway import StructuredExtractionGateway
from .llm_port import GatewayBackedLlmPort
from .prompt_registry import PROMPTS
from .reasoning import reasoning_effort_for_stage


class MutationFallbackPlan(BaseModel):
    """Typed output of the mutation fallback LLM pass.

    The runtime applies this by calling
    ``_vm_merge_frontmatter(vm, path, frontmatter_updates)`` —
    canonical provenance from the target's own metadata table is
    lifted in automatically, and the typed updates here layer the
    mutation's new evidence on top.
    """

    decision: Literal["apply", "clarify", "refuse"] = "clarify"
    reason: str = Field(
        default="",
        description="One short sentence explaining the decision.",
    )
    target_path: str | None = Field(
        default=None,
        description=(
            "Canonical repo-absolute path to the target markdown "
            "record, e.g. '/50_finance/purchases/...md'. Required "
            "when decision=apply."
        ),
    )
    frontmatter_updates: dict[str, str | int | float | bool] = Field(
        default_factory=dict,
        description=(
            "Flat field->value updates to merge into the target "
            "record's YAML frontmatter. No nested objects, no lists. "
            "Keys are canonical frontmatter field names (e.g. "
            "payment_state, amount_eur, settlement_reference). "
            "Empty when decision != apply."
        ),
    )


def plan_mutation_fallback(
    gateway: StructuredExtractionGateway,
    model: str,
    *,
    task_text: str,
    command_summary: str,
    existing_record_text: str | None = None,
    root_policy_text: str = "",
    lane_policy_text: str = "",
    lane_label: str = "",
    max_completion_tokens: int = 400,
) -> MutationFallbackPlan | None:
    pieces = [
        f"Task: {task_text.strip()}",
        f"Typed command: {command_summary.strip()}",
    ]
    if existing_record_text:
        truncated = existing_record_text.strip()[:4000]
        pieces.append(f"Existing record markdown:\n{truncated}")
    payload = "\n\n".join(pieces)

    system_prompt = PROMPTS["mutation_fallback"]
    policy_segments: list[str] = []
    root = str(root_policy_text or "").strip()
    if root:
        policy_segments.append(
            "Root workspace policy (AGENTS.MD at repo root):\n" + root
        )
    lane = str(lane_policy_text or "").strip()
    if lane:
        label = (str(lane_label or "").strip() or "Lane")
        policy_segments.append(
            f"{label} folder policy (AGENTS.MD — OVERRIDES the root policy "
            "on any conflict):\n" + lane
        )
    if policy_segments:
        system_prompt = system_prompt + "\n\n" + "\n\n".join(policy_segments)
    reasoning_effort = reasoning_effort_for_stage("mutation_fallback")

    llm_port = GatewayBackedLlmPort(gateway, model)
    return llm_port.plan(
        stage="mutation_fallback",
        role="fallback",
        response_format=MutationFallbackPlan,
        messages=[
            {"role": "system", "content": system_prompt},
            {"role": "user", "content": payload},
        ],
        max_completion_tokens=max_completion_tokens,
        reasoning_effort=reasoning_effort,
    )


__all__ = ["MutationFallbackPlan", "plan_mutation_fallback"]
