"""Dağıtım algılama ve destek durumu testleri."""

from pathlib import Path

import pytest

from linwas.backend.distro import (
    DistroInfo,
    SupportStatus,
    detect_distro,
    distro_from_mapping,
    evaluate_support,
    parse_os_release,
)

UBUNTU_2204 = """\
PRETTY_NAME="Ubuntu 22.04.4 LTS"
NAME="Ubuntu"
VERSION_ID="22.04"
VERSION="22.04.4 LTS (Jammy Jellyfish)"
ID=ubuntu
ID_LIKE=debian
"""

PARDUS_23 = """\
PRETTY_NAME="Pardus 23.2"
NAME="Pardus"
VERSION_ID="23.2"
ID=pardus
ID_LIKE=debian
"""


def test_parse_handles_quotes_comments_and_bad_lines():
    text = '# yorum\nNAME="Linux Mint"\nID=linuxmint\nbozuk satir\nX="kapanmamis\n\n'
    data = parse_os_release(text)
    assert data["NAME"] == "Linux Mint"
    assert data["ID"] == "linuxmint"
    assert "X" not in data


def test_distro_from_mapping_ubuntu():
    info = distro_from_mapping(parse_os_release(UBUNTU_2204))
    assert info.id == "ubuntu"
    assert info.version_id == "22.04"
    assert info.id_like == ("debian",)
    assert info.display_name == "Ubuntu 22.04.4 LTS"


def test_display_name_without_pretty_name():
    info = DistroInfo(id="debian", name="Debian GNU/Linux", version_id="12")
    assert info.display_name == "Debian GNU/Linux 12"


@pytest.mark.parametrize(
    ("distro_id", "version", "expected"),
    [
        ("ubuntu", "18.04", SupportStatus.UNSUPPORTED),
        ("ubuntu", "20.04", SupportStatus.END_OF_LIFE),
        ("ubuntu", "22.04", SupportStatus.SUPPORTED),
        ("ubuntu", "24.04", SupportStatus.SUPPORTED),
        ("debian", "10", SupportStatus.UNSUPPORTED),
        ("debian", "11", SupportStatus.END_OF_LIFE),
        ("debian", "12", SupportStatus.SUPPORTED),
        ("debian", "13", SupportStatus.SUPPORTED),
        ("linuxmint", "20.3", SupportStatus.END_OF_LIFE),
        ("linuxmint", "21.3", SupportStatus.SUPPORTED),
        ("linuxmint", "22", SupportStatus.SUPPORTED),
        ("pardus", "21.5", SupportStatus.UNSUPPORTED),
        ("pardus", "23.2", SupportStatus.SUPPORTED),
        ("pardus", "25.0", SupportStatus.SUPPORTED),
    ],
)
def test_evaluate_support_known(distro_id, version, expected):
    assert evaluate_support(DistroInfo(id=distro_id, version_id=version)) is expected


def test_lmde_is_untested_family():
    info = DistroInfo(id="linuxmint", name="LMDE", version_id="6", id_like=("debian",))
    assert evaluate_support(info) is SupportStatus.UNTESTED_FAMILY


def test_unknown_debian_family_is_untested():
    info = DistroInfo(id="zorin", version_id="17", id_like=("ubuntu", "debian"))
    assert evaluate_support(info) is SupportStatus.UNTESTED_FAMILY


def test_non_debian_is_unsupported():
    info = DistroInfo(id="fedora", version_id="40", id_like=())
    assert evaluate_support(info) is SupportStatus.UNSUPPORTED


def test_detect_distro_reads_first_existing_file(tmp_path: Path):
    missing = tmp_path / "yok"
    present = tmp_path / "os-release"
    present.write_text(PARDUS_23, encoding="utf-8")
    info = detect_distro((missing, present))
    assert info.id == "pardus"
    assert evaluate_support(info) is SupportStatus.SUPPORTED


def test_detect_distro_without_files_returns_empty(tmp_path: Path):
    info = detect_distro((tmp_path / "a", tmp_path / "b"))
    assert info == DistroInfo()
    assert evaluate_support(info) is SupportStatus.UNSUPPORTED
