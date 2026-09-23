"""Оркестрация обработки запроса: три ветки роутинга.

Маскирование: детекция → резолвер пересечений → замена спанов.
Демаскирование: по payload_id из vault возвращается original.
"""

import logging
import time
from concurrent.futures import ProcessPoolExecutor, ThreadPoolExecutor

from app.core.config import Config, SystemConfig
from app.core.resolver import resolve
from app.core.span import MaskRecord, Span
from app.detectors import all_detectors
from app.detectors.worker import detect as detect_in_process
from app.masking.masker import apply_masks
from app.observability.logging import safe_span
from app.observability.metrics import metrics
from app.vault.base import Vault

logger = logging.getLogger(__name__)

#: Порог длины текста (символов), при превышении которого включается чанкование.
_CHUNK_THRESHOLD = 50_000
#: Целевой размер чанка (символов). Чанки режутся по границам пробелов.
_CHUNK_SIZE = 50_000
#: Размер перекрытия между соседними чанками (символов). Достаточен для
#: многословного ПД (например, ФИО из трёх слов), пересекающего границу чанка.
_CHUNK_OVERLAP = 200


def _split_chunks(text: str, max_size: int) -> list[tuple[int, str]]:
    """Разбивает текст на чанки по границам пробелов, не режа слова.

    Каждый чанк не длиннее max_size. Если в окне [start, start+max_size)
    есть пробел — режем по последнему пробелу, иначе по жёсткой границе
    (патологический случай: один токен длиннее max_size).

    Между соседними чанками добавляется перекрытие _CHUNK_OVERLAP символов:
    следующий чанк начинается на _CHUNK_OVERLAP символов раньше конца
    предыдущего, чтобы многословное ПД, пересекающее границу, целиком
    попадало хотя бы в один чанк.

    Возвращает список (start, chunk) — глобальную позицию начала и текст.
    """
    chunks: list[tuple[int, str]] = []
    start = 0
    n = len(text)
    while start < n:
        end = min(start + max_size, n)
        if end < n:
            cut = text.rfind(" ", start, end)
            if cut > start:
                end = cut
        chunks.append((start, text[start:end]))
        # Следующий чанк начинается с перекрытием, но не раньше текущего start
        # (иначе бесконечный цикл, если cut близко к start).
        next_start = end - _CHUNK_OVERLAP
        start = next_start if next_start > start else end
        if start >= n:
            break
    return chunks


