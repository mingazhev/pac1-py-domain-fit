from __future__ import annotations

from dataclasses import dataclass, field

from .finance_record import FinanceRecord
from .record_type import RecordType


@dataclass(frozen=True, slots=True)
class Invoice(FinanceRecord):
    record_type: RecordType = field(init=False, default=RecordType.INVOICE)

    @property
    def invoice_number(self) -> str:
        return self.reference_number
