from __future__ import annotations

from dataclasses import dataclass
from enum import Enum


class SemanticReferenceKind(str, Enum):
    ENTITY = "entity"
    PROJECT = "project"


class ProjectGraphRole(str, Enum):
    OWNER = "owner"
    LINKED_ENTITY = "linked_entity"
    PARTICIPANT = "participant"


@dataclass(frozen=True, slots=True)
class SemanticReference:
    target_kind: SemanticReferenceKind
    target_id: str
    title: str = ""
    path: str = ""


@dataclass(frozen=True, slots=True)
class GraphEdge:
    role: ProjectGraphRole
    reference: SemanticReference
