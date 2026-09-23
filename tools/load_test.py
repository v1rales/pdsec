"""Нагрузочный тест сервиса маскирования/демаскирования ПД.

Отправляет пары запросов на POST /process:
  1) маскирование — новый payload_id + исходный текст → маска;
  2) демаскирование — тот же payload_id + маска → исходный текст.
Проверяет round-trip (демаскирование вернуло исходный текст) и измеряет
RPS, латентность (p50/p95/p99), долю ошибок и точность round-trip.

Датасет берётся из tests/golden_set.json (JSON: список {text, spans, negative})
или генерируется tools/gen_dataset.py, если путь не задан.

CLI: python tools/load_test.py --url http://127.0.0.1:8000 \
      --dataset tests/golden_set.json --rps 1000 --duration 30

Возвращает код 0, если RPS >= 1000 и p95 <= 1 с, иначе код 1.
"""

import argparse
import asyncio
import json
import os
import statistics
import subprocess
import sys
import time
import uuid

import httpx

# UTF-8 для stdout/stderr (Windows-консоль по умолчанию cp1252 не выводит кириллицу).
if hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding="utf-8")
    sys.stderr.reconfigure(encoding="utf-8")

#: Корень проекта (родитель каталога tools/) — для вызова gen_dataset.py.
_PROJECT_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
#: Путь к генератору датасета по умолчанию.
_GEN_DATASET = os.path.join(_PROJECT_ROOT, "tools", "gen_dataset.py")
#: Путь к датасету по умолчанию.
_DEFAULT_DATASET = os.path.join(_PROJECT_ROOT, "tests", "golden_set.json")

#: Порог RPS для успешного прохождения теста.
_RPS_THRESHOLD = 1000
#: Порог p95 латентности (секунды) для успешного прохождения теста.
_P95_THRESHOLD = 1.0


def _load_dataset(path: str | None) -> list[dict]:
    """Загружает датасет: из файла или генерирует через gen_dataset.py.

    Если path задан — читает JSON-файл. Иначе вызывает gen_dataset.py
    во временный файл внутри проекта (.work/) и читает его.
    """
    if path:
        with open(path, "r", encoding="utf-8") as f:
            return json.load(f)

    work_dir = os.path.join(_PROJECT_ROOT, ".work")
    os.makedirs(work_dir, exist_ok=True)
    tmp_path = os.path.join(work_dir, "load_test_dataset.json")
    subprocess.run(
        [sys.executable, _GEN_DATASET, "--out", tmp_path, "--count", "200"],
        check=True,
    )
    with open(tmp_path, "r", encoding="utf-8") as f:
        return json.load(f)


def _percentile(sorted_values: list[float], pct: float) -> float:
    """Квантиль отсортированного списка значений (линейная интерполяция)."""
    if not sorted_values:
        return 0.0
    if len(sorted_values) == 1:
        return sorted_values[0]
    rank = (len(sorted_values) - 1) * pct
    lower = int(rank)
    upper = min(lower + 1, len(sorted_values) - 1)
    frac = rank - lower
    return sorted_values[lower] + (sorted_values[upper] - sorted_values[lower]) * frac


class _Stats:
    """Накопитель метрик: латентности, ошибки, round-trip.

    record() вызывается на КАЖДЫЙ HTTP-запрос (и маскирование, и
    демаскирование), поэтому requests_total = число HTTP-запросов,
    а latencies содержит latency каждого запроса отдельно.
    """

    def __init__(self) -> None:
        self.latencies: list[float] = []
        self.requests_total = 0
        self.errors = 0
        self.round_trip_ok = 0
        self.round_trip_total = 0

    def record(self, latency: float, ok: bool, round_trip: bool | None) -> None:
        """Фиксирует один HTTP-запрос: латентность, успех, результат round-trip."""
        self.latencies.append(latency)
        self.requests_total += 1
        if not ok:
            self.errors += 1
        if round_trip is not None:
            self.round_trip_total += 1
            if round_trip:
                self.round_trip_ok += 1


