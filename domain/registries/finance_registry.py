from __future__ import annotations

import re
from collections.abc import Iterable, Mapping
from dataclasses import dataclass, field
from types import MappingProxyType

from domain.finance.finance_record import FinanceRecord
from domain.finance.record_type import RecordType
from domain.finance.series_resolution import document_occurrence_key


def _normalize(value: object) -> str:
    return re.sub(r"\s+", " ", str(value or "").strip()).lower()


def _freeze_single(mapping: dict[str, FinanceRecord]) -> Mapping[str, FinanceRecord]:
    return MappingProxyType(dict(mapping))


def _freeze_multi(
    mapping: dict[str, list[FinanceRecord]],
) -> Mapping[str, tuple[FinanceRecord, ...]]:
    return MappingProxyType({key: tuple(values) for key, values in mapping.items()})


@dataclass(frozen=True, slots=True)
class FinanceRegistry:
    """Explicit read-model index over a canonical ``FinanceRecord`` collection.

    Forward indexes answer ``give me this record by path / by (type,
    reference) / by document-occurrence key``. Reverse indexes answer ``which
    finance records reference this counterparty / entity / project?`` — the
    cross-entity join the phase calls out for finance.
    """

    records: tuple[FinanceRecord, ...]
    _by_path: Mapping[str, FinanceRecord] = field(repr=False)
    _by_reference_number: Mapping[tuple[RecordType, str], tuple[FinanceRecord, ...]] = field(
        repr=False
    )
    _by_occurrence_key: Mapping[tuple[str, str, str, str], FinanceRecord] = field(
        repr=False
    )
    _by_counterparty: Mapping[str, tuple[FinanceRecord, ...]] = field(repr=False)
    _by_related_entity: Mapping[str, tuple[FinanceRecord, ...]] = field(repr=False)
    _by_project: Mapping[str, tuple[FinanceRecord, ...]] = field(repr=False)

    @classmethod
    def build(cls, records: Iterable[FinanceRecord]) -> FinanceRegistry:
        record_tuple = tuple(records)

        by_path: dict[str, FinanceRecord] = {}
        by_reference: dict[tuple[RecordType, str], list[FinanceRecord]] = {}
        by_occurrence: dict[tuple[str, str, str, str], FinanceRecord] = {}
        by_counterparty: dict[str, list[FinanceRecord]] = {}
        by_related_entity: dict[str, list[FinanceRecord]] = {}
        by_project: dict[str, list[FinanceRecord]] = {}

        for record in record_tuple:
            path_key = _normalize(record.path)
            if path_key and path_key not in by_path:
                by_path[path_key] = record

            reference_number = str(record.reference_number or "").strip()
            if reference_number:
                reference_key = (record.record_type, reference_number)
                by_reference.setdefault(reference_key, []).append(record)

            occurrence = document_occurrence_key(record)
            if occurrence is not None:
                tuple_key = occurrence.as_tuple()
                by_occurrence.setdefault(tuple_key, record)

            counterparty_key = _normalize(record.counterparty)
            if counterparty_key:
                by_counterparty.setdefault(counterparty_key, []).append(record)

            entity_key = _normalize(record.related_entity)
            if entity_key:
                by_related_entity.setdefault(entity_key, []).append(record)

            project_key = _normalize(record.project)
            if project_key:
                by_project.setdefault(project_key, []).append(record)

        return cls(
            records=record_tuple,
            _by_path=_freeze_single(by_path),
            _by_reference_number=MappingProxyType(
                {key: tuple(values) for key, values in by_reference.items()}
            ),
            _by_occurrence_key=MappingProxyType(dict(by_occurrence)),
            _by_counterparty=_freeze_multi(by_counterparty),
            _by_related_entity=_freeze_multi(by_related_entity),
            _by_project=_freeze_multi(by_project),
        )

    def __iter__(self):
        return iter(self.records)

    def __len__(self) -> int:
        return len(self.records)

    def by_path(self, path: str) -> FinanceRecord | None:
        return self._by_path.get(_normalize(path))

    def by_reference_number(
        self, record_type: RecordType, reference_number: str
    ) -> tuple[FinanceRecord, ...]:
        text = str(reference_number or "").strip()
        if not text:
            return ()
        return self._by_reference_number.get((record_type, text), ())

    def by_occurrence(
        self,
        *,
        record_type: RecordType,
        reference_number: str,
        counterparty: str,
        occurrence_date: str,
    ) -> FinanceRecord | None:
        reference_text = str(reference_number or "").strip()
        if not reference_text:
            return None
        record_type_literal = "invoice" if record_type is RecordType.INVOICE else "bill"
        key = (
            reference_text,
            str(counterparty or "").strip().lower(),
            record_type_literal,
            str(occurrence_date or ""),
        )
        return self._by_occurrence_key.get(key)

    def records_for_counterparty(self, counterparty: str) -> tuple[FinanceRecord, ...]:
        return self._by_counterparty.get(_normalize(counterparty), ())

    def records_for_related_entity(self, entity_display_name: str) -> tuple[FinanceRecord, ...]:
        return self._by_related_entity.get(_normalize(entity_display_name), ())

    def records_for_project(self, project_display_name: str) -> tuple[FinanceRecord, ...]:
        return self._by_project.get(_normalize(project_display_name), ())


__all__ = ["FinanceRegistry"]
