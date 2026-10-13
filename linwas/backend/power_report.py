"""Güç tanılama raporu (Windows'taki `powercfg /energy` benzeri; kullanıcı yetkisiyle).

Toplananlar: pil (sağlık, döngü, anlık tüketim), etkin plan ve servis durumu, çok işlemci
kullanan süreçler (2 sn örnek), uyandırabilen aygıtlar, çakışan güç araçları, hazırda bekletme.
powertop raporu varsa (root işlemi `power.powertop_report`) ayrıntı olarak eklenir.

Bulgular kod + parametre olarak döner; metinleri arayüz çevirir. Düzeltilebilen bulgunun
`fix` alanı: ("task", işlem adı, parametreler) ya da ("ui", eylem adı).
"""

from __future__ import annotations

import os
import time
from dataclasses import dataclass, field
from pathlib import Path

from linwas.backend import power, power_support
from linwas.backend.driver_health import _package_available
from linwas.backend.drivers import dpkg_installed
from linwas.core import power_apply, powerplan
from linwas.core.powerplan import AUTO

POWERTOP_CSV = Path("/var/lib/linwas-power/powertop.csv")
SAMPLE_SECONDS = 2.0
BUSY_PERCENT = 20.0  # bir çekirdeğin yüzdesi


@dataclass
class Finding:
    level: str  # "error" | "warning" | "suggestion" | "info"
    code: str
    params: dict[str, str] = field(default_factory=dict)
    fix: tuple = ()


@dataclass
class Process:
    pid: int
    name: str
    cpu: float  # bir çekirdeğin yüzdesi


@dataclass
class PowerReport:
    time: float
    laptop: bool
    batteries: list[power.Battery]
    watts: float | None  # pilde anlık tüketim
    plan_id: str
    plan_name: str  # özel planın adı; yerleşikte boş
    source: str
    service_running: bool
    processes: list[Process]
    wake_devices: list[str]
    findings: list[Finding]
    powertop: dict[str, list[list[str]]]  # bölüm → satırlar


def _read(path: Path) -> str:
    try:
        return path.read_text(encoding="utf-8").strip()
    except (OSError, UnicodeDecodeError):
        return ""


def _discharge_watts() -> float | None:
    root = powerplan.POWER_SUPPLY
    if not root.is_dir():
        return None
    total = 0.0
    found = False
    for bat in root.iterdir():
        if _read(bat / "type") != "Battery" or _read(bat / "status") != "Discharging":
            continue
        power_now = _read(bat / "power_now")  # µW
        if power_now.isdigit():
            total += int(power_now) / 1_000_000
            found = True
            continue
        current, voltage = _read(bat / "current_now"), _read(bat / "voltage_now")  # µA, µV
        if current.isdigit() and voltage.isdigit():
            total += int(current) * int(voltage) / 1e12
            found = True
    return round(total, 1) if found else None


def _proc_times() -> dict[int, tuple[str, int]]:
    out: dict[int, tuple[str, int]] = {}
    for d in Path("/proc").iterdir():
        if not d.name.isdigit():
            continue
        stat = _read(d / "stat")
        # comm parantez içinde ve boşluk içerebilir: son ")" sonrası alanlar
        end = stat.rfind(")")
        if end < 0:
            continue
        name = stat[stat.find("(") + 1 : end]
        fields = stat[end + 2 :].split()
        if len(fields) > 12:
            out[int(d.name)] = (name, int(fields[11]) + int(fields[12]))  # utime + stime
    return out


def busy_processes(seconds: float = SAMPLE_SECONDS) -> list[Process]:
    hz = os.sysconf("SC_CLK_TCK")
    before = _proc_times()
    time.sleep(seconds)
    after = _proc_times()
    result = []
    for pid, (name, ticks) in after.items():
        if pid in before:
            cpu = (ticks - before[pid][1]) / hz / seconds * 100
            if cpu >= 1:
                result.append(Process(pid, name, round(cpu, 1)))
    result.sort(key=lambda p: p.cpu, reverse=True)
    return result[:10]


def wake_devices() -> list[str]:
    """ACPI'de uyandırması açık aygıtlar (/proc/acpi/wakeup, "*enabled")."""
    devices = []
    for line in _read(Path("/proc/acpi/wakeup")).splitlines()[1:]:
        parts = line.split()
        if len(parts) >= 3 and parts[2] == "*enabled":
            sysfs = parts[3] if len(parts) > 3 else ""
            devices.append(f"{parts[0]} {sysfs}".strip())
    return devices


