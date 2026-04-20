from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True, slots=True)
class Contact:
    contact_id: str
    full_name: str = ""
    email: str = ""
    title: str = ""
    account_id: str = ""

    @property
    def searchable_terms(self) -> tuple[str, ...]:
        return tuple(
            term
            for term in (
                self.contact_id,
                self.full_name,
                self.email,
                self.title,
                self.account_id,
            )
            if str(term or "").strip()
        )
