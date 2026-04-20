from __future__ import annotations

from application.context import RuntimeContext
from application.ports import ReadStepInterpretationPort, ReadStepInterpretationResult
from application.queries import (
    render_account_lookup_result,
    render_contact_lookup_result,
    render_queue_state_lookup_result,
    resolve_contact_lookup_query,
)
from runtime.ports.read_interpretation_finance_intent import (
    build_finance_lookup_intent_deriver,
)
from task_routing.llm_port import GatewayBackedLlmPort
from runtime.ports.read_interpretation_finance_resolution import (
    build_finance_anchor_record_resolver,
    build_finance_lookup_fallback_planner,
)


def build_account_lookup_resolver(
    gateway: object,
    model: str,
):
    def _resolve_account_lookup(
        query: str,
        output_field: str,
        accounts,
    ) -> ReadStepInterpretationResult | None:
        if not accounts:
            return None
        from task_routing.record_selector import llm_resolve_account_record

        candidate = llm_resolve_account_record(
            gateway,
            model,
            [dict(record) for record in accounts],
            query,
        )
        if candidate is None:
            return None
        result = render_account_lookup_result(
            dict(candidate),
            output_field=output_field,
            fallback_refs=("/accounts.json",),
        )
        return _result_from_query_result(
            result,
            resolved_reason_code="account_lookup_resolved",
            clarify_reason_code="account_lookup_requires_clarification",
        )

    return _resolve_account_lookup


def build_contact_lookup_resolver(
    context,
    gateway: object,
    model: str,
):
    def _resolve_contact_lookup(
        query: str,
        relationship_role: str,
        output_field: str,
        accounts,
        contacts,
    ) -> ReadStepInterpretationResult | None:
        fallback_refs = ("/accounts.json", "/contacts.json")
        from task_routing.record_selector import (
            llm_resolve_account_record,
            llm_resolve_contact_record,
        )

        if relationship_role == "direct":
            candidate = llm_resolve_contact_record(
                gateway,
                model,
                [dict(record) for record in contacts],
                query,
            )
            if candidate is None:
                return None
            result = render_contact_lookup_result(
                dict(candidate),
                output_field=output_field,
                fallback_refs=fallback_refs,
            )
        else:
            account_candidate = llm_resolve_account_record(
                gateway,
                model,
                [dict(record) for record in accounts],
                query,
            )
            if account_candidate is None:
                return None
            result = resolve_contact_lookup_query(
                tuple(
                    account
                    for account in getattr(context, "typed_accounts", ())
                    if (
                        (
                            str(account_candidate.get("account_id") or "").strip()
                            and str(getattr(account, "account_id", "") or "").strip()
                            == str(account_candidate.get("account_id") or "").strip()
                        )
                        or (
                            str(account_candidate.get("legal_name") or "").strip()
                            and str(getattr(account, "legal_name", "") or "").strip().lower()
                            == str(account_candidate.get("legal_name") or "").strip().lower()
                        )
                        or (
                            str(account_candidate.get("display_name") or "").strip()
                            and str(getattr(account, "display_name", "") or "").strip().lower()
                            == str(account_candidate.get("display_name") or "").strip().lower()
                        )
                    )
                ),
                getattr(context, "typed_contacts", ()),
                query=query,
                relationship_role=relationship_role,
                output_field=output_field,
                fallback_refs=fallback_refs,
            )
        if result is None:
            return None
        return _result_from_query_result(
            result,
            resolved_reason_code="contact_lookup_resolved",
            clarify_reason_code="contact_lookup_requires_clarification",
        )

    return _resolve_contact_lookup


def build_queue_state_lookup_resolver(
    gateway: object,
    model: str,
):
    def _resolve_queue_state_lookup(
        queue_reference: str,
        entries,
        fallback_refs,
    ) -> ReadStepInterpretationResult | None:
        if not entries:
            return None
        from task_routing.record_selector import llm_select_queue_entries

        matched_indices = llm_select_queue_entries(
            gateway,
            model,
            instruction=queue_reference,
            entries=entries,
        )
        if not matched_indices:
            return None
        selected_entries = tuple(
            entries[index] for index in matched_indices if 0 <= index < len(entries)
        )
        if not selected_entries:
            return None
        result = render_queue_state_lookup_result(
            selected_entries,
            fallback_refs=fallback_refs,
        )
        return ReadStepInterpretationResult(
            status="done",
            message=result.message,
            reason_code="queue_state_lookup_resolved",
            refs=tuple(getattr(result, "grounding_refs", ()) or ()),
        )

    return _resolve_queue_state_lookup


def _result_from_query_result(
    result,
    *,
    resolved_reason_code: str,
    clarify_reason_code: str,
) -> ReadStepInterpretationResult:
    status = "done" if getattr(result, "status", "") == "resolved" else "clarify"
    return ReadStepInterpretationResult(
        status=status,
        message=result.message,
        reason_code=resolved_reason_code if status == "done" else clarify_reason_code,
        refs=tuple(getattr(result, "grounding_refs", ()) or ()),
    )


def build_read_step_interpretation_port(
    context: RuntimeContext,
    gateway: object | None,
    model: str | None,
) -> ReadStepInterpretationPort | None:
    if gateway is None or not model:
        return None
    return ReadStepInterpretationPort(
        resolve_account_lookup=build_account_lookup_resolver(gateway, model),
        resolve_contact_lookup=build_contact_lookup_resolver(context, gateway, model),
        resolve_queue_state_lookup=build_queue_state_lookup_resolver(gateway, model),
        derive_finance_lookup_intent=build_finance_lookup_intent_deriver(
            context,
            GatewayBackedLlmPort(gateway, model),
        ),
        resolve_finance_anchor_record_ref=build_finance_anchor_record_resolver(
            gateway,
            model,
        ),
        plan_finance_lookup_fallback=build_finance_lookup_fallback_planner(
            gateway,
            model,
        ),
    )


__all__ = [
    "build_account_lookup_resolver",
    "build_contact_lookup_resolver",
    "build_queue_state_lookup_resolver",
    "build_read_step_interpretation_port",
]
