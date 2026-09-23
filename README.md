# Модуль безопасности персональных данных

Сервис-прокси между системой-потребителем и LLM: идентифицирует, маскирует и демаскирует персональные данные по контракту `POST /process`.

## Запуск

```bash
pip install -r requirements.txt
uvicorn app.main:app --host 0.0.0.0 --port 8000 --workers 1
```

Или через Docker: `docker build -t pdmask . && docker run -p 8000:8000 pdmask`.

## Пример запроса

```bash
curl -X POST http://127.0.0.1:8000/process \
  -H "Content-Type: application/json" \
  -d '{"payload":"Клиент Иванов Иван Иванович, паспорт 4509 123456","payload_id":"demo-1"}'
```

Ответ: `{"result": "Клиент И. И. И., паспорт 45** ****56"}`.

## Настройка

Правила систем задаются в `config/systems.yaml`: список систем (вкл/откл), перечень типов ПД для маскирования, наличие демаскирования, вид маски, правило `multi_type_rule` и `allowed_systems` (allowlist). При отсутствии заголовка `X-System-Id` применяется `default_system`. Отключённая система (`enabled: false`) маскирует, но не демаскирует. Новый тип ПД добавляется одним файлом в `app/detectors/`.

## Проверка качества

```bash
python tools/gen_dataset.py --out tests/golden_set.json   # генерация датасета
python tools/score.py --dataset tests/golden_set.json     # F1 по спанам
pytest                                                    # тесты контракта
```

## Документация

- `docs/jury_guide.md` — инструкция для жюри по проверке.
- `docs/architecture.md` — схема архитектуры и настройки.
- `docs/performance.md` — сведения о производительности и доп. возможностях.
- `docs/limitations.md` — ограничения и план развития.