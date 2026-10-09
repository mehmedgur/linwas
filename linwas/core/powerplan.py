"""Güç planları: ayar kataloğu, plan modeli, doğrulama ve etkin planın seçimi (kararlar.md ›
Yeni özellikler › Güç ve pil › Gelişmiş güç seçenekleri).

Ayar dosyası `/etc/linwas/power.json` (herkes okur, yalnızca root helper yazar). Sistem tarafını
`linwas-power.service` (core/power_apply.py, root), masaüstü tarafını oturumdaki ajan
(core/power_agent.py, kullanıcı) uygular. Bu modül Qt'ye ve donanıma bağımlı değildir.

Her ayarın Prizde ("ac") ve Pilde ("bat") ayrı değeri vardır. "auto" = Linwas dokunmaz
(sistem/masaüstü varsayılanı; daha önce Linwas değiştirdiyse eski değer geri yüklenir).
"""

from __future__ import annotations

import copy
import json
import os
import re
from dataclasses import dataclass, field
from datetime import datetime, time
from pathlib import Path
from typing import Any

CONFIG_PATH = Path("/etc/linwas/power.json")
CONFIG_VERSION = 1
SOURCES = ("ac", "bat")
AUTO = "auto"

BUILTIN_PLANS = ("power-saver", "balanced", "performance")
DEFAULT_PLAN = "balanced"
MAX_CUSTOM_PLANS = 10
MAX_NAME_LEN = 40

# Bölümler (arayüzdeki sıra)
SECTIONS = (
    "display",  # Ekran ve uyku
    "buttons",  # Düğmeler ve kapak (tüm planlar)
    "cpu",  # İşlemci
    "battery",  # Pil (tüm planlar)
    "devices",  # USB / PCIe / disk
    "wireless",  # Kablosuz
    "graphics",  # Ekran kartı ve parlaklık
)

_MINUTES = ("1", "2", "3", "5", "10", "15", "20", "30", "45", "60", "90", "120")
_PERCENTS = tuple(str(n) for n in range(0, 101, 5))
_LEVELS = tuple(str(n) for n in range(1, 51))


@dataclass(frozen=True)
class SettingSpec:
    id: str
    section: str
    values: tuple[str, ...]  # "auto" hariç izinli değerler
    scope: str  # "system" (root servis) | "user" (masaüstü ajanı) | "logind" | "upower"
    per_plan: bool = True  # False: tüm planlar için tek değer (Düğmeler, Pil)
    split: bool = True  # False: prizde/pilde ayrımı yok (tek değer, ikisine de yazılır)
    laptop_only: bool = False
    # Değerin yalnızca plan ya da priz/pil değişiminde uygulanması (kullanıcının sonradan yaptığı
    # değişikliği ezmemek için; ör. parlaklık, sistem güç profili)
    on_change_only: bool = False


