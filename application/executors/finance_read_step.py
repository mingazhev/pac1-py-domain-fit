from __future__ import annotations

from dataclasses import replace
from datetime import datetime
from application.contracts import FinanceLookupIntent
from application.ports import (
    InterpretationRequest,
    KIND_FINANCE_LOOKUP_FALLBACK,
    dispatch_read_interpretation,
)
from application.queries import resolve_finance_lookup_query
from domain.finance.anchor_resolution import resolve_exact_finance_anchor_by_path
from domain.finance.exact_matching import (
    finance_record_find_unique_line_item_by_name,
    finance_record_matches_counterparty_name,
)

from .read_result import ReadStepExecutionResult, from_interpretation_result


def execute_finance_lookup_step(
    command,
    *,
    task_text: str,
    context,
    interpretation_port,
) -> ReadStepExecutionResult:
    derived_anchor = str(getattr(command, "anchor_record_ref", "") or "").strip()
    extracted_payload = command_payload(command)
    intent = None
    if (
        interpretation_port is not None
        and interpretation_port.derive_finance_lookup_intent is not None
    ):
        intent = interpretation_port.derive_finance_lookup_intent(
            task_text,
            extracted_payload,
            getattr(command, "translated_text", None),
            context.context_payload,
        )
    result = None
    if intent is not None:
        derived_anchor = _resolve_finance_anchor_after_intent(
            derived_anchor,
            task_text=task_text,
            records=context.finance_records,
            intent=intent,
            interpretation_port=interpretation_port,
        )
        intent = enrich_finance_intent_from_anchor(
            intent, derived_anchor, context.finance_records
        )
        result = resolve_finance_lookup_query(
            context.finance_records,
            intent=intent,
            task_text=task_text,
        )
    if (
        result is None
        and interpretation_port is not None
        and interpretation_port.derive_finance_lookup_intent is not None
        and extracted_payload
        ):
        retried_intent = interpretation_port.derive_finance_lookup_intent(
            task_text,
            {},
            getattr(command, "translated_text", None),
            context.context_payload,
        )
        if retried_intent is not None:
            derived_anchor = _resolve_finance_anchor_after_intent(
                derived_anchor,
                task_text=task_text,
                records=context.finance_records,
                intent=retried_intent,
                interpretation_port=interpretation_port,
            )
            retried_intent = enrich_finance_intent_from_anchor(
                retried_intent, derived_anchor, context.finance_records
            )
            result = resolve_finance_lookup_query(
                context.finance_records,
                intent=retried_intent,
                task_text=task_text,
            )
            if result is not None:
                intent = retried_intent
    if result is not None:
        return ReadStepExecutionResult(
            status="done",
            message=result.message,
            reason_code="finance_lookup_resolved",
            refs=result.grounding_refs,
        )
    if (
        interpretation_port is not None
        and interpretation_port.plan_finance_lookup_fallback is not None
    ):
        envelope = dispatch_read_interpretation(
            interpretation_port,
            InterpretationRequest(
                kind=KIND_FINANCE_LOOKUP_FALLBACK,
                payload={
                    "task_text": task_text,
                    "finance_records": context.finance_records,
                    "root_policy": context.workspace_policies.root,
                    "finance_policy": context.workspace_policies.finance,
                },
            ),
        )
        if envelope.plan is not None:
            return from_interpretation_result(
                envelope.plan,
                llm_stage=envelope.llm_stage or "finance_lookup_fallback",
            )
    if intent is None:
        return ReadStepExecutionResult(
            status="clarify",
            message="Could not derive a deterministic finance lookup intent from the request.",
            reason_code="finance_lookup_requires_clarification",
        )
    return ReadStepExecutionResult(
        status="clarify",
        message="Could not resolve the requested finance record or aggregate from canonical finance records.",
        reason_code="finance_lookup_requires_clarification",
    )


