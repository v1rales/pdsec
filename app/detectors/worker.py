"""Детекция в отдельном процессе (для ProcessPoolExecutor).

Детекторы загружаются один раз при инициализации процесса (initializer),
затем detect() вызывается для каждого текста. Это обходит GIL: каждый
процесс выполняет regex-детекцию на своём ядре CPU.
"""

import logging

from app.core.span import Span
from app.detectors import all_detectors

logger = logging.getLogger(__name__)

_detectors = None


def _init() -> None:
    """Загружает детекторы в дочернем процессе (вызывается один раз)."""
    global _detectors
    _detectors = all_detectors()


def detect(text: str) -> list[Span]:
    """Вызывает все детекторы в текущем процессе, каждый в try-except."""
    spans: list[Span] = []
    for detector in _detectors:
        try:
            spans.extend(detector.detect(text))
        except Exception:  # noqa: BLE001 — падение одного не роняет запрос
            logger.exception("Детектор %s упал", detector.type)
    return spans