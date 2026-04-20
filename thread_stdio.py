from __future__ import annotations

import sys
import threading
from contextlib import contextmanager
from typing import Iterator, TextIO


class _ThreadLocalTextProxy:
    def __init__(self, original: TextIO) -> None:
        self._original = original
        self._lock = threading.RLock()
        self._targets: dict[int, list[TextIO]] = {}

    def push_target(self, target: TextIO) -> None:
        ident = threading.get_ident()
        with self._lock:
            self._targets.setdefault(ident, []).append(target)

    def pop_target(self) -> None:
        ident = threading.get_ident()
        with self._lock:
            stack = self._targets.get(ident)
            if not stack:
                return
            stack.pop()
            if not stack:
                self._targets.pop(ident, None)

    def _stream(self) -> TextIO:
        ident = threading.get_ident()
        with self._lock:
            stack = self._targets.get(ident)
            if stack:
                return stack[-1]
        return self._original

    def write(self, data: str) -> int:
        return self._stream().write(data)

    def flush(self) -> None:
        self._stream().flush()

    def isatty(self) -> bool:
        stream = self._stream()
        if hasattr(stream, "isatty"):
            return bool(stream.isatty())
        return False

    @property
    def encoding(self) -> str | None:
        stream = self._stream()
        return getattr(stream, "encoding", getattr(self._original, "encoding", None))

    @property
    def errors(self) -> str | None:
        stream = self._stream()
        return getattr(stream, "errors", getattr(self._original, "errors", None))

    def __getattr__(self, name: str):
        return getattr(self._original, name)


_INSTALL_LOCK = threading.Lock()


def _install_proxy(name: str) -> _ThreadLocalTextProxy:
    with _INSTALL_LOCK:
        current = getattr(sys, name)
        if isinstance(current, _ThreadLocalTextProxy):
            return current
        proxy = _ThreadLocalTextProxy(current)
        setattr(sys, name, proxy)
        return proxy


@contextmanager
def capture_thread_stdio(stdout: TextIO, stderr: TextIO) -> Iterator[None]:
    stdout_proxy = _install_proxy("stdout")
    stderr_proxy = _install_proxy("stderr")
    stdout_proxy.push_target(stdout)
    stderr_proxy.push_target(stderr)
    try:
        yield
    finally:
        stderr_proxy.pop_target()
        stdout_proxy.pop_target()
