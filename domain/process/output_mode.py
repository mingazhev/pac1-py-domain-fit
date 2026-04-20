"""Typed response-shape contract (Phase 22B).

``NORTH_STAR_PLAN.MD`` Phase 22B retires three response-shape
heuristics (``_looks_like_scalar_only_request``,
``_looks_like_linewise_list_request``,
``_looks_like_explanatory_question``) that lived as dead duplicates in
``runtime_controls.py``.  The plan's retirement rule requires a named
typed owner to exist and be exercised by tests before the heuristic is
removed.

``OutputMode`` is that typed owner.  It names the five response shapes
preflight and downstream renderers already distinguish today via the
loose ``literal_mode: str`` field on ``PreflightContract``:

- ``DEFAULT`` — freeform prose answer (matches the legacy
  ``"freeform"`` string).
- ``SCALAR_ONLY`` — single-value answer such as a name, number, or
  status (matches ``"scalar"``).
- ``LINEWISE_LIST`` — one-per-line list (matches ``"list_lines"``).
- ``DATE_ONLY`` — a single ``YYYY-MM-DD`` date (matches ``"date"``).
- ``EXPLANATORY`` — an explanation of a tool, command, or concept.
  This variant did not have a ``literal_mode`` string equivalent; the
  preflight helper ``_explanatory_question`` used it only to exempt a
  sentence from side-effect detection.  Naming it here makes the
  response-shape contract complete.

``from_literal_mode`` / ``to_literal_mode`` are the single conversion
boundary between the typed enum and the string field.  Phase 23 will
migrate ``PreflightContract.literal_mode`` onto this enum; until then
the string stays as the storage representation with ``OutputMode`` as
the typed surface callers can reason about.
"""
from __future__ import annotations

from enum import Enum


class OutputMode(str, Enum):
    """Typed response-shape contract for a request or plan.

    The string values match the legacy ``literal_mode`` tokens so
    ``OutputMode.SCALAR_ONLY.value == "scalar"`` is usable directly
    against code that still consumes the string.
    """

    DEFAULT = "freeform"
    SCALAR_ONLY = "scalar"
    LINEWISE_LIST = "list_lines"
    DATE_ONLY = "date"
    EXPLANATORY = "explanatory"


class OutputModeContractError(ValueError):
    """Raised when an unknown legacy literal_mode token is seen."""


_LEGACY_TOKENS_TO_ENUM: dict[str, OutputMode] = {
    "freeform": OutputMode.DEFAULT,
    "scalar": OutputMode.SCALAR_ONLY,
    "list_lines": OutputMode.LINEWISE_LIST,
    "date": OutputMode.DATE_ONLY,
    "explanatory": OutputMode.EXPLANATORY,
    # ``article`` and ``AUTO`` appear in legacy call sites for tests and
    # temporal-lookup paths.  They are not response shapes but runtime
    # execution hints, so they deliberately do not map onto OutputMode:
    # callers holding those strings still use the loose ``literal_mode``
    # field until Phase 23 lifts them into their own typed owners.
}


def from_literal_mode(literal_mode: str) -> OutputMode:
    """Map a legacy ``literal_mode`` string to the typed enum.

    Raises :class:`OutputModeContractError` for tokens that have no
    ``OutputMode`` equivalent (``"article"``, ``"AUTO"``).  Those
    tokens are recorded as out-of-scope for Phase 22B so callers must
    keep using the loose string until their own migration lands.
    """

    token = (literal_mode or "").strip()
    if not token:
        return OutputMode.DEFAULT
    try:
        return _LEGACY_TOKENS_TO_ENUM[token]
    except KeyError as exc:
        raise OutputModeContractError(
            f"No OutputMode for legacy literal_mode={token!r}; "
            "Phase 22B covers freeform/scalar/list_lines/date/explanatory "
            "only.  Callers holding other tokens (e.g. 'article', "
            "'AUTO') must keep the loose string until their migration."
        ) from exc


def to_literal_mode(mode: OutputMode) -> str:
    """Map the typed enum back to the legacy string value."""

    if not isinstance(mode, OutputMode):
        raise OutputModeContractError(
            f"to_literal_mode requires OutputMode; got {type(mode).__name__}"
        )
    return mode.value


def literal_mode_to_output_mode(literal_mode: str) -> OutputMode | None:
    """Safe, non-raising mapping for mixed-token callers.

    Phase V1 (NORTH_STAR_PLAN_V2.MD) adds a typed ``output_mode``
    field to ``PreflightContract`` alongside the legacy
    ``literal_mode: str``.  Some legacy tokens (``article``, ``AUTO``)
    are not response-shape contracts and have no ``OutputMode``
    equivalent; this helper returns ``None`` for them so the caller
    keeps consulting the string field until those tokens get their
    own typed owner.
    """

    token = (literal_mode or "").strip()
    if not token:
        return OutputMode.DEFAULT
    return _LEGACY_TOKENS_TO_ENUM.get(token)


__all__ = [
    "OutputMode",
    "OutputModeContractError",
    "from_literal_mode",
    "literal_mode_to_output_mode",
    "to_literal_mode",
]
