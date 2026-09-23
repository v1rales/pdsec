# Модуль безопасности персональных данных

Сервис-прокси между системой-потребителем и LLM: идентифицирует, маскирует и демаскирует персональные данные по контракту `POST /process`.

## Запуск

```bash
pip install -r requirements.txt
uvicorn app.main:app --host 0.0.0.0 --port 8000 --workers 1
```

Или через Docker: `docker build -t pdmask . && docker run -p 8000:8000 pdmask`.

## Настройка

Правила систем задаются в `config/systems.yaml`: список систем (вкл/откл), перечень типов ПД для маскирования, наличие демаскирования, вид маски и правило `multi_type_rule`. При отсутствии заголовка `X-System-Id` применяется `default_system`. Новый тип ПД добавляется одним файлом в `app/detectors/`.

## Проверка качества

```bash
python tools/gen_dataset.py --out tests/golden_set.json   # генерация датасета
python tools/score.py --dataset tests/golden_set.json     # F1 по спанам
pytest                                                    # тесты контракта
```