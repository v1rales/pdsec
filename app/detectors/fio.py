"""Детектор ФИО.

Распознаёт полные ФИО (фамилия + имя + отчество) в любом порядке и фамилию
с инициалами. Фамилии определяются морфологией суффиксов (словаря фамилий
нет), имена и отчества — из закрытого словаря. Негативный контекст
(поэт, писатель, памятник, музей, композитор, художник) подавляет
срабатывание на короткой форме «имя + фамилия».
"""

import re

from app.core.span import Span
from app.data.names import _KNOWN_PERSONALITIES, _NAMES
from app.detectors.base import Detector

#: Суффиксы фамилий (мужские и женские).
_SURNAME_SUFFIXES = (
    "ов", "ев", "ин", "ын", "ский", "цкий", "ской", "цкой",
    "ова", "ева", "ина", "ына", "ская", "цкая",
)
#: Слово, оканчивающееся на суффикс фамилии.
_SURNAME = r"[А-ЯЁ][а-яё]*(?:" + "|".join(_SURNAME_SUFFIXES) + r")"

#: Латинские суффиксы фамилий (имя держателя карты).
_LATIN_SURNAME_SUFFIXES = (
    "ov", "ev", "in", "yn", "sky", "ski", "enko", "ova", "eva", "ina",
)
_LATIN_SURNAME = r"[A-Z][a-z]*(?:" + "|".join(_LATIN_SURNAME_SUFFIXES) + r")"

#: Словарь латинских имён (закрытое множество).
_LATIN_NAMES = (
    "Ivan", "Alex", "Alexander", "Andrey", "Anna", "Boris", "Dmitry",
    "Elena", "Igor", "Ilya", "Irina", "Kirill", "Maxim", "Mikhail",
    "Nikolay", "Oleg", "Olga", "Pavel", "Peter", "Sergey", "Vladimir",
    "Viktor", "Yuri", "Maria", "Natalia", "Svetlana", "Tatiana",
)
_LATIN_NAME = "|".join(sorted(_LATIN_NAMES, key=len, reverse=True))

#: Слово с заглавной буквы (имя в полном ФИО — морфологическая эвристика).
#: В полном ФИО имя стоит между фамилией и отчеством; отчество — сильный
#: якорь, поэтому имя может быть любым словом с заглавной.
_NAME_FULL = r"[А-ЯЁ][а-яё]+"

#: Словарь имён (закрытое множество) для коротких форм «имя + фамилия»,
#: где нет отчества-якоря — широкий паттерн дал бы ложные срабатывания.
_NAME_SHORT = "|".join(sorted(_NAMES, key=len, reverse=True))

#: Окончания отчеств (морфологическая эвристика вместо закрытого словаря).
_PATRONYMIC_SUFFIXES = (
    "ович", "евич", "овна", "евна", "ична", "инична",
)
_PATRONYMIC = r"[А-ЯЁ][а-яё]*(?:" + "|".join(_PATRONYMIC_SUFFIXES) + r")"

#: Инициал (заглавная буква с точкой).
_INITIAL = r"[А-ЯЁ]\."

#: Полное ФИО: фамилия + имя + отчество (имя — широкий паттерн, отчество — якорь).
#: IGNORECASE сохранён для регистронезависимости. Известное ограничение:
#: строчный прогон без границы слова перед ФИО ('а'*100 + 'Иванов') может
#: матчиться как фамилия (редкий краевой случай, компромисс с регистронезависимостью).
_FULL_SURNAME_FIRST = re.compile(
    rf"\b({_SURNAME})\s+({_NAME_FULL})\s+({_PATRONYMIC})\b",
    re.IGNORECASE,
)
#: Полное ФИО: имя + отчество + фамилия.
_FULL_NAME_FIRST = re.compile(
    rf"\b({_NAME_FULL})\s+({_PATRONYMIC})\s+({_SURNAME})\b",
    re.IGNORECASE,
)
#: Фамилия + инициалы.
_INITIALS = re.compile(
    rf"\b({_SURNAME})\s+({_INITIAL})\s*({_INITIAL})(?![А-ЯЁA-Zа-яёa-z])",
    re.IGNORECASE,
)
#: Короткая форма: имя + фамилия (закрытый словарь имён, подавляется негативным контекстом).
_NAME_SURNAME = re.compile(
    rf"\b({_NAME_SHORT})\s+({_SURNAME})\b",
    re.IGNORECASE,
)
#: Короткая форма: фамилия + имя (без отчества, подавляется негативным контекстом).
_SURNAME_NAME = re.compile(
    rf"\b({_SURNAME})\s+({_NAME_SHORT})\b",
    re.IGNORECASE,
)

#: Латинское имя + латинская фамилия (имя держателя карты).
_LATIN_NAME_SURNAME = re.compile(
    rf"\b({_LATIN_NAME})\s+({_LATIN_SURNAME})\b",
    re.IGNORECASE,
)
#: Латинская фамилия + латинское имя.
_LATIN_SURNAME_NAME = re.compile(
    rf"\b({_LATIN_SURNAME})\s+({_LATIN_NAME})\b",
    re.IGNORECASE,
)

