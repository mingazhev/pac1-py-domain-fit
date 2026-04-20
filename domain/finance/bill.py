from __future__ import annotations

from dataclasses import dataclass, field

from .finance_record import FinanceRecord
from .record_type import RecordType


@dataclass(frozen=True, slots=True)
class Bill(FinanceRecord):
    record_type: RecordType = field(init=False, default=RecordType.BILL)

    @property
    def bill_id(self) -> str:
        return self.reference_number
