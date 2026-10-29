# SPDX-FileCopyrightText: 2026 Mehmed Gürbüz and Linwas contributors
# SPDX-License-Identifier: GPL-3.0-or-later
# Additional terms (GPL-3.0 section 7): see NOTICE.md — keep this notice.
"""Hazırda bekletme kurulumunun saf parçaları (core/hibernate.py) ve izin listesi."""

import pytest

from linwas.core import hibernate
from linwas.core.whitelist import ValidationError, validate

FILEFRAG = """\
Filesystem type is: ef53
File size of /swapfile is 1073741824 (262144 blocks of 4096 bytes)
 ext:     logical_offset:        physical_offset: length:   expected: flags:
   0:        0..   32767:      34816..     67583:  32768:
   1:    32768..   63487:      67584..     98303:  30720:
/swapfile: 2 extents found
"""


def test_filefrag_offset():
    assert hibernate.parse_filefrag_offset(FILEFRAG) == 34816


def test_filefrag_offset_converts_block_size():
    out = FILEFRAG.replace("blocks of 4096 bytes", "blocks of 1024 bytes")
    assert hibernate.parse_filefrag_offset(out) == 34816 * 1024 // 4096


def test_filefrag_offset_missing():
    assert hibernate.parse_filefrag_offset("garbage") is None


def test_btrfs_offset():
    assert hibernate.parse_btrfs_offset("198122980\n") == 198122980
    assert hibernate.parse_btrfs_offset("ERROR: not a swapfile") is None


def test_sizes():
    mem_kb = 23 * 1024 * 1024 + 500_000  # ~23.5 GiB
    assert hibernate.recommended_size_gb(mem_kb) == 24
    assert hibernate.minimum_size_gb(mem_kb) == 12
    assert hibernate.recommended_size_gb(0) == hibernate.MIN_SIZE_GB


def test_grub_dropin_keeps_existing_options():
    text = hibernate.grub_dropin_text("9b4611c8-b3f0", 34816)
    assert '"$GRUB_CMDLINE_LINUX_DEFAULT resume=UUID=9b4611c8-b3f0 resume_offset=34816"' in text


def test_fstab_add_remove_roundtrip():
    original = "UUID=x / ext4 defaults 0 1\n/dev/mapper/vg-swap none swap sw 0 0"
    added = hibernate.fstab_add(original)
    assert hibernate.has_fstab_entry(added)
    assert hibernate.fstab_add(added) == added  # ikinci kez eklenmez
    assert hibernate.fstab_remove(added) == original + "\n"


def test_other_swapfile_entry():
    assert hibernate.other_swapfile_entry("/swapfile none swap sw 0 0\n")
    assert not hibernate.other_swapfile_entry("# /swapfile none swap sw 0 0\n")
    assert not hibernate.other_swapfile_entry(hibernate.fstab_line() + "\n")


def test_cmdline_resume_offset():
    assert hibernate.cmdline_resume_offset("quiet resume=UUID=a resume_offset=34816") == "34816"
    assert hibernate.cmdline_resume_offset("quiet splash") == ""


def test_disk_swap_excludes_zram():
    swaps = hibernate.parse_swaps(
        "Filename Type Size Used Priority\n"
        "/dev/zram0 partition 8000000 0 100\n"
        "/swapfile file 24000000 0 -2\n"
    )
    assert hibernate.disk_swap_kb(swaps) == 24000000


def test_whitelist_swap_size():
    assert validate("hibernate.setup", {"size_gb": "024"}) == {"size_gb": "24"}
    for bad in ("0", "257", "-1", "8G", "1e2"):
        with pytest.raises(ValidationError):
            validate("hibernate.setup", {"size_gb": bad})
    assert validate("hibernate.remove", {}) == {}