async def _send_pair(
    client: httpx.AsyncClient,
    url: str,
    text: str,
    stats: _Stats,
    semaphore: asyncio.Semaphore,
) -> None:
    """Отправляет пару маскирование→демаскирование и проверяет round-trip.

    Маскирование: новый payload_id + исходный текст → маска.
    Демаскирование: тот же payload_id + маска → исходный текст.
    record() вызывается на каждый HTTP-запрос отдельно.
    """
    # POST идёт на /process (контракт), а не на базовый URL.
    process_url = url.rstrip("/") + "/process"
    try:
        payload_id = str(uuid.uuid4())

        # Шаг 1: маскирование.
        start = time.perf_counter()
        try:
            resp = await client.post(
                process_url,
                json={"payload": text, "payload_id": payload_id},
            )
            latency = time.perf_counter() - start
            if resp.status_code != 200:
                stats.record(latency, False, None)
                return
            mask = resp.json().get("result")
            stats.record(latency, True, None)
        except httpx.HTTPError:
            stats.record(time.perf_counter() - start, False, None)
            return

        # Шаг 2: демаскирование.
        start = time.perf_counter()
        try:
            resp = await client.post(
                process_url,
                json={"payload": mask, "payload_id": payload_id},
            )
            latency = time.perf_counter() - start
            if resp.status_code != 200:
                stats.record(latency, False, None)
                return
            result = resp.json().get("result")
        except httpx.HTTPError:
            stats.record(time.perf_counter() - start, False, None)
            return

        # Round-trip успешен, если демаскирование вернуло исходный текст.
        stats.record(latency, True, result == text)
    finally:
        semaphore.release()


def _get_server_stats(base_url: str) -> dict | None:
    """Снимает latency-метрики сервера: /stats, при неудаче — /metrics.

    Возвращает словарь с полями latency_p50/p95/p99_seconds и requests_total,
    либо None, если ни /stats, ни /metrics не прочитаны (сервер недоступен).
    None — честный признак «недоступно», а не подмена реальной метрики нулём.
    """
    base = base_url.rstrip("/")
    try:
        with httpx.Client(timeout=httpx.Timeout(5.0)) as client:
            # Сначала /stats (содержит metrics + vault).
            resp = client.get(base + "/stats")
            if resp.status_code == 200:
                metrics = resp.json().get("metrics")
                if metrics:
                    return metrics
            # Fallback: /metrics возвращает те же latency-поля напрямую.
            resp = client.get(base + "/metrics")
            if resp.status_code == 200:
                metrics = resp.json()
                if metrics:
                    return metrics
    except Exception:
        pass
    return None


