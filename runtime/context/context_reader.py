from __future__ import annotations

from collections.abc import Sequence
from dataclasses import dataclass
from typing import Any

from runtime.context.context_persistence import parse_markdown_document
from runtime.io.vm_tools import read_text
from telemetry.trace import emit_runtime_exception


@dataclass(frozen=True)
class ContextDocumentReader:
    vm: object
    top_level_names: frozenset[str]

    def __post_init__(self) -> None:
        object.__setattr__(self, "_read_cache", {})

    def read(self, path: str) -> dict[str, Any] | None:
        read_cache: dict[str, dict[str, Any]] = object.__getattribute__(
            self, "_read_cache"
        )
        if path in read_cache:
            return read_cache[path]
        try:
            body = read_text(self.vm, path)
        except Exception as exc:  # noqa: BLE001
            emit_runtime_exception(
                stage="context_loader",
                operation="read_text",
                error=exc,
                extra={"path": path},
            )
            return None
        doc = parse_markdown_document(body, path)
        read_cache[path] = doc
        return doc

    def prime(self, paths: Sequence[str]) -> list[dict[str, Any]]:
        docs: list[dict[str, Any]] = []
        for path in paths:
            doc = self.read(path)
            if doc is not None:
                docs.append(doc)
        return docs

    def has_top_level(self, name: str) -> bool:
        return name.lower() in self.top_level_names


def build_context_document_reader(
    vm: object,
    *,
    top_level_names: frozenset[str],
) -> ContextDocumentReader:
    return ContextDocumentReader(vm=vm, top_level_names=top_level_names)


__all__ = ["ContextDocumentReader", "build_context_document_reader"]
