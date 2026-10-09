"""Güç planlarının masaüstü tarafı (kullanıcı oturumu, şimdilik GNOME).

Oturum açılınca XDG autostart ile başlar (`linwas-power-agent`); etkin plan, priz/pil ya da ayar
dosyası değişince ekran/uyku/düğme ayarlarını gsettings ile uygular. "auto" olan ayar, yalnızca
daha önce Linwas değiştirdiyse masaüstü varsayılanına döndürülür (`gsettings reset`).

Anahtarlar (GNOME 42–47 şemaları, `gsettings range` ile doğrulandı):
- org.gnome.desktop.session idle-delay (uint32, sn; 0 = hiçbir zaman) — ekranı kapat
- org.gnome.settings-daemon.plugins.power: idle-dim, sleep-inactive-{ac,battery}-timeout (sn),
  sleep-inactive-{ac,battery}-type (suspend | hibernate | nothing …), power-button-action
  (nothing | suspend | hibernate | interactive), ambient-enabled
"""

from __future__ import annotations

import json
import os
import subprocess
import sys
import time
from pathlib import Path

from linwas.core import powerplan
from linwas.core.powerplan import AUTO, PowerConfig, PowerPlan

SESSION = "org.gnome.desktop.session"
GSD_POWER = "org.gnome.settings-daemon.plugins.power"
POLL_SECONDS = 20


def _state_path() -> Path:
    base = os.environ.get("XDG_STATE_HOME") or str(Path.home() / ".local" / "state")
    return Path(base) / "linwas" / "power-agent.json"


def is_supported_desktop() -> bool:
    return "GNOME" in os.environ.get("XDG_CURRENT_DESKTOP", "").upper().split(":")


def _gsettings(*args: str) -> subprocess.CompletedProcess[str] | None:
    try:
        return subprocess.run(
            ["gsettings", *args], capture_output=True, text=True, timeout=10, shell=False
        )
    except (FileNotFoundError, subprocess.TimeoutExpired):
        return None


def has_key(schema: str, key: str) -> bool:
    r = _gsettings("range", schema, key)
    return bool(r and r.returncode == 0)


def _minutes_to_seconds(value: str) -> str:
    return "0" if value == "never" else str(int(value) * 60)


def desired_settings(cfg: PowerConfig, plan: PowerPlan, source: str) -> dict[tuple[str, str], str]:
    """{(şema, anahtar): değer}; "auto" değerler AUTO olarak döner (sıfırlanacak)."""
    out: dict[tuple[str, str], str] = {}
    dim = cfg.value(plan, "screen_dim", source)
    out[(GSD_POWER, "idle-dim")] = AUTO if dim == AUTO else ("true" if dim == "on" else "false")
    off = cfg.value(plan, "screen_off", source)
    out[(SESSION, "idle-delay")] = AUTO if off == AUTO else _minutes_to_seconds(off)
    # Uyku: GNOME'un kendi prizde/pilde anahtarları var; ikisi birden yazılır
    for src, name in (("ac", "ac"), ("bat", "battery")):
        after = cfg.value(plan, "sleep_after", src)
        action = cfg.value(plan, "sleep_action", src)
        out[(GSD_POWER, f"sleep-inactive-{name}-timeout")] = (
            AUTO if after in (AUTO, "never") else _minutes_to_seconds(after)
        )
        if after == "never":
            kind = "nothing"
        elif action != AUTO:
            kind = action
        elif after != AUTO:
            kind = "suspend"
        else:
            kind = AUTO
        out[(GSD_POWER, f"sleep-inactive-{name}-type")] = kind
    key = cfg.value(plan, "power_key", source)
    out[(GSD_POWER, "power-button-action")] = key
    ambient = cfg.value(plan, "adaptive_brightness", source)
    out[(GSD_POWER, "ambient-enabled")] = (
        AUTO if ambient == AUTO else ("true" if ambient == "on" else "false")
    )
    return out


def _load_touched() -> set[str]:
    try:
        data = json.loads(_state_path().read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return set()
    return {k for k in data if isinstance(k, str)} if isinstance(data, list) else set()


def _save_touched(touched: set[str]) -> None:
    path = _state_path()
    try:
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(json.dumps(sorted(touched)), encoding="utf-8")
    except OSError:
        pass


def apply_user(cfg: PowerConfig, plan: PowerPlan, source: str) -> None:
    if not is_supported_desktop():
        return
    touched = _load_touched()
    for (schema, key), value in desired_settings(cfg, plan, source).items():
        name = f"{schema} {key}"
        if not has_key(schema, key):
            continue
        if value == AUTO:
            if name in touched:
                _gsettings("reset", schema, key)
                touched.discard(name)
            continue
        if value in ("suspend", "hibernate", "nothing", "interactive"):
            value = f"'{value}'"  # enum değerleri GVariant metni olarak verilir
        r = _gsettings("set", schema, key, value)
        if r and r.returncode == 0:
            touched.add(name)
    _save_touched(touched)


def apply_now() -> None:
    """Etkin planın masaüstü ayarlarını hemen uygular (arayüz kaydettikten sonra çağırır)."""
    cfg = powerplan.load_config()
    state = powerplan.read_power_state()
    plan, _ = powerplan.effective_plan(cfg, state)
    apply_user(cfg, plan, "ac" if state.on_ac else "bat")


def run() -> None:
    if not is_supported_desktop():
        return
    last: tuple[object, ...] | None = None
    while True:
        cfg = powerplan.load_config()
        state = powerplan.read_power_state()
        plan, _ = powerplan.effective_plan(cfg, state)
        source = "ac" if state.on_ac else "bat"
        try:
            mtime = powerplan.CONFIG_PATH.stat().st_mtime
        except OSError:
            mtime = 0.0
        key = (plan.id, source, mtime)
        if key != last:
            apply_user(cfg, plan, source)
            last = key
        time.sleep(POLL_SECONDS)


if __name__ == "__main__":
    try:
        run()
    except KeyboardInterrupt:
        sys.exit(0)
