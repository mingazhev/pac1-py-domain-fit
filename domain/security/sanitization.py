from __future__ import annotations

import unicodedata


def normalize_security_text(text: str) -> str:
    return unicodedata.normalize("NFKC", str(text or ""))


def _is_invisible_security_char(ch: str) -> bool:
    code = ord(ch)
    if 0xE0000 <= code <= 0xE007F:
        return True
    return unicodedata.category(ch) == "Cf"


def sanitize_security_text(text: str) -> str:
    normalized = normalize_security_text(text)
    return "".join(ch for ch in normalized if not _is_invisible_security_char(ch))
