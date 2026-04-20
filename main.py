from __future__ import annotations

import argparse
import concurrent.futures
import io
import json
import os
import textwrap
import time
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from bitgn.harness_connect import HarnessServiceClientSync
from bitgn.harness_pb2 import (
    EndTrialRequest,
    EvalPolicy,
    GetBenchmarkRequest,
    GetRunRequest,
    StartRunRequest,
    StartTrialRequest,
    StatusRequest,
    SubmitRunRequest,
)
from connectrpc.errors import ConnectError
from google.protobuf.json_format import MessageToDict
from thread_stdio import capture_thread_stdio

DEFAULT_BITGN_URL = "https://api.bitgn.com"
DEFAULT_BENCH_ID = "bitgn/pac1-dev"
DEFAULT_MODEL_ID = "gpt-5.4-mini"
PAC1_MAX_WORKERS_ENV = "PAC1_MAX_WORKERS"
PAC1_RUN_LABEL_ENV = "PAC1_RUN_LABEL"
PAC1_RUN_OUTPUT_DIR_ENV = "PAC1_RUN_OUTPUT_DIR"
PAC1_EVAL_POLL_TIMEOUT_SECONDS_ENV = "PAC1_EVAL_POLL_TIMEOUT_SECONDS"
DEFAULT_EVAL_POLL_TIMEOUT_SECONDS = 120
DEFAULT_DEV_MAX_WORKERS = 5
DEFAULT_PROD_MAX_WORKERS = 104
RUNTIME_NAME = "main"
DEFAULT_ARTIFACTS_DIR = Path(".artifacts")

CLI_RED = "\x1B[31m"
CLI_GREEN = "\x1B[32m"
CLI_BLUE = "\x1B[34m"
CLI_CLR = "\x1B[0m"


@dataclass(frozen=True, slots=True)
class RuntimeSelection:
    task_ids: tuple[str, ...]
    max_workers: int
    runtime_name: str = RUNTIME_NAME


@dataclass(frozen=True, slots=True)
class RuntimeConfig:
    bitgn_url: str
    bitgn_api_key: str
    bench_id: str
    model_id: str


@dataclass(frozen=True, slots=True)
class TrialExecutionResult:
    task_id: str
    trial_id: str
    instruction: str
    score: float
    score_detail: tuple[str, ...]
    stdout_text: str
    stderr_text: str
    error_text: str


def _proto_to_dict(message: Any) -> dict[str, Any]:
    return MessageToDict(message, preserving_proto_field_name=True)


def _write_json(path: Path, payload: Any) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(
        json.dumps(payload, indent=2, ensure_ascii=False, sort_keys=True),
        encoding="utf-8",
    )


def _utc_stamp() -> str:
    return datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ")


def _benchmark_slug(benchmark_id: str) -> str:
    return benchmark_id.rsplit("/", 1)[-1].strip() or benchmark_id


def default_max_workers_for_benchmark(benchmark_id: str) -> int:
    return DEFAULT_PROD_MAX_WORKERS if "prod" in benchmark_id.lower() else DEFAULT_DEV_MAX_WORKERS


def parse_max_workers(raw_value: str | int | None, *, benchmark_id: str) -> int:
    if raw_value in (None, ""):
        return default_max_workers_for_benchmark(benchmark_id)
    try:
        max_workers = int(raw_value)
    except (TypeError, ValueError) as exc:
        raise SystemExit(f"{PAC1_MAX_WORKERS_ENV} must be a positive integer.") from exc
    if max_workers <= 0:
        raise SystemExit(f"{PAC1_MAX_WORKERS_ENV} must be a positive integer.")
    return max_workers


def parse_runtime_selection(argv: list[str] | None = None) -> RuntimeSelection:
    parser = argparse.ArgumentParser(description="Run the clean PAC1 runtime against BitGN.")
    parser.add_argument("--max-workers", type=int, help="Run multiple BitGN trials in parallel.")
    parser.add_argument("task_ids", nargs="*", help="Optional task ids to filter the benchmark run.")
    args = parser.parse_args(argv)
    benchmark_id = os.environ.get("BENCH_ID") or DEFAULT_BENCH_ID
    max_workers = parse_max_workers(
        args.max_workers if args.max_workers is not None else os.environ.get(PAC1_MAX_WORKERS_ENV),
        benchmark_id=benchmark_id,
    )
    return RuntimeSelection(task_ids=tuple(args.task_ids), max_workers=max_workers)


def load_runtime_config() -> RuntimeConfig:
    return RuntimeConfig(
        bitgn_url=os.environ.get("BITGN_HOST") or DEFAULT_BITGN_URL,
        bitgn_api_key=os.environ.get("BITGN_API_KEY") or "",
        bench_id=os.environ.get("BENCH_ID") or DEFAULT_BENCH_ID,
        model_id=os.environ.get("MODEL_ID") or DEFAULT_MODEL_ID,
    )


def require_non_empty_value(value: str, env_name: str) -> str:
    if not value:
        raise SystemExit(f"Missing required {env_name}. Export {env_name} before running the benchmark.")
    return value


