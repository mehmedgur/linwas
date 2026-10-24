"""Güç planlarının sistem tarafı (root): sysfs, power-profiles-daemon, iw, hdparm.

`linwas-power.service` bu modülü sürekli çalıştırır: `python -I -m linwas.core.power_apply`.
Yoklama yok: UPower (priz/pil, pil seviyesi) ve power-profiles-daemon (güç kipi) sinyalleri
`gdbus monitor` ile dinlenir (core/power_events.py); zamanlı planın başlangıç/bitiş anında
ve en geç 5 dakikada bir de uyanır. Takılan yeni aygıtlar için düşük seviye ayarları 10
dakikada bir yeniden uygular. Ayar değişince root helper (ya da plan değiştirici) servise
SIGUSR1 gönderir.

power-profiles-daemon (ppd) GNOME/KDE menüsündeki güç kipini sağlar ve işlemciyi kendisi
ayarlar. Hazır planlar yalnızca ppd'nin kipini seçer; GNOME menüsünden kip değişirse (ve
bunu ppd'nin "geçici tutma"sı yapmadıysa) Linwas da aynı adlı hazır plana geçer. Özel planda
"İşlemciyi Linwas yönetsin" açıksa plan etkinken ppd geçici olarak (`systemctl mask
--runtime`: yeniden başlatınca kendiliğinden kalkar) durdurulur; ppd D-Bus ile kendiliğinden
başlatılabildiği için yalnızca durdurmak yetmez.

`--switch <plan>`: etkin planı değiştirir (polkit eylemi org.linwas.power.switch; etkin oturumda
şifre sorulmaz). Plan kimliği ayar dosyasındaki planlarla doğrulanır.

Kaynaklar (Linux ABI ve kılavuz sayfaları):
- cpufreq: Documentation/admin-guide/pm/cpufreq.rst, intel_pstate.rst, amd-pstate.rst
- Çalışma zamanı güç yönetimi: sysfs-devices-power (power/control: auto | on)
- ASPM: /sys/module/pcie_aspm/parameters/policy; SATA: link_power_management_policy
- rfkill: sysfs-class-rfkill (soft); RTC uyandırma: power/wakeup (enabled | disabled)
- AMD GPU: power_dpm_force_performance_level; Intel i915: gt_max_freq_mhz, gt_RP0/RP1_freq_mhz
- iw(8) `dev <ad> set power_save on|off`; hdparm(8) -S; powerprofilesctl
- logind.conf(5) HandleLidSwitch*, HandlePowerKey; UPower.conf
"""

from __future__ import annotations

import contextlib
import json
import os
import re
import shutil
import signal
import subprocess
import sys
import threading
import time
from collections.abc import Iterable
from datetime import datetime
from pathlib import Path

from linwas.core import powerplan
from linwas.core.powerplan import AUTO, PowerConfig, PowerPlan

STATE_DIR = Path("/run/linwas-power")
STATE_FILE = STATE_DIR / "state.json"  # Linwas değiştirmeden önceki değerler
STATUS_FILE = STATE_DIR / "status.json"  # arayüz okur: etkin plan, neden, sonuçlar
PID_FILE = STATE_DIR / "pid"

LOGIND_DROPIN = Path("/etc/systemd/logind.conf.d/90-linwas-power.conf")
LEGACY_LID_DROPIN = Path("/etc/systemd/logind.conf.d/90-linwas-lid.conf")
UPOWER_CONF = Path("/etc/UPower/UPower.conf")
# Eski sürümlerin "Pil koruma" (şarj sınırı) kuralı; özellik kaldırıldı (kararlar.md, 25 Ekim 2026)
LEGACY_BATTERY_RULE = Path("/etc/udev/rules.d/90-linwas-battery.rules")

CPU = Path("/sys/devices/system/cpu")
INTEL_PSTATE = CPU / "intel_pstate"
CPUFREQ = CPU / "cpufreq"
USB_DEVICES = Path("/sys/bus/usb/devices")
PCI_DEVICES = Path("/sys/bus/pci/devices")
ASPM_POLICY = Path("/sys/module/pcie_aspm/parameters/policy")
SCSI_HOSTS = Path("/sys/class/scsi_host")
BLOCK = Path("/sys/block")
NET = Path("/sys/class/net")
RFKILL = Path("/sys/class/rfkill")
RTC = Path("/sys/class/rtc")
DRM = Path("/sys/class/drm")
BACKLIGHT = Path("/sys/class/backlight")

FALLBACK_SECONDS = 300  # sinyal gelmese de en geç bu kadar sürede bir denetle
REAPPLY_SECONDS = 600
PPD_UNIT = "power-profiles-daemon.service"
# (D-Bus adı, nesne yolu); yeni ad ppd 0.20+, eski ad bütün sürümlerde
PPD_BUSES = (
    ("org.freedesktop.UPower.PowerProfiles", "/org/freedesktop/UPower/PowerProfiles"),
    ("net.hadess.PowerProfiles", "/net/hadess/PowerProfiles"),
)
PPD_MASK_KEY = "linwas:ppd-masked"  # durum dosyasında: ppd'yi Linwas durdurdu

