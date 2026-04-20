"""Shared domain-level workspace contracts."""

from .workspace import (
    DEFAULT_WORKSPACE_LAYOUT,
    WorkspaceLayout,
    resolve_workspace_layout,
)

__all__ = [
    "DEFAULT_WORKSPACE_LAYOUT",
    "WorkspaceLayout",
    "resolve_workspace_layout",
]
