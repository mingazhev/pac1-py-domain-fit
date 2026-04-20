from __future__ import annotations

from dataclasses import replace
from typing import Any

from domain.process import AuthorizationStamp, decide_blocked
from task_routing import StepPolicyClass, contract_for_command
from telemetry.trace import emit_runtime_exception

from runtime.io.mutation_result_mapping import MutationExecutionResult


def command_has_authorization(command: object) -> bool:
    return command_authorization(command) is not None


def command_authorization(command: object) -> AuthorizationStamp | None:
    return AuthorizationStamp.from_fields(
        getattr(command, "authorization_kind", None),
        getattr(command, "authorized_by", None),
    )


def stamp_command_authorization(
    command: object,
    *,
    authorization_kind: str,
    authorized_by: str,
    require_authz_contract: bool = True,
) -> object:
    if command_has_authorization(command):
        return command
    stamp = AuthorizationStamp.from_fields(authorization_kind, authorized_by)
    if stamp is None:
        return command
    if require_authz_contract:
        try:
            contract = contract_for_command(command)
        except Exception as exc:  # noqa: BLE001
            emit_runtime_exception(
                stage="authorization",
                operation="contract_for_command",
                error=exc,
                extra={"command_type": type(command).__name__},
            )
            return command
        if contract.policy_class is not StepPolicyClass.AUTHZ_REQUIRED:
            return command
    if hasattr(command, "model_copy"):
        return command.model_copy(update=stamp.to_update_dict())
    try:
        return replace(command, **stamp.to_update_dict())
    except Exception as exc:  # noqa: BLE001
        emit_runtime_exception(
            stage="authorization",
            operation="replace",
            error=exc,
            extra={"command_type": type(command).__name__},
        )
        return command


def missing_authorization_result() -> MutationExecutionResult:
    return MutationExecutionResult(
        decision=decide_blocked(reason_code="mutation_requires_authorization"),
        message=(
            "This mutation is declared AUTHZ_REQUIRED by its StepContract "
            "but the typed step did not carry authorization_kind and "
            "authorized_by. Direct user requests must be stamped by the "
            "orchestrator; inbox-originated work is stamped by the "
            "workflow coordinator."
        ),
        refs=(),
    )


__all__ = [
    "command_authorization",
    "command_has_authorization",
    "missing_authorization_result",
    "stamp_command_authorization",
]
