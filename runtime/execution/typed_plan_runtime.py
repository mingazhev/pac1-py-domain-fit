from __future__ import annotations

from typing import Any, Callable

from pydantic import BaseModel

from domain.process import (
    DependencyBindingError,
    DependencyBindingKind,
    SubcommandDependency,
    TypedStepPlan,
    WorkItem,
    decide_unsupported,
    validate_subcommand_dependency,
)

from runtime.context.context_assembly import needed_kinds_for_command


def execute_typed_plan(
    typed_plan: TypedStepPlan,
    *,
    current_work_item: WorkItem,
    vm,
    gateway,
    model: str,
    load_runtime_context_fn: Callable[..., Any],
    execute_typed_command_fn: Callable[..., Any],
    materialize_typed_step_fn: Callable[..., Any],
):
    from runtime.execution.execution_engine import DeterministicExecutionResult

    shared_refs = tuple(
        str(ref).strip() for ref in typed_plan.shared_evidence_refs if str(ref).strip()
    )
    prior_results: list[DeterministicExecutionResult] = []
    last_result = None
    for step_index, step in enumerate(typed_plan.steps):
        command = materialize_typed_step_fn(step.command)
        if command is None:
            return DeterministicExecutionResult(
                decision=decide_unsupported(reason_code="typed_plan_step_invalid"),
                message="Typed plan contained a step that is not a valid typed command.",
                refs=tuple(dict.fromkeys((*shared_refs, *step.evidence_refs))),
            )
        binding_error = validate_typed_plan_dependencies(
            dependency_bindings=step.dependency_bindings,
            plan_length=len(typed_plan.steps),
            target_step_index=step_index,
        )
        if binding_error is not None:
            return DeterministicExecutionResult(
                decision=decide_unsupported(reason_code="typed_plan_dependency_invalid"),
                message=binding_error,
                refs=tuple(dict.fromkeys((*shared_refs, *step.evidence_refs))),
            )
        command, binding_error = apply_typed_plan_dependencies(
            command,
            dependency_bindings=step.dependency_bindings,
            prior_results=prior_results,
        )
        if binding_error is not None:
            return DeterministicExecutionResult(
                decision=decide_unsupported(reason_code="typed_plan_dependency_unresolved"),
                message=binding_error,
                refs=tuple(dict.fromkeys((*shared_refs, *step.evidence_refs))),
            )
        needed_kinds = needed_kinds_for_command(command)
        context = load_runtime_context_fn(vm, needed_kinds=needed_kinds)
        result = execute_typed_command_fn(
            command,
            task_text=str(step.task_text or "").strip() or current_work_item.goal,
            context=context,
            continuation_budget=typed_plan.continuation_budget,
            current_work_item=current_work_item,
            vm=vm,
            gateway=gateway,
            model=model,
        )
        if result.decision.next_work_item is not None:
            return result
        if result.decision.kind.value != "done":
            return result
        if shared_refs or step.evidence_refs:
            result = DeterministicExecutionResult(
                decision=result.decision,
                message=result.message,
                refs=tuple(dict.fromkeys((*result.refs, *shared_refs, *step.evidence_refs))),
            )
        prior_results.append(result)
        last_result = result
    assert last_result is not None
    return last_result


def validate_typed_plan_dependencies(
    *,
    dependency_bindings: tuple[SubcommandDependency, ...],
    plan_length: int,
    target_step_index: int,
) -> str | None:
    for dependency in dependency_bindings:
        try:
            validate_subcommand_dependency(
                dependency,
                plan_length=plan_length,
                target_step_index=target_step_index,
            )
        except DependencyBindingError as exc:
            return str(exc)
    return None


def apply_typed_plan_dependencies(
    command,
    *,
    dependency_bindings: tuple[SubcommandDependency, ...],
    prior_results: list,
):
    bound_command = command
    for dependency in dependency_bindings:
        source_result = prior_results[dependency.source_step_index]
        source_value, error = resolve_typed_plan_binding_value(
            source_result,
            source_field=dependency.source_field,
        )
        if error is not None:
            return None, error
        bound_command, error = bind_typed_plan_command_field(
            bound_command,
            target_field=dependency.target_field,
            value=source_value,
            kind=dependency.kind,
        )
        if error is not None:
            return None, error
    return bound_command, None


def resolve_typed_plan_binding_value(result, *, source_field: str):
    field_name = str(source_field or "").strip()
    if not field_name:
        return None, "Typed plan dependency source_field must be non-empty."
    if field_name == "message":
        return result.message, None
    if field_name in {"reason_code", "decision.reason_code"}:
        return result.decision.reason_code, None
    if field_name in {"refs", "result.refs"}:
        return result.refs, None
    if field_name in {"outcome.reason_code", "decision.outcome.reason_code"}:
        outcome = result.decision.outcome
        if outcome is None:
            return None, (
                "Typed plan dependency requested outcome.reason_code from a step "
                "without a typed outcome."
            )
        return outcome.reason_code, None
    return None, f"Typed plan dependency source_field '{field_name}' is not supported."


def bind_typed_plan_command_field(command, *, target_field: str, value, kind: DependencyBindingKind):
    field_name = str(target_field or "").strip()
    if not field_name:
        return None, "Typed plan dependency target_field must be non-empty."
    if isinstance(command, BaseModel):
        payload = command.model_dump()
        if field_name not in payload:
            return None, (
                f"Typed plan dependency target_field '{field_name}' is not present on "
                f"{type(command).__name__}."
            )
        current = payload.get(field_name)
        new_value, error = merge_typed_plan_binding_value(current, value=value, kind=kind)
        if error is not None:
            return None, error
        return command.model_copy(update={field_name: new_value}), None
    return None, (
        f"Typed plan dependency target binding is unsupported for command type "
        f"{type(command).__name__}."
    )


def merge_typed_plan_binding_value(current, *, value, kind: DependencyBindingKind):
    if kind is DependencyBindingKind.EQUAL:
        return value, None
    if kind is DependencyBindingKind.GUARD:
        if value:
            return current, None
        return None, "Typed plan GUARD dependency evaluated false."
    if kind is DependencyBindingKind.INCLUDES:
        if current is None:
            current_items: list[object] = []
        elif isinstance(current, (tuple, list, set)):
            current_items = list(current)
        else:
            current_items = [current]
        if isinstance(value, (tuple, list, set)):
            additions = list(value)
        else:
            additions = [value]
        merged: list[object] = list(current_items)
        for item in additions:
            if item not in merged:
                merged.append(item)
        if isinstance(current, tuple):
            return tuple(merged), None
        if isinstance(current, set):
            return set(merged), None
        if isinstance(current, list):
            return merged, None
        if current is None and len(merged) == 1:
            return merged[0], None
        return tuple(merged), None
    return None, f"Typed plan dependency kind '{kind.value}' is not supported."


__all__ = ["execute_typed_plan"]