class Pipeline:
    """Координирует vault, детекторы, конфигурацию и маскирование."""

    def __init__(
        self,
        vault: Vault,
        config: Config | None = None,
        detect_executor: ProcessPoolExecutor | None = None,
    ) -> None:
        self._vault = vault
        self._config = config or Config()
        self._detectors = all_detectors()
        self._detect_executor = detect_executor

    def process(self, payload: str, payload_id: str, system_id: str | None = None) -> str:
        """Обрабатывает запрос по трём веткам роутинга.

        - id известен и payload == mask → вернуть original (демаскирование);
        - id известен и payload == original → вернуть mask (ретрай маскирования);
        - id неизвестен → маскировать, сохранить, вернуть mask.
        """
        system = self._config.get_system(system_id)

        # Отказ доступа для системы вне allowlist: возвращаем payload как есть
        # (200, без маскирования). /process не отдаёт 4XX/5XX.
        if not self._config.is_allowed(system_id):
            return payload

        record = self._vault.get(payload_id)

        if record is not None:
            if payload == record.mask:
                # Демаскирование разрешено только для включённой системы
                # с unmask_enabled. Отключённая система получает только маску.
                if system.enabled and system.unmask_enabled:
                    return record.original
                return payload
            if payload == record.original:
                return record.mask
            # payload не совпал ни с маской, ни с оригиналом — новый текст

        mask, types = self._mask(payload, system)
        self._vault.put(
            MaskRecord(
                payload_id=payload_id,
                mask=mask,
                original=payload,
                types=types,
                created_at=time.time(),
            )
        )
        return mask

    def _mask(self, text: str, system: SystemConfig) -> tuple[str, list[str]]:
        """Детекция, резолвер и маскирование. Возвращает маску и типы ПД.

        Длинный текст (> _CHUNK_THRESHOLD) обрабатывается по чанкам
        параллельно, чтобы уложиться в таймаут проверяющей системы.
        """
        if len(text) <= _CHUNK_THRESHOLD:
            return self._mask_whole(text, system)
        return self._mask_chunked(text, system)

    def _mask_whole(self, text: str, system: SystemConfig) -> tuple[str, list[str]]:
        """Маскирование короткого текста целиком (без чанкования)."""
        spans = self._detect(text)
        return self._finish_mask(text, spans, system)

    def _mask_chunked(self, text: str, system: SystemConfig) -> tuple[str, list[str]]:
        """Маскирование длинного текста: чанки детектируются параллельно.

        Спаны каждого чанка смещаются в глобальные координаты, затем
        резолвер и фильтры применяются ко всему тексту сразу — результат
        идентичен обработке без чанкования (при условии, что ПД не
        пересекают границы чанков, а чанки режутся по пробелам).

        Чанки перекрываются на _CHUNK_OVERLAP символов, чтобы многословное
        ПД, пересекающее границу, целиком попадало хотя бы в один чанк.
        При склейке спаны, начинающиеся в зоне перекрытия (первые
        _CHUNK_OVERLAP символов чанка), отбрасываются для всех чанков кроме
        первого — они уже обработаны предыдущим чанком, иначе были бы дубли.
        """
        chunks = _split_chunks(text, _CHUNK_SIZE)
        chunk_spans = self._detect_chunks([c for _, c in chunks])

        spans: list[Span] = []
        n_chunks = len(chunks)
        for i, ((chunk_start, chunk), local) in enumerate(zip(chunks, chunk_spans)):
            # Для промежуточных чанков (не первый и не последний) отбрасываем
            # спаны в зоне перекрытия (первые _CHUNK_OVERLAP символов) — они
            # уже обработаны предыдущим чанком. Первый и последний чанки
            # перекрытие не отбрасывают: у первого нет предыдущего, у
            # последнего нет следующего, который покрыл бы его хвост.
            drop_before = _CHUNK_OVERLAP if 0 < i < n_chunks - 1 else 0
            for s in local:
                if s.start < drop_before:
                    continue
                spans.append(
                    Span(
                        s.type,
                        chunk_start + s.start,
                        chunk_start + s.end,
                        s.value,
                        s.confidence,
                    )
                )
        return self._finish_mask(text, spans, system)

    def _finish_mask(
        self, text: str, spans: list[Span], system: SystemConfig
    ) -> tuple[str, list[str]]:
        """Общий хвост маскирования: резолвер, фильтры, замена спанов."""
        resolved = resolve(spans, self._detectors)

        # Фильтр по типам, разрешённым для системы
        if "all" not in system.mask_types:
            resolved = [s for s in resolved if s.type in system.mask_types]

        # multi_type_rule: маскировать только при нескольких типах
        if system.multi_type_rule and len({s.type for s in resolved}) < 2:
            resolved = []

        types = sorted({s.type for s in resolved})
        # Метрика masked_types_total: инкремент по каждому выявленному типу ПД.
        for t in types:
            metrics.inc_masked_type(t)
        # Безопасное логирование выявленных типов ПД по каждому запросу (ТЗ §3.1/§3.4).
        # INFO-уровень: одна сводка типов на запрос — без значений ПД.
        if types:
            logger.info("Обнаружены типы ПД: %s", ", ".join(types))
        # Поспановое логирование — DEBUG-уровень: только тип, позиция, длина,
        # без значений ПД. Не пишется при INFO-уровне логирования.
        for s in resolved:
            logger.debug("Найден спан %s", safe_span(s.type, s.start, s.end))
        mask = apply_masks(text, resolved, system.mask_style)
        return mask, types

    def _detect_chunks(self, chunks: list[str]) -> list[list[Span]]:
        """Параллельная детекция по чанкам.

        При наличии пула процессов — через ProcessPoolExecutor (обход GIL),
        иначе — через ThreadPoolExecutor в текущем процессе.
        """
        if self._detect_executor is not None:
            futures = [
                self._detect_executor.submit(detect_in_process, chunk)
                for chunk in chunks
            ]
            return [f.result() for f in futures]
        with ThreadPoolExecutor() as executor:
            return list(executor.map(self._detect, chunks))

    def _detect(self, text: str) -> list:
        """Детекция: в ProcessPoolExecutor (обход GIL) или в текущем процессе."""
        if self._detect_executor is not None:
            return self._detect_executor.submit(detect_in_process, text).result()
        # Без пула процессов — детекция в текущем процессе, каждый в try-except.
        spans = []
        for detector in self._detectors:
            try:
                spans.extend(detector.detect(text))
            except Exception:  # noqa: BLE001 — падение одного не роняет запрос
                logger.exception("Детектор %s упал", detector.type)
        return spans