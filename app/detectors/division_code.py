"""Детектор кода подразделения.

Формат: 3 цифры-3 цифры (например, 770-123), только при наличии
якорного слова (код подразделения).
"""

import re

from app.core.span import Span
from app.detectors.base import Detector

#: 3 цифры-3 цифры.
_CODE = re.compile(r"(?<!\d)\d{3}-\d{3}(?!\d)")
#: Якорные слова: код подразделения, подразделения.
_ANCHOR = re.compile(r"(?:код[ ]?подразделения|подразделения)", re.IGNORECASE)


class DivisionCodeDetector(Detector):
    """Находит код подразделения рядом с якорным словом."""

    type = "division_code"
    priority = 30

    def detect(self, text: str) -> list[Span]:
        spans: list[Span] = []
        for match in _CODE.finditer(text):
            window = text[max(0, match.start() - 30):match.end() + 10]
            if _ANCHOR.search(window):
                spans.append(Span(
                    type=self.type,
                    start=match.start(),
                    end=match.end(),
                    value=match.group(),
                    confidence=0.9,
                ))
        return spans