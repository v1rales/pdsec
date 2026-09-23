"""Детектор email-адреса."""

import re

from app.core.span import Span
from app.detectors.base import Detector

#: Локальная часть @ домен.точка-зона.
#: Lookahead исключает только буквы/цифры/@, чтобы пунктуация (точка, запятая)
#: после email не ломала матч.
_PATTERN = re.compile(
    r"(?<![A-Za-z0-9._%+-])[A-Za-z0-9._%+-]+@[A-Za-z0-9.-]+\.[A-Za-z]{2,}"
    r"(?![A-Za-z0-9@])",
    re.IGNORECASE,
)


class EmailDetector(Detector):
    """Находит email-адреса."""

    type = "email"
    priority = 30

    def detect(self, text: str) -> list[Span]:
        spans: list[Span] = []
        for match in _PATTERN.finditer(text):
            spans.append(Span(
                type=self.type,
                start=match.start(),
                end=match.end(),
                value=match.group(),
                confidence=0.98,
            ))
        return spans