def load_runtime_runner():
    from runtime.orchestration.orchestrator import run_agent

    return run_agent


def build_run_name(config: RuntimeConfig, selection: RuntimeSelection) -> str:
    base = (
        f"PAC1 {_benchmark_slug(config.bench_id)} "
        f"{selection.runtime_name} {config.model_id} w{selection.max_workers}"
    )
    label = str(os.environ.get(PAC1_RUN_LABEL_ENV, "")).strip()
    return f"{base} | {label}" if label else base


def build_run_artifact_dir(config: RuntimeConfig, selection: RuntimeSelection) -> Path:
    override = str(os.environ.get(PAC1_RUN_OUTPUT_DIR_ENV, "")).strip()
    if override:
        return Path(override)
    return DEFAULT_ARTIFACTS_DIR / f"run-{_benchmark_slug(config.bench_id)}-{selection.runtime_name}-{_utc_stamp()}"


def _poll_timeout_seconds() -> int:
    raw_value = os.environ.get(PAC1_EVAL_POLL_TIMEOUT_SECONDS_ENV)
    if raw_value in (None, ""):
        return DEFAULT_EVAL_POLL_TIMEOUT_SECONDS
    try:
        timeout = int(raw_value)
    except ValueError as exc:
        raise SystemExit(f"{PAC1_EVAL_POLL_TIMEOUT_SECONDS_ENV} must be a non-negative integer.") from exc
    if timeout < 0:
        raise SystemExit(f"{PAC1_EVAL_POLL_TIMEOUT_SECONDS_ENV} must be a non-negative integer.")
    return timeout


def _render_trial_result_block(result: TrialExecutionResult) -> str:
    lines = [
        f"{'=' * 24} Completed task: {result.task_id} (trial: {result.trial_id}) {'=' * 24}",
        f"{CLI_BLUE}{result.instruction}{CLI_CLR}",
        "-" * 80,
    ]
    if result.stdout_text:
        lines.append(result.stdout_text.rstrip("\n"))
    if result.stderr_text:
        lines.append(result.stderr_text.rstrip("\n"))
    if result.score >= 0:
        color = CLI_GREEN if result.score == 1 else CLI_RED
        explain = textwrap.indent("\n".join(result.score_detail), "  ")
        lines.extend(["", f"{color}Score: {result.score:0.2f}", explain, CLI_CLR])
    return "\n".join(lines).rstrip() + "\n"


def _execute_trial(
    config: RuntimeConfig,
    run_agent,
    trial_id: str,
) -> TrialExecutionResult:
    client = HarnessServiceClientSync(config.bitgn_url)
    started = client.start_trial(StartTrialRequest(trial_id=trial_id))

    stdout_buf = io.StringIO()
    stderr_buf = io.StringIO()
    error_text = ""
    max_attempts = int(os.environ.get("PAC1_TRIAL_RETRY", "2"))

    with capture_thread_stdio(stdout_buf, stderr_buf):
        for attempt in range(max_attempts):
            try:
                run_agent(config.model_id, started.harness_url, started.instruction)
                break
            except Exception as exc:  # noqa: BLE001
                error_text = f"{type(exc).__name__}: {exc}"
                if attempt < max_attempts - 1:
                    print(f"RETRY: attempt {attempt + 1} failed ({error_text}), retrying...")
                    time.sleep(2)
                    continue
                print(error_text)

    result = client.end_trial(EndTrialRequest(trial_id=started.trial_id))
    return TrialExecutionResult(
        task_id=started.task_id,
        trial_id=started.trial_id,
        instruction=started.instruction,
        score=float(result.score),
        score_detail=tuple(result.score_detail),
        stdout_text=stdout_buf.getvalue(),
        stderr_text=stderr_buf.getvalue(),
        error_text=error_text,
    )


def _poll_run_until_evaluated(
    client: HarnessServiceClientSync,
    run_id: str,
    *,
    timeout_seconds: int,
) -> dict[str, Any]:
    run_dict = _proto_to_dict(client.get_run(GetRunRequest(run_id=run_id)))
    if timeout_seconds == 0:
        return run_dict
    deadline = time.time() + timeout_seconds
    while time.time() < deadline:
        state = str(run_dict.get("state", ""))
        if run_dict.get("score") is not None or state in {
            "RUN_STATE_DONE",
            "RUN_STATE_FAILED",
            "RUN_STATE_EVALUATED",
        }:
            return run_dict
        time.sleep(2)
        run_dict = _proto_to_dict(client.get_run(GetRunRequest(run_id=run_id)))
    return run_dict


