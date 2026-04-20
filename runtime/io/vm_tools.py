from __future__ import annotations

import json
import time
from collections.abc import Iterable
from dataclasses import dataclass
from typing import Any

try:
    from bitgn.vm.pcm_connect import PcmRuntimeClientSync
    from bitgn.vm.pcm_pb2 import (
        AnswerRequest,
        ContextRequest,
        DeleteRequest,
        ListRequest,
        Outcome,
        ReadRequest,
        WriteRequest,
    )
except ModuleNotFoundError:  # pragma: no cover - local test fallback only
    PcmRuntimeClientSync = Any  # type: ignore[assignment]

    @dataclass
    class AnswerRequest:  # type: ignore[override]
        message: str
        outcome: int
        refs: list[str]

    @dataclass
    class ContextRequest:  # type: ignore[override]
        pass

    @dataclass
    class DeleteRequest:  # type: ignore[override]
        path: str

    @dataclass
    class ListRequest:  # type: ignore[override]
        name: str

    @dataclass
    class ReadRequest:  # type: ignore[override]
        path: str

    @dataclass
    class WriteRequest:  # type: ignore[override]
        path: str
        content: bytes

    class Outcome:  # type: ignore[override]
        OUTCOME_OK = 1
        OUTCOME_DENIED_SECURITY = 2
        OUTCOME_NONE_CLARIFICATION = 3
        OUTCOME_NONE_UNSUPPORTED = 4
        OUTCOME_ERR_INTERNAL = 5

from domain.process import DecisionKind, PublicDecision
from task_routing.outcome_classifier import classify_task_outcome
from telemetry.trace import emit_runtime_exception

CLI_RED = "\x1B[31m"
CLI_GREEN = "\x1B[32m"
CLI_CLR = "\x1B[0m"
CLI_YELLOW = "\x1B[33m"
TERMINAL_RESULT_PREFIX = "TERMINAL_RESULT_JSON:"

OUTCOME_BY_NAME = {
    "OUTCOME_OK": Outcome.OUTCOME_OK,
    "OUTCOME_DENIED_SECURITY": Outcome.OUTCOME_DENIED_SECURITY,
    "OUTCOME_NONE_CLARIFICATION": Outcome.OUTCOME_NONE_CLARIFICATION,
    "OUTCOME_NONE_UNSUPPORTED": Outcome.OUTCOME_NONE_UNSUPPORTED,
    "OUTCOME_ERR_INTERNAL": Outcome.OUTCOME_ERR_INTERNAL,
}

PUBLIC_DECISION_OUTCOME_NAMES: dict[DecisionKind, str] = {
    DecisionKind.DONE: "OUTCOME_OK",
    DecisionKind.BLOCKED: "OUTCOME_DENIED_SECURITY",
    DecisionKind.CLARIFY: "OUTCOME_NONE_CLARIFICATION",
    DecisionKind.UNSUPPORTED: "OUTCOME_NONE_UNSUPPORTED",
    DecisionKind.FALLBACK: "OUTCOME_ERR_INTERNAL",
}


@dataclass(frozen=True, slots=True)
class VmEntry:
    path: str
    is_dir: bool


def normalize_repo_path(path: str) -> str:
    text = str(path or "").strip().replace("\\", "/")
    if not text:
        return "/"
    if not text.startswith("/"):
        text = f"/{text}"
    while "//" in text:
        text = text.replace("//", "/")
    return text.rstrip("/") or "/"


