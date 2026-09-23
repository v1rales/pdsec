"""Детектор органа выдачи паспорта.

Якорное слово «выдан»/«выдано»/«выдана» обязательно. За якорем захватывается
следующий фрагмент — наименование органа выдачи. Хвостовая пунктуация
(точка, запятая) в спан не входит.
"""

import re

from app.core.span import Span
from app.detectors.base import Detector

#: Якорное слово + следующий фрагмент (до 12 слов).
_ISSUER = re.compile(
    r"(?:выдан|выдано|выдана)"
    r"(?:\s+[А-ЯЁA-Zа-яёa-z0-9.-]+){1,12}",
    re.IGNORECASE,
)

#: Хвостовая пунктуация, которую нужно отрезать от конца спана.
_TRAILING = re.compile(r"[.,;:!?]+$")

#: Ключевые слова органа выдачи: без них «выдан …» — не наименование органа
#: (например, «выдан в 2020 году»).
_AUTHORITY = re.compile(
    r"ОВД|УФМС|отдел|отделение|город|район|край|область|управление",
    re.IGNORECASE,
)


class IssuerDetector(Detector):
    """Находит орган выдачи паспорта."""

    type = "issuer"
    priority = 25

    def detect(self, text: str) -> list[Span]:
        spans: list[Span] = []
        for match in _ISSUER.finditer(text):
            end = match.end()
            # Отрезаем хвостовую пунктуацию, чтобы границы совпадали с эталоном.
            trimmed = _TRAILING.search(text, match.start(), end)
            if trimmed:
                end = trimmed.start()
            # Без ключевого слова органа выдачи спан не является issuer.
            if not _AUTHORITY.search(text[match.start():end]):
                continue
            spans.append(Span(
                type=self.type,
                start=match.start(),
                end=end,
                value=text[match.start():end],
                confidence=0.85,
            ))
        return spans