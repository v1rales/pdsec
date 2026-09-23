"""Детектор номера телефона РФ.

Формат: префикс +7/8/7 + 10 цифр (11 цифр всего), допускаются разделители
(пробелы, дефисы, скобки) между группами цифр.
"""

import re

from app.core.span import Span
from app.detectors.base import Detector

#: Префикс (+7/8/7) + 10 цифр с необязательными разделителями.
_PATTERN = re.compile(
    r"(?<!\d)(?:\+7|8|7)[ ]?-?\(?\d{3}\)?[ ]?-?\d{3}[ ]?-?\d{2}[ ]?-?\d{2}(?!\d)"
)


class PhoneDetector(Detector):
    """Находит номера телефонов РФ."""

    type = "phone"
    priority = 30

    def detect(self, text: str) -> list[Span]:
        spans: list[Span] = []
        for match in _PATTERN.finditer(text):
            spans.append(Span(
                type=self.type,
                start=match.start(),
                end=match.end(),
                value=match.group(),
                confidence=0.95,
            ))
        return spans