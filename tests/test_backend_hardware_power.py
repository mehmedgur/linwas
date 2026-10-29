# SPDX-FileCopyrightText: 2026 Mehmed Gürbüz and Linwas contributors
# SPDX-License-Identifier: GPL-3.0-or-later
# Additional terms (GPL-3.0 section 7): see NOTICE.md — keep this notice.
"""Donanım, güç/pil ve kişisel yedek ayrıştırıcı testleri."""

from datetime import datetime

from linwas.backend import hardware, personal_backup, power


class TestHardware:
    def test_lscpu(self):
        out = "Architecture: x86_64\nCPU(s): 16\nModel name: Intel(R) Core(TM) i5\n"
        assert hardware.parse_lscpu(out) == ("Intel(R) Core(TM) i5", 16)

    def test_meminfo(self):
        assert hardware.parse_meminfo("MemTotal:  1024 kB\nMemFree: 1 kB\n") == 1024 * 1024

    def test_lspci_gpus(self):
        out = (
            '00:02.0 "VGA compatible controller" "Intel Corporation" "Alder Lake-P" -r0c\n'
            '01:00.0 "3D controller" "NVIDIA Corporation" "TU117M" -ra1\n'
            '00:1f.3 "Audio device" "Intel Corporation" "HDA" -r01\n'
        )
        assert hardware.parse_lspci_gpus(out) == [
            "Intel Corporation Alder Lake-P",
            "NVIDIA Corporation TU117M",
        ]

    def test_lsblk_disks(self):
        out = (
            '{"blockdevices":[{"name":"nvme0n1","size":"476.9G","model":"SAMSUNG ",'
            '"rota":false,"type":"disk"},{"name":"loop0","size":"4K","model":null,'
            '"rota":false,"type":"loop"},{"name":"sda","size":"1T","model":"WD",'
            '"rota":true,"type":"disk"}]}'
        )
        disks = hardware.parse_lsblk_disks(out)
        assert [(d.name, d.model, d.ssd) for d in disks] == [
            ("nvme0n1", "SAMSUNG", True),
            ("sda", "WD", False),
        ]

    def test_lpstat(self):
        out = (
            "printer HP_LaserJet is idle.  enabled since Mon 06 Oct 2026\n"
            "printer Canon disabled since Mon 06 Oct 2026 -\n"
            "system default destination: HP_LaserJet\n"
        )
        printers = hardware.parse_lpstat(out)
        assert [(p.name, p.enabled, p.is_default) for p in printers] == [
            ("HP_LaserJet", True, True),
            ("Canon", False, False),
        ]
        assert hardware.parse_lpstat("lpstat: No destinations added.") == []

    def test_usb_printers(self, tmp_path):
        dev = tmp_path / "1-2"
        dev.mkdir()
        (dev / "manufacturer").write_text("HP\n")
        (dev / "product").write_text("LaserJet 1020\n")
        iface = tmp_path / "1-2:1.0"
        iface.mkdir()
        (iface / "bInterfaceClass").write_text("07\n")
        other = tmp_path / "1-3:1.0"
        other.mkdir()
        (other / "bInterfaceClass").write_text("03\n")
        assert hardware.detect_usb_printers(tmp_path) == ["HP LaserJet 1020"]

    def test_scanimage(self):
        out = (
            "device `epson2:net:192.168.1.5' is a Epson PID 08D1 flatbed scanner\n"
            "device `airscan:e0:Canon' is an eSCL Canon MF ip scanner\n"
        )
        assert hardware.parse_scanimage_list(out) == [
            "Epson PID 08D1 flatbed scanner",
            "eSCL Canon MF ip scanner",
        ]


def _battery(root, name, **files):
    d = root / name
    d.mkdir()
    for k, v in files.items():
        (d / k).write_text(f"{v}\n")


class TestPower:
    def test_batteries(self, tmp_path):
        _battery(
            tmp_path,
            "BAT0",
            type="Battery",
            capacity=72,
            status="Discharging",
            energy_full=40000,
            energy_full_design=50000,
            cycle_count=0,
        )
        _battery(tmp_path, "hidpp_battery_0", type="Battery", scope="Device", capacity=50)
        _battery(tmp_path, "ADP1", type="Mains")
        bats = power.list_batteries(tmp_path)
        assert len(bats) == 1
        b = bats[0]
        assert (b.name, b.capacity, b.health, b.cycle_count) == ("BAT0", 72, 80, None)

    def test_charge_full(self, tmp_path):
        _battery(tmp_path, "BAT1", type="Battery", charge_full=3000, charge_full_design=4000)
        b = power.list_batteries(tmp_path)[0]
        assert b.health == 75

    def test_profiles(self):
        out = (
            "* performance:\n    Driver:     platform_profile\n    Degraded:   no\n\n"
            "  balanced:\n    Driver:     platform_profile\n\n"
            "  power-saver:\n    Driver:     platform_profile\n"
        )
        assert power.parse_profiles(out) == (
            ["performance", "balanced", "power-saver"],
            "performance",
        )

    def test_lid_action(self):
        text = (
            "[Login]\n#HandleLidSwitch=ignore\nHandleLidSwitch=lock\n[Other]\nHandleLidSwitch=x\n"
        )
        assert power.parse_lid_action(text) == "lock"
        assert power.parse_lid_action("[Login]\n") is None


class TestPersonalBackup:
    def test_removable(self):
        out = (
            '{"blockdevices":['
            '{"name":"sda","mountpoint":null,"rm":true,"hotplug":true,"children":['
            '{"name":"sda1","mountpoint":"/media/u/USB","label":"USB","size":"16G",'
            '"fstype":"vfat","rm":true,"hotplug":true}]},'
            '{"name":"nvme0n1","mountpoint":null,"rm":false,"hotplug":false,"children":['
            '{"name":"nvme0n1p2","mountpoint":"/","label":null,"size":"400G",'
            '"fstype":"ext4","rm":false,"hotplug":false}]}]}'
        )
        dests = personal_backup.parse_lsblk_removable(out)
        assert [(str(d.mountpoint), d.label, d.fstype) for d in dests] == [
            ("/media/u/USB", "USB", "vfat")
        ]

    def test_progress(self):
        line = "    1,234,567  45%    1.23MB/s    0:00:12 (xfr#3, to-chk=10/20)"
        assert personal_backup.parse_progress(line) == 45
        assert personal_backup.parse_progress("sending incremental file list") is None

    def test_rsync_command_copies_folder_itself(self, tmp_path):
        cmd = personal_backup.rsync_command(tmp_path / "Belgeler", tmp_path / "t")
        assert cmd[-2] == str(tmp_path / "Belgeler") and cmd[-1].endswith("/")
        assert "-rt" in cmd and "--" in cmd

    def test_run_backup_and_list(self, tmp_path):
        src = tmp_path / "Belgeler"
        (src / "alt").mkdir(parents=True)
        (src / "alt" / "a.txt").write_text("merhaba")
        dest = tmp_path / "usb"
        dest.mkdir()
        seen = []
        ok, target, err = personal_backup.run_backup(
            [src], dest, lambda i, n, p: seen.append(p), now=datetime(2026, 10, 6, 12, 0, 0)
        )
        assert ok, err
        assert (target / "Belgeler" / "alt" / "a.txt").read_text() == "merhaba"
        assert seen[-1] == 100
        sets = personal_backup.list_backups(dest)
        assert [s.folders for s in sets] == [["Belgeler"]]
        assert sets[0].created == datetime(2026, 10, 6, 12, 0, 0)