SETTINGS: tuple[SettingSpec, ...] = (
    # Sistem güç profili (power-profiles-daemon)
    SettingSpec(
        "ppd_profile",
        "cpu",
        ("power-saver", "balanced", "performance"),
        "system",
        on_change_only=True,
    ),
    # Ekran ve uyku
    SettingSpec("screen_dim", "display", ("on", "off"), "user"),
    SettingSpec("screen_off", "display", ("never", *_MINUTES), "user"),
    SettingSpec("sleep_after", "display", ("never", *_MINUTES), "user"),
    SettingSpec("sleep_action", "display", ("suspend", "hibernate"), "user"),
    SettingSpec("wake_timers", "display", ("on", "off"), "system"),
    # Düğmeler ve kapak (logind; açılışta geçerli)
    SettingSpec(
        "lid",
        "buttons",
        ("suspend", "hibernate", "hybrid-sleep", "lock", "ignore", "poweroff"),
        "logind",
        per_plan=False,
        laptop_only=True,
    ),
    SettingSpec(
        "lid_docked",
        "buttons",
        ("suspend", "hibernate", "lock", "ignore"),
        "logind",
        per_plan=False,
        split=False,
        laptop_only=True,
    ),
    SettingSpec(
        "power_key",
        "buttons",
        ("interactive", "suspend", "hibernate", "nothing"),
        "logind",
        per_plan=False,
        split=False,
    ),
    # İşlemci
    SettingSpec("cpu_boost", "cpu", ("on", "off"), "system"),
    SettingSpec(
        "cpu_epp",
        "cpu",
        ("performance", "balance_performance", "balance_power", "power"),
        "system",
    ),
    SettingSpec("cpu_min", "cpu", _PERCENTS, "system"),
    SettingSpec("cpu_max", "cpu", _PERCENTS, "system"),
    SettingSpec(
        "cpu_governor",
        "cpu",
        ("powersave", "performance", "schedutil", "ondemand", "conservative"),
        "system",
    ),
    # Pil (UPower; tüm planlar)
    SettingSpec(
        "battery_low", "battery", _LEVELS, "upower", per_plan=False, split=False, laptop_only=True
    ),
    SettingSpec(
        "battery_critical",
        "battery",
        _LEVELS,
        "upower",
        per_plan=False,
        split=False,
        laptop_only=True,
    ),
    SettingSpec(
        "battery_action_level",
        "battery",
        _LEVELS,
        "upower",
        per_plan=False,
        split=False,
        laptop_only=True,
    ),
    SettingSpec(
        "battery_action",
        "battery",
        ("HybridSleep", "Hibernate", "PowerOff"),
        "upower",
        per_plan=False,
        split=False,
        laptop_only=True,
    ),
    # USB / PCIe / disk
    SettingSpec("usb_autosuspend", "devices", ("on", "off"), "system"),
    SettingSpec(
        "pcie_aspm", "devices", ("default", "performance", "powersave", "powersupersave"), "system"
    ),
    SettingSpec("pci_runtime_pm", "devices", ("on", "off"), "system"),
    SettingSpec(
        "sata_alpm",
        "devices",
        ("max_performance", "medium_power", "med_power_with_dipm", "min_power"),
        "system",
    ),
    SettingSpec("disk_spindown", "devices", ("off", "5", "10", "20", "30", "60"), "system"),
    # Kablosuz
    SettingSpec("wifi_powersave", "wireless", ("on", "off"), "system"),
    SettingSpec("bluetooth", "wireless", ("off",), "system"),
    # Ekran kartı ve parlaklık
    SettingSpec("gpu_power", "graphics", ("powersave", "performance"), "system"),
    SettingSpec(
        "brightness",
        "graphics",
        tuple(str(n) for n in range(10, 101, 10)),
        "system",
        on_change_only=True,
        laptop_only=True,
    ),
    SettingSpec("adaptive_brightness", "graphics", ("on", "off"), "user"),
)

SPECS: dict[str, SettingSpec] = {s.id: s for s in SETTINGS}


def _all(value: str) -> dict[str, str]:
    return {"ac": value, "bat": value}


def _vals(ac: str, bat: str) -> dict[str, str]:
    return {"ac": ac, "bat": bat}


# Fabrika değerleri; listede olmayan ayar "auto". Güvenli kalmak için riskli ayarlar
# (ASPM powersupersave, disk kapanma, Bluetooth) varsayılan planlarda kullanılmaz.
_FACTORY: dict[str, dict[str, dict[str, str]]] = {
    "power-saver": {
        "ppd_profile": _all("power-saver"),
        "screen_off": _vals("10", "5"),
        "sleep_after": _vals("30", "15"),
        "cpu_boost": _vals("auto", "off"),
        "usb_autosuspend": _vals("auto", "on"),
        "pci_runtime_pm": _vals("auto", "on"),
        "sata_alpm": _vals("auto", "med_power_with_dipm"),
        "wifi_powersave": _vals("auto", "on"),
        "gpu_power": _vals("auto", "powersave"),
        "brightness": _vals("auto", "50"),
    },
    "balanced": {
        "ppd_profile": _all("balanced"),
    },
    "performance": {
        "ppd_profile": _all("performance"),
        "cpu_boost": _all("on"),
        "sata_alpm": _vals("max_performance", "auto"),
        "wifi_powersave": _vals("off", "auto"),
    },
}

_FACTORY_GLOBALS: dict[str, dict[str, str]] = {}  # hepsi "auto": sistemin kendi ayarı


class PowerConfigError(ValueError):
    pass


@dataclass
class PowerPlan:
    id: str
    name: str = ""  # yerleşik planlarda boş (arayüz çevirir)
    builtin: bool = False
    values: dict[str, dict[str, str]] = field(default_factory=dict)

    def get(self, setting: str, source: str) -> str:
        return self.values.get(setting, {}).get(source, AUTO)


