# Инструкция для жюри по проверке

## Запуск сервиса

```bash
pip install -r requirements.txt
uvicorn app.main:app --host 0.0.0.0 --port 8000 --workers 1
```

Или через Docker: `docker build -t pdmask . && docker run -p 8000:8000 pdmask`.

Сервис доступен на `http://127.0.0.1:8000`.

## Как отправить тестовый текст

Эндпоинт `POST /process` принимает `{payload, payload_id}` и возвращает `{"result": "..."}`.

### Маскирование (прямой шаг)

```bash
curl -X POST http://127.0.0.1:8000/process \
  -H "Content-Type: application/json" \
  -d '{"payload":"Клиент Иванов Иван Иванович, паспорт 4509 123456, тел +7 900 123-45-67","payload_id":"demo-1"}'
```

Ответ: `{"result": "Клиент ****** **** ********, паспорт **** ******, тел +* *** ***-**-**"}`.

### Демаскирование (обратный шаг)

Тот же `payload_id`, `payload` = ранее полученная маска:

```bash
curl -X POST http://127.0.0.1:8000/process \
  -H "Content-Type: application/json" \
  -d '{"payload":"Клиент ****** **** ********, паспорт **** ******, тел +* *** ***-**-**","payload_id":"demo-1"}'
```

Ответ: `{"result": "Клиент Иванов Иван Иванович, паспорт 4509 123456, тел +7 900 123-45-67"}`.

### Ретрай (идемпотентность)

Тот же `payload_id` и тот же исходный текст → возвращается та же маска.

## Ловушки (не должны маскироваться)

```bash
curl -X POST http://127.0.0.1:8000/process \
  -H "Content-Type: application/json" \
  -d '{"payload":"поэт Александр Пушкин","payload_id":"demo-2"}'
```

Ответ: `{"result": "поэт Александр Пушкин"}` (не маскируется).

```bash
curl -X POST http://127.0.0.1:8000/process \
  -H "Content-Type: application/json" \
  -d '{"payload":"отделение Банка по адресу г. Москва, ул. Ленина, 10","payload_id":"demo-3"}'
```

Ответ: `{"result": "отделение Банка по адресу г. Москва, ул. Ленина, 10"}` (не маскируется).

## Где посмотреть логи и метрики

- **Логи**: выводятся в консоль uvicorn. Содержат только тип, позицию и длину спана (без значений ПД).
- **Метрики**: `GET /metrics` → `{requests_total, rps, avg_latency_seconds, latency_p50/p95/p99, tokens_total}`.
- **Статистика**: `GET /stats` → `{vault, metrics}`.
- **Здоровье**: `GET /health` → `{"status": "ok"}`.
- **Готовность**: `GET /ready` → `{"status": "ready", "vault": ...}`.

## Проверка качества

```bash
python tools/gen_dataset.py --out tests/golden_set.json   # генерация датасета
python tools/score.py --dataset tests/golden_set.json     # F1 по спанам
pytest                                                    # тесты контракта
```

## Нагрузочное тестирование

```bash
python tools/load_test.py --url http://127.0.0.1:8000 --dataset tests/golden_set.json --rps 1000 --processes 8
```

Ожидаемый результат: RPS ≥ 1000, сервер latency p95 ≤ 1 с.