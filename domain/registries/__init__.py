"""Typed read-model registries for Phase 9.

The bounded-context packages (`domain/cast/`, `domain/projects/`,
`domain/finance/`) own canonical shape and per-record behavior; the
registries in this package provide explicit read-model indexes and
reverse-reference joins built from those canonical collections.

Phase 9 intent:

- Pre-built O(1) lookups by canonical id/slug/alias/email so resolvers
  no longer re-scan flat sequences at every call site.
- Reverse indexes for cross-record traversal (entity → projects,
  entity → finance records, project → finance records).
- A typed contact/sender registry derived from the canonical cast
  roster, so the canonical-email gate stops depending on implicit
  rosters buried in loaders or LLM heuristics.
"""

from .cast_registry import CastRegistry
from .contact_registry import ContactIdentity, ContactRegistry
from .finance_registry import FinanceRegistry
from .project_registry import ProjectRegistry
from .record_graph import CrossContextRecordGraph

__all__ = [
    "CastRegistry",
    "ContactIdentity",
    "ContactRegistry",
    "CrossContextRecordGraph",
    "FinanceRegistry",
    "ProjectRegistry",
]
