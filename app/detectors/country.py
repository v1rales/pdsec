"""Детектор стран.

Словарь стран, включая составные названия («Российская Федерация»,
«Соединённые Штаты Америки»).
"""

import re

from app.core.span import Span
from app.data.countries import _COUNTRIES
from app.detectors.base import Detector

#: Паттерн страны (длинные варианты первыми, чтобы не было частичных совпадений).
_COUNTRY_RE = re.compile(
    r"\b(?:" + "|".join(sorted(_COUNTRIES, key=len, reverse=True)) + r")\b",
    re.IGNORECASE,
)

#: ПД-контекст — признак того, что страна относится к человеку.
#: Голое название страны без такого контекста ПД не является.
_PD_MARKERS = (
    "гражданин", "гражданство", "страна", "родился", "проживает",
    "адрес", "подданство",
)
_PD_RE = re.compile(
    r"(?:" + "|".join(re.escape(m) for m in _PD_MARKERS) + r")",
    re.IGNORECASE,
)


class CountryDetector(Detector):
    """Находит названия стран."""

    type = "country"
    priority = 20

    def detect(self, text: str) -> list[Span]:
        spans: list[Span] = []
        for match in _COUNTRY_RE.finditer(text):
            # Голое название страны без ПД-контекста не является ПД.
            if not self._has_pd_context(text, match.start()):
                continue
            spans.append(Span(
                type=self.type,
                start=match.start(),
                end=match.end(),
                value=match.group(),
                confidence=0.9,
            ))
        return spans

    def _has_pd_context(self, text: str, start: int, window: int = 80) -> bool:
        """Возвращает True, если перед страной есть ПД-контекст."""
        left = max(0, start - window)
        return _PD_RE.search(text[left:start]) is not None