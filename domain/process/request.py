"""First-class ``Request`` envelope for the public machine.

Phase 18 of ``NORTH_STAR_PLAN.MD`` promotes ``Request`` from raw ``task_text``
travelling through constructors into a typed value object so the first edge
of ``Request -> WorkItem -> Plan -> Decision`` from ``NORTH_STAR.md`` is held
together by the type system, not by convention.

Load-bearing invariants enforced structurally (not via prose):

- ``identifier`` is non-empty so trace, telemetry, and continuation provenance
  can join across the public machine.
- ``task_text`` is non-empty.  Refusal-shaped decisions happen later at
  preflight or at interpretation, not at the public edge: a ``Request`` with
  empty text is a construction bug, not a domain outcome.
- ``source`` is a known ``RequestSource``.  Free-form source strings turn
  routing into folklore.
- ``received_at`` is a timezone-aware timestamp so duration math, replay
  filtering, and audit trails all stay correct across daylight-saving and
  log-shipping boundaries.  The factory defaults to ``datetime.now(UTC)``
  so callers that omit the field get UTC automatically; non-UTC
  zones are accepted because they convert losslessly.
- ``envelope_refs`` are stripped and deduplicated.  May be empty because
  evidence is gathered during interpretation.

The ``new_request`` factory enforces every invariant; callers must go through
it instead of constructing ``Request`` directly with raw fields.
"""
from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timezone
from enum import Enum


class RequestSource(str, Enum):
    """Where a request entered the public machine from.

    HARNESS
        The external benchmark / agent runner ( ``agent.run_agent`` ).

    INBOX
        Workspace inbox pickup that promoted a queued item into a request.

    SHORTCUT
        Explicit shortcut entry ( ``agent_shortcuts`` ).

    REPLAY
        Trace replay or local eval reconstructing a historical request.
    """

    HARNESS = "harness"
    INBOX = "inbox"
    SHORTCUT = "shortcut"
    REPLAY = "replay"


class RequestContractError(ValueError):
    """Raised when a ``Request`` would violate its construction invariants."""


@dataclass(frozen=True, slots=True)
class Request:
    """Typed envelope for an external ask entering the public machine.

    Construct through :func:`new_request` for default-valued fields.
    Direct ``Request(...)`` construction is also legal: ``__post_init__``
    enforces every invariant so there is no back door that bypasses
    them.
    """

    identifier: str
    task_text: str
    source: RequestSource
    received_at: datetime
    envelope_refs: tuple[str, ...] = ()

    def __post_init__(self) -> None:
        if not isinstance(self.identifier, str) or not self.identifier.strip():
            raise RequestContractError(
                "Request.identifier must be a non-empty string"
            )
        if not isinstance(self.task_text, str) or not self.task_text.strip():
            raise RequestContractError(
                "Request.task_text must be a non-empty string"
            )
        if not isinstance(self.source, RequestSource):
            raise RequestContractError(
                "Request.source must be a RequestSource enum value; "
                f"got {type(self.source).__name__}"
            )
        if not isinstance(self.received_at, datetime):
            raise RequestContractError(
                "Request.received_at must be a datetime; "
                f"got {type(self.received_at).__name__}"
            )
        if (
            self.received_at.tzinfo is None
            or self.received_at.tzinfo.utcoffset(self.received_at) is None
        ):
            raise RequestContractError(
                "Request.received_at must be a timezone-aware datetime"
            )
        if not isinstance(self.envelope_refs, tuple):
            raise RequestContractError(
                "Request.envelope_refs must be a tuple of strings"
            )
        for ref in self.envelope_refs:
            if not isinstance(ref, str) or not ref.strip():
                raise RequestContractError(
                    "Request.envelope_refs entries must be non-empty strings"
                )


def new_request(
    *,
    identifier: str,
    task_text: str,
    source: RequestSource,
    received_at: datetime | None = None,
    envelope_refs: tuple[str, ...] | list[str] | None = None,
) -> Request:
    """Build a typed ``Request`` enforcing every invariant.

    Raises :class:`RequestContractError` on any violation so the public-machine
    edge cannot silently emit an ill-shaped request.
    """

    ident = (identifier or "").strip()
    if not ident:
        raise RequestContractError("Request.identifier must be non-empty")
    text = (task_text or "").strip()
    if not text:
        raise RequestContractError(
            "Request.task_text must be non-empty; refusal-shaped decisions "
            "belong at preflight or interpretation, not at the public edge"
        )
    if not isinstance(source, RequestSource):
        raise RequestContractError(
            "Request.source must be a RequestSource enum value; "
            f"got {type(source).__name__}"
        )
    when = received_at if received_at is not None else datetime.now(timezone.utc)
    if when.tzinfo is None or when.tzinfo.utcoffset(when) is None:
        raise RequestContractError(
            "Request.received_at must be a timezone-aware datetime"
        )
    refs = tuple(
        sorted(
            {
                str(ref).strip()
                for ref in (envelope_refs or ())
                if str(ref or "").strip()
            }
        )
    )
    return Request(
        identifier=ident,
        task_text=text,
        source=source,
        received_at=when,
        envelope_refs=refs,
    )


__all__ = [
    "Request",
    "RequestContractError",
    "RequestSource",
    "new_request",
]
