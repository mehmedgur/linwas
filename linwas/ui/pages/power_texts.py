"""Güç sayfasının ayar, değer ve neden metinleri (gelişmiş güç seçenekleri)."""

from __future__ import annotations

from PySide6.QtCore import QCoreApplication

from linwas.core.powerplan import AUTO, PowerPlan


def tr(text: str) -> str:
    return QCoreApplication.translate("PowerPage", text)


def section_name(section: str) -> str:
    return {
        "display": tr("Display and sleep"),
        "buttons": tr("Buttons and lid (same in all plans)"),
        "cpu": tr("Processor"),
        "battery": tr("Battery (same in all plans)"),
        "devices": tr("Connected devices and disks"),
        "wireless": tr("Wireless connections"),
        "graphics": tr("Graphics and brightness"),
    }.get(section, section)


def setting_name(sid: str) -> str:
    return {
        "ppd_profile": tr("System power mode"),
        "screen_dim": tr("Dim the screen when not in use"),
        "screen_off": tr("Turn off the screen after"),
        "sleep_after": tr("Put the computer to sleep after"),
        "sleep_action": tr("Sleep type"),
        "wake_timers": tr("Let scheduled tasks wake the computer"),
        "lid": tr("When I close the lid"),
        "lid_docked": tr("Closing the lid with another screen connected"),
        "power_key": tr("When I press the power button"),
        "cpu_boost": tr("Processor speed boost (turbo)"),
        "cpu_epp": tr("Processor: speed or battery"),
        "cpu_min": tr("Lowest processor speed"),
        "cpu_max": tr("Highest processor speed"),
        "cpu_governor": tr("Speed control method"),
        "battery_low": tr("“Battery low” warning at"),
        "battery_critical": tr("“Battery very low” warning at"),
        "battery_action_level": tr("Last level before the battery runs out"),
        "battery_action": tr("When the battery is almost empty"),
        "usb_autosuspend": tr("Put unused USB devices to sleep"),
        "pcie_aspm": tr("Save power on internal card connections"),
        "pci_runtime_pm": tr("Put unused internal devices to sleep"),
        "sata_alpm": tr("Save power on the disk connection"),
        "disk_spindown": tr("Stop the hard disk after"),
        "wifi_powersave": tr("Wi-Fi battery saving"),
        "bluetooth": tr("Bluetooth"),
        "gpu_power": tr("Graphics card power mode"),
        "brightness": tr("Screen brightness when switching to this plan"),
        "adaptive_brightness": tr("Brightness by room light"),
    }.get(sid, sid)


def setting_help(sid: str) -> str:
    return {
        "ppd_profile": tr(
            "The Power saver / Balanced / Performance choice in the system menu at the top right."
        ),
        "screen_dim": tr(
            "The screen gets darker a little before it turns off; moving the mouse brings it back."
        ),
        "screen_off": tr("If you do not touch the computer for this long, the screen turns off."),
        "sleep_after": tr("If you do not touch the computer for this long, it goes to sleep."),
        "battery_critical": tr("Below this level a “battery very low” warning appears."),
        "battery_action": tr("What the computer does so that your work is not lost."),
        "pci_runtime_pm": tr("Devices inside the computer sleep when they are not used."),
        "sata_alpm": tr(
            "The disk uses less power when idle; some disks may become very slightly slower."
        ),
        "sleep_action": tr(
            "Sleep uses a little power and wakes instantly. Hibernate saves your work to the disk "
            "and turns the computer off completely."
        ),
        "wake_timers": tr(
            "A scheduled task, such as a night-time update, may wake the sleeping computer."
        ),
        "lid": tr("Takes effect after the computer restarts."),
        "lid_docked": tr("Takes effect after the computer restarts."),
        "power_key": tr("The login screen also follows this after the computer restarts."),
        "cpu_boost": tr(
            "When on, the processor speeds up when needed. Turning it off makes the computer "
            "cooler, quieter and longer on battery, but a little slower."
        ),
        "cpu_epp": tr("Tells the processor what comes first: speed or battery life."),
        "cpu_min": tr(
            "Percent of the processor's top speed. Usually there is no need to change it."
        ),
        "cpu_max": tr(
            "Percent of the processor's top speed. A lower value saves battery but makes the "
            "computer slower."
        ),
        "cpu_governor": tr("For experts: how Linux adjusts the processor speed."),
        "battery_low": tr("A warning appears when the battery reaches this level."),
        "battery_action_level": tr("At this level the computer does what you choose below."),
        "usb_autosuspend": tr(
            "USB devices that are not used for a while sleep to save power. Mice and keyboards "
            "are not included."
        ),
        "pcie_aspm": tr(
            "Cards inside the computer (such as Wi-Fi) use less power when idle. Some computers "
            "do not allow this; then it has no effect."
        ),
        "disk_spindown": tr("Only for older, spinning hard disks; it does not affect SSDs."),
        "wifi_powersave": tr(
            "The battery lasts longer; the internet can sometimes be a little slower."
        ),
        "bluetooth": tr(
            "Bluetooth is turned off in this plan and turned back on when you leave it."
        ),
        "gpu_power": tr(
            "How much power the graphics card may use. On NVIDIA the card is switched off when "
            "not in use."
        ),
        "brightness": tr(
            "Set once when the plan changes or you plug in or unplug; you can change it afterwards."
        ),
        "adaptive_brightness": tr(
            "The screen gets brighter or darker by itself, following the light in the room."
        ),
    }.get(sid, "")