def parse_powertop_csv(text: str) -> dict[str, list[list[str]]]:
    """powertop --csv çıktısı: "____" çizgileriyle ayrılmış bölümler, alanlar ";" ile ayrılır.
    Biçim sürümden sürüme değişebildiği için yalnızca bölüm adı + satırlar alınır."""
    sections: dict[str, list[list[str]]] = {}
    current = ""
    for raw in text.splitlines():
        line = raw.strip()
        if not line or set(line) <= {"_", "*", " "}:
            continue
        if line.startswith("*") and line.endswith("*"):
            current = line.strip("* ").strip()
            sections.setdefault(current, [])
            continue
        if current and ";" in line:
            sections[current].append([c.strip() for c in line.split(";") if c.strip()])
    return {k: v[:30] for k, v in sections.items() if v}


def collect() -> PowerReport:
    batteries = power.list_batteries()
    laptop = bool(batteries)
    support = power_support.detect(laptop)
    cfg = powerplan.load_config()
    state = powerplan.read_power_state()
    plan, _reason = powerplan.effective_plan(cfg, state)
    source = "ac" if state.on_ac else "bat"
    status = power_apply.read_status()
    processes = busy_processes()
    wakes = wake_devices()
    findings: list[Finding] = []

    # Servis
    service = power_apply.service_state()
    installed = service != "missing"
    running = service == "running" and bool(status)
    if installed and not running:
        findings.append(
            Finding(
                "error",
                "service_stopped",
                fix=(
                    "task",
                    [
                        ("service.enable", {"name": "linwas-power.service"}),
                        ("service.restart", {"name": "linwas-power.service"}),
                    ],
                ),
            )
        )
    errors = [k for k, v in dict(status.get("results", {})).items() if v == "error"]
    if errors:
        findings.append(Finding("warning", "apply_errors", {"settings": ",".join(errors)}))

    # Çakışan araçlar
    for tool in support.conflicts:
        fix: tuple = ()
        if tool.removable == "apt":
            fix = ("task", [("package.remove", {"name": tool.package})])
        elif tool.removable == "snap":
            fix = ("task", [("app.remove_snap", {"name": tool.package})])
        findings.append(Finding("error", "conflict", {"name": tool.name}, fix))

    # Pil
    for bat in batteries:
        if bat.health is not None and bat.health < 60:
            findings.append(Finding("warning", "battery_worn", {"n": str(bat.health)}))
        elif bat.health is not None and bat.health < 80:
            findings.append(Finding("info", "battery_aging", {"n": str(bat.health)}))
        if bat.charge_limit == 100 and state.on_ac:
            findings.append(Finding("suggestion", "charge_limit", fix=("ui", "charge_limit")))
    watts = _discharge_watts()
    if watts is not None and watts >= 20:
        findings.append(Finding("warning", "high_drain", {"w": str(watts)}))

    # Süreçler
    for proc in processes:
        if proc.cpu >= BUSY_PERCENT:
            findings.append(
                Finding("warning", "busy_process", {"name": proc.name, "cpu": str(proc.cpu)})
            )

    # Plan önerileri (dizüstünde pilde)
    if laptop:

        def bat_value(sid: str) -> str:
            return cfg.value(plan, sid, "bat")

        unsupported = support.unsupported
        if not cfg.battery_saver.enabled:
            findings.append(Finding("suggestion", "battery_saver_off", fix=("ui", "automation")))
        for sid in ("usb_autosuspend", "wifi_powersave", "pci_runtime_pm"):
            if sid not in unsupported and bat_value(sid) != "on":
                findings.append(Finding("suggestion", f"bat_{sid}", fix=("ui", "advanced")))
        bright = bat_value("brightness")
        if "brightness" not in unsupported and bright != AUTO and int(bright) > 70:
            findings.append(Finding("suggestion", "bat_brightness", {"n": bright}))

    if (
        "ppd_profile" in support.unsupported
        and not support.conflicts
        and _package_available("power-profiles-daemon")
    ):
        findings.append(
            Finding(
                "suggestion",
                "install_ppd",
                fix=("task", [("package.install", {"name": "power-profiles-daemon"})]),
            )
        )
    if not support.hibernate.available:
        findings.append(
            Finding("info", "no_hibernate", {"reasons": ",".join(support.hibernate.reasons)})
        )
    if len(wakes) > 3:
        findings.append(Finding("info", "many_wake_devices", {"n": str(len(wakes))}))

    if not dpkg_installed("powertop") and _package_available("powertop"):
        findings.append(
            Finding(
                "suggestion",
                "install_powertop",
                fix=("task", [("package.install", {"name": "powertop"})]),
            )
        )

    order = {"error": 0, "warning": 1, "suggestion": 2, "info": 3}
    findings.sort(key=lambda f: order[f.level])
    try:
        powertop = parse_powertop_csv(POWERTOP_CSV.read_text(encoding="utf-8", errors="replace"))
    except OSError:
        powertop = {}
    return PowerReport(
        time=time.time(),
        laptop=laptop,
        batteries=batteries,
        watts=watts,
        plan_id=plan.id,
        plan_name=plan.name,
        source=source,
        service_running=running,
        processes=processes,
        wake_devices=wakes,
        findings=findings,
        powertop=powertop,
    )