def _resolve_finance_anchor_after_intent(
    current_anchor: str,
    *,
    task_text: str,
    records,
    intent: FinanceLookupIntent,
    interpretation_port,
) -> str:
    if str(current_anchor or "").strip():
        return str(current_anchor or "").strip()
    exact_anchor = resolve_exact_finance_anchor_by_path(task_text, records)
    if exact_anchor:
        return exact_anchor
    if (
        interpretation_port is None
        or interpretation_port.resolve_finance_anchor_record_ref is None
    ):
        return ""
    candidates = _candidate_anchor_records(records, intent)
    if not candidates:
        candidates = tuple(records)
    resolved = interpretation_port.resolve_finance_anchor_record_ref(
        task_text,
        candidates,
    )
    return str(resolved or "").strip()


def _candidate_anchor_records(records, intent: FinanceLookupIntent):
    criteria = intent.anchor_criteria
    narrowed = []
    for record in records:
        if not record.matches_record_type(intent.requested_record_type):
            continue
        if (
            criteria.counterparty_name
            and not finance_record_matches_counterparty_name(
                record, criteria.counterparty_name
            )
        ):
            continue
        if (
            criteria.item_name
            and finance_record_find_unique_line_item_by_name(record, criteria.item_name) is None
        ):
            continue
        narrowed.append(record)
    if criteria.target_date and len(narrowed) > 1:
        nearest = _nearest_date_records(narrowed, criteria.target_date)
        if nearest:
            return nearest
    return tuple(narrowed)


def _nearest_date_records(records, target_date: str):
    try:
        target = datetime.strptime(str(target_date or "").strip(), "%Y-%m-%d").date()
    except ValueError:
        return ()
    ranked = []
    for record in records:
        record_date = str(getattr(record, "date", "") or "").strip()
        if not record_date:
            continue
        try:
            candidate = datetime.strptime(record_date, "%Y-%m-%d").date()
        except ValueError:
            continue
        ranked.append((abs((candidate - target).days), record_date, record))
    if not ranked:
        return ()
    ranked.sort(key=lambda item: (item[0], item[1]))
    best_distance = ranked[0][0]
    return tuple(record for distance, _, record in ranked if distance == best_distance)


def enrich_finance_intent_from_anchor(
    intent: FinanceLookupIntent,
    anchor_record_ref: str | None,
    finance_records,
):
    ref = str(anchor_record_ref or "").strip()
    if not ref:
        return intent
    normalized = ref if ref.startswith("/") else f"/{ref}"
    for record in finance_records:
        record_path = str(getattr(record, "path", "") or "").strip()
        candidate = record_path if record_path.startswith("/") else f"/{record_path}"
        if candidate != normalized:
            continue
        criteria = intent.anchor_criteria
        patched = {}
        if not (criteria.counterparty_name or "").strip() and getattr(
            record, "counterparty", ""
        ):
            patched["counterparty_name"] = str(record.counterparty).strip()
        if criteria.target_date is None and getattr(record, "date", ""):
            patched["target_date"] = str(record.date).strip() or None
        if not (criteria.path_reference_text or "").strip():
            patched["path_reference_text"] = normalized
        if not patched:
            return intent
        updated_criteria = replace(criteria, **patched)
        anchor_intent_patch: dict[str, object] = {"anchor_criteria": updated_criteria}
        if (
            not (getattr(intent, "requested_record_type", "") or "")
            and getattr(record, "record_type", None) is not None
        ):
            record_type = record.record_type
            anchor_intent_patch["requested_record_type"] = (
                record_type.value if hasattr(record_type, "value") else str(record_type)
            )
        return replace(intent, **anchor_intent_patch)
    return intent

def command_payload(command: object) -> dict[str, object]:
    model_dump = getattr(command, "model_dump", None)
    if not callable(model_dump):
        return {}
    payload = dict(model_dump(exclude_none=True))
    payload.pop("kind", None)
    action = getattr(command, "action", None)
    if action is not None and "action" not in payload:
        payload["action"] = action
    return payload


__all__ = [
    "command_payload",
    "enrich_finance_intent_from_anchor",
    "execute_finance_lookup_step",
]
