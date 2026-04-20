from __future__ import annotations

from collections.abc import Sequence
from typing import Literal

from pydantic import BaseModel, Field

from application.contracts import FinanceLookupIntent
from domain.finance import nearest_date_cluster
from domain.finance.exact_matching import finance_record_find_unique_line_item_by_name
from domain.finance.money import money_to_number
from task_routing.gateway import StructuredExtractionStatus
from task_routing.llm_port import LlmPort
from task_routing.model import FinanceLookupRequest, TaskIntent, TaskRouteDecision
from task_routing.prompt_registry import PROMPTS
from task_routing.prompts import build_extraction_prompt


class FinanceLineItemActionPick(BaseModel):
    action: Literal["line_item_price", "line_item_total"] = Field(
        description="Canonical finance action to run."
    )
    confidence: Literal["high", "medium", "low"] = "low"
    reason: str = Field(default="", description="One short sentence.")


def _candidate_line_item_action_records(
    records: Sequence[object],
    intent: FinanceLookupIntent,
) -> tuple[object, ...]:
    criteria = intent.anchor_criteria
    item_name = str(criteria.item_name or "").strip()
    if not item_name:
        return ()
    narrowed = []
    for record in records:
        if not record.matches_record_type(intent.requested_record_type):
            continue
        if str(criteria.counterparty_name or "").strip():
            counterparty = str(getattr(record, "counterparty", "") or "").strip()
            if counterparty.lower() != str(criteria.counterparty_name).strip().lower():
                continue
        if finance_record_find_unique_line_item_by_name(record, item_name) is None:
            continue
        narrowed.append(record)
    if not narrowed:
        return ()
    target_date = str(criteria.target_date or "").strip()
    if target_date and len(narrowed) > 1:
        nearest = nearest_date_cluster(narrowed, target_date=target_date)
        if nearest:
            return tuple(nearest)
    return tuple(narrowed)


def _line_item_action_is_ambiguous(
    records: Sequence[object],
    item_name: str,
) -> bool:
    normalized_name = str(item_name or "").strip()
    if not normalized_name:
        return False
    for record in records:
        line_item = finance_record_find_unique_line_item_by_name(record, normalized_name)
        if line_item is None:
            continue
        quantity = getattr(line_item, "quantity", None)
        if quantity is None or float(quantity) <= 1.0:
            continue
        unit = money_to_number(getattr(line_item, "unit_eur", None))
        line = money_to_number(getattr(line_item, "line_eur", None))
        if unit is None or line is None:
            continue
        if abs(float(unit) - float(line)) > 1e-9:
            return True
    return False


def _summarize_line_item_action_record(record: object, index: int) -> str:
    path = str(getattr(record, "path", "") or "").strip()
    record_type = str(getattr(record, "record_type", "") or "").strip()
    record_date = str(getattr(record, "date", "") or "").strip()
    counterparty = str(getattr(record, "counterparty", "") or "").strip()
    item_parts: list[str] = []
    for line_item in getattr(record, "line_items", ()) or ():
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
        item_parts.append(" ".join(parts))
    fields = [f"[{index}] {path}"]
    if record_type:
        fields.append(f"type={record_type}")
    if record_date:
        fields.append(f"date={record_date}")
    if counterparty:
        fields.append(f"counterparty={counterparty}")
    if item_parts:
        fields.append("items=" + "; ".join(item_parts[:8]))
    return " | ".join(fields)


def _maybe_disambiguate_line_item_action(
    llm_port: LlmPort,
    *,
    task_text: str,
    records: Sequence[object],
    intent: FinanceLookupIntent,
) -> FinanceLookupIntent:
    if intent.action not in {"line_item_price", "line_item_total"}:
        return intent
    criteria = intent.anchor_criteria
    item_name = str(criteria.item_name or "").strip()
    if not item_name:
        return intent
    candidates = _candidate_line_item_action_records(records, intent)
    if not candidates:
        return intent
    if not _line_item_action_is_ambiguous(candidates, item_name):
        return intent
    payload = "\n".join(
        _summarize_line_item_action_record(record, index)
        for index, record in enumerate(candidates)
    )
    extraction = llm_port.run_raw(
        stage="finance_lookup_action_disambiguation",
        role="core",
        response_format=FinanceLineItemActionPick,
        messages=[
            {"role": "system", "content": PROMPTS["finance_lookup_action_disambiguation"]},
            {
                "role": "user",
                "content": f"Instruction: {task_text}\n\nCandidate records:\n{payload}",
            },
        ],
        max_completion_tokens=192,
        trace_context_extra={"intent": str(TaskIntent.FINANCE_LOOKUP.value)},
    )
    if extraction.status is not StructuredExtractionStatus.RESOLVED:
        return intent
    parsed = extraction.parsed
    if not isinstance(parsed, FinanceLineItemActionPick):
        return intent
    if parsed.action == intent.action:
        return intent
    return FinanceLookupIntent(
        action=parsed.action,
        anchor_criteria=intent.anchor_criteria,
        requested_record_type=intent.requested_record_type,
        since_date=intent.since_date,
        amount_hints=intent.amount_hints,
        output_format=intent.output_format,
    )


def build_finance_lookup_intent_deriver(
    context,
    llm_port: LlmPort,
):
    def _derive_finance_lookup_intent(
        task_text: str,
        extracted_payload,
        translated_text: str | None,
        context_payload,
    ):
        from task_routing.finance_lookup import resolve_finance_lookup_intent

        intent = resolve_finance_lookup_intent(
            task_text,
            extracted=extracted_payload,
            translated_text=translated_text,
            context_payload=context_payload,
        )
        if intent is not None:
            return _maybe_disambiguate_line_item_action(
                llm_port,
                task_text=translated_text or task_text,
                records=context.finance_records,
                intent=intent,
            )
        if extracted_payload:
            return None
        extraction = llm_port.run_raw(
            stage="finance_lookup_reextract",
            role="core",
            response_format=FinanceLookupRequest,
            messages=[
                {
                    "role": "system",
                    "content": build_extraction_prompt(
                        TaskRouteDecision(intent=TaskIntent.FINANCE_LOOKUP),
                        workspace_policies=context.workspace_policies,
                    ),
                },
                {"role": "user", "content": translated_text or task_text},
            ],
            max_completion_tokens=512,
            trace_context_extra={"intent": str(TaskIntent.FINANCE_LOOKUP.value)},
        )
        if extraction.status is not StructuredExtractionStatus.RESOLVED:
            return None
        parsed = extraction.parsed
        if not isinstance(parsed, FinanceLookupRequest):
            return None
        reextracted_intent = resolve_finance_lookup_intent(
            task_text,
            extracted=parsed.model_dump(exclude_none=True),
            translated_text=translated_text,
            context_payload=context_payload,
        )
        if reextracted_intent is None:
            return None
        return _maybe_disambiguate_line_item_action(
            llm_port,
            task_text=translated_text or task_text,
            records=context.finance_records,
            intent=reextracted_intent,
        )

    return _derive_finance_lookup_intent


__all__ = ["build_finance_lookup_intent_deriver"]
