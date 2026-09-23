"""Безопасное логирование: значения ПД не попадают в логи.

В логгер уходит только безопасное представление спана: тип, позиция, длина.
"""

import logging
import os
from logging.handlers import RotatingFileHandler

#: Путь к файлу лога относительно корня проекта.
_LOG_FILE = os.path.join(os.path.dirname(__file__), "..", "..", "logs", "app.log")
#: Максимальный размер одного файла лога до ротации (10 МБ).
_LOG_MAX_BYTES = 10 * 1024 * 1024
#: Количество хранимых ротированных файлов лога.
_LOG_BACKUP_COUNT = 5


def safe_span(type_: str, start: int, end: int) -> str:
    """Безопасное представление спана без значения."""
    return f"{type_}[{start}:{end}]"


def configure_logging(level: int = logging.INFO) -> None:
    """Настраивает корневой логгер.

    Логи пишутся в stderr (как при запуске через uvicorn) и в файл
    logs/app.log с ротацией по размеру (RotatingFileHandler), чтобы
    ограничить рост логов при высокой нагрузке.
    """
    log_format = "%(asctime)s %(levelname)s %(name)s %(message)s"
    formatter = logging.Formatter(log_format)

    root = logging.getLogger()
    root.setLevel(level)

    # stderr-хендлер (uvicorn пишет логи в stderr).
    stderr_handler = logging.StreamHandler()
    stderr_handler.setFormatter(formatter)
    root.addHandler(stderr_handler)

    # Файловый хендлер с ротацией по размеру.
    log_dir = os.path.dirname(_LOG_FILE)
    os.makedirs(log_dir, exist_ok=True)
    file_handler = RotatingFileHandler(
        _LOG_FILE,
        maxBytes=_LOG_MAX_BYTES,
        backupCount=_LOG_BACKUP_COUNT,
        encoding="utf-8",
    )
    file_handler.setFormatter(formatter)
    root.addHandler(file_handler)