def _build_run_summary(
    *,
    config: RuntimeConfig,
    selection: RuntimeSelection,
    run_name: str,
    run_dict: dict[str, Any],
    trial_results: list[TrialExecutionResult],
    final_run_dict: dict[str, Any],
) -> dict[str, Any]:
    return {
        "run_id": run_dict.get("run_id", ""),
        "run_name": run_name,
        "benchmark_id": config.bench_id,
        "model_id": config.model_id,
        "runtime_name": selection.runtime_name,
        "max_workers": selection.max_workers,
        "task_filter": list(selection.task_ids),
        "score": float(final_run_dict["score"]) if final_run_dict.get("score") is not None else None,
        "state": final_run_dict.get("state", ""),
        "trial_count": len(final_run_dict.get("trials", ())),
        "completed_trial_count": len(trial_results),
        "task_scores": [
            {
                "task_id": item.task_id,
                "trial_id": item.trial_id,
                "score": item.score,
            }
            for item in trial_results
        ],
    }


def main() -> None:
    selection = parse_runtime_selection()
    config = load_runtime_config()
    run_agent = load_runtime_runner()
    artifact_dir = build_run_artifact_dir(config, selection)
    eval_poll_timeout_seconds = _poll_timeout_seconds()
    bitgn_api_key = require_non_empty_value(config.bitgn_api_key, "BITGN_API_KEY")

    scores: list[tuple[str, float]] = []
    trial_results: list[TrialExecutionResult] = []

    try:
        client = HarnessServiceClientSync(config.bitgn_url)

        print("Connecting to BitGN", client.status(StatusRequest()))
        benchmark = client.get_benchmark(GetBenchmarkRequest(benchmark_id=config.bench_id))
        print(
            f"{EvalPolicy.Name(benchmark.policy)} benchmark: {benchmark.benchmark_id} "
            f"with {len(benchmark.tasks)} tasks.\n{CLI_GREEN}{benchmark.description}{CLI_CLR}"
        )

        run_name = build_run_name(config, selection)
        run = client.start_run(
            StartRunRequest(
                name=run_name,
                benchmark_id=config.bench_id,
                api_key=bitgn_api_key,
            )
        )
        run_dict = _proto_to_dict(run)
        _write_json(artifact_dir / "run-start.json", run_dict)
        print(
            f"Run started: {run_name} | workers={selection.max_workers} "
            f"| tasks={'all' if not selection.task_ids else ','.join(selection.task_ids)}"
        )
        print(f"Run artifact dir: {artifact_dir}")

        try:
            run_state = client.get_run(GetRunRequest(run_id=run.run_id))
            run_state_dict = _proto_to_dict(run_state)
            _write_json(artifact_dir / "run-state-before.json", run_state_dict)
            selected_trials = [
                trial
                for trial in run_state.trials
                if not selection.task_ids or trial.task_id in selection.task_ids
            ]
            _write_json(
                artifact_dir / "trial-map.json",
                {
                    "run_id": run.run_id,
                    "trials": [
                        {
                            "task_id": trial.task_id,
                            "trial_id": trial.trial_id,
                            "state": trial.state,
                            "instruction": trial.instruction,
                        }
                        for trial in selected_trials
                    ],
                },
            )

            with concurrent.futures.ThreadPoolExecutor(max_workers=selection.max_workers) as executor:
                future_to_task_id = {
                    executor.submit(_execute_trial, config, run_agent, trial.trial_id): trial.task_id
                    for trial in selected_trials
                }
                for future in concurrent.futures.as_completed(future_to_task_id):
                    result = future.result()
                    trial_results.append(result)
                    print(_render_trial_result_block(result), end="")
                    scores.append((result.task_id, result.score))

            _write_json(
                artifact_dir / "trial-results.json",
                [
                    {
                        "task_id": item.task_id,
                        "trial_id": item.trial_id,
                        "instruction": item.instruction,
                        "score": item.score,
                        "score_detail": list(item.score_detail),
                        "stdout_text": item.stdout_text,
                        "stderr_text": item.stderr_text,
                        "error_text": item.error_text,
                    }
                    for item in trial_results
                ],
            )
        finally:
            submit_response = client.submit_run(SubmitRunRequest(run_id=run.run_id, force=True))
            _write_json(artifact_dir / "run-submit.json", _proto_to_dict(submit_response))
            final_run_dict = _poll_run_until_evaluated(
                client,
                run.run_id,
                timeout_seconds=eval_poll_timeout_seconds,
            )
            _write_json(artifact_dir / "run-state-after.json", final_run_dict)
            _write_json(
                artifact_dir / "run-summary.json",
                _build_run_summary(
                    config=config,
                    selection=selection,
                    run_name=run_name,
                    run_dict=run_dict,
                    trial_results=trial_results,
                    final_run_dict=final_run_dict,
                ),
            )

    except ConnectError as exc:
        print(f"{exc.code}: {exc.message}")
        raise SystemExit(1) from exc
    except KeyboardInterrupt as exc:
        print(f"{CLI_RED}Interrupted{CLI_CLR}")
        raise SystemExit(130) from exc

    if scores:
        for task_id, score in scores:
            color = CLI_GREEN if score == 1 else CLI_RED
            print(f"{task_id}: {color}{score:0.2f}{CLI_CLR}")
        total = sum(score for _, score in scores) / len(scores) * 100.0
        print(f"FINAL: {total:0.2f}%")


if __name__ == "__main__":
    main()
