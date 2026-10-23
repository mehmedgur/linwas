"""Ayar şeması ve arka uç arayüzü (Qt'siz).

Eco sürümünde ayarların sahibi eco servisleridir (docs/eco-entegrasyonu.md); Linwas şemayı
gösterir ve değişikliği arka uca yazar. Arka uçlar: eco (D-Bus, sonra), Plasma (prototip),
bellek içi (test). Her yazma kuyruk/izin listesi/geri alma kurallarından geçer (ayrı aşama).
"""

from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass
from enum import Enum
from typing import Any, Protocol


class Risk(Enum):
    """Değişikliğin riski; onay ve geri alma davranışını belirler."""

    LOW = "low"  # anında uygulanır, geri alınabilir
    MEDIUM = "medium"  # uygulanır, geri alma düğmesi gösterilir
    HIGH = "high"  # onay ister


@dataclass(frozen=True)
class SettingDef:
    key: str  # ör. "appearance.color_scheme"
    kind: type  # bool, int, float, str
    default: Any
    risk: Risk = Risk.LOW
    minimum: float | None = None
    maximum: float | None = None
    choices: tuple[Any, ...] = ()

    def validate(self, value: Any) -> Any:
        """Değeri şemaya göre doğrular; geçersizse ValueError."""
        # bool, int'in alt sınıfıdır; int beklenen yere True gelmesin
        if self.kind is not bool and isinstance(value, bool):
            raise ValueError(f"{self.key}: bool kabul edilmez")
        if not isinstance(value, self.kind):
            raise ValueError(f"{self.key}: {self.kind.__name__} bekleniyordu")
        if self.choices and value not in self.choices:
            raise ValueError(f"{self.key}: geçersiz seçim {value!r}")
        if self.minimum is not None and value < self.minimum:
            raise ValueError(f"{self.key}: {self.minimum} altında")
        if self.maximum is not None and value > self.maximum:
            raise ValueError(f"{self.key}: {self.maximum} üstünde")
        return value


class SettingsBackend(Protocol):
    """Ayarları tutan ve uygulayan taraf (eco servisleri, Plasma, bellek içi...)."""

    def get(self, setting: SettingDef) -> Any: ...

    def set(self, setting: SettingDef, value: Any) -> None: ...

    def watch(self, callback: Callable[[str, Any], None]) -> Callable[[], None]:
        """Değişiklikleri izler; çağrıldığında izlemeyi bırakan işlevi döndürür."""
        ...


class MemoryBackend:
    """Bellek içi arka uç: testler ve arayüz geliştirme için."""

    def __init__(self) -> None:
        self._values: dict[str, Any] = {}
        self._watchers: list[Callable[[str, Any], None]] = []

    def get(self, setting: SettingDef) -> Any:
        return self._values.get(setting.key, setting.default)

    def set(self, setting: SettingDef, value: Any) -> None:
        self._values[setting.key] = setting.validate(value)
        for callback in list(self._watchers):
            callback(setting.key, self._values[setting.key])

    def watch(self, callback: Callable[[str, Any], None]) -> Callable[[], None]:
        self._watchers.append(callback)
        return lambda: self._watchers.remove(callback) if callback in self._watchers else None