async def _run_load(
    url: str,
    dataset: list[dict],
    rps: int,
    duration: float,
    max_requests: int | None = None,
) -> tuple[_Stats, float, dict | None, dict | None]:
    """Гоняет нагрузку с заданным RPS в течение duration секунд.

    Пейсинг через токен-бакет: между стартами запросов выдерживается
    интервал 1/rps, чтобы держать целевой RPS. Запросы выполняются
    конкурентно через httpx.AsyncClient. Если задан max_requests —
    останавливается по достижении лимита (что наступит раньше).

    Возвращает (stats, gen_time, server_before, server_after) — статистику
    клиента, время генерации и снимки /stats сервера до/после нагрузки.
    """
    stats = _Stats()
    # Снимок /stats до нагрузки (для расчёта дельты requests_total).
    server_before = _get_server_stats(url)
    # Токен-бакет по монотонным часам: компенсирует грубую гранулярность
    # asyncio.sleep на Windows и держит фактический RPS близко к целевому.
    interval = 1.0 / rps if rps > 0 else 0.0
    start_time = time.monotonic()
    deadline = start_time + duration
    next_slot = start_time
    index = 0
    sent = 0

    # Ограничение числа незавершённых задач: окно, достаточное для генерации
    # целевого RPS без блокировки цикла, но не создающее бесконечную очередь.
    semaphore = asyncio.Semaphore(100)

    tasks: list[asyncio.Task] = []
    # Увеличиваем лимит соединений httpx: дефолт 100 не хватает под нагрузкой,
    # запросы ждут свободное соединение, искажая latency.
    limits = httpx.Limits(max_connections=2000, max_keepalive_connections=2000)
    async with httpx.AsyncClient(timeout=httpx.Timeout(30.0), limits=limits) as client:
        while time.monotonic() < deadline:
            if max_requests is not None and sent >= max_requests:
                break
            text = dataset[index % len(dataset)]["text"]
            index += 1
            sent += 1
            await semaphore.acquire()
            task = asyncio.create_task(
                _send_pair(client, url, text, stats, semaphore)
            )
            tasks.append(task)
            if interval > 0:
                next_slot += interval
                # Если отстали от графика — не нагоняем, а выравниваем по часам.
                delay = next_slot - time.monotonic()
                if delay > 0:
                    await asyncio.sleep(delay)
                else:
                    next_slot = time.monotonic()

        # Время активной генерации (от старта до выхода из цикла).
        gen_time = time.monotonic() - start_time

        # Дожидаемся завершения всех запущенных задач ДО закрытия клиента.
        if tasks:
            await asyncio.gather(*tasks, return_exceptions=True)

    # Снимок /stats после нагрузки.
    server_after = _get_server_stats(url)
    return stats, gen_time, server_before, server_after


def _format_report(
    stats: _Stats,
    elapsed: float,
    rps: int,
    server_after: dict | None,
) -> tuple[str, bool]:
    """Формирует текстовый отчёт и флаг успешности (код возврата).

    RPS считается по числу HTTP-запросов (requests_total), а не по парам:
    каждая пара = 2 запроса. Время — активная генерация (gen_time).

    Критерий прохождения — честный end-to-end latency клиента (client_p95),
    замеренный на клиенте от отправки до получения ответа. Latency сервера
    из /stats (server_after) показывается справочно.
    """
    total = stats.requests_total
    actual_rps = total / elapsed if elapsed > 0 else 0.0
    error_rate = stats.errors / total if total else 0.0
    round_trip_acc = (
        stats.round_trip_ok / stats.round_trip_total
        if stats.round_trip_total
        else 0.0
    )

    # End-to-end latency клиента (честный замер от отправки до ответа).
    sorted_lat = sorted(stats.latencies)
    client_p50 = _percentile(sorted_lat, 0.50)
    client_p95 = _percentile(sorted_lat, 0.95)
    client_p99 = _percentile(sorted_lat, 0.99)

    # Latency сервера из /stats (или /metrics). Если серверные метрики не
    # прочитаны — честно помечаем «недоступно», а не показываем 0.0 как
    # реальную метрику.
    if server_after:
        server_p95 = server_after.get("latency_p95_seconds", 0.0)
        server_p95_str = f"{server_p95 * 1000:.2f}"
    else:
        server_p95_str = "недоступно"

    lines = [
        "=== Отчёт нагрузочного теста ===",
        f"Целевой RPS:            {rps}",
        f"Фактический RPS:        {actual_rps:.1f}",
        f"Всего HTTP-запросов:    {total}",
        f"Длительность (с):       {elapsed:.2f}",
        f"Клиент latency p50 (мс): {client_p50 * 1000:.2f}",
        f"Клиент latency p95 (мс): {client_p95 * 1000:.2f}",
        f"Клиент latency p99 (мс): {client_p99 * 1000:.2f}",
        f"Сервер latency p95 (мс): {server_p95_str} (справочно)",
        f"Доля ошибок:            {error_rate * 100:.2f}%",
        f"Round-trip точность:    {round_trip_acc * 100:.2f}%",
    ]

    passed = actual_rps >= _RPS_THRESHOLD and client_p95 <= _P95_THRESHOLD
    lines.append("")
    lines.append(
        f"Результат: {'ПРОЙДЕН' if passed else 'НЕ ПРОЙДЕН'} "
        f"(требуется RPS >= {_RPS_THRESHOLD} и клиент p95 <= {_P95_THRESHOLD} с)"
    )
    return "\n".join(lines), passed