_ENUMS = {
    "suspend": "Sleep",
    "hibernate": "Hibernate",
    "hybrid-sleep": "Sleep and hibernate together",
    "lock": "Lock the screen",
    "ignore": "Do nothing",
    "nothing": "Do nothing",
    "poweroff": "Shut down",
    "interactive": "Ask what to do",
    "power-saver": "Power saver",
    "balanced": "Balanced",
    "performance": "Performance",
    "balance_performance": "Balanced, closer to speed",
    "balance_power": "Balanced, closer to battery",
    "power": "Power saving",
    "powersave": "Power saving",
    "default": "Manufacturer’s setting",
    "powersupersave": "Most power saving",
    "max_performance": "Performance",
    "medium_power": "Medium",
    "med_power_with_dipm": "Balanced",
    "min_power": "Most power saving",
    "HybridSleep": "Sleep and hibernate together",
    "Hibernate": "Hibernate",
    "PowerOff": "Shut down",
}


def _enum_markers() -> None:
    """Çeviri aracı için: _ENUMS metinleri value_text() içinde tr(…) ile çevrilir."""
    tr("Sleep")
    tr("Hibernate")
    tr("Sleep and hibernate together")
    tr("Lock the screen")
    tr("Do nothing")
    tr("Shut down")
    tr("Ask what to do")
    tr("Power saver")
    tr("Balanced")
    tr("Performance")
    tr("Balanced, closer to speed")
    tr("Balanced, closer to battery")
    tr("Power saving")
    tr("Manufacturer’s setting")
    tr("Most power saving")
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
        return {
            "schedutil": tr("Automatic (recommended)"),
            "ondemand": tr("Fast when needed"),
            "conservative": tr("Speeds up slowly"),
        }[value]
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
        "ppd": tr("Set by the system power mode"),
        "linwas_cpu": tr("Not used while Linwas manages the processor"),
        "builtin": tr("Ready-made plans cannot be changed"),
    }.get(code, code)


def hibernate_reason_text(code: str) -> str:
    return {
        "kernel": tr("The kernel does not support hibernation."),
        "lockdown": tr("Secure Boot (kernel lockdown) blocks hibernation."),
        "swap": tr("The swap space is smaller than the memory (RAM)."),
        "resume": tr("No resume device is set up."),
    }.get(code, code)


def hibernate_setup_problem_text(code: str) -> str:
    """Linwas'ın hazırda bekletmeyi kuramama nedeni (backend/hibernate_setup.py)."""
    return {
        "kernel": tr("The kernel does not support hibernation."),
        "lockdown": tr(
            "Secure Boot (kernel lockdown) blocks hibernation. It works only if Secure Boot is "
            "turned off in the firmware settings."
        ),
        "fs": tr("The system disk's file system is not supported (ext4, XFS or Btrfs needed)."),
        "btrfs_tools": tr("Btrfs tools are too old (version 6.1 or newer needed)."),
        "bootloader": tr("Only computers that start with GRUB are supported."),
        "initramfs": tr("Only systems that use initramfs-tools are supported."),
        "space": tr("There is not enough free space on the system disk."),
        "manual": tr("A /swapfile already exists; Linwas does not change it."),
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
