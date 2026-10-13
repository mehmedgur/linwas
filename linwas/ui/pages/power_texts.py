"""Güç sayfasının ayar, değer ve neden metinleri (gelişmiş güç seçenekleri)."""

from __future__ import annotations

from PySide6.QtCore import QCoreApplication

from linwas.core.powerplan import AUTO, PowerPlan


def tr(text: str) -> str:
    return QCoreApplication.translate("PowerPage", text)


def section_name(section: str) -> str:
    return {
        "display": tr("Display and sleep"),
        "buttons": tr("Buttons and lid (all plans)"),
        "cpu": tr("Processor"),
        "battery": tr("Battery (all plans)"),
        "devices": tr("USB, PCIe and disks"),
        "wireless": tr("Wireless"),
        "graphics": tr("Graphics and brightness"),
    }.get(section, section)


def setting_name(sid: str) -> str:
    return {
        "ppd_profile": tr("System power mode"),
        "screen_dim": tr("Dim the screen when inactive"),
        "screen_off": tr("Turn off the screen after"),
        "sleep_after": tr("Put the computer to sleep after"),
        "sleep_action": tr("Sleep type"),
        "wake_timers": tr("Allow wake timers"),
        "lid": tr("When I close the lid"),
        "lid_docked": tr("Closing the lid with an external screen"),
        "power_key": tr("When I press the power button"),
        "cpu_boost": tr("Turbo boost"),
        "cpu_epp": tr("Energy preference (EPP)"),
        "cpu_min": tr("Minimum processor state"),
        "cpu_max": tr("Maximum processor state"),
        "cpu_governor": tr("Frequency governor"),
        "battery_low": tr("Low battery level"),
        "battery_critical": tr("Critical battery level"),
        "battery_action_level": tr("Critical battery action level"),
        "battery_action": tr("Critical battery action"),
        "usb_autosuspend": tr("USB selective suspend"),
        "pcie_aspm": tr("PCI Express link state power management"),
        "pci_runtime_pm": tr("PCI device power management"),
        "sata_alpm": tr("SATA link power management"),
        "disk_spindown": tr("Turn off hard disk after"),
        "wifi_powersave": tr("Wi-Fi power saving"),
        "bluetooth": tr("Bluetooth"),
        "gpu_power": tr("Graphics card power mode"),
        "brightness": tr("Screen brightness when switching to this plan"),
        "adaptive_brightness": tr("Adaptive brightness"),
    }.get(sid, sid)


def setting_help(sid: str) -> str:
    return {
        "ppd_profile": tr("The Power saver / Balanced / Performance mode in the system menu."),
        "screen_dim": tr("Makes the screen darker shortly before it turns off."),
        "screen_off": tr("The screen turns off when you do not use the computer for this long."),
        "sleep_after": tr("The computer sleeps when you do not use it for this long."),
        "battery_critical": tr("Below this level the battery is shown as critical."),
        "battery_action": tr("What the computer does when the battery is almost empty."),
        "pci_runtime_pm": tr("Idle internal devices are switched off to save power."),
        "sata_alpm": tr("Lets SATA disks save power when idle; may slow some disks slightly."),
        "sleep_action": tr("Hibernate saves your work to disk and turns the computer off."),
        "wake_timers": tr("Lets scheduled tasks wake the computer from sleep."),
        "lid": tr("Takes effect after the next restart."),
        "lid_docked": tr("Takes effect after the next restart."),
        "power_key": tr("The login screen follows this setting after the next restart."),
        "cpu_boost": tr("Turning turbo off makes the computer cooler and quieter but slower."),
        "cpu_epp": tr("Tells the processor whether to favour speed or battery life."),
        "cpu_min": tr("Percentage of the highest processor speed."),
        "cpu_max": tr("Percentage of the highest processor speed. Lower values save battery."),
        "cpu_governor": tr("Advanced: the kernel's frequency scaling method."),
        "battery_low": tr("You are warned at this level."),
        "battery_action_level": tr("The critical battery action runs at this level."),
        "usb_autosuspend": tr(
            "Idle USB devices are switched off. Mice and keyboards are excluded."
        ),
        "pcie_aspm": tr("Some computers do not allow changing this; then it has no effect."),
        "disk_spindown": tr("Only for hard disks with spinning platters."),
        "wifi_powersave": tr("Saves battery; can slightly slow down the connection."),
        "bluetooth": tr("Bluetooth is turned back on when you leave this plan."),
        "gpu_power": tr("AMD and Intel: speed limit; NVIDIA: switch off the card when not in use."),
        "brightness": tr(
            "Applied once when the plan or power source changes; you can still adjust it."
        ),
        "adaptive_brightness": tr("Adjusts brightness using the light sensor."),
    }.get(sid, "")


