# SPDX-FileCopyrightText: 2026 Mehmed Gürbüz and Linwas contributors
# SPDX-License-Identifier: GPL-3.0-or-later
# Additional terms (GPL-3.0 section 7): see NOTICE.md — keep this notice.
"""Bluetooth ses cihazları (kulaklık, hoparlör): ses modu ve varsayılan çıkış. Qt'siz.

PulseAudio ve PipeWire'ın PulseAudio uyumlu katmanı için `pactl` kullanılır. Komutlar pactl(1)
belgesinden, çıktı biçimleri PulseAudio kaynağından (src/utils/pactl.c) doğrulandı:
`pactl list cards`, `pactl list short sinks`, `pactl get-default-sink`,
`pactl set-card-profile KART PROFİL`, `pactl set-default-sink SINK`.

Sade iki mod sunulur (ham profil adları gizlenir): "müzik" (A2DP, yüksek kalite, mikrofon yok) ve
"çağrı" (HSP/HFP, mikrofonlu, düşük kalite).
"""

from __future__ import annotations

import re
import shutil
import time
from collections.abc import Callable
from dataclasses import dataclass, field

from linwas.backend import network

MUSIC = "music"
CALLS = "calls"

_CARD_NAME = re.compile(r"bluez_card\.([0-9A-Fa-f]{2}(?:_[0-9A-Fa-f]{2}){5})")
_PROFILE_LINE = re.compile(
    r"^\t\t(\S+): (.*) \(sinks: (\d+), sources: (\d+), priority: (\d+)(?:, available: (\w+))?\)$"
)
# pactl'a seçenek gibi görünen değer geçmesin: ad harfle/rakamla başlar
_SAFE_NAME = re.compile(r"^[A-Za-z0-9][A-Za-z0-9_.:@-]*$")


@dataclass(frozen=True)
class AudioProfile:
    name: str
    description: str
    priority: int
    available: bool = True


@dataclass
class AudioCard:
    name: str  # "bluez_card.AA_BB_CC_DD_EE_FF"
    mac: str  # "AA:BB:CC:DD:EE:FF"
    profiles: list[AudioProfile] = field(default_factory=list)
    active: str = ""


@dataclass
class BtAudio:
    """Bir Bluetooth ses cihazının arayüzde gösterilecek durumu."""

    card: AudioCard
    modes: list[str]  # kullanılabilir modlar (MUSIC, CALLS sırasıyla)
    mode: str  # şimdiki mod ("" bilinmiyor/kapalı)
    is_output: bool  # varsayılan ses çıkışı bu cihaz mı


def profile_mode(profile: str) -> str | None:
    """Profil adından sade mod; ses dışı/kapalı profiller (off, a2dp-source…) None."""
    if profile.startswith("a2dp-sink"):
        return MUSIC
    if profile.startswith("headset-head-unit"):
        return CALLS
    return None


def parse_cards(out: str) -> list[AudioCard]:
    """`pactl list cards` çıktısından yalnızca Bluetooth (bluez_card.*) kartları."""
    cards: list[AudioCard] = []
    for block in re.split(r"(?m)^Card #\d+\s*$", out)[1:]:
        name_match = re.search(r"(?m)^\tName: (.+)$", block)
        if not name_match:
            continue
        name = name_match.group(1).strip()
        card_match = _CARD_NAME.fullmatch(name)
        if not card_match:
            continue
        card = AudioCard(name=name, mac=card_match.group(1).upper().replace("_", ":"))
        in_profiles = False
        for line in block.splitlines():
            if re.match(r"^\t\S", line):  # tek sekmeli başlık: bölüm değişti
                in_profiles = line.startswith("\tProfiles:")
                active = re.match(r"^\tActive Profile: (.+)$", line)
                if active:
                    card.active = active.group(1).strip()
                continue
            if in_profiles:
                m = _PROFILE_LINE.match(line)
                if m:
                    card.profiles.append(
                        AudioProfile(
                            name=m.group(1),
                            description=m.group(2),
                            priority=int(m.group(5)),
                            available=(m.group(6) or "yes").lower() != "no",
                        )
                    )
        cards.append(card)
    return cards


