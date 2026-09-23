"""Базовый класс детектора и саморегистрация.

Новый тип ПД = один новый файл в app/detectors/, наследующий Detector
и регистрирующийся через __init_subclass__. Каталог сканируется при старте.
"""

from abc import ABC, abstractmethod

from app.core.span import Span


class Detector(ABC):
    """Интерфейс детектора персональных данных."""

    #: тип ПД, например "passport"
    type: str = ""
    #: приоритет при разрешении пересечений (выше — важнее)
    priority: int = 0
    #: есть ли контрольная сумма (повышает приоритет)
    has_checksum: bool = False

    #: реестр всех детекторов (заполняется при импорте)
    _registry: list["Detector"] = []

    def __init_subclass__(cls, **kwargs):
        super().__init_subclass__(**kwargs)
        if cls.type:
            cls._registry.append(cls())

    @abstractmethod
    def detect(self, text: str) -> list[Span]:
        """Возвращает найденные спаны ПД в тексте."""
        raise NotImplementedError


def all_detectors() -> list[Detector]:
    """Возвращает все зарегистрированные детекторы."""
    return list(Detector._registry)