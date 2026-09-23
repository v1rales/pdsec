"""Маскирование спанов в тексте.

Маска собирается из кусков за один проход по спанам (слева направо),
без пересоздания строки на каждую замену. Это O(n + m) вместо O(n × m):
пересоздание строки на каждую замену даёт квадратичную сложность на
больших текстах с множеством ПД.
"""

from app.core.span import Span
from app.masking.formats import mask_span


def apply_masks(text: str, spans: list[Span], mask_style: str = "partial") -> str:
    """Заменяет спаны на маски, собирая результат из кусков.

    Спаны должны быть непересекающимися (после резолвера). Сборка идёт
    слева направо по исходным позициям — смещения не едут, т.к. исходная
    строка не модифицируется, а новая собирается из кусков.

    mask_style передаётся в mask_span (partial | full | tokenize).
    """
    parts: list[str] = []
    last = 0
    for span in sorted(spans, key=lambda s: s.start):
        parts.append(text[last : span.start])
        parts.append(mask_span(span.value, span.type, mask_style))
        last = span.end
    parts.append(text[last:])
    return "".join(parts)