#: Негативный контекст — признак знаменитости, подавляет срабатывание.
_NEGATIVE_MARKERS = (
    "поэт", "писатель", "памятник", "музей", "композитор", "художник",
)
_NEGATIVE_RE = re.compile(
    r"(?:" + "|".join(re.escape(m) for m in _NEGATIVE_MARKERS) + r")",
    re.IGNORECASE,
)

#: Известные личности (фамилии), чьи полные ФИО не являются ПД и не
#: маскируются даже без негативного маркера рядом. Включены только
#: фамилии, однозначно ассоциируемые со знаменитостями; распространённые
#: фамилии (например, «Павлов», «Крылов»), которые могут принадлежать
#: обычным людям, сюда не входят.
_KNOWN_PERSONALITIES_RE = re.compile(
    r"(?:" + "|".join(re.escape(p) for p in _KNOWN_PERSONALITIES) + r")",
    re.IGNORECASE,
)

#: ПД-контекст — признак того, что короткое ФИО относится к человеку.
#: Короткая форма «имя + фамилия» маскируется только при таком контексте,
#: иначе голое имя знаменитости (например, «Александр Пушкин») не является ПД.
_PD_MARKERS = (
    "клиент", "гражданин", "паспорт", "заявитель", "владелец",
    "держатель", "проживает", "родился", "подписант",
)
_PD_RE = re.compile(
    r"(?:" + "|".join(re.escape(m) for m in _PD_MARKERS) + r")",
    re.IGNORECASE,
)


class FioDetector(Detector):
    """Находит ФИО в тексте."""

    type = "fio"
    priority = 30

    def detect(self, text: str) -> list[Span]:
        spans: list[Span] = []
        # Полное ФИО подавляется негативным контекстом (знаменитость)
        # или если фамилия входит в список известных личностей.
        for pattern in (_FULL_SURNAME_FIRST, _FULL_NAME_FIRST):
            for match in pattern.finditer(text):
                if self._has_negative_context(text, match.start(), match.end()):
                    continue
                if self._is_known_personality(match, pattern):
                    continue
                span = self._span(match)
                if span is not None:
                    spans.append(span)
        for pattern in (_INITIALS, _LATIN_NAME_SURNAME, _LATIN_SURNAME_NAME):
            for match in pattern.finditer(text):
                span = self._span(match)
                if span is not None:
                    spans.append(span)
        for match in _NAME_SURNAME.finditer(text):
            if self._has_negative_context(text, match.start(), match.end()):
                continue
            if not self._has_pd_context(text, match.start(), match.end()):
                continue
            span = self._span(match)
            if span is not None:
                spans.append(span)
        for match in _SURNAME_NAME.finditer(text):
            if self._has_negative_context(text, match.start(), match.end()):
                continue
            if not self._has_pd_context(text, match.start(), match.end()):
                continue
            span = self._span(match)
            if span is not None:
                spans.append(span)
        return spans

    def _span(self, match: re.Match) -> Span:
        value = match.group()
        # Защита от катастрофического совпадения: под re.IGNORECASE строчный
        # прогон ('а'*100 + 'Иванов') матчится как одна «фамилия» — длинный спан
        # со строчной первой буквой. Реальные ФИО короткие и с заглавной.
        # Отбрасываем длинные спаны (>30 символов), начинающиеся со строчной.
        if len(value) > 30 and value[0].islower():
            return None  # type: ignore[return-value]
        return Span(
            type=self.type,
            start=match.start(),
            end=match.end(),
            value=value,
            confidence=0.9,
        )

    def _has_negative_context(self, text: str, start: int, end: int,
                              window: int = 60) -> bool:
        """Возвращает True, если рядом с фрагментом есть негативный контекст."""
        left = max(0, start - window)
        right = min(len(text), end + window)
        return _NEGATIVE_RE.search(text[left:right]) is not None

    def _is_known_personality(self, match: re.Match, pattern: re.Pattern) -> bool:
        """Возвращает True, если фамилия в ФИО — известная личность.

        Фамилия — первая группа в форме «фамилия + имя + отчество»
        (_FULL_SURNAME_FIRST) и третья в форме «имя + отчество + фамилия»
        (_FULL_NAME_FIRST). Сравнение регистронезависимое (флаг re.IGNORECASE).
        """
        surname_group = 1 if pattern is _FULL_SURNAME_FIRST else 3
        surname = match.group(surname_group)
        return _KNOWN_PERSONALITIES_RE.fullmatch(surname) is not None

    def _has_pd_context(self, text: str, start: int, end: int,
                        window: int = 60) -> bool:
        """Возвращает True, если рядом с фрагментом есть ПД-контекст."""
        left = max(0, start - window)
        right = min(len(text), end + window)
        return _PD_RE.search(text[left:right]) is not None