@dataclass
class Schedule:
    enabled: bool = False
    start: str = "22:00"
    end: str = "07:00"
    plan: str = "power-saver"


@dataclass
class BatterySaver:
    enabled: bool = False
    threshold: int = 20
    plan: str = "power-saver"


@dataclass
class PowerConfig:
    active: str = DEFAULT_PLAN
    plans: list[PowerPlan] = field(default_factory=list)
    globals: dict[str, dict[str, str]] = field(default_factory=dict)
    schedule: Schedule = field(default_factory=Schedule)
    battery_saver: BatterySaver = field(default_factory=BatterySaver)

    def plan(self, plan_id: str) -> PowerPlan | None:
        return next((p for p in self.plans if p.id == plan_id), None)

    def value(self, plan: PowerPlan, setting: str, source: str) -> str:
        spec = SPECS[setting]
        if not spec.per_plan:
            return self.globals.get(setting, {}).get(source, AUTO)
        return plan.get(setting, source)


# --- Fabrika değerleri ---


def factory_plan(plan_id: str) -> PowerPlan:
    return PowerPlan(id=plan_id, builtin=True, values=copy.deepcopy(_FACTORY.get(plan_id, {})))


def default_config() -> PowerConfig:
    return PowerConfig(
        plans=[factory_plan(p) for p in BUILTIN_PLANS],
        globals=copy.deepcopy(_FACTORY_GLOBALS),
    )


def reset_plan(cfg: PowerConfig, plan_id: str) -> None:
    """Yerleşik planı fabrika değerine döndürür; özel planda yalnızca değerleri siler."""
    plan = cfg.plan(plan_id)
    if plan is None:
        return
    plan.values = copy.deepcopy(_FACTORY.get(plan_id, {})) if plan.builtin else {}


def new_custom_plan(cfg: PowerConfig, name: str, based_on: str) -> PowerPlan:
    customs = [p for p in cfg.plans if not p.builtin]
    if len(customs) >= MAX_CUSTOM_PLANS:
        raise PowerConfigError("too many plans")
    used = {p.id for p in cfg.plans}
    n = 1
    while f"custom-{n}" in used:
        n += 1
    base = cfg.plan(based_on)
    plan = PowerPlan(
        id=f"custom-{n}",
        name=_clean_name(name),
        values=copy.deepcopy(base.values) if base else {},
    )
    cfg.plans.append(plan)
    return plan


def delete_plan(cfg: PowerConfig, plan_id: str) -> None:
    plan = cfg.plan(plan_id)
    if plan is None or plan.builtin:
        return
    cfg.plans.remove(plan)
    if cfg.active == plan_id:
        cfg.active = DEFAULT_PLAN
    if cfg.schedule.plan == plan_id:
        cfg.schedule.plan = "power-saver"
    if cfg.battery_saver.plan == plan_id:
        cfg.battery_saver.plan = "power-saver"


# --- Doğrulama ---

_RE_PLAN_ID = re.compile(r"^(power-saver|balanced|performance|custom-[1-9][0-9]?)$")
_RE_CLOCK = re.compile(r"^([01][0-9]|2[0-3]):[0-5][0-9]$")


def _clean_name(name: Any) -> str:
    if not isinstance(name, str):
        raise PowerConfigError("plan name must be text")
    name = " ".join(name.split())
    if not name or len(name) > MAX_NAME_LEN or any(ord(c) < 32 for c in name):
        raise PowerConfigError("invalid plan name")
    return name


def _check_values(raw: Any, per_plan: bool) -> dict[str, dict[str, str]]:
    if not isinstance(raw, dict):
        raise PowerConfigError("values must be an object")
    out: dict[str, dict[str, str]] = {}
    for sid, pair in raw.items():
        spec = SPECS.get(sid)
        if spec is None or spec.per_plan != per_plan:
            raise PowerConfigError(f"unknown setting: {sid!r}")
        if not isinstance(pair, dict) or set(pair) - set(SOURCES):
            raise PowerConfigError(f"invalid value for {sid!r}")
        clean: dict[str, str] = {}
        for src in SOURCES:
            v = pair.get(src, AUTO)
            if v != AUTO and v not in spec.values:
                raise PowerConfigError(f"invalid value for {sid!r}: {v!r}")
            clean[src] = v
        if not spec.split:
            clean["bat"] = clean["ac"]
        if clean != _all(AUTO):
            out[sid] = clean
    return out


