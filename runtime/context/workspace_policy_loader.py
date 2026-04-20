from __future__ import annotations

from collections.abc import Sequence

from domain.workspace import WorkspaceLayout, WorkspacePolicies
from telemetry.trace import emit_runtime_exception
from runtime.io.vm_tools import normalize_repo_path, read_text


def load_workspace_policies_from_paths(
    vm,
    *,
    layout: WorkspaceLayout,
    file_paths: Sequence[str],
) -> WorkspacePolicies:
    agents_candidates = [
        path
        for path in file_paths
        if path.rsplit("/", 1)[-1].lower() == "agents.md"
    ]

    def _read_body(path: str) -> str:
        try:
            body = read_text(vm, path)
        except Exception as exc:  # noqa: BLE001
            emit_runtime_exception(
                error=exc,
                stage="workspace_policy_loader",
                operation="read_policy_body",
                extra={"path": path},
            )
            return ""
        return str(body or "").strip()

    role_policy: dict[str, str] = {}
    for role in (
        "inbox",
        "cast",
        "knowledge",
        "work",
        "finance",
        "outbox",
        "memory",
        "system",
        "process",
        "capture",
    ):
        roots = layout.roots_for_role(role)
        for root in roots:
            normalized_root = root.rstrip("/")
            agents_path = next(
                (
                    path
                    for path in agents_candidates
                    if normalize_repo_path(path).rsplit("/", 1)[0] == normalized_root
                ),
                None,
            )
            if agents_path is None:
                continue
            body = _read_body(agents_path)
            if body:
                role_policy[role] = body
                break

    root_agents = next(
        (
            path
            for path in agents_candidates
            if normalize_repo_path(path).count("/") == 1
        ),
        None,
    )
    root_body = _read_body(root_agents) if root_agents else ""

    projects_agents = next(
        (
            path
            for path in agents_candidates
            if normalize_repo_path(path).rsplit("/", 1)[0]
            in set(layout.projects)
        ),
        None,
    )
    if projects_agents is None:
        projects_agents = next(
            (
                path
                for path in agents_candidates
                if looks_like_projects_root(normalize_repo_path(path))
            ),
            None,
        )
    projects_body = _read_body(projects_agents) if projects_agents else ""

    extra_workflows: list[tuple[str, str]] = []
    for wanted in (
        "99_system/workflows/sending-email.md",
        "99_system/workflows/processing-inbox-email.md",
    ):
        match = next(
            (
                path
                for path in file_paths
                if normalize_repo_path(path).lstrip("/").lower() == wanted
            ),
            None,
        )
        if match is None:
            continue
        body = _read_body(match)
        if body:
            extra_workflows.append((wanted, body))

    return WorkspacePolicies(
        inbox=role_policy.get("inbox", ""),
        cast=role_policy.get("cast", ""),
        knowledge=role_policy.get("knowledge", ""),
        work=role_policy.get("work", ""),
        finance=role_policy.get("finance", ""),
        outbox=role_policy.get("outbox", ""),
        memory=role_policy.get("memory", ""),
        system=role_policy.get("system", ""),
        process=role_policy.get("process", ""),
        capture=role_policy.get("capture", ""),
        projects=projects_body,
        root=root_body,
        extra_workflows=tuple(extra_workflows),
    )


def looks_like_projects_root(normalized_path: str) -> bool:
    if normalized_path.count("/") != 2:
        return False
    parent = normalized_path.rsplit("/", 1)[0].lstrip("/").lower()
    if not parent:
        return False
    tail = parent.split("_", 1)[-1] if "_" in parent else parent
    return parent == "projects" or tail == "projects"


__all__ = ["load_workspace_policies_from_paths", "looks_like_projects_root"]
