"""Служебные эндпоинты: /health, /ready, /metrics, /stats."""

from fastapi import APIRouter, Request

from app.observability.metrics import metrics

router = APIRouter()


@router.get("/health")
async def health() -> dict:
    """Живость процесса."""
    return {"status": "ok"}


@router.get("/ready")
async def ready(request: Request) -> dict:
    """Готовность принимать трафик."""
    vault = request.app.state.vault
    return {"status": "ready", "vault": vault.stats()}


@router.get("/metrics")
async def metrics_endpoint() -> dict:
    """Метрики Latency, RPS, TPS."""
    return metrics.snapshot()


@router.get("/stats")
async def stats(request: Request) -> dict:
    """Статистика vault и метрик."""
    vault = request.app.state.vault
    return {"vault": vault.stats(), "metrics": metrics.snapshot()}