"""Конфигурация систем-потребителей.

Загружает config/systems.yaml. /process не авторизует: при отсутствии
заголовка X-System-Id применяется default_system.
"""

import os
from dataclasses import dataclass, field

import yaml

_CONFIG_PATH = os.path.join(
    os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))),
    "config",
    "systems.yaml",
)


@dataclass
class SystemConfig:
    """Настройки одной системы-потребителя."""
    id: str
    enabled: bool = True
    mask_types: list[str] = field(default_factory=lambda: ["all"])
    unmask_enabled: bool = True
    mask_style: str = "partial"
    multi_type_rule: bool = False


class Config:
    """Загружает и хранит настройки систем."""

    def __init__(self, path: str = _CONFIG_PATH) -> None:
        with open(path, encoding="utf-8") as f:
            data = yaml.safe_load(f)
        self._default_id = data.get("default_system", "default")
        self._systems: dict[str, SystemConfig] = {}
        for item in data.get("systems", []):
            self._systems[item["id"]] = SystemConfig(**item)
        # Allowlist разрешённых систем. default_system всегда разрешена.
        self._allowed_systems: set[str] = set(data.get("allowed_systems", []))
        self._allowed_systems.add(self._default_id)

    def is_allowed(self, system_id: str | None) -> bool:
        """Проверяет, разрешена ли система в allowlist.

        Отсутствие заголовка X-System-Id (None) трактуется как default_system,
        которая всегда разрешена.
        """
        if system_id is None:
            return True
        return system_id in self._allowed_systems

    def get_system(self, system_id: str | None) -> SystemConfig:
        """Возвращает настройки системы; при отсутствии id — default_system."""
        if system_id is None or system_id not in self._systems:
            return self._systems[self._default_id]
        return self._systems[system_id]