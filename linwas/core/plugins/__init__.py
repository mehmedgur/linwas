"""Eklenti altyapısı: temel sınıf ve kapı (gate) tanımları.

Eklentiler bu modüldeki sınıfları devralır ve kapıları uygular.
Linwas'ın yerleşik eklentileri de (Oyun, Yazıcı, Yedekleme vb.) bu yapıyı kullanır.
"""

from __future__ import annotations

from abc import ABC, abstractmethod
from collections.abc import Callable
from dataclasses import dataclass, field
from typing import Any

# Eklentinin kaynağı (Ayarlar › Eklentiler'deki rozet)
SOURCE_BUILTIN = "builtin"  # Linwas'ın içinde
SOURCE_OFFICIAL = "official"  # imzalı APT deposundan .deb (Python, entry point)
SOURCE_CATALOG = "catalog"  # imzalı Linwas kataloğundan kodsuz eklenti
SOURCE_DEVELOPER = "developer"  # geliştirici kipinde imzasız yerel dosya


@dataclass
class PluginMeta:
    """Eklenti kimliği ve sürüm bilgisi."""

    id: str  # örn. "linwas.gaming"
    name: str  # görünen ad (İngilizce; UI çevirir)
    version: str  # semver
    api_version: str = "1"  # uyumsuz eklenti kapatılır
    publisher: str = "Linwas"
    description: str = ""  # kısa açıklama (görüntülenecek dilde)


@dataclass
class PluginAction:
    """Eklentinin sunduğu düğme. Tür:
    - "page": Linwas sayfasına gider (`target` = sayfa kimliği)
    - "settings": sistem ayarını açar (`target` = data/settings_map.json anahtarı)
    - "task": görevi kuyruğa koyar (`steps` = [(işlem, parametreler)]; izin listesinden geçer)
    - "url": https bağlantısını tarayıcıda açar
    """

    kind: str
    label: str
    target: str = ""
    steps: list[tuple[str, dict[str, str]]] = field(default_factory=list)


@dataclass
class PageSpec:
    """Menüye eklenecek sayfa tanımı."""

    id: str
    label: str  # İngilizce
    icon: str = ""  # SVG simge adı
    parent: str = ""  # Varsa üst menü öğesi ID'si (ör. "system")
    order: int = 100


@dataclass
class TaskTypeSpec:
    """Eklentinin kuyruğa ekleyebileceği görev türü."""

    op_id: str
    label: str


@dataclass
class WhitelistProposal:
    """Eklentinin önerdiği yeni işlem tanımı.

    Çekirdek bu öneriyi onaylayabilir veya reddedebilir.
    Şimdilik öneri mekanizması arayüz tamamlanana kadar pasif.
    """

    op_id: str
    label: str
    params_description: str


@dataclass
class ScanCheck:
    """Sorun giderme taramasına eklenen kontrol.

    `run` (ok, ayrıntı) döner; arka planda çalışır, Qt kullanmamalı. Sorun varsa
    `problem_label` ve `fixes` gösterilir.
    """

    id: str
    label: str  # sorun yokken gösterilen metin
    description: str = ""
    problem_label: str = ""
    run: Callable[[], tuple[bool, str]] | None = None
    fixes: list[PluginAction] = field(default_factory=list)


@dataclass
class TroubleshootingCard:
    """Sorun Giderme sayfasına eklenen belirti kartı."""

    id: str
    symptom: str
    solutions: list[str] = field(default_factory=list)  # eski biçim: düz metin öneriler
    description: str = ""
    actions: list[PluginAction] = field(default_factory=list)


@dataclass
class GuideEntry:
    """Rehber/arama girdisi ve eşleşen Linwas sayfası veya sistem ayarı."""

    keywords: list[str]
    label: str
    target_page_id: str = ""
    settings_launcher_key: str = ""  # data/settings_map.json içindeki anahtar
    kind: str = "concept"  # setting | program | shortcut | concept (Rehber'deki süzgeç)


@dataclass
class OnboardingStep:
    """İlk açılış sihirbazına eklenen adım."""

    id: str
    label: str
    order: int = 100


class PluginBase(ABC):
    """Tüm eklentilerin devraldığı temel sınıf.

    Kapılar isteğe bağlıdır; eklenti yalnızca kullandıklarını geçersiz kılar.
    """

    # Kapatılamaz (başka sayfalar buna dayanıyor, ör. donanım bilgisi)
    required: bool = False
    # Ayarlar › Eklentiler'deki rozet; yükleyici kaynağa göre ayarlar
    source: str = SOURCE_OFFICIAL

    @property
    @abstractmethod
    def meta(self) -> PluginMeta:
        """Eklenti kimliği ve sürüm bilgisi."""

    # --- Kapılar ---

    def pages(self) -> list[PageSpec]:
        """Menüye eklencek sayfaları döner."""
        return []

    def create_page(self, page_id: str, parent: object) -> object | None:
        """pages() içindeki sayfanın arayüz nesnesini oluşturur (arayüz katmanı çağırır).

        Çekirdek Qt'ye bağımlı olmadığı için dönüş türü genel tutulur; eklenti Qt
        modülünü yalnızca bu işlev çağrıldığında içe aktarmalıdır.
        """
        return None

    def task_types(self) -> list[TaskTypeSpec]:
        """Kuyruğa eklenebilecek görev türlerini döner."""
        return []

    def whitelist_proposals(self) -> list[WhitelistProposal]:
        """İzin listesine önerilen yeni işlemleri döner."""
        return []

    def scan_checks(self) -> list[ScanCheck]:
        """Sistem taramasına eklenecek kontrolleri döner."""
        return []

    def troubleshooting_cards(self) -> list[TroubleshootingCard]:
        """Sorun Giderme sayfasına eklenecek belirti kartlarını döner."""
        return []

    def guide_entries(self) -> list[GuideEntry]:
        """Rehber/arama içeriğini döner."""
        return []

    def onboarding_steps(self) -> list[OnboardingStep]:
        """İlk açılış sihirbazına eklenecek adımları döner."""
        return []

    def ai_context(self) -> dict[str, Any]:
        """AI sağlayıcısına iletilecek ek bağlam bilgisini döner."""
        return {}
