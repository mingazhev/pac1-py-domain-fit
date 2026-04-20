"""Inbox command enrichment: workflow authorization stamping and LLM-backed
intent/classifier ports.

Consolidates two previously-split modules:

- ``inbox_authorization`` — stamp workflow-policy authorization on typed
  commands and normalize inbox-typed commands.
- ``inbox_interpretation_ports`` — build the ``WorkflowInterpretationPort``,
  the inbox classifier, and the typed-step execution port wired against
  the LLM gateway.
"""

from __future__ import annotations

from application.context import RuntimeContext
from application.contracts import FinanceMutationAction, OutboxDraftAction
from application.ports import (
    TypedStepExecutionPort,
    WorkflowInterpretationPort,
    WorkflowSubTaskRoutingResult,
    WorkflowTypedIntentExtractionResult,
)
from application.workflows.inbox_workflow import (
    InboxClassifierVerdict,
    coerce_finance_document_ingest_request,
    coerce_finance_payment_request,
    coerce_invoice_email_request,
)
from domain.cast.relationship import expand_cast_relationship_aliases
from domain.process import AuthorizationKind
from runtime.authorization.authorization import stamp_command_authorization
from task_routing import (
    FinanceMutationCommand,
    OutboxDraftCommand,
    QueueMutationCommand,
    TaskIntent,
    TaskRouteDecision,
    extract_task_inputs_for_decision,
)


# ---------------------------------------------------------------------------
# Authorization stamping (formerly inbox_authorization.py).


def stamp_workflow_authorization(command):
    if isinstance(command, FinanceMutationAction | OutboxDraftAction):
        return stamp_command_authorization(
            command,
            authorization_kind=AuthorizationKind.WORKFLOW_POLICY.value,
            authorized_by="inbox_workflow",
            require_authz_contract=False,
        )
    workflow_types = (
        FinanceMutationCommand,
        OutboxDraftCommand,
        QueueMutationCommand,
    )
    if not isinstance(command, workflow_types):
        return command
    return stamp_command_authorization(
        command,
        authorization_kind=AuthorizationKind.WORKFLOW_POLICY.value,
        authorized_by="inbox_workflow",
        require_authz_contract=True,
    )


def enrich_inbox_typed_command(command, source_text: str):
    _ = source_text
    if not isinstance(command, OutboxDraftCommand):
        return command
    return command


# ---------------------------------------------------------------------------
# Interpretation ports (formerly inbox_interpretation_ports.py).


def build_inbox_classifier(
    gateway: object | None,
    model: str | None,
    *,
    inbox_policy: str = "",
    root_policy: str = "",
):
    if gateway is None or not model:
        return None
    from task_routing.inbox_classifier import classify_inbox_item

    def _classify(body_text, envelope=None):
        verdict = classify_inbox_item(
            gateway,
            model,
            body_text=body_text,
            envelope=envelope,
            inbox_policy_text=inbox_policy,
            root_policy_text=root_policy,
        )
        if verdict is None:
            return None
        invoice_email_request = coerce_invoice_email_request(
            verdict.invoice_email_request
        )
        return InboxClassifierVerdict(
            decision=verdict.decision,
            reason=verdict.reason,
            sub_task_text=verdict.sub_task_text,
            continuation_intent=verdict.continuation_intent,
            invoice_email_request=invoice_email_request,
            finance_payment_request=coerce_finance_payment_request(
                verdict.finance_payment_request
            ),
            finance_document_ingest_request=coerce_finance_document_ingest_request(
                verdict.finance_document_ingest_request
            ),
        )

    return _classify


def extract_task_inputs_via_runtime(*args, **kwargs):
    from task_routing import extract_task_inputs

    return extract_task_inputs(*args, **kwargs)


