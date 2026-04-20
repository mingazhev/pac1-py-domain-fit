from __future__ import annotations


def build_finance_record_index(finance_records: tuple) -> str:
    if not finance_records:
        return ""
    lines: list[str] = []
    for record in finance_records[:80]:
        amount = getattr(record, "total_eur", None)
        if amount is None:
            amount = getattr(record, "amount_eur", None)
        if amount is None:
            amount = getattr(record, "amount", None)
        kind = getattr(record.record_type, "value", str(record.record_type))
        counterparty = str(record.counterparty or "").strip() or "(unknown)"
        date = str(record.date or "").strip() or "?"
        pieces = [record.path, kind, date, counterparty]
        if amount is not None:
            pieces.append(str(amount))
        lines.append("- " + "; ".join(pieces))
    return "\n".join(lines)


__all__ = ["build_finance_record_index"]
