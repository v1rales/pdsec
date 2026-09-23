"""Резолвер пересечений спанов.

Выбирает непересекающиеся спаны по приоритету: тип → длина → уверенность.
Типам с контрольной суммой приоритет выше.
"""

from app.core.span import Span
from app.detectors.base import Detector


class _Fallback:
    """Заглушка для типа без зарегистрированного детектора."""
    has_checksum = False
    priority = 0


def _span_key(span: Span, detector: Detector) -> tuple:
    """Ключ приоритета спана: контрольная сумма, тип, длина, уверенность."""
    checksum = 1 if detector.has_checksum else 0
    return (checksum, detector.priority, span.end - span.start, span.confidence)


def resolve(spans: list[Span], detectors: list[Detector]) -> list[Span]:
    """Возвращает непересекающиеся спаны, разрешая конфликты.

    Спаны сортируются по start (и по приоритету как tie-breaker), затем
    жадный выбор с проверкой только последнего выбранного: O(n log n)
    сортировка + O(n) проход. Если текущий спан не пересекается с последним
    выбранным, он не пересекается и с предыдущими (все их start ≤ последнего).
    При пересечении с последним остаётся спан с более высоким приоритетом.
    """
    # Карта тип → детектор для доступа к приоритету/контрольной сумме
    by_type = {d.type: d for d in detectors}

    # Сортировка по start (и по приоритету как tie-breaker)
    keyed = sorted(
        ((s, _span_key(s, by_type.get(s.type, _Fallback()))) for s in spans),
        key=lambda sk: (sk[0].start, sk[1]),
    )

    selected: list[Span] = []
    selected_keys: list[tuple] = []
    for span, key in keyed:
        if not selected:
            selected.append(span)
            selected_keys.append(key)
            continue
        last = selected[-1]
        if span.start < last.end and last.start < span.end:
            # Пересечение с последним выбранным — оставить более приоритетный
            if key > selected_keys[-1]:
                selected[-1] = span
                selected_keys[-1] = key
        else:
            selected.append(span)
            selected_keys.append(key)

    # Вернуть в порядке появления в тексте
    return sorted(selected, key=lambda s: s.start)