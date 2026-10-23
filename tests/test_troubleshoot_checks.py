"""Sorun gidermenin yeni denetimlerindeki ayrıştırıcılar."""

from pathlib import Path

from linwas.backend import troubleshoot


def test_parse_boot_seconds():
    out = (
        "Startup finished in 4.1s (firmware) + 2.0s (loader) + 3.2s (kernel) "
        "+ 1min 5.204s (userspace) = 1min 14.504s\n"
        "graphical.target reached after 1min 5.1s in userspace."
    )
    assert troubleshoot.parse_boot_seconds(out) == 74.504
    assert troubleshoot.parse_boot_seconds("... = 4.050s") == 4.05
    assert troubleshoot.parse_boot_seconds("Bootup is not yet finished") is None


def test_parse_mount_options_uses_last_mount():
    mounts = (
        "/dev/sda1 / ext4 rw,relatime 0 0\n"
        "/dev/sda1 / ext4 ro,relatime 0 0\n"
        "/dev/sda2 /boot ext2 rw 0 0\n"
    )
    assert troubleshoot.parse_mount_options(mounts)[0] == "ro"
    assert troubleshoot.parse_mount_options(mounts, "/boot") == ["rw"]


def test_max_temperature(tmp_path: Path):
    for name, value in (("thermal_zone0", "45000"), ("thermal_zone1", "92500")):
        (tmp_path / name).mkdir()
        (tmp_path / name / "temp").write_text(value)
    (tmp_path / "thermal_zone2").mkdir()
    (tmp_path / "thermal_zone2" / "temp").write_text("-273000")  # anlamsız değer atlanır
    assert troubleshoot.max_temperature(tmp_path) == 92.5
    assert troubleshoot.max_temperature(tmp_path / "missing") is None
