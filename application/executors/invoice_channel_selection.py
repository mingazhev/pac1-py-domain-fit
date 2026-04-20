from __future__ import annotations

import re
from collections.abc import Sequence
from pathlib import PurePosixPath

from domain.finance import Invoice
from domain.messages import ChannelDefinition, ChannelTransportKind


def _normalize_text(value: object) -> str:
    return re.sub(r"\s+", " ", str(value or "").strip()).lower()


def _normalized_channel_path(channel: str | ChannelDefinition) -> str:
    if isinstance(channel, ChannelDefinition):
        return str(channel.path or "").strip()
    return str(channel or "").strip()


def _channel_search_terms(channel: str | ChannelDefinition) -> tuple[str, ...]:
    if isinstance(channel, ChannelDefinition):
        return channel.search_terms()
    path = _normalized_channel_path(channel)
    return tuple(
        value
        for value in (
            path,
            PurePosixPath(path).stem.replace("_", " ").strip(),
        )
        if value
    )


def _invoice_identity_terms(invoice_records: Sequence[Invoice]) -> frozenset[str]:
    return frozenset(
        normalized
        for normalized in (
            _normalize_text(field)
            for record in invoice_records
            for field in (
                record.counterparty,
                record.project,
                record.path,
                record.alias,
                record.title,
                record.related_entity,
            )
            if field
        )
        if normalized
    )


def select_outbox_channel_for_invoices(
    channels: Sequence[str | ChannelDefinition],
    invoice_records: Sequence[Invoice],
) -> str | None:
    normalized_paths = tuple(
        channel
        for channel in channels
        if _normalized_channel_path(channel)
    )
    if not normalized_paths:
        return None
    if len(normalized_paths) == 1:
        return _normalized_channel_path(normalized_paths[0])

    invoice_terms = _invoice_identity_terms(invoice_records)
    if not invoice_terms:
        return None
    exact_matches: list[str | ChannelDefinition] = []
    for channel in normalized_paths:
        channel_terms = {
            _normalize_text(term)
            for term in _channel_search_terms(channel)
            if _normalize_text(term)
        }
        if invoice_terms.intersection(channel_terms):
            exact_matches.append(channel)
    if len(exact_matches) == 1:
        return _normalized_channel_path(exact_matches[0])
    email_matches = [
        channel
        for channel in exact_matches
        if isinstance(channel, ChannelDefinition)
        and channel.transport_kind is ChannelTransportKind.EMAIL
    ]
    if len(email_matches) == 1:
        return _normalized_channel_path(email_matches[0])
    if exact_matches:
        return None
    email_channels = [
        channel
        for channel in normalized_paths
        if isinstance(channel, ChannelDefinition)
        and channel.transport_kind is ChannelTransportKind.EMAIL
    ]
    if len(email_channels) == 1:
        return _normalized_channel_path(email_channels[0])
    if len(normalized_paths) == 2:
        normalized_string_paths = {
            _normalized_channel_path(channel)
            for channel in normalized_paths
        }
        if len(normalized_string_paths) == 1:
            return next(iter(normalized_string_paths))
        return None
    return None


__all__ = ["select_outbox_channel_for_invoices"]
