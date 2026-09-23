from abc import ABC, abstractmethod

from app.core.span import MaskRecord


class Vault(ABC):
    """Интерфейс хранилища соответствий payload_id → MaskRecord."""

    @abstractmethod
    def get(self, payload_id: str) -> MaskRecord | None: ...

    @abstractmethod
    def put(self, record: MaskRecord) -> None: ...

    @abstractmethod
    def stats(self) -> dict: ...