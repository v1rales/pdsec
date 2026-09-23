"""Сканирование каталога детекторов при старте.

Импортирует все модули app/detectors/*.py, что регистрирует детекторы
через __init_subclass__ в Detector._registry.
"""

import importlib
import pkgutil

from app.detectors.base import Detector, all_detectors

__all__ = ["Detector", "all_detectors"]


def _load_all() -> None:
    """Импортирует все модули пакета detectors."""
    for module_info in pkgutil.iter_modules(__path__):
        if module_info.name != "base":
            importlib.import_module(f"{__name__}.{module_info.name}")


_load_all()