def _check_plan_ref(value: Any, ids: set[str]) -> str:
    if not isinstance(value, str) or value not in ids:
        raise PowerConfigError(f"unknown plan: {value!r}")
    return value


def config_from_dict(data: Any) -> PowerConfig:
    """Sözlükten katı doğrulamayla ayar üretir (root helper ve içe aktarma bunu kullanır)."""
    if not isinstance(data, dict):
        raise PowerConfigError("config must be an object")
    raw_plans = data.get("plans")
    if not isinstance(raw_plans, list) or len(raw_plans) > len(BUILTIN_PLANS) + MAX_CUSTOM_PLANS:
        raise PowerConfigError("invalid plan list")
    plans: list[PowerPlan] = []
    for raw in raw_plans:
        if not isinstance(raw, dict):
            raise PowerConfigError("invalid plan")
        pid = raw.get("id")
        if not isinstance(pid, str) or not _RE_PLAN_ID.match(pid):
            raise PowerConfigError(f"invalid plan id: {pid!r}")
        if any(p.id == pid for p in plans):
            raise PowerConfigError(f"duplicate plan id: {pid!r}")
        builtin = pid in BUILTIN_PLANS
        plans.append(
            PowerPlan(
                id=pid,
                name="" if builtin else _clean_name(raw.get("name")),
                builtin=builtin,
                values=_check_values(raw.get("values", {}), per_plan=True),
            )
        )
    # Yerleşik planlar her zaman var
    for pid in BUILTIN_PLANS:
        if not any(p.id == pid for p in plans):
            plans.append(factory_plan(pid))
    plans.sort(key=lambda p: (not p.builtin, BUILTIN_PLANS.index(p.id) if p.builtin else 0))
    ids = {p.id for p in plans}

    sched_raw = data.get("schedule", {})
    saver_raw = data.get("battery_saver", {})
    if not isinstance(sched_raw, dict) or not isinstance(saver_raw, dict):
        raise PowerConfigError("invalid automation settings")
    start = sched_raw.get("start", "22:00")
    end = sched_raw.get("end", "07:00")
    if not (isinstance(start, str) and _RE_CLOCK.match(start)) or not (
        isinstance(end, str) and _RE_CLOCK.match(end)
    ):
        raise PowerConfigError("invalid schedule time")
    threshold = saver_raw.get("threshold", 20)
    if not isinstance(threshold, int) or isinstance(threshold, bool) or not 5 <= threshold <= 50:
        raise PowerConfigError("invalid battery saver threshold")
    return PowerConfig(
        active=_check_plan_ref(data.get("active", DEFAULT_PLAN), ids),
        plans=plans,
        globals=_check_values(data.get("globals", {}), per_plan=False),
        schedule=Schedule(
            enabled=sched_raw.get("enabled", False) is True,
            start=start,
            end=end,
            plan=_check_plan_ref(sched_raw.get("plan", "power-saver"), ids),
        ),
        battery_saver=BatterySaver(
            enabled=saver_raw.get("enabled", False) is True,
            threshold=threshold,
            plan=_check_plan_ref(saver_raw.get("plan", "power-saver"), ids),
        ),
    )


def config_to_dict(cfg: PowerConfig) -> dict[str, Any]:
    return {
        "version": CONFIG_VERSION,
        "active": cfg.active,
        "plans": [
            {"id": p.id, **({} if p.builtin else {"name": p.name}), "values": p.values}
            for p in cfg.plans
        ],
        "globals": cfg.globals,
        "schedule": vars(cfg.schedule).copy(),
        "battery_saver": vars(cfg.battery_saver).copy(),
    }


def dumps(cfg: PowerConfig) -> str:
    return json.dumps(config_to_dict(cfg), ensure_ascii=False, sort_keys=True)


def loads(text: str) -> PowerConfig:
    try:
        data = json.loads(text)
    except json.JSONDecodeError as exc:
        raise PowerConfigError(f"invalid JSON: {exc}") from exc
    return config_from_dict(data)


def load_config(path: Path = CONFIG_PATH) -> PowerConfig:
    """Ayar dosyası yoksa ya da bozuksa fabrika ayarı döner."""
    try:
        return loads(path.read_text(encoding="utf-8"))
    except (OSError, UnicodeDecodeError, PowerConfigError):
        return default_config()


