"""Детектор адреса.

Один составной спан от первого до последнего компонента адреса:
страна, индекс (6 цифр), город, улица, дом, квартира. Маркеры:
«г.», «ул.», «д.», «кв.», «индекс». Пример: «г. Москва, ул. Тверская,
д. 1, кв. 5» — один спан. Город в начале адреса распознаётся и без
маркера «г.», если за ним следует ул./д./кв. («Москва, ул. Тверская,
д. 1»).
"""

import re

from app.core.span import Span
from app.detectors.base import Detector
from app.detectors.country import _COUNTRIES

#: Названия стран как компонент адреса.
_COUNTRY = "|".join(sorted(_COUNTRIES, key=len, reverse=True))

#: Отдельный компонент адреса.
_COMPONENT = re.compile(
    r"(?:"
    r"индекс[:\s]*\d{6}"
    r"|г\.\s*[А-ЯЁ][а-яё-]+(?:\s+[А-ЯЁ][а-яё-]+)*"
    r"|ул\.\s*[А-ЯЁ][а-яё-]+(?:\s+[А-ЯЁ][а-яё-]+)*"
    r"|д\.\s*\d+"
    r"|кв\.\s*\d+"
    r"|\b(?:" + _COUNTRY + r")\b"
    r"|[А-ЯЁ][а-яё-]+"
    r")",
    re.IGNORECASE,
)

#: Разделители между компонентами адреса (пробелы, запятые, точки с запятой).
_SEPARATOR = re.compile(r"[\s,;]+")

#: Структурные маркеры адреса: без них одиночный компонент (например, страна)
#: адресом не является.
_MARKER = re.compile(r"г\.|ул\.|д\.|кв\.|индекс", re.IGNORECASE)

#: Компонент, начинающийся со структурного маркера (не голое слово).
_MARKER_PREFIX = re.compile(r"^(?:индекс|г\.|ул\.|д\.|кв\.)", re.IGNORECASE)

#: Негативный контекст — адрес отделения/офиса Банка не является ПД.
_NEGATIVE_MARKERS = (
    "отделение банка", "офис банка", "отделение банка по адресу",
    "адрес отделения банка", "адрес банка", "банк по адресу",
)
_NEGATIVE_RE = re.compile(
    r"(?:" + "|".join(re.escape(m) for m in _NEGATIVE_MARKERS) + r")",
    re.IGNORECASE,
)


class AddressDetector(Detector):
    """Находит адрес как один составной спан."""

    type = "address"
    priority = 25

    def detect(self, text: str) -> list[Span]:
        spans: list[Span] = []
        # Голое слово (город/страна) — только если начинается с заглавной буквы.
        # Служебные слова в нижнем регистре («выдан», «по») компонентом не являются.
        matches = [
            m for m in _COMPONENT.finditer(text)
            if _MARKER_PREFIX.match(m.group()) or m.group()[0].isupper()
        ]
        i = 0
        while i < len(matches):
            start = matches[i].start()
            end = matches[i].end()
            j = i + 1
            # Сливаем соседние компоненты, разделённые только разделителями.
            while j < len(matches):
                gap = text[end:matches[j].start()]
                if _SEPARATOR.fullmatch(gap):
                    end = matches[j].end()
                    j += 1
                else:
                    break
            # Адрес — только если есть структурный маркер (г./ул./д./кв./индекс).
            # Одиночная страна или город адресом не являются.
            if _MARKER.search(text[start:end]):
                # Негативный контекст: адрес отделения/офиса Банка не ПД.
                if self._has_negative_context(text, start):
                    i = j
                    continue
                spans.append(Span(
                    type=self.type,
                    start=start,
                    end=end,
                    value=text[start:end],
                    confidence=0.9,
                ))
            i = j
        return spans

    def _has_negative_context(self, text: str, start: int, window: int = 80) -> bool:
        """Возвращает True, если перед адресом есть контекст отделения Банка."""
        left = max(0, start - window)
        return _NEGATIVE_RE.search(text[left:start]) is not None