def parse_sinks(out: str) -> list[str]:
    """`pactl list short sinks` (dizin, ad, sürücü, örnekleme, durum) → sink adları."""
    names = []
    for line in out.splitlines():
        parts = line.split("\t")
        if len(parts) >= 2 and parts[1].strip():
            names.append(parts[1].strip())
    return names


def sink_for(mac: str, sinks: list[str]) -> str | None:
    """Cihazın ses çıkışı: PulseAudio'da `bluez_sink.AA_….a2dp_sink`, PipeWire'da
    `bluez_output.AA_….1`; ikisi de `bluez_` ile başlar ve adresi alt çizgili içerir."""
    token = mac.replace(":", "_").upper()
    for name in sinks:
        if name.startswith("bluez_") and token in name.upper():
            return name
    return None


def available_modes(card: AudioCard) -> list[str]:
    found = {profile_mode(p.name) for p in card.profiles if p.available}
    return [mode for mode in (MUSIC, CALLS) if mode in found]


def pick_profile(card: AudioCard, mode: str) -> str | None:
    """Modun kullanılabilir profilleri arasında önceliği en yüksek olan."""
    candidates = [p for p in card.profiles if p.available and profile_mode(p.name) == mode]
    return max(candidates, key=lambda p: p.priority).name if candidates else None


def _pactl(*args: str, timeout: int = 10) -> tuple[str, str]:
    return network._run(["pactl", *args], timeout)


def available() -> bool:
    return shutil.which("pactl") is not None


def audio_info(mac: str) -> BtAudio | None:
    """Cihazın ses kartı varsa durumu (bağlı Bluetooth ses cihazı); yoksa None."""
    if not available() or not network._valid_mac(mac):
        return None
    card = next((c for c in parse_cards(_pactl("list", "cards")[0]) if c.mac == mac), None)
    if card is None:
        return None
    sink = sink_for(mac, parse_sinks(_pactl("list", "short", "sinks")[0]))
    default = _pactl("get-default-sink")[0].strip()
    return BtAudio(
        card=card,
        modes=available_modes(card),
        mode=profile_mode(card.active) or "",
        is_output=bool(sink) and sink == default,
    )


def set_mode(mac: str, mode: str) -> tuple[bool, str]:
    """Kartı moda uygun profile geçirir (`pactl set-card-profile`)."""
    info = audio_info(mac)
    if info is None:
        return False, "no audio card"
    profile = pick_profile(info.card, mode)
    if profile is None or not _SAFE_NAME.match(info.card.name) or not _SAFE_NAME.match(profile):
        return False, "no such profile"
    code, out = network._run_rc(["pactl", "set-card-profile", info.card.name, profile], timeout=15)
    return code == 0, out


def set_output(
    mac: str, wait: float = 3.0, sleep: Callable[[float], None] = time.sleep
) -> tuple[bool, str]:
    """Bu cihazı varsayılan ses çıkışı yapar. Profil yeni değiştiyse çıkış birazdan belirir."""
    deadline = time.monotonic() + wait
    sink = None
    while True:
        sink = sink_for(mac, parse_sinks(_pactl("list", "short", "sinks")[0]))
        if sink or time.monotonic() >= deadline:
            break
        sleep(0.3)
    if sink is None or not _SAFE_NAME.match(sink):
        return False, "no sink"
    code, out = network._run_rc(["pactl", "set-default-sink", sink], timeout=10)
    return code == 0, out


def apply(mac: str, mode: str | None, make_output: bool) -> list[str]:
    """Seçimleri uygular; başarısız adımların adlarını döndürür (boş liste: hepsi tamam)."""
    failures: list[str] = []
    if mode is not None:
        ok, msg = set_mode(mac, mode)
        if not ok:
            failures.append(msg or "mode")
    if make_output:
        ok, msg = set_output(mac)
        if not ok:
            failures.append(msg or "output")
    return failures
