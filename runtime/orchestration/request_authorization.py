from __future__ import annotations

from dataclasses import dataclass

from domain.process import AuthorizationKind, RequestSource
from task_routing import TypedStep

from runtime.authorization.authorization import stamp_command_authorization


# Trusted request sources. A source is trusted when the harness layer has
# already established the authenticity of the external caller before the
# request entered the public machine. Anything outside this set must be
# blocked BEFORE we ever hand ``task_text`` to an LLM extractor, because
# interpreting unauthorized input is itself the attack surface.
TRUSTED_REQUEST_SOURCES: frozenset[RequestSource] = frozenset(
    {
        RequestSource.HARNESS,
        RequestSource.SHORTCUT,
        RequestSource.INBOX,
        RequestSource.REPLAY,
    }
)


@dataclass(frozen=True, slots=True)
class RequestAuthorizationContext:
    """Pre-interpretation authorization decision for an incoming request.

    Computed BEFORE any LLM call in the public machine. Carries both the
    enum source (for downstream stamping) and a ``trusted`` flag that
    gates whether the request is allowed to reach the semantic
    interpretation stage at all. ``reason_code`` is populated only when
    ``trusted`` is ``False`` so callers can emit a structured ``blocked``
    decision without re-deriving the reason.

    ``source`` is ``None`` for rejected non-enum inputs — honest refusal
    to attribute an unauthorized caller to any known source. Callers
    that need an enum must first check ``trusted``.
    """

    source: RequestSource | None
    trusted: bool
    reason_code: str | None = None


def classify_request_source(source: object) -> RequestAuthorizationContext:
    """Pre-LLM gate: decide whether a request may reach interpretation.

    NORTH_STAR: security starts BEFORE full semantic understanding.
    An unknown / non-enum / non-trusted source must be blocked here so
    that we never pay the cost — or assume the risk — of shipping raw
    ``task_text`` into a structured-extraction LLM call on behalf of an
    uncredentialed caller.
    """

    if not isinstance(source, RequestSource):
        return RequestAuthorizationContext(
            source=None,
            trusted=False,
            reason_code="unauthorized_source",
        )
    if source not in TRUSTED_REQUEST_SOURCES:
        return RequestAuthorizationContext(
            source=source,
            trusted=False,
            reason_code="unauthorized_source",
        )
    return RequestAuthorizationContext(source=source, trusted=True)


def stamp_request_authorization(
    command: TypedStep,
    *,
    source: RequestSource,
) -> TypedStep:
    if source not in {RequestSource.HARNESS, RequestSource.SHORTCUT}:
        return command
    return stamp_command_authorization(
        command,
        authorization_kind=AuthorizationKind.EXPLICIT_USER_CONFIRMATION.value,
        authorized_by=source.value,
        require_authz_contract=True,
    )


__all__ = [
    "RequestAuthorizationContext",
    "TRUSTED_REQUEST_SOURCES",
    "classify_request_source",
    "stamp_request_authorization",
]
