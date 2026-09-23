"""Детектор пин-кода.

4-6 цифр, только при наличии якорного слова (пин/pin).
"""

import re

from app.core.span import Span
from app.detectors.base import Detector

#: 4-6 цифр.
_DIGITS = re.compile(r"(?<!\d)\d{4,6}(?!\d)")
#: Якорные слова: пин, pin.
_ANCHOR = re.compile(r"\b(?:пин|pin)\b", re.IGNORECASE)


class PinDetector(Detector):
    """Находит пин-код только рядом с якорным словом."""

    type = "pin"
    priority = 30

    def detect(self, text: str) -> list[Span]:
        spans: list[Span] = []
        for match in _DIGITS.finditer(text):
            window = text[max(0, match.start() - 15):match.end() + 10]
            if _ANCHOR.search(window):
                spans.append(Span(
                    type=self.type,
                    start=match.start(),
                    end=match.end(),
                    value=match.group(),
                    confidence=0.9,
                ))
        return spans