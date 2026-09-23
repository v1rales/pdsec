"""Тесты контракта POST /process и служебных эндпоинтов."""

from fastapi.testclient import TestClient

from app.main import app

client = TestClient(app)


def test_mask_new_id():
    """Новый id → маскирование (заглушка: mask == original)."""
    resp = client.post("/process", json={"payload": "текст", "payload_id": "id-1"})
    assert resp.status_code == 200
    assert resp.json() == {"result": "текст"}


def test_retry_same_id_same_text():
    """Ретрай: тот же id и тот же текст → та же маска."""
    body = {"payload": "текст", "payload_id": "id-2"}
    first = client.post("/process", json=body).json()["result"]
    second = client.post("/process", json=body).json()["result"]
    assert first == second


def test_unmask_with_mask():
    """Обратный шаг: тот же id и маска → original."""
    payload = "текст"
    pid = "id-3"
    mask = client.post("/process", json={"payload": payload, "payload_id": pid}).json()["result"]
    resp = client.post("/process", json={"payload": mask, "payload_id": pid})
    assert resp.status_code == 200
    assert resp.json() == {"result": payload}


def test_unknown_id_is_200():
    """Неизвестный id → 200, обрабатывается как новый текст, не 404."""
    resp = client.post("/process", json={"payload": "новый", "payload_id": "never-seen"})
    assert resp.status_code == 200


def test_invalid_json_is_422():
    """Невалидный JSON → 422 от pydantic, не 500."""
    resp = client.post("/process", json={"payload": "x"})  # нет payload_id
    assert resp.status_code == 422


def test_health():
    """Служебный эндпоинт /health."""
    resp = client.get("/health")
    assert resp.status_code == 200
    assert resp.json() == {"status": "ok"}


def test_ready():
    """Служебный эндпоинт /ready."""
    resp = client.get("/ready")
    assert resp.status_code == 200
    assert resp.json()["status"] == "ready"


def test_metrics():
    """Служебный эндпоинт /metrics."""
    resp = client.get("/metrics")
    assert resp.status_code == 200
    assert "requests_total" in resp.json()


def test_stats():
    """Служебный эндпоинт /stats."""
    resp = client.get("/stats")
    assert resp.status_code == 200
    assert "vault" in resp.json()
    assert "metrics" in resp.json()