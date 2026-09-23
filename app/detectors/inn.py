"""Детектор ИНН.

12 цифр — физлицо (маскируем), контрольные разряды обязательны.
10 цифр — юрлицо, не ПД, не маскируем.
"""

import re

from app.core.span import Span
from app.detectors.base import Detector

#: 12 цифр (ИНН физлица), допускаются пробелы/дефисы/точки между группами.
_PATTERN = re.compile(r"(?<!\d)\d{4}[ \-.]?\d{4}[ \-.]?\d{4}(?!\d)")

#: Весовые коэффициенты для контрольных разрядов ИНН.
_WEIGHTS_11 = (7, 2, 4, 10, 3, 5, 9, 4, 6, 8)
_WEIGHTS_12 = (3, 7, 2, 4, 10, 3, 5, 9, 4, 6, 8)


def _check_digit(digits: str, weights: tuple[int, ...]) -> int:
    """Вычисляет контрольный разряд по весовым коэффициентам."""
    total = sum(int(d) * w for d, w in zip(digits, weights))
    return total % 11 % 10


class InnDetector(Detector):
    """Находит ИНН физлица (12 цифр) с валидными контрольными разрядами."""

    type = "inn"
    priority = 40
    has_checksum = True

    def detect(self, text: str) -> list[Span]:
        spans: list[Span] = []
        for match in _PATTERN.finditer(text):
            digits = re.sub(r"\D", "", match.group())
            # 11-й контрольный разряд.
            if _check_digit(digits[:10], _WEIGHTS_11) != int(digits[10]):
                continue
            # 12-й контрольный разряд.
            if _check_digit(digits[:11], _WEIGHTS_12) != int(digits[11]):
                continue
            spans.append(Span(
                type=self.type,
                start=match.start(),
                end=match.end(),
                value=digits,
                confidence=0.99,
            ))
        return spans