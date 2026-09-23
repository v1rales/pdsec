"""Детектор даты рождения.

Форматы: мм.дд.гггг, гггг.дд.мм, а также текстом (например, «12 мая 1990»).
"""

import re

from app.core.span import Span
from app.detectors.base import Detector

#: Разделители даты: точка, слэш, дефис.
_SEP = r"[./-]"
#: Год: 2 или 4 цифры.
_YEAR = r"\d{2,4}"

#: мм.дд.гггг или дд.мм.гггг (две группы по 2 цифры + год).
#: Первая группа не должна быть частью 4-значного года (иначе «1990-03-15»
#: ошибочно разбивается на «19-90-03»).
_MDY = re.compile(
    rf"(?<!\d)(\d{{2}})(?!\d){_SEP}(\d{{2}})(?!\d){_SEP}({_YEAR})(?!\d)"
)
#: гггг.дд.мм или гггг.мм.дд (год + две группы по 2 цифры).
_YDM = re.compile(
    rf"(?<!\d)(\d{{4}}){_SEP}(\d{{2}})(?!\d){_SEP}(\d{{2}})(?!\d)"
)
#: Русские названия месяцев в родительном падеже.
_MONTHS = (
    "января", "февраля", "марта", "апреля", "мая", "июня",
    "июля", "августа", "сентября", "октября", "ноября", "декабря",
)
_MONTH_RE = "|".join(_MONTHS)
#: число + месяц + год текстом.
_TEXT = re.compile(
    rf"(?<!\d)(\d{{1,2}})[ ]?(?:{_MONTH_RE})[ ]?(\d{{4}})(?!\d)",
    re.IGNORECASE,
)

#: Словесные порядковые числа (родительный падеж) для дат текстом.
_ORDINALS = {
    "первого": 1, "второго": 2, "третьего": 3, "четвёртого": 4,
    "пятого": 5, "шестого": 6, "седьмого": 7, "восьмого": 8,
    "девятого": 9, "десятого": 10, "одиннадцатого": 11, "двенадцатого": 12,
    "тринадцатого": 13, "четырнадцатого": 14, "пятнадцатого": 15,
    "шестнадцатого": 16, "семнадцатого": 17, "восемнадцатого": 18,
    "девятнадцатого": 19, "двадцатого": 20, "двадцать первого": 21,
    "двадцать второго": 22, "двадцать третьего": 23, "двадцать четвёртого": 24,
    "двадцать пятого": 25, "двадцать шестого": 26, "двадцать седьмого": 27,
    "двадцать восьмого": 28, "двадцать девятого": 29, "тридцатого": 30,
    "тридцать первого": 31,
}
_ORDINAL_RE = "|".join(sorted(_ORDINALS, key=len, reverse=True))
#: словесное число + месяц + год текстом.
_TEXT_WORD = re.compile(
    rf"(?<!\w)(?:{_ORDINAL_RE})[ ]?(?:{_MONTH_RE})[ ]?(\d{{4}})(?!\d)",
    re.IGNORECASE,
)


def _days_in_month(month: int, year: int) -> int:
    """Число дней в месяце с учётом високосного года."""
    if month == 2:
        if year % 4 == 0 and (year % 100 != 0 or year % 400 == 0):
            return 29
        return 28
    if month in (4, 6, 9, 11):
        return 30
    return 31


def _valid(day: int, month: int, year: int) -> bool:
    """Проверяет правдоподобность даты."""
    # Двузначный год трактуем как 19xx (дата рождения).
    if year < 100:
        year += 1900
    if not (1 <= month <= 12):
        return False
    if not (1 <= day <= _days_in_month(month, year)):
        return False
    if not (1900 <= year <= 2100):
        return False
    return True


def _valid_mdy(a: int, b: int, year: int) -> bool:
    """Принимает дату, если a.b — месяц.день ИЛИ день.месяц."""
    return _valid(b, a, year) or _valid(a, b, year)


class DateDetector(Detector):
    """Находит даты рождения."""

    type = "date"
    priority = 20

    def detect(self, text: str) -> list[Span]:
        spans: list[Span] = []
        for match in _MDY.finditer(text):
            a, b, year = (int(g) for g in match.groups())
            if _valid_mdy(a, b, year):
                spans.append(self._span(match))
        for match in _YDM.finditer(text):
            year, a, b = (int(g) for g in match.groups())
            if _valid_mdy(a, b, year):
                spans.append(self._span(match))
        for match in _TEXT.finditer(text):
            day, year = (int(g) for g in match.groups())
            if _valid(day, 1, year):
                spans.append(self._span(match))
        for match in _TEXT_WORD.finditer(text):
            year = int(match.group(1))
            if _valid(1, 1, year):
                spans.append(self._span(match))
        return spans

    def _span(self, match: re.Match) -> Span:
        return Span(
            type=self.type,
            start=match.start(),
            end=match.end(),
            value=match.group(),
            confidence=0.9,
        )