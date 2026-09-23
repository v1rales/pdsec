"""Детектор городов РФ.

Словарь городов, включая топонимы из двух слов («Нижний Новгород»),
с дефисом («Ростов-на-Дону», «Санкт-Петербург») и падежные формы
(родительный/предложный) для контекста «проживает в Москве».
"""

import re

from app.core.span import Span
from app.data.cities import _CITIES
from app.detectors.base import Detector

#: Паттерн города (длинные варианты первыми, чтобы не было частичных совпадений).
_CITY_RE = re.compile(
    r"\b(?:" + "|".join(sorted(_CITIES, key=len, reverse=True)) + r")\b",
    re.IGNORECASE,
)

#: Негативный контекст — город в адресе отделения/офиса Банка не является ПД.
_NEGATIVE_MARKERS = (
    "отделение банка", "офис банка", "отделение банка по адресу",
    "адрес отделения банка", "адрес банка", "банк по адресу",
)
_NEGATIVE_RE = re.compile(
    r"(?:" + "|".join(re.escape(m) for m in _NEGATIVE_MARKERS) + r")",
    re.IGNORECASE,
)

#: ПД-контекст — признак того, что город относится к человеку.
#: Голое название города без такого контекста ПД не является.
_PD_MARKERS = (
    "город", "проживает", "адрес", "гражданин", "родился",
    "клиент", "зарегистрирован",
)
_PD_RE = re.compile(
    r"(?:" + "|".join(re.escape(m) for m in _PD_MARKERS) + r")",
    re.IGNORECASE,
)


class CityDetector(Detector):
    """Находит названия городов РФ."""

    type = "city"
    priority = 20

    def detect(self, text: str) -> list[Span]:
        spans: list[Span] = []
        for match in _CITY_RE.finditer(text):
            # Город в адресе отделения/офиса Банка не является ПД.
            if self._has_negative_context(text, match.start()):
                continue
            # Голое название города без ПД-контекста не является ПД.
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

    def _has_negative_context(self, text: str, start: int, window: int = 80) -> bool:
        """Возвращает True, если перед городом есть контекст отделения Банка."""
        left = max(0, start - window)
        return _NEGATIVE_RE.search(text[left:start]) is not None

    def _has_pd_context(self, text: str, start: int, window: int = 80) -> bool:
        """Возвращает True, если перед городом есть ПД-контекст."""
        left = max(0, start - window)
        return _PD_RE.search(text[left:start]) is not None