def list_entries(vm: PcmRuntimeClientSync, path: str) -> tuple[VmEntry, ...]:
    normalized = normalize_repo_path(path)
    attempts = 3
    last_error: Exception | None = None
    response = None
    for attempt in range(1, attempts + 1):
        try:
            response = vm.list(ListRequest(name=normalized))
            last_error = None
            break
        except Exception as exc:  # noqa: BLE001
            last_error = exc
            if attempt >= attempts:
                raise
            time.sleep(0.15 * attempt)
    if response is None:
        assert last_error is not None
        raise last_error
    entries: list[VmEntry] = []
    for entry in getattr(response, "entries", ()):
        child_name = str(getattr(entry, "name", "") or "").strip().rstrip("/")
        if not child_name:
            continue
        child_path = (
            f"/{child_name}" if normalized == "/" else f"{normalized}/{child_name}"
        )
        entries.append(
            VmEntry(
                path=normalize_repo_path(child_path),
                is_dir=bool(getattr(entry, "is_dir", False)),
            )
        )
    return tuple(sorted(entries, key=lambda item: item.path.lower()))


def walk_files(
    vm: PcmRuntimeClientSync,
    roots: Iterable[str],
    *,
    max_depth: int = 6,
    max_files: int = 4000,
) -> tuple[str, ...]:
    files: list[str] = []
    seen_dirs: set[str] = set()
    queue: list[tuple[str, int]] = [(normalize_repo_path(root), 0) for root in roots]
    while queue and len(files) < max_files:
        current, depth = queue.pop(0)
        if current in seen_dirs:
            continue
        seen_dirs.add(current)
        try:
            entries = list_entries(vm, current)
        except Exception as exc:  # noqa: BLE001
            emit_runtime_exception(
                stage="vm_tools",
                operation="list_entries",
                error=exc,
                extra={"path": current},
            )
            continue
        for entry in entries:
            if entry.is_dir:
                if depth < max_depth:
                    queue.append((entry.path, depth + 1))
                continue
            files.append(entry.path)
            if len(files) >= max_files:
                break
    return tuple(dict.fromkeys(files))


def read_text(vm: PcmRuntimeClientSync, path: str) -> str:
    normalized = normalize_repo_path(path)
    response = vm.read(ReadRequest(path=normalized))
    return str(getattr(response, "content", "") or "")


def read_context_payload(vm: PcmRuntimeClientSync) -> dict[str, object]:
    response = vm.context(ContextRequest())
    return {
        "unix_time": int(getattr(response, "unix_time", 0) or 0),
        "time": str(getattr(response, "time", "") or ""),
    }


def delete_path(vm: PcmRuntimeClientSync, path: str) -> None:
    normalized = normalize_repo_path(path)
    vm.delete(DeleteRequest(path=normalized))


def write_text(vm: PcmRuntimeClientSync, path: str, content: str) -> None:
    normalized = normalize_repo_path(path)
    vm.write(WriteRequest(path=normalized, content=content.encode("utf-8")))


def emit_terminal_public_decision(
    vm: PcmRuntimeClientSync,
    decision: PublicDecision,
    *,
    message: str,
    refs: Iterable[str] = (),
) -> str:
    outcome_name = public_decision_outcome_name(decision.kind)
    vm.answer(
        AnswerRequest(
            message=str(message or ""),
            outcome=OUTCOME_BY_NAME[outcome_name],
            refs=[normalize_repo_path(ref) for ref in refs if str(ref or "").strip()],
        )
    )
    task_outcome = classify_task_outcome(outcome_name, reason_code=decision.reason_code)
    print(
        f"{TERMINAL_RESULT_PREFIX} "
        f"{json.dumps({'outcome': outcome_name, 'reason_code': decision.reason_code, 'task_outcome_kind': task_outcome.kind.value}, ensure_ascii=False, sort_keys=True)}"
    )
    color = (
        CLI_GREEN
        if outcome_name == "OUTCOME_OK"
        else CLI_YELLOW
        if outcome_name == "OUTCOME_NONE_CLARIFICATION"
        else CLI_RED
    )
    print(f"{color}agent {outcome_name}{CLI_CLR}. Summary:\n{message}")
    return outcome_name


def public_decision_outcome_name(kind: DecisionKind) -> str:
    return PUBLIC_DECISION_OUTCOME_NAMES[kind]
