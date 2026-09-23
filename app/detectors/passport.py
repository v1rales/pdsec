"""Детектор серии и номера паспорта РФ.

Формат: серия (4 цифры, первые две — код региона) + номер (6 цифр),
итого 10 цифр. Контрольная сумма — валидность кода региона серии.
"""

import re

from app.core.span import Span
from app.data.regions import _VALID_REGIONS
from app.detectors.base import Detector

#: Серия (4 цифры) + номер (6 цифр). Между группами обязателен разделитель
#: (пробел или слово «номер»/«№»), чтобы голый 10-значный номер в/у
#: (без разделителя) паспортом не считался.
_PATTERN = re.compile(
    r"(?<!\d)\d{4}(?:[ ](?:номер|№)?[ ]?|(?:номер|№)[ ]?)\d{6}(?!\d)",
    re.IGNORECASE,
)


class PassportDetector(Detector):
    """Находит серию и номер паспорта РФ."""

    type = "passport"
    priority = 40
    has_checksum = True

    def detect(self, text: str) -> list[Span]:
        spans: list[Span] = []
        for match in _PATTERN.finditer(text):
            digits = re.sub(r"\D", "", match.group())
            region = int(digits[:2])
            if region not in _VALID_REGIONS:
                continue
            spans.append(Span(
                type=self.type,
                start=match.start(),
                end=match.end(),
                value=match.group(),
                confidence=0.99,
            ))
        return spans