def write_config(cfg: PowerConfig, path: Path = CONFIG_PATH) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    os.chmod(path.parent, 0o755)
    tmp = path.with_suffix(".tmp")
    tmp.write_text(
        json.dumps(config_to_dict(cfg), ensure_ascii=False, indent=2) + "\n", encoding="utf-8"
    )
    os.chmod(tmp, 0o644)
    tmp.replace(path)


# --- Dışa / içe aktarma (tek plan) ---

EXPORT_KIND = "linwas-power-plan"


def export_plan(cfg: PowerConfig, plan_id: str, name: str) -> str:
    plan = cfg.plan(plan_id)
    if plan is None:
        raise PowerConfigError("unknown plan")
    return json.dumps(
        {"kind": EXPORT_KIND, "version": CONFIG_VERSION, "name": name, "values": plan.values},
        ensure_ascii=False,
        indent=2,
    )


def import_plan(cfg: PowerConfig, text: str, default_name: str) -> PowerPlan:
    """Dosyadaki planı yeni özel plan olarak ekler; desteklenmeyen ayar varsa hata."""
    try:
        data = json.loads(text)
    except json.JSONDecodeError as exc:
        raise PowerConfigError(f"invalid JSON: {exc}") from exc
    if not isinstance(data, dict) or data.get("kind") != EXPORT_KIND:
        raise PowerConfigError("not a Linwas power plan file")
    values = _check_values(data.get("values", {}), per_plan=True)
    plan = new_custom_plan(cfg, data.get("name") or default_name, based_on="")
    plan.values = values
    return plan


# --- Etkin plan ---


@dataclass(frozen=True)
class PowerState:
    on_ac: bool
    battery_percent: int | None  # pil yoksa None


def _in_window(now: time, start: str, end: str) -> bool:
    s = time.fromisoformat(start)
    e = time.fromisoformat(end)
    if s == e:
        return False
    if s < e:
        return s <= now < e
    return now >= s or now < e  # gece yarısını aşan aralık


def effective_plan(
    cfg: PowerConfig, state: PowerState, now: datetime | None = None
) -> tuple[PowerPlan, str]:
    """(uygulanacak plan, neden). Neden: "battery_saver" | "schedule" | "active"."""
    saver = cfg.battery_saver
    if (
        saver.enabled
        and not state.on_ac
        and state.battery_percent is not None
        and state.battery_percent <= saver.threshold
        and cfg.plan(saver.plan)
    ):
        return cfg.plan(saver.plan), "battery_saver"  # type: ignore[return-value]
    sched = cfg.schedule
    now = now or datetime.now()
    if sched.enabled and cfg.plan(sched.plan) and _in_window(now.time(), sched.start, sched.end):
        return cfg.plan(sched.plan), "schedule"  # type: ignore[return-value]
    plan = cfg.plan(cfg.active) or cfg.plan(DEFAULT_PLAN) or factory_plan(DEFAULT_PLAN)
    return plan, "active"


# --- Güç kaynağı (sysfs; root gerektirmez) ---

POWER_SUPPLY = Path("/sys/class/power_supply")


def _read(path: Path) -> str:
    try:
        return path.read_text(encoding="utf-8").strip()
    except (OSError, UnicodeDecodeError):
        return ""


def read_power_state(root: Path = POWER_SUPPLY) -> PowerState:
    """Prize takılı mı ve pil yüzdesi. Pil yoksa (masaüstü) her zaman prizde sayılır."""
    if not root.is_dir():
        return PowerState(True, None)
    supplies = list(root.iterdir())
    batteries = [
        d for d in supplies if _read(d / "type") == "Battery" and _read(d / "scope") != "Device"
    ]
    if not batteries:
        return PowerState(True, None)
    # USB-C ile şarj eden dizüstülerde güç kaynağı "USB" türünde görünür
    adapters = [d for d in supplies if _read(d / "type") in ("Mains", "USB")]
    if adapters:
        on_ac = any(_read(d / "online") == "1" for d in adapters)
    else:
        on_ac = all(_read(b / "status") != "Discharging" for b in batteries)
    levels = [int(v) for b in batteries if (v := _read(b / "capacity")).isdigit()]
    percent = round(sum(levels) / len(levels)) if levels else None
    return PowerState(on_ac, percent)
