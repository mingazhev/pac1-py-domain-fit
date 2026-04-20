from __future__ import annotations

from datetime import datetime

from application.ports import (
    InterpretationRequest,
    KIND_ACCOUNT_LOOKUP,
    dispatch_read_interpretation,
)
from application.queries import (
    resolve_account_lookup_query,
    resolve_capture_lookup_query,
    resolve_contact_lookup_query,
    resolve_entity_query,
    resolve_message_query,
    resolve_project_query,
    resolve_queue_state_lookup_query,
)
from application.temporal import resolve_relative_lookup_base_time

from .read_result import (
    ReadStepExecutionResult,
    from_interpretation_result,
    from_lookup_result,
    from_status_result,
)


def execute_non_finance_read_step(
    command,
    *,
    kind: str,
    task_text: str,
    context,
    record_resolution_port=None,
    query_resolution_port=None,
    interpretation_port=None,
) -> ReadStepExecutionResult | None:
    if kind == "account_lookup":
        result = resolve_account_lookup_query(
            getattr(context, "typed_accounts", ()),
            query=str(getattr(command, "query", "") or ""),
            output_field=str(getattr(command, "output_field", "legal_name") or "legal_name"),
            fallback_refs=("/accounts.json",),
            record_resolution_port=record_resolution_port,
        )
        if (
            interpretation_port is not None
            and interpretation_port.resolve_account_lookup is not None
            and (result is None or getattr(result, "status", "") == "clarify_missing")
        ):
            envelope = dispatch_read_interpretation(
                interpretation_port,
                InterpretationRequest(
                    kind=KIND_ACCOUNT_LOOKUP,
                    payload={
                        "query": str(getattr(command, "query", "") or ""),
                        "output_field": str(
                            getattr(command, "output_field", "legal_name")
                            or "legal_name"
                        ),
                        "accounts": context.accounts,
                    },
                ),
            )
            if envelope.plan is not None:
                return from_interpretation_result(
                    envelope.plan,
                    llm_stage=envelope.llm_stage
                    or "read_interpretation_account_lookup",
                )
        return from_status_result(
            result,
            clarify_reason="account_lookup_requires_clarification",
            done_reason="account_lookup_resolved",
        )

    if kind == "contact_lookup":
        result = resolve_contact_lookup_query(
            getattr(context, "typed_accounts", ()),
            getattr(context, "typed_contacts", ()),
            query=str(getattr(command, "query", "") or ""),
            relationship_role=str(getattr(command, "relationship_role", "direct") or "direct"),
            output_field=str(getattr(command, "output_field", "email") or "email"),
            fallback_refs=("/accounts.json", "/contacts.json"),
            record_resolution_port=record_resolution_port,
        )
        if (
            interpretation_port is not None
            and interpretation_port.resolve_contact_lookup is not None
            and (result is None or getattr(result, "status", "") == "clarify_missing")
        ):
            interpreted = interpretation_port.resolve_contact_lookup(
                str(getattr(command, "query", "") or ""),
                str(getattr(command, "relationship_role", "direct") or "direct"),
                str(getattr(command, "output_field", "email") or "email"),
                context.accounts,
                context.contacts,
            )
            if interpreted is not None:
                return from_interpretation_result(
                    interpreted,
                    llm_stage="read_interpretation_contact_lookup",
                )
        return from_status_result(
            result,
            clarify_reason="contact_lookup_requires_clarification",
            done_reason="contact_lookup_resolved",
        )

    if kind == "capture_lookup":
        capture_result = resolve_capture_lookup_query(
            getattr(context, "capture_projections", ()),
            relative_date_phrase=str(getattr(command, "relative_date_phrase", "") or ""),
            output_field=str(getattr(command, "output_field", "title") or "title"),
            context_payload=context.context_payload,
        )
        if capture_result is None:
            return ReadStepExecutionResult(
                status="clarify",
                message="Could not resolve the requested capture note.",
                reason_code="capture_lookup_requires_clarification",
            )
        if capture_result.status == "resolved":
            return ReadStepExecutionResult(
                status="done",
                message=capture_result.message,
                reason_code="capture_lookup_resolved",
                refs=capture_result.grounding_refs,
            )
        return ReadStepExecutionResult(
            status="clarify",
            message=capture_result.message,
            reason_code="capture_lookup_requires_clarification",
            refs=capture_result.grounding_refs,
        )

    if kind == "project_query":
        project_result = resolve_project_query(
            context.cast_records,
            getattr(context, "cast_entities", ()),
            context.project_records,
            getattr(context, "projects", ()),
            variant=str(getattr(command, "variant", "scalar_property") or "scalar_property"),
            property=str(getattr(command, "property", "start_date") or "start_date"),
            projection=str(getattr(command, "projection", "default") or "default"),
            sort=str(getattr(command, "sort", "default") or "default"),
            render=str(getattr(command, "render", "default") or "default"),
            status_filter=str(getattr(command, "status_filter", "any") or "any"),
            entity_reference=str(getattr(command, "entity_reference", "") or ""),
            output_format=str(getattr(command, "output_format", "iso") or "iso"),
            task_text=task_text,
            fallback_text=task_text,
            fallback_refs=context.document_refs,
            project_roots=context.workspace_layout.projects,
            resolution_port=query_resolution_port,
        )
        if project_result is None:
            return ReadStepExecutionResult(
                status="clarify",
                message="Could not resolve a unique project for the requested project query.",
                reason_code="project_query_not_found",
            )
        if project_result.status == "clarify_missing":
            return ReadStepExecutionResult(
                status="clarify",
                message=project_result.message,
                reason_code="project_query_not_found",
                refs=project_result.grounding_refs,
            )
        return ReadStepExecutionResult(
            status="done",
            message=project_result.message,
            reason_code="project_query_resolved",
            refs=project_result.grounding_refs,
        )

    if kind == "entity_query":
        reference_base = resolve_relative_lookup_base_time(context.context_payload)
        reference_date = reference_base if isinstance(reference_base, datetime) else None
        entity_result = resolve_entity_query(
            context.cast_records,
            getattr(context, "cast_entities", ()),
            variant=str(getattr(command, "variant", "scalar_property") or "scalar_property"),
            property=str(getattr(command, "property", "birthday") or "birthday"),
            aggregate=getattr(command, "aggregate", None),
            aggregate_filter=str(getattr(command, "aggregate_filter", "any") or "any"),
            entity_reference=str(getattr(command, "entity_reference", "") or ""),
            self_reference=bool(getattr(command, "self_reference", False)),
            output_format=str(getattr(command, "output_format", "iso") or "iso"),
            fallback_text=task_text,
            cast_refs=context.document_refs,
            resolution_port=query_resolution_port,
            reference_date=reference_date,
        )
        if entity_result is None:
            return ReadStepExecutionResult(
                status="clarify",
                message="Could not resolve the requested entity from canonical cast records.",
                reason_code="entity_query_requires_clarification",
            )
        if entity_result.status == "clarify_missing":
            return ReadStepExecutionResult(
                status="clarify",
                message=entity_result.message,
                reason_code="entity_query_requires_clarification",
                refs=entity_result.grounding_refs,
            )
        return ReadStepExecutionResult(
            status="done",
            message=entity_result.message,
            reason_code="entity_query_resolved",
            refs=entity_result.grounding_refs,
        )

    if kind == "message_query":
        result = resolve_message_query(
            context.cast_records,
            getattr(context, "cast_entities", ()),
            context.message_records,
            entity_reference=str(getattr(command, "entity_reference", "") or ""),
            selection=str(getattr(command, "selection", "last_recorded_message") or "last_recorded_message"),
            property=str(getattr(command, "property", "message") or "message"),
            fallback_text=task_text,
            cast_refs=context.document_refs,
            resolution_port=query_resolution_port,
        )
        return from_status_result(
            result,
            clarify_reason="message_query_requires_clarification",
            done_reason="message_query_resolved",
        )

    if kind == "queue_state_lookup":
        result = resolve_queue_state_lookup_query(
            context.queue_states,
            queue_reference=str(getattr(command, "queue_reference", "") or ""),
            fallback_refs=context.document_refs,
        )
        if (
            interpretation_port is not None
            and interpretation_port.resolve_queue_state_lookup is not None
            and result is None
        ):
            interpreted = interpretation_port.resolve_queue_state_lookup(
                str(getattr(command, "queue_reference", "") or ""),
                context.queue_states,
                context.document_refs,
            )
            if interpreted is not None:
                return from_interpretation_result(
                    interpreted,
                    llm_stage="read_interpretation_queue_state_lookup",
                )
        return from_lookup_result(
            result,
            clarify_message="No matching queue-state markers were found.",
            clarify_reason="queue_state_lookup_not_found",
            done_reason="queue_state_lookup_resolved",
        )

    return None


__all__ = ["execute_non_finance_read_step"]