def _run_process(
    url: str,
    dataset: list[dict],
    rps: int,
    duration: float,
    max_requests: int | None,
) -> tuple[_Stats, float, dict | None, dict | None]:
    """Запускает нагрузку в одном процессе (для multiprocessing)."""
    return asyncio.run(_run_load(url, dataset, rps, duration, max_requests))


def main() -> int:
    parser = argparse.ArgumentParser(description="Нагрузочный тест сервиса ПД")
    parser.add_argument("--url", default="http://127.0.0.1:8000", help="базовый URL сервиса")
    parser.add_argument(
        "--dataset",
        default=None,
        help="путь к датасету JSON (по умолчанию генерируется gen_dataset.py)",
    )
    parser.add_argument("--rps", type=int, default=1000, help="целевой RPS (суммарный)")
    parser.add_argument("--duration", type=float, default=30, help="длительность теста, с")
    parser.add_argument(
        "--max-requests",
        type=int,
        default=None,
        help="максимальное число пар запросов (по умолчанию без лимита)",
    )
    parser.add_argument(
        "--processes",
        type=int,
        default=1,
        help="число процессов для генерации нагрузки (по умолчанию 1)",
    )
    args = parser.parse_args()

    # Базовый URL без /process: /process добавляется только в _send_pair при POST,
    # а _get_server_stats запрашивает /stats и /metrics на базовом URL.
    url = args.url.rstrip("/")
    dataset = _load_dataset(args.dataset)
    if not dataset:
        print("Ошибка: датасет пуст", file=sys.stderr)
        return 1

    processes = max(1, args.processes)
    # RPS делится между процессами поровну.
    per_process_rps = max(1, args.rps // processes)
    # Лимит запросов делится между процессами поровну.
    per_process_max = (
        max(1, args.max_requests // processes) if args.max_requests else None
    )

    print(f"Загружено примеров: {len(dataset)}")
    print(
        f"URL: {url}, целевой RPS: {args.rps} ({processes} процессов по {per_process_rps}), "
        f"длительность: {args.duration} с, max_requests: {args.max_requests}"
    )

    start = time.monotonic()
    if processes == 1:
        stats, gen_time, server_before, server_after = _run_process(
            url, dataset, per_process_rps, args.duration, per_process_max
        )
        results = [(stats, gen_time, server_before, server_after)]
    else:
        import multiprocessing as mp

        ctx = mp.get_context("spawn")
        with ctx.Pool(processes) as pool:
            results = pool.starmap(
                _run_process,
                [
                    (url, dataset, per_process_rps, args.duration, per_process_max)
                    for _ in range(processes)
                ],
            )
    elapsed = time.monotonic() - start

    # Объединяем статистику всех процессов.
    merged = _Stats()
    # Время активной генерации — максимум по процессам (все стартуют вместе).
    gen_time = max((gt for _, gt, _, _ in results), default=elapsed)
    for s, _, _, _ in results:
        merged.latencies.extend(s.latencies)
        merged.requests_total += s.requests_total
        merged.errors += s.errors
        merged.round_trip_ok += s.round_trip_ok
        merged.round_trip_total += s.round_trip_total

    # Снимок /stats сервера после нагрузки (все процессы бьют в один сервер).
    server_after = results[-1][3] if results else None

    report, passed = _format_report(merged, gen_time, args.rps, server_after)
    print(report)
    return 0 if passed else 1


if __name__ == "__main__":
    sys.exit(main())