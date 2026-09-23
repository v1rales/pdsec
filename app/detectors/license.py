"""Детектор водительского удостоверения.

10 цифр, только при наличии якорного слова (водительск). Также
распознаётся разделённый формат «серия XXXX номер XXXXXX» (4 + 6 цифр).
"""

import re

from app.core.span import Span
from app.detectors.base import Detector

#: 10 цифр подряд (без разделителей).
_NUMBER = re.compile(r"(?<!\d)\d{10}(?!\d)")
#: Разделённый формат: серия (4 цифры) + номер (6 цифр) с разделителем
#: (пробел или дефис). Требует якорного слова рядом.
_SEPARATED = re.compile(r"(?<!\d)\d{4}[ -]\d{6}(?!\d)")
#: Формат «серия XXXX номер XXXXXX» (слова-разделители). Якорь не нужен:
#: паспорт с валидным кодом региона перехватывает детектор паспорта.
_SERIES_NUMBER = re.compile(
    r"(?<!\d)\d{4}\s+(?:номер|№)\s+\d{6}(?!\d)",
    re.IGNORECASE,
)
#: Якорные слова: водительск, ВУ, в/у, удостоверение водителя, права.
_ANCHOR = re.compile(
    r"водительск|водителя|\bВУ\b|\bв/у\b|\bправа\b",
    re.IGNORECASE,
)
#: Размер окна поиска якоря вокруг номера (в обе стороны).
_WINDOW = 40


class LicenseDetector(Detector):
    """Находит номер водительского удостоверения рядом с якорем."""

    type = "license"
    priority = 30

    def detect(self, text: str) -> list[Span]:
        spans: list[Span] = []

        # Формат «серия XXXX номер XXXXXX» — якорь не требуется.
        for match in _SERIES_NUMBER.finditer(text):
            spans.append(Span(
                type=self.type,
                start=match.start(),
                end=match.end(),
                value=match.group(),
                confidence=0.9,
            ))

        # Остальные форматы требуют якорного слова в окне вокруг номера.
        for pattern in (_NUMBER, _SEPARATED):
            for match in pattern.finditer(text):
                window = text[
                    max(0, match.start() - _WINDOW):match.end() + _WINDOW
                ]
                if _ANCHOR.search(window):
                    spans.append(Span(
                        type=self.type,
                        start=match.start(),
                        end=match.end(),
                        value=match.group(),
                        confidence=0.9,
                    ))
        return spans