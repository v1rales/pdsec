"""Точка входа FastAPI-приложения.

Запуск: uvicorn app.main:app --workers 1
"""

from concurrent.futures import ProcessPoolExecutor, ThreadPoolExecutor

from fastapi import FastAPI

from app.api import health, process
from app.core.config import Config
from app.core.pipeline import Pipeline
from app.detectors.worker import _init as _init_detect_workers
from app.observability.logging import configure_logging
from app.vault.memory import MemoryVault

configure_logging()

app = FastAPI(title="Модуль безопасности ПД", version="1.0.0")

# Глобальные зависимости приложения
app.state.vault = MemoryVault()
app.state.config = Config()

# Пул процессов для детекции: обходит GIL, каждый процесс выполняет
# regex-детекцию на своём ядре CPU. Детекторы загружаются один раз
# через initializer. Vault остаётся в памяти главного процесса.
app.state.detect_executor = ProcessPoolExecutor(
    max_workers=4, initializer=_init_detect_workers
)
app.state.pipeline = Pipeline(
    app.state.vault, app.state.config, app.state.detect_executor
)

# Расширенный пул потоков для обработки запросов.
app.state.executor = ThreadPoolExecutor(max_workers=64)

app.include_router(process.router)
app.include_router(health.router)