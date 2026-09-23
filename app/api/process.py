"""Эндпоинт POST /process — маскирование/демаскирование по контракту.

Правила (AGENTS.md):
- никогда не отдаёт 4XX/5XX, кроме 422 от pydantic и 429 с Retry-After;
- любое исключение → исходный payload с кодом 200;
- не авторизует;
- неизвестный payload_id → 200, обрабатывается как новый текст.
"""

import asyncio
import logging
import time

from fastapi import APIRouter, Request
from pydantic import BaseModel, Field

from app.core.pipeline import Pipeline
from app.observability.metrics import metrics

logger = logging.getLogger(__name__)

router = APIRouter()


class ProcessRequest(BaseModel):
    payload: str = Field(..., description="Исходный текст или маска")
    payload_id: str = Field(..., description="Ключ корреляции маскирование→демаскирование")


class ProcessResponse(BaseModel):
    result: str


def _make_pipeline(request: Request) -> Pipeline:
    """Достаёт pipeline из состояния приложения."""
    return request.app.state.pipeline


@router.post("/process", response_model=ProcessResponse)
async def process(request: Request, body: ProcessRequest) -> ProcessResponse:
    pipeline = _make_pipeline(request)
    executor = request.app.state.executor
    # Заголовок X-System-Id опционален: при отсутствии применяется default_system.
    # /process не авторизует (нет 403) — заголовок лишь выбирает политику системы.
    system_id = request.headers.get("X-System-Id")
    # perf_counter — высокое разрешение (наносекунды), в отличие от
    # time.monotonic (шаг ~15.6 мс на Windows), который даёт неточную latency.
    start = time.perf_counter()
    try:
        # Детекция — CPU-bound (regex). Выносим в расширенный пул потоков,
        # чтобы не блокировать event loop и обрабатывать больше конкурентных
        # запросов. GIL ограничивает CPU-масштабирование, но пул помогает
        # при I/O-ожиданиях и переключении контекста.
        loop = asyncio.get_running_loop()
        result = await loop.run_in_executor(
            executor, pipeline.process, body.payload, body.payload_id, system_id
        )
    except Exception:  # noqa: BLE001 — любое исключение не должно ронять запрос
        logger.exception("Ошибка обработки запроса, возвращаю исходный payload")
        result = body.payload
    metrics.observe(time.perf_counter() - start, len(body.payload))
    return ProcessResponse(result=result)