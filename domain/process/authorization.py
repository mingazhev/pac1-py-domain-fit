from __future__ import annotations

from dataclasses import dataclass
from enum import Enum


class AuthorizationKind(str, Enum):
    EXPLICIT_USER_CONFIRMATION = "explicit_user_confirmation"
    WORKFLOW_POLICY = "workflow_policy"
    PRE_AUTHORIZED_SERIES = "pre_authorized_series"


@dataclass(frozen=True, slots=True)
class AuthorizationStamp:
    kind: AuthorizationKind
    authorized_by: str

    @classmethod
    def from_fields(
        cls,
        authorization_kind: object,
        authorized_by: object,
    ) -> AuthorizationStamp | None:
        actor = str(authorized_by or "").strip()
        raw_kind = str(authorization_kind or "").strip()
        if not actor or not raw_kind:
            return None
        try:
            kind = AuthorizationKind(raw_kind)
        except ValueError:
            return None
        return cls(kind=kind, authorized_by=actor)

    def to_update_dict(self) -> dict[str, str]:
        return {
            "authorization_kind": self.kind.value,
            "authorized_by": self.authorized_by,
        }


__all__ = ["AuthorizationKind", "AuthorizationStamp"]