# Başka bir güç aracı bunları yönetiyorsa Linwas dokunmaz (kararlar.md: salt okunur)
LOW_LEVEL_SETTINGS = (
    frozenset(s.id for s in powerplan.SETTINGS if s.section in ("cpu", "devices", "wireless"))
    - {"ppd_profile"}
) | {"gpu_power"}

# (ad, systemd birimi, paket adı)
CONFLICTING_TOOLS = (
    ("TLP", "tlp.service", "tlp"),
    ("auto-cpufreq", "auto-cpufreq.service", "auto-cpufreq"),
    ("laptop-mode-tools", "laptop-mode.service", "laptop-mode-tools"),
)

_ENV = {"PATH": "/usr/sbin:/usr/bin:/sbin:/bin", "LANG": "C.UTF-8", "LC_ALL": "C.UTF-8"}


def _read(path: Path) -> str:
    try:
        return path.read_text(encoding="utf-8").strip()
    except (OSError, UnicodeDecodeError):
        return ""


def _selected(text: str) -> str:
    """ "[default] performance" gibi listelerde seçili olanı döner; liste değilse metnin kendisi."""
    m = re.search(r"\[([^\]]+)\]", text)
    return m.group(1) if m else text


def _run(cmd: list[str], timeout: int = 15) -> subprocess.CompletedProcess[str] | None:
    try:
        return subprocess.run(
            cmd, capture_output=True, text=True, timeout=timeout, shell=False, env=_ENV
        )
    except (FileNotFoundError, subprocess.TimeoutExpired):
        return None


def unit_enabled(unit: str) -> bool:
    r = _run(["systemctl", "is-enabled", unit])
    return bool(r and r.returncode == 0 and r.stdout.strip() == "enabled")


def conflicting_tools() -> list[tuple[str, str]]:
    """Etkin başka güç araçları: [(ad, paket adı)]."""
    return [(name, pkg) for name, unit, pkg in CONFLICTING_TOOLS if unit_enabled(unit)]


# --- Yazıcı: ilk değişiklikten önceki değeri saklar, "auto" olunca geri yükler ---


class _Writer:
    def __init__(self, originals: dict[str, str]) -> None:
        self.orig = originals
        self.failed = False

    def set(self, path: Path, value: str) -> bool:
        if not path.exists():
            return False
        current = _selected(_read(path))
        key = str(path)
        if key not in self.orig:
            self.orig[key] = current
        if current == value:
            return True
        try:
            path.write_text(value, encoding="utf-8")
        except OSError:
            self.failed = True
            return False
        return True

    def restore(self, paths: Iterable[Path]) -> None:
        for path in paths:
            old = self.orig.pop(str(path), None)
            if old is not None and _selected(_read(path)) != old:
                with contextlib.suppress(OSError):
                    path.write_text(old, encoding="utf-8")

    def forget(self, paths: Iterable[Path]) -> None:
        """Kayıtlı eski değeri yazmadan unutur (değeri artık ppd belirliyor)."""
        for path in paths:
            self.orig.pop(str(path), None)

    def restore_prefix(self, prefix: str) -> None:
        """Ön ekle başlayan bütün kayıtlı yolları geri yükler (artık var olmayanlar dahil)."""
        self.restore(Path(k) for k in list(self.orig) if k.startswith(prefix))


# --- Ayar uygulayıcıları: (değer, yazıcı) → desteklendiyse True ---


def _policies() -> list[Path]:
    return sorted(CPUFREQ.glob("policy[0-9]*")) if CPUFREQ.is_dir() else []


def _apply_cpu_boost(value: str, w: _Writer) -> bool:
    no_turbo = INTEL_PSTATE / "no_turbo"
    global_boost = CPUFREQ / "boost"
    per_policy = [p / "boost" for p in _policies() if (p / "boost").exists()]
    targets = (
        [(no_turbo, {"on": "0", "off": "1"})]
        if no_turbo.exists()
        else [(global_boost, {"on": "1", "off": "0"})]
        if global_boost.exists()
        else [(f, {"on": "1", "off": "0"}) for f in per_policy]
    )
    if not targets:
        return False
    for path, mapping in targets:
        if value == AUTO:
            w.restore([path])
        else:
            w.set(path, mapping[value])
    return True


def _apply_cpu_epp(value: str, w: _Writer) -> bool:
    files = [p / "energy_performance_preference" for p in _policies()]
    files = [f for f in files if f.exists()]
    if value == AUTO:
        w.restore(files)
        return bool(files)
    for f in files:
        available = _read(f.parent / "energy_performance_available_preferences").split()
        if value in available:
            w.set(f, value)
    return bool(files)


