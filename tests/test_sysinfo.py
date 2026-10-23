"""Sistem bilgisi okuyucu ve ayar şeması (PySide6 gerektirmez)."""

from __future__ import annotations

import pytest

from linwas.backend.sysinfo import (
    parse_cpuinfo,
    parse_meminfo_total,
    parse_uptime,
    read_system_info,
)
from linwas.core.settings import MemoryBackend, Risk, SettingDef

CPUINFO = """processor\t: 0
model name\t: AMD Ryzen 7 7700X 8-Core Processor
physical id\t: 0
core id\t\t: 0

processor\t: 1
model name\t: AMD Ryzen 7 7700X 8-Core Processor
physical id\t: 0
core id\t\t: 0

processor\t: 2
model name\t: AMD Ryzen 7 7700X 8-Core Processor
physical id\t: 0
core id\t\t: 1

processor\t: 3
model name\t: AMD Ryzen 7 7700X 8-Core Processor
physical id\t: 0
core id\t\t: 1
"""


def test_parse_cpuinfo():
    assert parse_cpuinfo(CPUINFO) == ("AMD Ryzen 7 7700X 8-Core Processor", 2, 4)
    assert parse_cpuinfo("") == ("", 0, 0)


def test_parse_meminfo_and_uptime():
    assert parse_meminfo_total("MemTotal:       32768000 kB\nMemFree: 1 kB\n") == 32768000 * 1024
    assert parse_meminfo_total("") == 0
    assert parse_uptime("12345.67 9999.00\n") == 12345
    assert parse_uptime("bozuk") == 0


def test_read_system_info_from_fake_root(tmp_path):
    (tmp_path / "proc").mkdir()
    (tmp_path / "proc/cpuinfo").write_text(CPUINFO)
    (tmp_path / "proc/meminfo").write_text("MemTotal: 1048576 kB\n")
    (tmp_path / "proc/uptime").write_text("90.5 1.0\n")
    dmi = tmp_path / "sys/class/dmi/id"
    dmi.mkdir(parents=True)
    (dmi / "board_vendor").write_text("ASUSTeK\n")
    (dmi / "board_name").write_text("ROG STRIX X670E-F\n")
    for name, model in (("nvme0n1", "Samsung 990 Pro"), ("loop0", "x"), ("sda", "")):
        (tmp_path / "sys/block" / name / "device").mkdir(parents=True)
        (tmp_path / "sys/block" / name / "device/model").write_text(model + "\n")
    info = read_system_info(tmp_path)
    assert info.cpu_threads == 4 and info.cpu_cores == 2
    assert info.ram_bytes == 1024**3
    assert info.uptime_seconds == 90
    assert info.board == "ASUSTeK ROG STRIX X670E-F"
    assert info.disks == ("Samsung 990 Pro",)


def test_read_system_info_missing_files(tmp_path):
    info = read_system_info(tmp_path)  # boş ağaç: hata vermeden boş değerler
    assert info.ram_bytes == 0 and info.disks == () and info.cpu_model == ""


def test_setting_validation():
    scale = SettingDef("display.scale", int, 100, minimum=100, maximum=300)
    assert scale.validate(150) == 150
    for bad in (50, 400, "150", True):
        with pytest.raises(ValueError):
            scale.validate(bad)
    scheme = SettingDef("appearance.scheme", str, "auto", Risk.LOW, choices=("auto", "light"))
    with pytest.raises(ValueError):
        scheme.validate("dark")


def test_memory_backend_get_set_watch():
    backend = MemoryBackend()
    setting = SettingDef("sound.muted", bool, False)
    seen = []
    stop = backend.watch(lambda key, value: seen.append((key, value)))
    assert backend.get(setting) is False
    backend.set(setting, True)
    assert backend.get(setting) is True and seen == [("sound.muted", True)]
    stop()
    backend.set(setting, False)
    assert len(seen) == 1
    with pytest.raises(ValueError):
        backend.set(setting, "evet")
