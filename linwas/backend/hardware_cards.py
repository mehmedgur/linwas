"""Sürücüler sayfasının donanım kartları: aygıtlar + sürücü önerilerinin eşleştirilmesi.

Qt'ye bağımlı değil. Her kart bir aygıttır (ekran kartı, ağ, ses, Bluetooth, kamera,
yazıcı); öneriler üretici adına göre ilgili aygıta bağlanır, eşleşmeyen öneri o gruptaki
ilk aygıta, grupta aygıt yoksa aygıtsız karta düşer.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path

from linwas.backend.devices import Device
from linwas.backend.drivers import DriverCandidate, DriverCategory

# Kart olarak gösterilen gruplar (gösterim sırası)
CARD_GROUPS = ("display", "network", "audio", "bluetooth", "camera", "printer")

# Öneri kategorisi → aygıt grubu
_CATEGORY_GROUP = {
    DriverCategory.GPU: "display",
    DriverCategory.NETWORK: "network",
    DriverCategory.PRINTER: "printer",
}

# PCI/USB üretici kimliği → önerilerde geçen üretici sözcüğü
_VENDOR_WORDS = {
    "10de": "nvidia",
    "1002": "amd",
    "8086": "intel",
    "8087": "intel",
    "14e4": "broadcom",
    "10ec": "realtek",
    "0bda": "realtek",
    "14c3": "mediatek",
    "0e8d": "mediatek",
}

# Kapalı kaynak çekirdek sürücüleri (gerisi Linux'la gelen açık kaynak sürücü)
PROPRIETARY_DRIVERS = {"nvidia", "wl"}

# Ad kısaltma: üretici adındaki gereksiz ekler
_NAME_NOISE = (
    " Corporation",
    " Corp.",
    " Co., Ltd.",
    " Co.,Ltd.",
    " Semiconductor",
    " Technology",
    " Inc.",
    " [AMD/ATI]",
)


@dataclass
class HardwareCard:
    group: str
    device: Device | None  # None: aygıtı bulunamayan öneri (ör. yazıcı takılı değil)
    candidates: list[DriverCandidate] = field(default_factory=list)

    @property
    def status(self) -> str:
        """ "problem" | "recommended" | "ok"."""
        if self.device is not None and self.device.problem:
            return "problem"
        if any(c.recommended and not c.installed for c in self.candidates):
            return "recommended"
        return "ok"


def short_name(name: str) -> str:
    for noise in _NAME_NOISE:
        name = name.replace(noise, "")
    return " ".join(name.split())


def _vendor_word(device: Device) -> str:
    return _VENDOR_WORDS.get(device.vendor, "")


def _matches(device: Device, cand: DriverCandidate) -> bool:
    word = _vendor_word(device)
    if not word:
        return False
    text = f"{cand.package} {cand.device_name} {cand.description}".lower()
    return word in text


def _skip(device: Device) -> bool:
    # Ekran kartının HDMI ses denetleyicisi ayrı ses kartı gibi gösterilmez
    return device.group == "audio" and device.vendor in ("10de", "1002") and device.bus == "pci"


def build_cards(devices: list[Device], candidates: list[DriverCandidate]) -> list[HardwareCard]:
    cards: list[HardwareCard] = []
    by_group: dict[str, list[HardwareCard]] = {g: [] for g in CARD_GROUPS}
    for dev in devices:
        if dev.group in by_group and not _skip(dev):
            card = HardwareCard(dev.group, dev)
            by_group[dev.group].append(card)

    for cand in candidates:
        group = _CATEGORY_GROUP.get(cand.category)
        if group is None:
            continue
        group_cards = by_group[group]
        target = next(
            (c for c in group_cards if c.device is not None and _matches(c.device, cand)), None
        )
        if target is None and group_cards:
            target = group_cards[0]
        if target is None:
            target = HardwareCard(group, None)
            group_cards.append(target)
        target.candidates.append(cand)

    for group in CARD_GROUPS:
        cards += by_group[group]
    # Sorunlular en üstte; sıra başka bakımdan korunur
    order = {"problem": 0, "recommended": 1, "ok": 2}
    return sorted(cards, key=lambda c: order[c.status])


def module_version(module: str, sys_module: Path = Path("/sys/module")) -> str:
    """Yüklü çekirdek modülünün sürümü (ör. nvidia 535.183.01); yoksa ""."""
    if not module:
        return ""
    try:
        return (sys_module / module.replace("-", "_") / "version").read_text().strip()
    except OSError:
        return ""
