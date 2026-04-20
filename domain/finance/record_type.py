from __future__ import annotations

from enum import Enum


def _normalize_record_type(value: object) -> str:
    text = str(value or "").strip().lower()
    if not text:
        return ""
    normalized_chars = [char if char.isalnum() else " " for char in text]
    return " ".join("".join(normalized_chars).split())


class RecordType(str, Enum):
    BILL = "bill"
    INVOICE = "invoice"

    @classmethod
    def parse(cls, value: object) -> RecordType | None:
        normalized = _normalize_record_type(value)
        if normalized == cls.BILL.value:
            return cls.BILL
        if normalized == cls.INVOICE.value:
            return cls.INVOICE
        return None
