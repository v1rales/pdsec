"""Детектор номера банковской карты.

13-19 цифр, контрольная сумма Луна обязательна.
Допускаются пробелы между группами цифр.
"""

import re

from app.core.span import Span
from app.detectors.base import Detector

#: Сплошные 13-19 цифр.
_PLAIN = re.compile(r"(?<!\d)\d{13,19}(?!\d)")
#: Группы по 4 цифры с необязательными разделителями (пробел/дефис/точка).
_GROUPED = re.compile(
    r"(?<!\d)\d{4}[ \-.]?\d{4}[ \-.]?\d{4}[ \-.]?\d{4}(?!\d)"
)


def _luhn(digits: str) -> bool:
    """Проверяет контрольную сумму Луна."""
    total = 0
    for i, ch in enumerate(reversed(digits)):
        d = int(ch)
        if i % 2 == 1:
            d *= 2
            if d > 9:
                d -= 9
        total += d
    return total % 10 == 0


class CardDetector(Detector):
    """Находит номера банковских карт с валидной суммой Луна."""

    type = "card"
    priority = 40
    has_checksum = True

    def detect(self, text: str) -> list[Span]:
        spans: list[Span] = []
        seen: set[tuple[int, int]] = set()
        for pattern in (_GROUPED, _PLAIN):
            for match in pattern.finditer(text):
                digits = re.sub(r"\D", "", match.group())
                if not _luhn(digits):
                    continue
                key = (match.start(), match.end())
                if key in seen:
                    continue
                seen.add(key)
                spans.append(Span(
                    type=self.type,
                    start=match.start(),
                    end=match.end(),
                    value=match.group(),
                    confidence=0.99,
                ))
        return spans