from __future__ import annotations

from application.ports import RecordResolutionPort, RecordResolutionResult


def build_record_resolution_port() -> RecordResolutionPort:
    from task_routing.record_resolution import resolve_records

    def _resolve(
        rows,
        query: str,
        notes,
    ) -> RecordResolutionResult:
        resolution = resolve_records(rows, query, notes=notes)
        return RecordResolutionResult(
            status=resolution.status,
            candidate=resolution.candidate,
        )

    return RecordResolutionPort(
        resolve_account_candidate=_resolve,
        resolve_contact_candidate=_resolve,
    )


__all__ = ["build_record_resolution_port"]
