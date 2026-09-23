"""Детектор CVV-кода.

3 цифры, только при наличии якорного слова (cvv/код).
"""

import re

from app.core.span import Span
from app.detectors.base import Detector

#: 3 цифры.
_DIGITS = re.compile(r"(?<!\d)\d{3}(?!\d)")
#: Якорные слова: cvv, cvc, код.
_ANCHOR = re.compile(r"\b(?:cvv|cvc|код)\b", re.IGNORECASE)


class CvvDetector(Detector):
    """Находит CVV-код только рядом с якорным словом."""

    type = "cvv"
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