def build_workflow_interpretation_port(
    gateway: object | None,
    model: str | None,
    *,
    extract_task_inputs_fn=extract_task_inputs_via_runtime,
    extract_task_inputs_for_decision_fn=extract_task_inputs_for_decision,
    stamp_workflow_authorization_fn=stamp_workflow_authorization,
    enrich_inbox_typed_command_fn=enrich_inbox_typed_command,
) -> WorkflowInterpretationPort:
    if gateway is None or not model:
        return WorkflowInterpretationPort(
            stamp_workflow_authorization=stamp_workflow_authorization_fn,
            enrich_inbox_typed_command=enrich_inbox_typed_command_fn,
        )

    from task_routing.record_selector import llm_select_finance_records
    from task_routing.record_selector import llm_resolve_cast_record
    from domain.cast import resolve_cast_identity

    def _extract_for_typed_intent(
        source_text: str,
        continuation_intent: str,
        supported_intents: frozenset[str],
        workspace_policies: object,
        finance_record_index: str,
        user_content: str,
    ) -> WorkflowTypedIntentExtractionResult:
        try:
            intent = TaskIntent(str(continuation_intent).strip())
        except ValueError:
            return WorkflowTypedIntentExtractionResult()
        extracted = extract_task_inputs_for_decision_fn(
            gateway,
            model,
            source_text,
            decision=TaskRouteDecision(intent=intent),
            supported_intents=frozenset(
                TaskIntent(value) for value in supported_intents
            ),
            workspace_policies=workspace_policies,
            finance_record_index=finance_record_index,
            user_content=user_content,
        )
        return WorkflowTypedIntentExtractionResult(
            typed_command=extracted.typed_command,
            effective_task_text=str(extracted.effective_task_text or ""),
        )

    def _route_sub_task(
        sub_task_text: str,
        supported_intents: frozenset[str],
        workspace_policies: object,
        finance_record_index: str,
    ) -> WorkflowSubTaskRoutingResult:
        routed = extract_task_inputs_fn(
            gateway,
            model,
            sub_task_text,
            supported_intents=frozenset(
                TaskIntent(value) for value in supported_intents
            ),
            workspace_policies=workspace_policies,
            finance_record_index=finance_record_index,
        )
        intent = getattr(routed.decision.intent, "value", "")
        if routed.decision.intent is TaskIntent.UNKNOWN:
            intent = ""
        return WorkflowSubTaskRoutingResult(
            intent=str(intent or ""),
            typed_command=routed.typed_command,
            effective_task_text=str(routed.effective_task_text or ""),
        )

    def _select_finance_record_subset(
        instruction: str,
        records,
    ) -> tuple[int, ...]:
        return llm_select_finance_records(
            gateway,
            model,
            instruction=instruction,
            records=records,
            accept_confidence=frozenset({"high", "medium", "low"}),
        )

    def _resolve_cast_identity_subset(
        instruction: str,
        entities,
    ):
        entity_list = tuple(entities or ())
        if not instruction or not entity_list:
            return None
        candidate_records = []
        for entity in entity_list:
            candidate_records.append(
                {
                    "path": str(getattr(entity, "path", "") or "").strip(),
                    "title": str(getattr(entity, "title", "") or "").strip(),
                    "entity_slug": str(getattr(entity, "entity_slug", "") or "").strip(),
                    "entity_id": str(getattr(entity, "entity_id", "") or "").strip(),
                    "alias": str(getattr(entity, "alias", "") or "").strip(),
                    "alias_terms": tuple(getattr(entity, "alias_terms", ()) or ()),
                    "identity_terms": tuple(
                        getattr(entity, "stable_identity_terms", ()) or ()
                    ),
                    "project_involvement_terms": tuple(
                        getattr(entity, "project_involvement_terms", ()) or ()
                    ),
                    "relationship": str(getattr(entity, "relationship", "") or "").strip(),
                    "relationship_alias_terms": tuple(
                        expand_cast_relationship_aliases(
                            getattr(entity, "relationship", "")
                        )
                    ),
                    "descriptor_terms": tuple(
                        getattr(entity, "descriptor_terms", ()) or ()
                    ),
                    "kind": (
                        getattr(getattr(entity, "kind", None), "value", "")
                        if getattr(entity, "kind", None) is not None
                        else ""
                    ),
                    "primary_contact_email": str(
                        getattr(entity, "primary_contact_email", "") or ""
                    ).strip(),
                    "body": str(getattr(entity, "body", "") or "").strip(),
                }
            )
        matched = llm_resolve_cast_record(
            gateway,
            model,
            candidate_records,
            instruction,
            accept_confidence=frozenset({"high", "medium", "low"}),
        )
        if matched is None:
            return None
        for key in (
            str(matched.get("path") or "").strip(),
            str(matched.get("entity_slug") or "").strip(),
            str(matched.get("entity_id") or "").strip(),
            str(matched.get("title") or "").strip(),
        ):
            if not key:
                continue
            projection = resolve_cast_identity(entity_list, key)
            if projection is not None:
                return projection
        return None

    return WorkflowInterpretationPort(
        extract_for_typed_intent=_extract_for_typed_intent,
        route_sub_task=_route_sub_task,
        select_finance_record_subset=_select_finance_record_subset,
        resolve_cast_identity_subset=_resolve_cast_identity_subset,
        stamp_workflow_authorization=stamp_workflow_authorization_fn,
        enrich_inbox_typed_command=enrich_inbox_typed_command_fn,
    )


def build_typed_step_execution_port(execute_typed_command_fn) -> TypedStepExecutionPort:
    def _execute(
        command: object,
        task_text: str,
        context: RuntimeContext,
        continuation_budget,
        vm: object | None,
    ):
        return execute_typed_command_fn(
            command,
            task_text=task_text,
            context=context,
            continuation_budget=continuation_budget,
            current_work_item=None,
            vm=vm,
            gateway=None,
            model=None,
            seen_signatures=frozenset(),
        )

    return TypedStepExecutionPort(execute=_execute)


__all__ = [
    "build_inbox_classifier",
    "build_typed_step_execution_port",
    "build_workflow_interpretation_port",
    "enrich_inbox_typed_command",
    "extract_task_inputs_via_runtime",
    "stamp_workflow_authorization",
]
