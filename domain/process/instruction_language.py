from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True, slots=True)
class InstructionLanguageDecision:
    original_text: str
    translated_text: str
    effective_text: str
    source: str
    is_translated: bool
    locale_signal: str

    def locale_attribution(self, *, reason_code: str = "") -> dict[str, object]:
        return {
            "source": self.source,
            "is_translated": self.is_translated,
            "original_text_present": bool(self.original_text),
            "locale_signal": self.locale_signal,
            "translated_text": self.translated_text,
            "locale_drift_detected": str(reason_code or "") == "output_language_drift",
        }


def resolve_instruction_language(
    original_text: str,
    *,
    translated_text: str = "",
) -> InstructionLanguageDecision:
    original = str(original_text or "").strip()
    translated = str(translated_text or "").strip()
    if translated:
        return InstructionLanguageDecision(
            original_text=original,
            translated_text=translated,
            effective_text=translated,
            source="translated_text",
            is_translated=True,
            locale_signal="non_english_input",
        )
    return InstructionLanguageDecision(
        original_text=original,
        translated_text="",
        effective_text=original,
        source="none",
        is_translated=False,
        locale_signal="default",
    )
