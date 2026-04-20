from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True, slots=True)
class Account:
    account_id: str
    legal_name: str = ""
    display_name: str = ""
    industry: str = ""
    country: str = ""
    city: str = ""
    primary_contact_id: str = ""
    account_manager_id: str = ""
    tags: tuple[str, ...] = ()

    @property
    def searchable_terms(self) -> tuple[str, ...]:
        return tuple(
            term
            for term in (
                self.account_id,
                self.legal_name,
                self.display_name,
                self.industry,
                self.country,
                self.city,
                *self.tags,
            )
            if str(term or "").strip()
        )