def _freq_target(policy: Path, pct: int) -> str:
    lo = int(_read(policy / "cpuinfo_min_freq") or 0)
    hi = int(_read(policy / "cpuinfo_max_freq") or 0)
    return str(max(lo, min(hi, hi * pct // 100)))


def _apply_cpu_limit(kind: str, value: str, w: _Writer) -> bool:
    """kind: "min" | "max". intel_pstate'te min/max_perf_pct, diğerlerinde scaling_*_freq."""
    pstate = INTEL_PSTATE / f"{kind}_perf_pct"
    if pstate.exists() and _read(INTEL_PSTATE / "status") != "off":
        if value == AUTO:
            w.restore([pstate])
        else:
            w.set(pstate, value)
        return True
    files = [p for p in _policies() if (p / f"scaling_{kind}_freq").exists()]
    if value == AUTO:
        w.restore(p / f"scaling_{kind}_freq" for p in files)
    else:
        for p in files:
            w.set(p / f"scaling_{kind}_freq", _freq_target(p, int(value)))
    return bool(files)


def _apply_cpu_governor(value: str, w: _Writer) -> bool:
    files = [p / "scaling_governor" for p in _policies() if (p / "scaling_governor").exists()]
    if value == AUTO:
        w.restore(files)
    else:
        for f in files:
            if value in _read(f.parent / "scaling_available_governors").split():
                w.set(f, value)
    return bool(files)


def _usb_skip(dev: Path) -> bool:
    """Fare/klavye (HID, sınıf 03) ve Bluetooth (e0) askıya alınmaz: gecikme/kopma yapar."""
    classes = {_read(i / "bInterfaceClass") for i in dev.glob(f"{dev.name}:*")}
    return bool(classes & {"03", "e0"})


def _apply_usb_autosuspend(value: str, w: _Writer) -> bool:
    if not USB_DEVICES.is_dir():
        return False
    if value == AUTO:
        w.restore_prefix(str(USB_DEVICES))
        return True
    for dev in USB_DEVICES.iterdir():
        control = dev / "power" / "control"
        if ":" in dev.name or not control.exists() or _usb_skip(dev):
            continue
        w.set(control, "auto" if value == "on" else "on")
    return True


def _pci_class(dev: Path) -> str:
    return _read(dev / "class")  # ör. 0x030000


def _apply_pci_runtime_pm(value: str, w: _Writer) -> bool:
    if not PCI_DEVICES.is_dir():
        return False
    # Ekran kartları ayrı ayarda (gpu_power)
    devices = [d for d in PCI_DEVICES.iterdir() if not _pci_class(d).startswith("0x03")]
    controls = [d / "power" / "control" for d in devices]
    if value == AUTO:
        w.restore(controls)
    else:
        for c in controls:
            w.set(c, "auto" if value == "on" else "on")
    return True


def _apply_single(path: Path, value: str, w: _Writer) -> bool:
    if not path.exists():
        return False
    if value == AUTO:
        w.restore([path])
        return True
    return w.set(path, value)


def _sata_hosts() -> list[Path]:
    if not SCSI_HOSTS.is_dir():
        return []
    return [
        h / "link_power_management_policy"
        for h in SCSI_HOSTS.iterdir()
        if (h / "link_power_management_policy").exists()
    ]


def _apply_sata_alpm(value: str, w: _Writer) -> bool:
    files = _sata_hosts()
    if value == AUTO:
        w.restore(files)
    else:
        for f in files:
            w.set(f, value)
    return bool(files)


# hdparm -S: 1–240 → ×5 sn, 241–251 → (n−240)×30 dk (hdparm(8))
_SPINDOWN = {"off": "0", "5": "60", "10": "120", "20": "240", "30": "241", "60": "242"}


def rotational_disks() -> list[str]:
    if not BLOCK.is_dir():
        return []
    return sorted(
        d.name
        for d in BLOCK.iterdir()
        if re.fullmatch(r"sd[a-z]+", d.name) and _read(d / "queue" / "rotational") == "1"
    )


def _apply_disk_spindown(value: str, w: _Writer) -> bool:
    disks = rotational_disks()
    if not disks or not shutil.which("hdparm", path=_ENV["PATH"]):
        return False
    if value == AUTO:  # hdparm eski değeri okuyamaz; dokunulmaz
        return True
    for disk in disks:
        _run(["hdparm", "-S", _SPINDOWN[value], f"/dev/{disk}"])
    return True


def wireless_interfaces() -> list[str]:
    if not NET.is_dir():
        return []
    return sorted(
        i.name for i in NET.iterdir() if (i / "wireless").exists() or (i / "phy80211").exists()
    )


def _iw_power_save(iface: str) -> str:
    r = _run(["iw", "dev", iface, "get", "power_save"])
    m = re.search(r"Power save:\s*(on|off)", r.stdout if r else "")
    return m.group(1) if m else ""


def _apply_wifi_powersave(value: str, w: _Writer) -> bool:
    ifaces = wireless_interfaces()
    if not ifaces or not shutil.which("iw", path=_ENV["PATH"]):
        return False
    for iface in ifaces:
        key = f"iw:{iface}"
        if value == AUTO:
            old = w.orig.pop(key, None)
            if old:
                _run(["iw", "dev", iface, "set", "power_save", old])
            continue
        current = _iw_power_save(iface)
        if not current:
            continue
        w.orig.setdefault(key, current)
        if current != value:
            _run(["iw", "dev", iface, "set", "power_save", value])
    return True


def _rfkill_soft(kind: str) -> list[Path]:
    if not RFKILL.is_dir():
        return []
    return [d / "soft" for d in RFKILL.iterdir() if _read(d / "type") == kind]


def _apply_bluetooth(value: str, w: _Writer) -> bool:
    files = _rfkill_soft("bluetooth")
    if value == AUTO:
        w.restore_prefix(str(RFKILL))  # yalnızca Linwas'ın kapattıkları açılır
    else:
        for f in files:
            w.set(f, "1")
    return bool(files)


def _apply_wake_timers(value: str, w: _Writer) -> bool:
    files = [r / "device" / "power" / "wakeup" for r in RTC.glob("rtc*")] if RTC.is_dir() else []
    files = [f for f in files if f.exists()]
    if value == AUTO:
        w.restore(files)
    else:
        for f in files:
            w.set(f, "enabled" if value == "on" else "disabled")
    return bool(files)


def gpu_cards() -> list[Path]:
    """drm kartları (card0, card1 …; bağlayıcılar hariç)."""
    if not DRM.is_dir():
        return []
    return sorted(c for c in DRM.iterdir() if re.fullmatch(r"card[0-9]+", c.name))


def _apply_gpu_power(value: str, w: _Writer) -> bool:
    supported = False
    for card in gpu_cards():
        vendor = _read(card / "device" / "vendor")
        amd = card / "device" / "power_dpm_force_performance_level"
        if vendor == "0x1002" and amd.exists():
            supported = True
            if value == AUTO:
                w.restore([amd])
            else:
                w.set(amd, "low" if value == "powersave" else "high")
        elif vendor == "0x8086" and (card / "gt_max_freq_mhz").exists():
            supported = True
            target = card / "gt_max_freq_mhz"
            if value == AUTO:
                w.restore([target])
            else:
                rp = "gt_RP1_freq_mhz" if value == "powersave" else "gt_RP0_freq_mhz"
                freq = _read(card / rp)
                if freq.isdigit():
                    w.set(target, freq)
        elif vendor == "0x10de" and (card / "device" / "power" / "control").exists():
            # NVIDIA: PCI çalışma zamanı güç yönetimi (kullanılmayınca kartı kapatır)
            supported = True
            control = card / "device" / "power" / "control"
            if value == AUTO:
                w.restore([control])
            else:
                w.set(control, "auto" if value == "powersave" else "on")
    return supported


def backlight_device() -> Path | None:
    """GNOME'un da seçtiği sırayla: firmware → platform → raw."""
    if not BACKLIGHT.is_dir():
        return None
    devices = [d for d in BACKLIGHT.iterdir() if (d / "max_brightness").exists()]
    order = {"firmware": 0, "platform": 1, "raw": 2}
    devices.sort(key=lambda d: (order.get(_read(d / "type"), 3), d.name))
    return devices[0] if devices else None


def _apply_brightness(value: str, w: _Writer) -> bool:
    dev = backlight_device()
    if dev is None:
        return False
    if value != AUTO:
        top = int(_read(dev / "max_brightness") or 0)
        if top > 0:
            with contextlib.suppress(OSError):
                (dev / "brightness").write_text(str(max(1, top * int(value) // 100)))
    return True


def ppd_profiles() -> list[str]:
    r = _run(["powerprofilesctl", "list"])
    if not r or r.returncode != 0:
        return []
    return re.findall(r"^\*?\s*([a-z][a-z-]*):\s*$", r.stdout, re.M)


def _apply_ppd(value: str, w: _Writer) -> bool:
    profiles = ppd_profiles()
    if value != AUTO and value in profiles:
        _run(["powerprofilesctl", "set", value])
    return bool(profiles)


def cpu_driver() -> str:
    """cpufreq sürücüsü (intel_pstate, amd-pstate-epp, acpi-cpufreq …); yoksa boş."""
    policies = _policies()
    return _read(policies[0] / "scaling_driver") if policies else ""


def ppd_installed() -> bool:
    return any(
        Path(d, PPD_UNIT).exists() for d in ("/usr/lib/systemd/system", "/lib/systemd/system")
    )


def ppd_state() -> tuple[str, bool] | None:
    """(etkin kip, geçici tutma var mı); ppd çalışmıyorsa None. Tutma: ör. GNOME pil azalınca
    Tasarruf'u geçici olarak tutar (ActiveProfileHolds)."""
    for bus, path in PPD_BUSES:
        r = _run(
            ["busctl", "get-property", bus, path, bus, "ActiveProfile", "ActiveProfileHolds"],
            timeout=5,
        )
        if not r or r.returncode != 0:
            continue
        m = re.match(r'\s*s "([a-z-]+)"\s*\n\s*aa\{sv\} (\d+)', r.stdout)
        if m:
            return m.group(1), m.group(2) != "0"
    return None


def ppd_owned_now() -> frozenset[str]:
    """ppd çalışıyorsa onun yönettiği işlemci ayarları; çalışmıyorsa boş küme."""
    if not ppd_installed() or ppd_state() is None:
        return frozenset()
    return powerplan.ppd_owned(_cpu_driver_family())


def _cpu_driver_family() -> str:
    driver = cpu_driver()
    if driver == "intel_pstate" and _read(INTEL_PSTATE / "status") == "active":
        return "intel_pstate"
    return driver


def hold_ppd(originals: dict[str, str]) -> bool:
    """ppd'yi geçici olarak durdurur (yeniden başlatınca kalkar). Durdurulduysa True."""
    if not ppd_installed():
        return False
    if originals.get(PPD_MASK_KEY) != "1":
        r = _run(["systemctl", "mask", "--runtime", "--now", "--", PPD_UNIT], timeout=30)
        if not r or r.returncode != 0:
            return False
        originals[PPD_MASK_KEY] = "1"
    return True


def release_ppd(originals: dict[str, str]) -> None:
    """Linwas durdurduysa ppd'yi yeniden açar (kip, ppd'nin kendi kaydından gelir)."""
    if originals.pop(PPD_MASK_KEY, None) != "1":
        return
    _run(["systemctl", "unmask", "--runtime", "--", PPD_UNIT], timeout=30)
    # --no-block: bilgisayar kapanırken servis dururken beklemesin (geçici kilit zaten kalkar)
    _run(["systemctl", "start", "--no-block", "--", PPD_UNIT], timeout=30)


_APPLIERS = {
    "ppd_profile": _apply_ppd,  # önce: profil EPP'yi değiştirir, sonra planın EPP'si yazılır
    "cpu_governor": _apply_cpu_governor,
    "cpu_epp": _apply_cpu_epp,
    "cpu_boost": _apply_cpu_boost,
    "cpu_max": lambda v, w: _apply_cpu_limit("max", v, w),
    "cpu_min": lambda v, w: _apply_cpu_limit("min", v, w),
    "usb_autosuspend": _apply_usb_autosuspend,
    "pci_runtime_pm": _apply_pci_runtime_pm,
    "pcie_aspm": lambda v, w: _apply_single(ASPM_POLICY, v, w),
    "sata_alpm": _apply_sata_alpm,
    "disk_spindown": _apply_disk_spindown,
    "wifi_powersave": _apply_wifi_powersave,
    "bluetooth": _apply_bluetooth,
    "wake_timers": _apply_wake_timers,
    "gpu_power": _apply_gpu_power,
    "brightness": _apply_brightness,
}


def _owned_paths(sid: str) -> list[Path]:
    """ppd'ye bırakılan ayarın, Linwas'ın daha önce yazmış olabileceği dosyaları."""
    files = {
        "cpu_epp": ["energy_performance_preference"],
        "cpu_governor": ["scaling_governor"],
        "cpu_boost": ["boost"],
        "cpu_min": ["scaling_min_freq"],
    }.get(sid, [])
    paths = [p / name for p in _policies() for name in files]
    if sid == "cpu_boost":
        paths += [INTEL_PSTATE / "no_turbo", CPUFREQ / "boost"]
    if sid == "cpu_min":
        paths.append(INTEL_PSTATE / "min_perf_pct")
    return paths


# --- Durum dosyaları ---


def _load_state() -> dict[str, str]:
    try:
        data = json.loads(STATE_FILE.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return {}
    return {k: v for k, v in data.items() if isinstance(k, str) and isinstance(v, str)}


def _write_json(path: Path, data: object) -> None:
    STATE_DIR.mkdir(parents=True, exist_ok=True)
    os.chmod(STATE_DIR, 0o755)
    tmp = path.with_suffix(".tmp")
    tmp.write_text(json.dumps(data, ensure_ascii=False), encoding="utf-8")
    os.chmod(tmp, 0o644)
    tmp.replace(path)


def apply_system(cfg: PowerConfig, plan: PowerPlan, source: str, changed: bool) -> dict[str, str]:
    """Planın sistem ayarlarını uygular. Sonuç: {ayar: "ok" | "unsupported" | "error" |
    "managed" | "ppd"} ("managed": başka güç aracı yönettiği için, "ppd": işlemciyi
    power-profiles-daemon yönettiği için dokunulmadı)."""
    conflicts = bool(conflicting_tools())
    originals = _load_state()
    w = _Writer(originals)
    results: dict[str, str] = {}
    # İşlemciyi Linwas yönetecekse ppd önce durur; yoksa (durdurulmuşsa) önce geri açılır ki
    # aşağıda kip seçilebilsin. Linwas'ın değiştirdiği işlemci değerleri "auto" ile geri döner.
    control = plan.cpu_control and not conflicts and hold_ppd(originals)
    if not control:
        release_ppd(originals)
    owned = frozenset() if control else ppd_owned_now()
    for sid, applier in _APPLIERS.items():
        spec = powerplan.SPECS[sid]
        if sid == "ppd_profile" and control:
            results[sid] = "ppd"  # ppd durduruldu; kip seçilmez
            continue
        if spec.on_change_only and not changed:
            continue
        if conflicts and sid in LOW_LEVEL_SETTINGS:
            results[sid] = "managed"
            continue
        if sid in owned:
            w.forget(_owned_paths(sid))  # ppd yeniden açılınca kendi değerini yazar
            results[sid] = "ppd"
            continue
        w.failed = False
        try:
            ok = applier(cfg.value(plan, sid, source), w)
        except (OSError, ValueError):
            ok, w.failed = True, True
        results[sid] = "unsupported" if not ok else "error" if w.failed else "ok"
    with contextlib.suppress(OSError):
        _write_json(STATE_FILE, w.orig)
    return results


def apply_once() -> dict[str, object]:
    """Etkin planı bir kez uygular, durumu yazar (servis çalışmıyorsa helper kullanır)."""
    cfg = powerplan.load_config()
    state = powerplan.read_power_state()
    plan, reason = powerplan.effective_plan(cfg, state)
    source = "ac" if state.on_ac else "bat"
    results = apply_system(cfg, plan, source, changed=True)
    status = {
        "plan": plan.id,
        "reason": reason,
        "source": source,
        "time": int(time.time()),
        "results": results,
    }
    with contextlib.suppress(OSError):
        _write_json(STATUS_FILE, status)
    return status


def read_status() -> dict[str, object]:
    """Servisin son uygulama durumu (arayüz okur; root gerekmez)."""
    try:
        data = json.loads(STATUS_FILE.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return {}
    return data if isinstance(data, dict) else {}


# --- Servis ---

SERVICE_NAME = "linwas-power.service"
# "Linwas yönetsin" ile kapatılan başka güç araçlarının birimleri (geri vermek için)
TAKEOVER_PATH = Path("/etc/linwas/power-takeover.json")
SERVICE_UNIT = Path("/usr/lib/systemd/system") / SERVICE_NAME


def _service_pid() -> int | None:
    """Çalışan servisin PID'i (PID dosyası var ve süreç gerçekten bu servisse)."""
    try:
        pid = int(_read(PID_FILE))
        cmdline = Path(f"/proc/{pid}/cmdline").read_bytes()
    except (ValueError, OSError):
        return None
    return pid if b"linwas.core.power_apply" in cmdline else None


def service_state() -> str:
    """ "missing": servis kurulu değil (ör. kaynak koddan çalıştırma), "stopped", "running"."""
    if not SERVICE_UNIT.exists():
        return "missing"
    return "running" if _service_pid() is not None else "stopped"


def notify_service() -> bool:
    """Çalışan servise "ayar değişti" der. Servis yoksa False (çağıran apply_once yapar)."""
    pid = _service_pid()
    if pid is None:
        return False
    try:
        os.kill(pid, signal.SIGUSR1)
    except OSError:
        return False
    return True


def _config_mtime() -> float:
    try:
        return powerplan.CONFIG_PATH.stat().st_mtime
    except OSError:
        return 0.0


def remove_legacy_charge_limit() -> None:
    """Eski sürüm şarj sınırı koyduysa kuralı siler ve sınırı kaldırır (%100)."""
    if not LEGACY_BATTERY_RULE.exists():
        return
    with contextlib.suppress(OSError):
        LEGACY_BATTERY_RULE.unlink()
    for limit in powerplan.POWER_SUPPLY.glob("*/charge_control_end_threshold"):
        with contextlib.suppress(OSError):
            limit.write_text("100", encoding="utf-8")


def _ensure_clock() -> None:
    from linwas.core import clock

    with contextlib.suppress(Exception):  # saat denetimi güç servisini durdurmasın
        clock.ensure()


def release_ppd_now() -> None:
    """Durum dosyasına bakarak ppd'yi geri açar (servis kapanırken, yönetimi geri verirken)."""
    originals = _load_state()
    if originals.get(PPD_MASK_KEY) != "1":
        return
    release_ppd(originals)
    with contextlib.suppress(OSError):
        _write_json(STATE_FILE, originals)


def _sync_from_menu(
    cfg: PowerConfig, plan: PowerPlan, reason: str, source: str, seen: str | None
) -> str | None:
    """GNOME/KDE menüsünden güç kipi değiştiyse etkin planı aynı adlı hazır plana geçirir.
    `seen`: son uygulamadan sonra görülen kip. Dönüş: şimdi görülen kip."""
    state = ppd_state()
    if state is None:
        return None
    profile, held = state
    want = cfg.value(plan, "ppd_profile", source)
    if (
        seen is not None
        and profile != seen
        and not held  # ör. GNOME'un düşük pil tutması: plan değişmez
        and reason == "active"  # otomatik geçiş varken menüdeki seçim geçicidir
        and want not in (AUTO, profile)
        and profile in powerplan.BUILTIN_PLANS
    ):
        cfg.active = profile
        with contextlib.suppress(OSError):
            powerplan.write_config(cfg)
    return profile


def _next_wait(cfg: PowerConfig, last_full: float) -> float:
    waits = [FALLBACK_SECONDS, max(1.0, REAPPLY_SECONDS - (time.monotonic() - last_full))]
    boundary = powerplan.seconds_to_boundary(cfg, datetime.now())
    if boundary is not None:
        waits.append(boundary + 1)
    return min(waits)


def run_service() -> None:
    from linwas.core import power_events

    wake = threading.Event()
    forced_flag = threading.Event()
    stop = threading.Event()

    def _on_usr1(*_args: object) -> None:
        forced_flag.set()
        wake.set()

    signal.signal(signal.SIGUSR1, _on_usr1)
    signal.signal(signal.SIGTERM, lambda *_: (stop.set(), wake.set()))
    STATE_DIR.mkdir(parents=True, exist_ok=True)
    os.chmod(STATE_DIR, 0o755)
    PID_FILE.write_text(str(os.getpid()), encoding="utf-8")
    # Her açılışta saat ayarını denetle (silinmişse yeniden yazılır) ve saati eşitle; ağ henüz
    # yoksa chrony ayar gereği ilk ölçümde saati kendisi atlatır (core/clock.py).
    threading.Thread(target=_ensure_clock, daemon=True).start()
    remove_legacy_charge_limit()
    watcher = power_events.EventWatcher(wake)
    watcher.start()

    last_key: tuple[object, ...] | None = None
    last_full = 0.0
    seen_profile: str | None = None
    forced = False  # SIGUSR1: ayar değişti ya da "planı yeniden uygula"
    while not stop.is_set():
        cfg = powerplan.load_config()
        state = powerplan.read_power_state()
        plan, reason = powerplan.effective_plan(cfg, state)
        source = "ac" if state.on_ac else "bat"
        if not forced and last_key is not None:
            seen_profile = _sync_from_menu(cfg, plan, reason, source, seen_profile)
            if cfg.active != plan.id and reason == "active":
                plan, reason = powerplan.effective_plan(cfg, state)
        key = (plan.id, source, _config_mtime())
        changed = forced or key != last_key
        now = time.monotonic()
        if changed or now - last_full >= REAPPLY_SECONDS:
            results = apply_system(cfg, plan, source, changed)
            status = {
                "plan": plan.id,
                "reason": reason,
                "source": source,
                "time": int(time.time()),
                "results": {**read_status().get("results", {}), **results},  # type: ignore[dict-item]
            }
            with contextlib.suppress(OSError):
                _write_json(STATUS_FILE, status)
            last_key, last_full = key, now
            seen_profile = (ppd_state() or (None, False))[0]
        power_events.wait(wake, _next_wait(cfg, last_full))
        forced = forced_flag.is_set()
        forced_flag.clear()
    watcher.stop()
    # Servis kapanırken (ör. "Yönetimi geri ver") ppd'yi Linwas durdurduysa geri aç
    release_ppd_now()
    with contextlib.suppress(OSError):
        PID_FILE.unlink()


def switch_plan(plan_id: str) -> int:
    """Etkin planı değiştirir (pkexec, org.linwas.power.switch). Çıkış kodu döner."""
    cfg = powerplan.load_config()
    if cfg.plan(plan_id) is None:
        print(f"unknown plan: {plan_id!r}", file=sys.stderr)
        return 2
    if cfg.active != plan_id:
        cfg.active = plan_id
        powerplan.write_config(cfg)
    if not notify_service():
        apply_once()
    return 0


# --- logind ve UPower (root helper, ayar kaydedilince) ---

_LOGIND_POWER_KEY = {"suspend": "suspend", "hibernate": "hibernate", "nothing": "ignore"}


def logind_dropin_text(cfg: PowerConfig) -> str:
    """Düğmeler ve kapak için logind ek ayarı; hepsi "auto" ise boş metin."""
    g = cfg.globals
    lines: list[str] = []
    lid = g.get("lid", {})
    if lid.get("bat", AUTO) != AUTO:
        lines.append(f"HandleLidSwitch={lid['bat']}")
    if lid.get("ac", AUTO) != AUTO:
        lines.append(f"HandleLidSwitchExternalPower={lid['ac']}")
    docked = g.get("lid_docked", {}).get("ac", AUTO)
    if docked != AUTO:
        lines.append(f"HandleLidSwitchDocked={docked}")
    key = g.get("power_key", {}).get("ac", AUTO)
    if key in _LOGIND_POWER_KEY:
        lines.append(f"HandlePowerKey={_LOGIND_POWER_KEY[key]}")
    if not lines:
        return ""
    return (
        "# Linwas tarafından yazıldı (Güç › Düğmeler ve kapak)\n[Login]\n" + "\n".join(lines) + "\n"
    )


def write_logind(cfg: PowerConfig) -> None:
    """Açılışta geçerli olur (systemd-logind çalışırken yeniden yüklenmez)."""
    text = logind_dropin_text(cfg)
    LEGACY_LID_DROPIN.unlink(missing_ok=True)
    if not text:
        LOGIND_DROPIN.unlink(missing_ok=True)
        return
    if _read(LOGIND_DROPIN) == text.strip():
        return
    LOGIND_DROPIN.parent.mkdir(parents=True, exist_ok=True)
    LOGIND_DROPIN.write_text(text, encoding="utf-8")
    LOGIND_DROPIN.chmod(0o644)


# UPower'ın kendi varsayılanları (dosyada anahtar yoksa)
_UPOWER_DEFAULTS = {"PercentageLow": "20", "PercentageCritical": "5", "PercentageAction": "2"}

_UPOWER_KEYS = {
    "battery_low": "PercentageLow",
    "battery_critical": "PercentageCritical",
    "battery_action_level": "PercentageAction",
    "battery_action": "CriticalPowerAction",
}


def upower_conf_text(current: str, cfg: PowerConfig) -> str:
    """UPower.conf'taki ilgili anahtarları değiştirir; diğer satırlar korunur.
    "auto" olan anahtara dokunulmaz. Seviyeler düşük > kritik > eylem sırasında olmalı."""
    wanted = {
        key: cfg.globals[sid]["ac"]
        for sid, key in _UPOWER_KEYS.items()
        if cfg.globals.get(sid, {}).get("ac", AUTO) != AUTO
    }
    if not wanted:
        return current
    if any(k.startswith("Percentage") for k in wanted):
        wanted["UsePercentageForPolicy"] = "true"
    existing = dict(re.findall(r"^\s*(\w+)\s*=\s*(\S*)\s*$", current, re.M))
    merged = {**_UPOWER_DEFAULTS, **existing, **wanted}
    try:
        levels = [int(merged[k]) for k in _UPOWER_DEFAULTS]
    except ValueError:
        levels = []
    if levels and not levels[0] > levels[1] > levels[2]:
        raise powerplan.PowerConfigError("battery levels must be low > critical > action")
    out: list[str] = []
    in_section = False
    seen: set[str] = set()
    for line in current.splitlines():
        stripped = line.strip()
        if stripped.startswith("["):
            if in_section:  # bölüm biterken eksik anahtarlar eklenir
                out.extend(f"{k}={v}" for k, v in wanted.items() if k not in seen)
                seen.update(wanted)
            in_section = stripped == "[UPower]"
        m = re.match(r"^\s*(\w+)\s*=", line)
        if in_section and m and m.group(1) in wanted:
            out.append(f"{m.group(1)}={wanted[m.group(1)]}")
            seen.add(m.group(1))
            continue
        out.append(line)
    if not any(line.strip() == "[UPower]" for line in current.splitlines()):
        out.append("[UPower]")
        in_section = True
    if in_section:
        out.extend(f"{k}={v}" for k, v in wanted.items() if k not in seen)
    return "\n".join(out) + "\n"


def check_upower(cfg: PowerConfig) -> None:
    """Pil seviyeleri tutarsızsa PowerConfigError."""
    upower_conf_text(_read(UPOWER_CONF) + "\n", cfg)


def write_upower(cfg: PowerConfig) -> bool:
    """Değiştiyse UPower.conf'u yazar ve upower'ı yeniden başlatır. Değiştiyse True."""
    current = _read(UPOWER_CONF)
    new = upower_conf_text(current + "\n" if current else "", cfg)
    if new.strip() == current.strip():
        return False
    UPOWER_CONF.parent.mkdir(parents=True, exist_ok=True)
    UPOWER_CONF.write_text(new, encoding="utf-8")
    UPOWER_CONF.chmod(0o644)
    _run(["systemctl", "try-restart", "upower.service"], timeout=30)
    return True


def main(argv: list[str]) -> int:
    if os.geteuid() != 0:
        print("root gerekli", file=sys.stderr)
        return 1
    if len(argv) == 2 and argv[0] == "--switch":
        return switch_plan(argv[1])
    if argv == ["--apply-once"]:
        apply_once()
        return 0
    if not argv:
        run_service()
        return 0
    print("kullanım: power_apply [--switch PLAN | --apply-once]", file=sys.stderr)
    return 2


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
