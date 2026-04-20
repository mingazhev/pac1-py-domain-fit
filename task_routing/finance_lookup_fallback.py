"""LLM fallback for finance-lookup shapes without a typed handler.

The deterministic finance-lookup resolver covers a closed set of
canonical actions (counterparty_total, service_line_total,
record_date, line_item_total, line_item_count, line_item_quantity,
line_item_price).
Tasks whose phrasing doesn't land cleanly on that set — e.g.
'find the invoice from <date> and <vendor>' or 'list oldest N
invoices linked to X' — used to fall off the end and clarify.

This module lets the LLM compose a typed lookup answer from the
canonical finance record summary the runtime already has. The LLM
never fabricates records; it picks from the visible set and answers
exactly what the task asks for.
"""
from __future__ import annotations

from typing import Literal

from pydantic import BaseModel, Field

from domain.finance import FinanceRecord
from domain.finance.money import money_to_number

from .gateway import StructuredExtractionGateway
from .llm_port import GatewayBackedLlmPort
from .prompt_registry import PROMPTS
from .reasoning import reasoning_effort_for_stage


class FinanceLookupFallbackPlan(BaseModel):
    """Typed output of the finance-lookup LLM fallback."""

    decision: Literal["answer", "clarify", "refuse"] = "clarify"
    answer_text: str = Field(
        default="",
        description=(
            "The exact answer string to return to the user when "
            "decision=answer. Formatted as the task requested."
        ),
    )
    reason: str = Field(
        default="",
        description="One short sentence explaining the decision.",
    )
    grounding_paths: tuple[str, ...] = Field(
        default=(),
        description=(
            "Canonical repo-absolute paths of the finance records "
            "that justify the answer. Must be drawn from the record "
            "summary — do not invent paths."
        ),
    )


def _format_record(record: FinanceRecord) -> str:
    amount = getattr(record, "total_eur", None)
    if amount is None:
        amount = getattr(record, "amount_eur", None)
    if amount is None:
        amount = getattr(record, "amount", None)
    amount = money_to_number(amount)
    counterparty = str(record.counterparty or "").strip() or "(unknown counterparty)"
    kind = getattr(record.record_type, "value", str(record.record_type))
    line_items: list[str] = []
    for line_item in record.line_items:
        item_name = str(getattr(line_item, "item", "") or "").strip()
        if not item_name:
            continue
        parts = [item_name]
        quantity = getattr(line_item, "quantity", None)
        if quantity is not None:
            parts.append(f"qty={quantity}")
        unit = money_to_number(getattr(line_item, "unit_eur", None))
        if unit is not None:
            parts.append(f"unit={unit}")
        line = money_to_number(getattr(line_item, "line_eur", None))
        if line is not None:
            parts.append(f"line={line}")
        line_items.append(" ".join(parts))
    pieces = [
        f"path={record.path}",
        f"kind={kind}",
        f"date={record.date or '?'}",
        f"counterparty={counterparty}",
    ]
    if amount is not None:
        pieces.append(f"amount={amount}")
    if line_items:
        pieces.append(f"line_items=[{'; '.join(line_items[:8])}]")
    return "- " + "; ".join(pieces)


def plan_finance_lookup_fallback(
    gateway: StructuredExtractionGateway,
    model: str,
    *,
    task_text: str,
    finance_records: tuple[FinanceRecord, ...],
    root_policy_text: str = "",
    finance_policy_text: str = "",
    max_records: int = 60,
    max_completion_tokens: int = 512,
) -> FinanceLookupFallbackPlan | None:
    records = finance_records[:max_records]
    if not records:
        return None
    summary = "\n".join(_format_record(r) for r in records)
    payload = (
        f"Task: {task_text.strip()}\n\n"
        f"Canonical finance records ({len(records)}):\n{summary}"
    )
    system_prompt = PROMPTS["finance_lookup_fallback"]
    policy_segments: list[str] = []
    root = str(root_policy_text or "").strip()
    if root:
        policy_segments.append(
            "Root workspace policy (AGENTS.MD at repo root):\n" + root
        )
    finance_policy = str(finance_policy_text or "").strip()
    if finance_policy:
        policy_segments.append(
            "Finance folder policy (AGENTS.MD — OVERRIDES the root policy "
            "on any conflict):\n" + finance_policy
        )
    if policy_segments:
        system_prompt = system_prompt + "\n\n" + "\n\n".join(policy_segments)
    reasoning_effort = reasoning_effort_for_stage("finance_lookup_fallback")
    llm_port = GatewayBackedLlmPort(gateway, model)
    return llm_port.plan(
        stage="finance_lookup_fallback",
        role="fallback",
        response_format=FinanceLookupFallbackPlan,
        messages=[
            {"role": "system", "content": system_prompt},
            {"role": "user", "content": payload},
        ],
        max_completion_tokens=max_completion_tokens,
        reasoning_effort=reasoning_effort,
    )


__all__ = ["FinanceLookupFallbackPlan", "plan_finance_lookup_fallback"]
