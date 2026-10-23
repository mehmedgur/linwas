"""Hazırda bekletme kurulumu: swap dosyası ve resume ayarının saf (yan etkisiz) parçaları.

Linux hazırda bekletmede belleği yalnızca swap'a yazar. Linwas, Windows'taki hiberfil.sys gibi
`/swapfile` oluşturur ve çekirdeğe açılışta nereden uyanacağını söyler:
`resume=UUID=<kök dosya sistemi> resume_offset=<dosyanın ilk fiziksel sayfası>`.
initramfs-tools çekirdek satırındaki `resume=` ve `resume_offset=`'i okur (init,
local-premount/resume; Pardus 23'te 0.142 ile doğrulandı); bu yüzden initramfs ayar dosyasına
dokunulmaz.

Bu modül hem root helper'da hem arayüzde kullanılır; Qt'ye bağımlı değildir.
"""

from __future__ import annotations

import math
import re
from pathlib import Path

SWAPFILE = Path("/swapfile")
GRUB_DROPIN = Path("/etc/default/grub.d/linwas-hibernate.cfg")
FSTAB = Path("/etc/fstab")
FSTAB_MARKER = "# linwas-hibernate"
# Çekirdeğin resume_offset birimi: sayfa (x86_64'te 4096 bayt)
PAGE_SIZE = 4096
# Desteklenen kök dosya sistemleri (btrfs için btrfs-progs ≥ 6.1 gerekir)
SUPPORTED_FS = ("ext4", "xfs", "btrfs")
MIN_SIZE_GB = 1
MAX_SIZE_GB = 256
# Swap dosyasından sonra diskte kalması gereken en az boş alan
SPARE_GB = 2


def recommended_size_gb(mem_total_kb: int) -> int:
    """Önerilen boyut: RAM kadar (yukarı yuvarlanmış GiB)."""
    return max(MIN_SIZE_GB, min(MAX_SIZE_GB, math.ceil(mem_total_kb / 1024 / 1024)))


def minimum_size_gb(mem_total_kb: int) -> int:
    """Kabul edilen en küçük boyut: RAM'in yarısı (çekirdek görüntüyü sıkıştırır; çoğu
    zaman yeter ama bellek doluysa hazırda bekletme başarısız olabilir)."""
    return max(MIN_SIZE_GB, math.ceil(recommended_size_gb(mem_total_kb) / 2))


def parse_filefrag_offset(out: str) -> int | None:
    """`filefrag -v FILE` çıktısından ilk parçanın fiziksel başlangıcını sayfa biriminde döner.

    Örnek satırlar:
        File size of /swapfile is 1073741824 (262144 blocks of 4096 bytes)
         ext:     logical_offset:        physical_offset: length:   expected: flags:
           0:        0..   32767:      34816..     67583:  32768:
    """
    block = PAGE_SIZE
    m = re.search(r"blocks of (\d+) bytes", out)
    if m:
        block = int(m.group(1))
    for line in out.splitlines():
        m = re.match(r"^\s*0:\s*\d+\.\.\s*\d+:\s*(\d+)\.\.", line)
        if m:
            return int(m.group(1)) * block // PAGE_SIZE
    return None


def parse_btrfs_offset(out: str) -> int | None:
    """`btrfs inspect-internal map-swapfile -r FILE` çıktısı: yalnızca resume_offset sayısı."""
    text = out.strip()
    return int(text) if text.isdigit() else None


def grub_dropin_text(fs_uuid: str, offset: int) -> str:
    """/etc/default/grub.d/ altına yazılacak dosya; mevcut çekirdek seçeneklerine eklenir."""
    return (
        "# Linwas tarafından yazıldı (Güç ve pil › Hazırda bekletme). Silinirse hazırda\n"
        '# bekletmeden uyanılamaz; kaldırmak için Linwas\'taki "Kaldır" düğmesini kullanın.\n'
        f'GRUB_CMDLINE_LINUX_DEFAULT="$GRUB_CMDLINE_LINUX_DEFAULT '
        f'resume=UUID={fs_uuid} resume_offset={offset}"\n'
    )


def fstab_line() -> str:
    return f"{SWAPFILE} none swap sw 0 0 {FSTAB_MARKER}"


def fstab_add(text: str) -> str:
    """fstab'a swap dosyası satırını ekler (zaten varsa değiştirmez)."""
    if has_fstab_entry(text):
        return text
    if text and not text.endswith("\n"):
        text += "\n"
    return text + fstab_line() + "\n"


def fstab_remove(text: str) -> str:
    """Yalnızca Linwas'ın eklediği satırı siler; elle eklenmiş satırlara dokunmaz."""
    lines = text.splitlines(keepends=True)
    return "".join(line for line in lines if FSTAB_MARKER not in line)


def has_fstab_entry(text: str) -> bool:
    return any(FSTAB_MARKER in line for line in text.splitlines())


def other_swapfile_entry(text: str) -> bool:
    """/swapfile fstab'da Linwas dışında tanımlıysa (elle oluşturulmuş) dokunulmaz."""
    for line in text.splitlines():
        fields = line.split()
        if (
            fields
            and not line.lstrip().startswith("#")
            and fields[0] == str(SWAPFILE)
            and FSTAB_MARKER not in line
        ):
            return True
    return False


def cmdline_resume_offset(cmdline: str) -> str:
    """Çalışan çekirdeğin satırındaki resume_offset değeri ("" yoksa)."""
    m = re.search(r"(?:^|\s)resume_offset=(\d+)", cmdline)
    return m.group(1) if m else ""


def parse_swaps(text: str) -> list[tuple[str, str, int]]:
    """/proc/swaps → [(ad, tür, boyut_kb)]."""
    found = []
    for line in text.splitlines()[1:]:
        fields = line.split()
        if len(fields) >= 3 and fields[2].isdigit():
            found.append((fields[0], fields[1], int(fields[2])))
    return found


def disk_swap_kb(swaps: list[tuple[str, str, int]]) -> int:
    """Hazırda bekletmede kullanılabilecek swap (zram bellekte durur, sayılmaz)."""
    return sum(size for name, _kind, size in swaps if not name.startswith("/dev/zram"))
