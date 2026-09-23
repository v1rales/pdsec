"""In-memory LRU-хранилище соответствий payload_id → MaskRecord с TTL.

Потокобезопасно: доступ к кэшу защищён блокировкой. Вытеснение по LRU
при превышении max_size, устаревшие записи отбрасываются по TTL.
"""

import threading
import time
from collections import OrderedDict

from app.core.span import MaskRecord
from app.vault.base import Vault


class MemoryVault(Vault):
    """LRU-кэш с TTL за интерфейсом Vault."""

    def __init__(self, max_size: int = 500_000, ttl_seconds: float = 3600.0) -> None:
        self._max_size = max_size
        self._ttl = ttl_seconds
        self._lock = threading.Lock()
        self._data: OrderedDict[str, MaskRecord] = OrderedDict()

    def get(self, payload_id: str) -> MaskRecord | None:
        with self._lock:
            record = self._data.get(payload_id)
            if record is None:
                return None
            if time.time() - record.created_at > self._ttl:
                del self._data[payload_id]
                return None
            # LRU: переместить в конец (самый свежий)
            self._data.move_to_end(payload_id)
            return record

    def put(self, record: MaskRecord) -> None:
        with self._lock:
            self._data[record.payload_id] = record
            self._data.move_to_end(record.payload_id)
            # Вытеснение самых старых при превышении размера
            while len(self._data) > self._max_size:
                self._data.popitem(last=False)

    def stats(self) -> dict:
        with self._lock:
            return {
                "size": len(self._data),
                "max_size": self._max_size,
                "ttl_seconds": self._ttl,
            }