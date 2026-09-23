from dataclasses import dataclass, field


@dataclass
class Span:
    """Спан персональных данных в тексте."""
    type: str          # тип ПД, например "passport"
    start: int         # позиция начала в оригинале
    end: int           # позиция конца (не включительно)
    value: str         # исходное значение (только внутри обработки, не в логи)
    confidence: float  # уверенность [0..1]


@dataclass
class MaskRecord:
    """Запись соответствия payload_id → маска/оригинал для vault."""
    payload_id: str
    mask: str          # замаскированная строка
    original: str      # исходная строка
    types: list[str] = field(default_factory=list)  # выявленные типы ПД
    created_at: float = 0.0  # timestamp для TTL