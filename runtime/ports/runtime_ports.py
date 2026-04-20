from __future__ import annotations

from dataclasses import dataclass

from application.context import RuntimeContext
from application.ports import (
    QueryResolutionPort,
    ReadStepInterpretationPort,
    RecordResolutionPort,
)
from task_routing import CastResolverSet, ProjectResolverSet

from runtime.ports.read_interpretation_strategies import build_read_step_interpretation_port
from runtime.ports.record_resolution_runtime import build_record_resolution_port
from runtime.ports.resolver_sets import (
    build_cast_resolvers,
    build_project_resolvers,
    build_query_resolution_port,
)


@dataclass(frozen=True, slots=True)
class RuntimePorts:
    cast_resolvers: CastResolverSet
    project_resolvers: ProjectResolverSet
    query_resolution: QueryResolutionPort
    read_interpretation: ReadStepInterpretationPort
    record_resolution: RecordResolutionPort


def build_runtime_ports(
    *,
    context: RuntimeContext,
    gateway: object | None,
    model: str | None,
) -> RuntimePorts:
    cast_resolvers = build_cast_resolvers(
        gateway,
        model,
        finance_records=tuple(getattr(context, "finance_records", ()) or ()),
    )
    project_resolvers = build_project_resolvers(gateway, model)
    return RuntimePorts(
        cast_resolvers=cast_resolvers,
        project_resolvers=project_resolvers,
        query_resolution=build_query_resolution_port(
            cast_resolvers,
            project_resolvers,
        ),
        read_interpretation=build_read_step_interpretation_port(
            context,
            gateway,
            model,
        ),
        record_resolution=build_record_resolution_port(),
    )


__all__ = ["RuntimePorts", "build_runtime_ports"]
