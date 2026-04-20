from __future__ import annotations

from application.ports import ReadStepInterpretationResult


def build_finance_lookup_fallback_planner(
    gateway: object,
    model: str,
):
    def _plan_finance_lookup_fallback(
        task_text: str,
        finance_records,
        root_policy_text: str,
        finance_policy_text: str,
    ) -> ReadStepInterpretationResult | None:
        if not finance_records:
            return None
        from task_routing.finance_lookup_fallback import plan_finance_lookup_fallback

        plan = plan_finance_lookup_fallback(
            gateway,
            model,
            task_text=task_text,
            finance_records=finance_records,
            root_policy_text=root_policy_text,
            finance_policy_text=finance_policy_text,
        )
        if plan is None:
            return None
        if plan.decision == "refuse":
            return ReadStepInterpretationResult(
                status="blocked",
                message=plan.reason or "Finance lookup refused on safety grounds.",
                reason_code="finance_lookup_fallback_refused",
            )
        if plan.decision == "clarify" or not str(plan.answer_text or "").strip():
            return ReadStepInterpretationResult(
                status="clarify",
                message=plan.reason or "Finance lookup needs clarification.",
                reason_code="finance_lookup_requires_clarification",
            )
        return ReadStepInterpretationResult(
            status="done",
            message=plan.answer_text.strip(),
            reason_code="finance_lookup_resolved_via_fallback",
            refs=tuple(plan.grounding_paths),
        )

    return _plan_finance_lookup_fallback


def build_finance_anchor_record_resolver(
    gateway: object,
    model: str,
):
    def _resolve_finance_anchor_record_ref(
        task_text: str,
        finance_records,
    ) -> str | None:
        if not finance_records:
            return None
        from task_routing.record_selector import llm_resolve_finance_record

        match = llm_resolve_finance_record(
            gateway,
            model,
            instruction=task_text,
            records=finance_records,
        )
        if match is None:
            return None
        path = str(getattr(match, "path", "") or "").strip()
        if not path:
            return None
        return path if path.startswith("/") else f"/{path}"

    return _resolve_finance_anchor_record_ref


__all__ = [
    "build_finance_anchor_record_resolver",
    "build_finance_lookup_fallback_planner",
]