_ENUMS = {
    "suspend": "Sleep",
    "hibernate": "Hibernate",
    "hybrid-sleep": "Hybrid sleep",
    "lock": "Lock the screen",
    "ignore": "Do nothing",
    "nothing": "Do nothing",
    "poweroff": "Shut down",
    "interactive": "Ask what to do",
    "power-saver": "Power saver",
    "balanced": "Balanced",
    "performance": "Performance",
    "balance_performance": "Balanced, faster",
    "balance_power": "Balanced, longer battery",
    "power": "Power saving",
    "powersave": "Power saving",
    "default": "Firmware default",
    "powersupersave": "Maximum power saving",
    "max_performance": "Performance",
    "medium_power": "Medium",
    "med_power_with_dipm": "Balanced",
    "min_power": "Maximum power saving",
    "HybridSleep": "Hybrid sleep",
    "Hibernate": "Hibernate",
    "PowerOff": "Shut down",
}


def _enum_markers() -> None:
    """Çeviri aracı için: _ENUMS metinleri value_text() içinde tr(…) ile çevrilir."""
    tr("Sleep")
    tr("Hibernate")
    tr("Hybrid sleep")
    tr("Lock the screen")
    tr("Do nothing")
    tr("Shut down")
    tr("Ask what to do")
    tr("Power saver")
    tr("Balanced")
    tr("Performance")
    tr("Balanced, faster")
    tr("Balanced, longer battery")
    tr("Power saving")
    tr("Firmware default")
    tr("Maximum power saving")
    tr("Medium")


_GOVERNORS = ("schedutil", "ondemand", "conservative")
_MINUTE_SETTINGS = ("screen_off", "sleep_after", "disk_spindown")
_PERCENT_SETTINGS = (
    "cpu_min",
    "cpu_max",
    "brightness",
    "battery_low",
    "battery_critical",
    "battery_action_level",
)


def value_text(sid: str, value: str) -> str:
    if value == AUTO:
        return tr("System default")
    if sid in _MINUTE_SETTINGS:
        if value in ("never", "off"):
            return tr("Never")
        return tr("{n} min").format(n=value)
    if sid in _PERCENT_SETTINGS:
        return tr("{n}%").format(n=value)
    if sid == "cpu_governor" and value in _GOVERNORS:
        return value
    if sid == "bluetooth":
        return tr("Turn off")
    if sid == "wake_timers":
        return tr("Allow") if value == "on" else tr("Do not allow")
    if value == "on":
        return tr("On")
    if value == "off":
        return tr("Off")
    text = _ENUMS.get(value)
    return QCoreApplication.translate("PowerPage", text) if text else value


def reason_text(code: str) -> str:
    return {
        "no_hardware": tr("Not supported by this computer"),
        "not_laptop": tr("Only on laptops"),
        "no_desktop": tr("Not yet supported on this desktop (GNOME only for now)"),
        "no_ppd": tr("power-profiles-daemon is not installed"),
        "no_iw": tr("The iw tool is not installed"),
        "no_hdparm": tr("The hdparm tool is not installed"),
        "managed": tr("Managed by another power tool"),
    }.get(code, code)


def hibernate_reason_text(code: str) -> str:
    return {
        "kernel": tr("The kernel does not support hibernation."),
        "lockdown": tr("Secure Boot (kernel lockdown) blocks hibernation."),
        "swap": tr("The swap space is smaller than the memory (RAM)."),
        "resume": tr("No resume device is set up."),
    }.get(code, code)


def plan_name(plan: PowerPlan) -> str:
    if not plan.builtin:
        return plan.name
    return {
        "power-saver": tr("Power saver"),
        "balanced": tr("Balanced"),
        "performance": tr("Performance"),
    }.get(plan.id, plan.id)


def plan_description(plan: PowerPlan) -> str:
    if not plan.builtin:
        return tr("Custom plan")
    return {
        "power-saver": tr("Longer battery life, slower computer"),
        "balanced": tr("Recommended for everyday use"),
        "performance": tr("Fastest, uses more battery"),
    }.get(plan.id, "")
