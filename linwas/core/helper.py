"""Root helper: pkexec aracılığıyla root olarak çalışır.

Protokol: stdin/stdout üzerinden JSON satırları.
  İstek  → {"seq": int, "op_id": str, "params": {str: str}}
  Yanıt  → {"seq": int, "status": "ok"|"error", "message": str, "progress": float}

Kurallar:
- Her parametre whitelist'e karşı yeniden doğrulanır (istemci ne gönderirse göndersin).
- Kabuk (shell) hiç kullanılmaz; subprocess yalnızca açık argüman listesiyle çağrılır.
- Başarısız adım helper'ı sonlandırır (kısmi uygulama önlenir).
"""

from __future__ import annotations

import contextlib
import json
import os
import pwd
import re
import shutil
import subprocess
import sys
from pathlib import Path
from typing import Any

from linwas.core import package_guard
from linwas.core.rollback import ROLLBACK_DIR, FileBackup, RollbackRecord, load_record, save_record
from linwas.core.whitelist import ValidationError, validate


def _send(obj: dict[str, Any]) -> None:
    print(json.dumps(obj, ensure_ascii=False), flush=True)


def _ok(seq: int, message: str = "", progress: float = 1.0) -> None:
    _send({"seq": seq, "status": "ok", "message": message, "progress": progress})


def _error(seq: int, message: str) -> None:
    _send({"seq": seq, "status": "error", "message": message, "progress": 0.0})


# --- Uygulayıcılar ---


def _run(cmd: list[str], seq: int, env: dict[str, str] | None = None) -> bool:
    """Komutu çalıştırır; çıktıyı satır satır ilerleme olarak gönderir."""
    try:
        proc = subprocess.Popen(
            cmd,
            stdout=subprocess.PIPE,
            stderr=subprocess.STDOUT,
            text=True,
            shell=False,
            env={**os.environ, **env} if env else None,
        )
        assert proc.stdout is not None
        for line in proc.stdout:
            _send({"seq": seq, "status": "ok", "message": line.rstrip(), "progress": 0.5})
        proc.wait()
        if proc.returncode != 0:
            _error(seq, f"Komut başarısız (kod {proc.returncode}): {' '.join(cmd)}")
            return False
    except FileNotFoundError:
        _error(seq, f"Komut bulunamadı: {cmd[0]!r}")
        return False
    return True


def _apt_installed(name: str) -> bool:
    try:
        r = subprocess.run(
            ["dpkg-query", "-W", "-f=${Status}", "--", name],
            capture_output=True,
            text=True,
            timeout=15,
            shell=False,
        )
    except (FileNotFoundError, subprocess.TimeoutExpired):
        return False
    return r.stdout.strip().endswith(" installed")


def _exec_package_install(seq: int, params: dict[str, str]) -> bool:
    name = params["name"]
    was_installed = _apt_installed(name)
    cmd = ["apt-get", "install", "-y", "--", name]
    if not _run(cmd, seq, {"DEBIAN_FRONTEND": "noninteractive"}):
        return False
    # Yeni kurulumsa geri alınabilir (güncellemede kayıt yazılmaz)
    if not was_installed:
        _save_rollback(RollbackRecord(task_label=name, packages_to_install=[name]), seq)
    return True


def _exec_package_remove(seq: int, params: dict[str, str]) -> bool:
    try:
        proc = subprocess.Popen(
            ["apt-get", "remove", "-y", "--", params["name"]],
            stdout=subprocess.PIPE,
            stderr=subprocess.STDOUT,
            text=True,
            shell=False,
        )
        assert proc.stdout is not None
        for line in proc.stdout:
            _send({"seq": seq, "status": "ok", "message": line.rstrip(), "progress": 0.5})
        proc.wait()
        if proc.returncode != 0:
            _error(seq, f"Paket kaldırılamadı: {params['name']!r}")
            return False
    except FileNotFoundError:
        _error(seq, "apt-get bulunamadı")
        return False
    return True


def _exec_package_fix_broken(seq: int, params: dict[str, str]) -> bool:
    """dpkg --configure -a (yarım kalanlar) + apt-get -f install (bağımlılık onarımı)."""
    env = {"DEBIAN_FRONTEND": "noninteractive"}
    return _run(["dpkg", "--configure", "-a"], seq, env) and _run(
        ["apt-get", "-f", "install", "-y"], seq, env
    )


def _exec_clock_fix(seq: int, params: dict[str, str]) -> bool:
    """Saati eşitler ve büyük farkların (uykudan uyanınca) hemen düzelmesini sağlar."""
    from linwas.core import clock

    try:
        done = clock.ensure(wait_sync=True)
    except OSError as exc:
        _error(seq, f"Saat ayarı yazılamadı: {exc}")
        return False
    for line in done:
        _send({"seq": seq, "status": "ok", "message": line})
    offset = clock.offset_seconds()
    if offset is not None and abs(offset) >= clock.WRONG_SECONDS:
        _error(seq, f"Saat hâlâ {offset:+.0f} sn farklı (internet bağlantısını denetleyin)")
        return False
    return True


def _exec_package_autoremove(seq: int, params: dict[str, str]) -> bool:
    """Gereksiz paketleri ve eski çekirdekleri kaldırır (çalışan çekirdek apt tarafından korunur).
    Dolu /boot'u boşaltmanın güvenli yolu."""
    env = {"DEBIAN_FRONTEND": "noninteractive"}
    return _run(["apt-get", "autoremove", "--purge", "-y"], seq, env)


def _exec_package_update_index(seq: int, params: dict[str, str]) -> bool:
    return _run(["apt-get", "update"], seq)


def _exec_package_update_all(seq: int, params: dict[str, str]) -> bool:
    return _run(["apt-get", "update"], seq) and _run(["apt-get", "upgrade", "-y"], seq)


def _exec_service_enable(seq: int, params: dict[str, str]) -> bool:
    return _run(["systemctl", "enable", "--", params["name"]], seq)


def _exec_service_disable(seq: int, params: dict[str, str]) -> bool:
    return _run(["systemctl", "disable", "--", params["name"]], seq)


def _exec_service_restart(seq: int, params: dict[str, str]) -> bool:
    return _run(["systemctl", "restart", "--", params["name"]], seq)


def _exec_snapshot_timeshift_create(seq: int, params: dict[str, str]) -> bool:
    return _run(["timeshift", "--create", "--comments", "Linwas otomatik yedek"], seq)


def _exec_firmware_fwupd_update(seq: int, params: dict[str, str]) -> bool:
    return _run(["fwupdmgr", "update", "--no-reboot-check", "-y"], seq)


def _exec_snapshot_timeshift_restore(seq: int, params: dict[str, str]) -> bool:
    return _run(["timeshift", "--restore", "--snapshot", params["name"], "--yes"], seq)


def _exec_snapshot_timeshift_delete(seq: int, params: dict[str, str]) -> bool:
    return _run(["timeshift", "--delete", "--snapshot", params["name"]], seq)


def _exec_apt_clean(seq: int, params: dict[str, str]) -> bool:
    return _run(["apt-get", "clean"], seq)


def _exec_journal_vacuum(seq: int, params: dict[str, str]) -> bool:
    return _run(["journalctl", "--vacuum-size=100M"], seq)


def _exec_apt_add_key(seq: int, params: dict[str, str]) -> bool:
    """GPG anahtarını URL'den indirir, dearmor ederek keyring_path'e yazar."""
    import urllib.error
    import urllib.request
    from pathlib import Path

    url = params["url"]
    dest = Path(params["keyring_path"])
    try:
        with urllib.request.urlopen(url, timeout=30) as resp:
            raw = resp.read()
    except (urllib.error.URLError, OSError) as exc:
        _error(seq, f"Anahtar indirilemedi: {exc}")
        return False

    # ASCII armor ise dearmor et, değilse doğrudan yaz
    try:
        if raw.startswith(b"-----BEGIN"):
            proc = subprocess.run(
                ["gpg", "--dearmor"],
                input=raw,
                capture_output=True,
                shell=False,
            )
            if proc.returncode != 0:
                _error(seq, "gpg --dearmor başarısız")
                return False
            raw = proc.stdout
    except FileNotFoundError:
        pass  # gpg yoksa ham veriyi yaz

    try:
        dest.parent.mkdir(parents=True, exist_ok=True)
        dest.write_bytes(raw)
        dest.chmod(0o644)
    except OSError as exc:
        _error(seq, f"Anahtar dosyası yazılamadı: {exc}")
        return False

    _ok(seq, f"Anahtar kaydedildi: {dest}")
    return True


def _exec_apt_add_source(seq: int, params: dict[str, str]) -> bool:
    """APT kaynak satırını sources.list.d altına yazar."""
    from pathlib import Path

    list_path = Path("/etc/apt/sources.list.d") / params["list_name"]
    try:
        list_path.write_text(params["source_line"] + "\n", encoding="utf-8")
        list_path.chmod(0o644)
    except OSError as exc:
        _error(seq, f"Kaynak dosyası yazılamadı: {exc}")
        return False
    _ok(seq, f"Kaynak eklendi: {list_path}")
    return True


def _exec_deb_install(seq: int, params: dict[str, str]) -> bool:
    """Yerel .deb dosyasını kurar; eksik bağımlılıkları APT tamamlar."""
    path = params["path"]
    try:
        r = subprocess.run(
            ["dpkg-deb", "-f", "--", path, "Package"],
            capture_output=True,
            text=True,
            timeout=60,
            shell=False,
        )
        name = r.stdout.strip()
    except (FileNotFoundError, subprocess.TimeoutExpired):
        name = ""
    was_installed = bool(name) and _apt_installed(name)
    env = {"DEBIAN_FRONTEND": "noninteractive"}
    # Bağımlılık eksikse dpkg yarıda kalır; apt-get -f tamamlar
    dpkg_ok = _run(["dpkg", "-i", "--", path], seq, env)
    if not dpkg_ok and not _run(["apt-get", "-f", "install", "-y"], seq, env):
        return False
    if name and not _apt_installed(name):
        _error(seq, f"Paket kurulamadı: {name}")
        return False
    if name and not was_installed:
        _save_rollback(RollbackRecord(task_label=name, packages_to_install=[name]), seq)
    return True


# --- Program kaldırma ve güncelleme ---

_APT_ENV = {"DEBIAN_FRONTEND": "noninteractive"}


def _blocked_message(blocked: list[package_guard.BlockedPackage]) -> str:
    names = ", ".join(f"{b.name} ({b.category})" for b in blocked)
    return f"Kritik sistem paketleri kaldırılacağı için işlem engellendi: {names}"


def _save_rollback(record: RollbackRecord, seq: int) -> None:
    """Geri alma kaydını yazar; yazılamazsa kaldırma başarılı sayılır, uyarı verilir."""
    try:
        save_record(record)
    except OSError as exc:
        _send({"seq": seq, "status": "ok", "message": f"Geri alma kaydı yazılamadı: {exc}"})


def _remove_apt(seq: int, name: str, purge: bool) -> bool:
    # Arayüzün planına güvenilmez: plan burada, root olarak yeniden hesaplanır
    plan = package_guard.plan_apt_removal(name)
    if plan.error:
        _error(seq, f"Kaldırma planı hesaplanamadı: {plan.error}")
        return False
    if plan.blocked:
        _error(seq, _blocked_message(plan.blocked))
        return False
    action = "purge" if purge else "remove"
    if not _run(["apt-get", action, "-y", "--autoremove", "--", name], seq, _APT_ENV):
        return False
    # Geri almada hedef ve ona bağımlı olduğu için kaldırılanlar yeniden kurulur;
    # artık gerekmeyen bağımlılıklar bunlarla birlikte kendiliğinden gelir.
    _save_rollback(RollbackRecord(task_label=name, packages_to_remove=plan.removed), seq)
    return True


def _exec_app_remove_apt(seq: int, params: dict[str, str]) -> bool:
    return _remove_apt(seq, params["name"], purge=False)


def _exec_app_remove_apt_purge(seq: int, params: dict[str, str]) -> bool:
    return _remove_apt(seq, params["name"], purge=True)


def _invoking_user_home() -> Path | None:
    """pkexec'i çağıran kullanıcının ev klasörü (PKEXEC_UID, bkz. pkexec(1))."""
    try:
        uid = int(os.environ["PKEXEC_UID"])
        return Path(pwd.getpwuid(uid).pw_dir)
    except (KeyError, ValueError):
        return None


def _delete_flatpak_user_data(seq: int, app_id: str) -> None:
    """~/.var/app/<app_id> klasörünü siler (flatpak --delete-data'nın karşılığı).

    Helper root olarak çalıştığı için `flatpak --delete-data` root'un ev klasörüne
    bakar; bu yüzden çağıran kullanıcının klasörü burada silinir.
    """
    home = _invoking_user_home()
    if home is None:
        _send({"seq": seq, "status": "ok", "message": "Kullanıcı ayarları bulunamadı"})
        return
    var_dir = home / ".var"
    app_root = var_dir / "app"
    target = app_root / app_id
    # Sembolik bağlantı izlenmez: yol bileşenlerinden biri bağlantıysa silinmez
    for part in (var_dir, app_root, target):
        if part.is_symlink():
            _send({"seq": seq, "status": "ok", "message": f"Atlandı (bağlantı): {part}"})
            return
    if not target.is_dir():
        return
    try:
        shutil.rmtree(target)
        _send({"seq": seq, "status": "ok", "message": f"Silindi: {target}"})
    except OSError as exc:
        _send({"seq": seq, "status": "ok", "message": f"Ayarlar silinemedi: {exc}"})


def _remove_flatpak(seq: int, app_id: str, delete_data: bool) -> bool:
    if not _run(["flatpak", "uninstall", "-y", "--noninteractive", "--system", app_id], seq):
        return False
    # Artık hiçbir uygulamanın kullanmadığı çalışma ortamları; başarısızlık önemsiz
    _run(["flatpak", "uninstall", "-y", "--noninteractive", "--system", "--unused"], seq)
    if delete_data:
        _delete_flatpak_user_data(seq, app_id)
    _save_rollback(RollbackRecord(task_label=app_id, flatpaks_removed=[app_id]), seq)
    return True


def _exec_app_remove_flatpak(seq: int, params: dict[str, str]) -> bool:
    return _remove_flatpak(seq, params["app_id"], delete_data=False)


def _exec_app_remove_flatpak_data(seq: int, params: dict[str, str]) -> bool:
    return _remove_flatpak(seq, params["app_id"], delete_data=True)


def _snap_notes(name: str) -> str | None:
    """`snap list <ad>` çıktısındaki Notes sütunu; snap kurulu değilse None."""
    try:
        r = subprocess.run(
            ["snap", "list", name],
            capture_output=True,
            text=True,
            timeout=30,
            shell=False,
            env={**os.environ, "LANG": "C.UTF-8", "LC_ALL": "C.UTF-8"},
        )
    except (FileNotFoundError, subprocess.TimeoutExpired):
        return None
    for line in r.stdout.splitlines()[1:]:
        parts = line.split()
        if parts and parts[0] == name:
            return parts[-1]
    return None


def _remove_snap(seq: int, name: str, purge: bool) -> bool:
    notes = _snap_notes(name)
    if notes is None:
        _error(seq, f"Snap kurulu değil: {name}")
        return False
    blocked = package_guard.snap_blocked(name, notes)
    if blocked:
        _error(seq, _blocked_message(blocked))
        return False
    cmd = ["snap", "remove"]
    if purge:
        cmd.append("--purge")
    if not _run([*cmd, name], seq):
        return False
    classic = [name] if "classic" in notes.split(",") else []
    record = RollbackRecord(task_label=name, snaps_removed=[name], snaps_classic=classic)
    _save_rollback(record, seq)
    return True


def _exec_app_remove_snap(seq: int, params: dict[str, str]) -> bool:
    return _remove_snap(seq, params["name"], purge=False)


def _exec_app_remove_snap_purge(seq: int, params: dict[str, str]) -> bool:
    return _remove_snap(seq, params["name"], purge=True)


def _exec_package_upgrade_one(seq: int, params: dict[str, str]) -> bool:
    cmd = ["apt-get", "install", "--only-upgrade", "-y", "--", params["name"]]
    return _run(cmd, seq, _APT_ENV)


def _exec_flatpak_update(seq: int, params: dict[str, str]) -> bool:
    cmd = ["flatpak", "update", "-y", "--noninteractive", "--system", params["app_id"]]
    return _run(cmd, seq)


def _exec_flatpak_install(seq: int, params: dict[str, str]) -> bool:
    app_id = params["app_id"]
    try:
        info = subprocess.run(
            ["flatpak", "info", "--system", app_id], capture_output=True, timeout=30, shell=False
        )
        was_installed = info.returncode == 0
    except (FileNotFoundError, subprocess.TimeoutExpired):
        was_installed = False
    cmd = ["flatpak", "install", "-y", "--noninteractive", "--system", "flathub", app_id]
    if not _run(cmd, seq):
        return False
    if not was_installed:
        _save_rollback(RollbackRecord(task_label=app_id, flatpaks_installed=[app_id]), seq)
    return True


def _exec_snap_refresh(seq: int, params: dict[str, str]) -> bool:
    return _run(["snap", "refresh", params["name"]], seq)


def _exec_flatpak_update_all(seq: int, params: dict[str, str]) -> bool:
    return _run(["flatpak", "update", "-y", "--noninteractive", "--system"], seq)


def _exec_snap_refresh_all(seq: int, params: dict[str, str]) -> bool:
    return _run(["snap", "refresh"], seq)


def _snap_install(seq: int, name: str, classic: bool) -> bool:
    was_installed = _snap_notes(name) is not None
    cmd = ["snap", "install", *(["--classic"] if classic else []), name]
    if not _run(cmd, seq):
        return False
    if not was_installed:
        _save_rollback(RollbackRecord(task_label=name, snaps_installed=[name]), seq)
    return True


def _exec_snap_install(seq: int, params: dict[str, str]) -> bool:
    return _snap_install(seq, params["name"], classic=False)


def _exec_snap_install_classic(seq: int, params: dict[str, str]) -> bool:
    return _snap_install(seq, params["name"], classic=True)


# --- Güç ve pil ---

# backend.power ile aynı yollar (helper backend'e bağımlı olmasın diye burada da tanımlı)
_LID_DROPIN = Path("/etc/systemd/logind.conf.d/90-linwas-lid.conf")


def _exec_power_set_lid_action(seq: int, params: dict[str, str]) -> bool:
    """logind ek ayar dosyası yazar; varsayılan (suspend) seçilince dosyayı siler.

    systemd-logind yeniden yüklenemez (CanReload=no) ve yeniden başlatmak oturumu
    etkileyebilir; ayar bir sonraki açılışta geçerli olur.
    """
    action = params["action"]
    try:
        if action == "suspend":
            _LID_DROPIN.unlink(missing_ok=True)
        else:
            _LID_DROPIN.parent.mkdir(parents=True, exist_ok=True)
            _LID_DROPIN.write_text(
                "# Linwas tarafından yazıldı (Güç ve pil › Kapak kapanınca)\n"
                "[Login]\n"
                f"HandleLidSwitch={action}\n"
                f"HandleLidSwitchExternalPower={action}\n",
                encoding="utf-8",
            )
            _LID_DROPIN.chmod(0o644)
    except OSError as exc:
        _error(seq, f"Kapak ayarı yazılamadı: {exc}")
        return False
    return True


# power.save_config'in değiştirdiği dosyalar (core.power_apply ile aynı yollar)
_POWER_FILES = [
    Path("/etc/linwas/power.json"),
    Path("/etc/systemd/logind.conf.d/90-linwas-power.conf"),
    _LID_DROPIN,
    Path("/etc/UPower/UPower.conf"),
]


def _exec_power_save_config(seq: int, params: dict[str, str]) -> bool:
    """Güç planlarını yazar; logind (düğmeler/kapak) ve UPower (pil seviyeleri) ayarlarını
    günceller, servise haber verir (servis yoksa planı hemen uygular)."""
    from linwas.core import power_apply, powerplan

    try:
        cfg = powerplan.loads(params["config"])
        power_apply.check_upower(cfg)  # pil seviyeleri sırası; hiçbir şey yazılmadan önce
        powerplan.write_config(cfg)
        power_apply.write_logind(cfg)
        power_apply.write_upower(cfg)
    except powerplan.PowerConfigError as exc:
        _error(seq, f"Geçersiz güç ayarı: {exc}")
        return False
    except OSError as exc:
        _error(seq, f"Güç ayarı yazılamadı: {exc}")
        return False
    if not power_apply.notify_service():
        power_apply.apply_once()
    return True


_POWERTOP_CSV = Path("/var/lib/linwas-power/powertop.csv")  # backend.power_report ile aynı yol


def _exec_power_powertop_report(seq: int, params: dict[str, str]) -> bool:
    """powertop'u 20 sn ölçümle çalıştırır; raporu herkesin okuyabileceği dosyaya yazar."""
    _POWERTOP_CSV.parent.mkdir(parents=True, exist_ok=True)
    _POWERTOP_CSV.parent.chmod(0o755)
    if not _run(["powertop", f"--csv={_POWERTOP_CSV}", "--time=20"], seq):
        return False
    try:
        _POWERTOP_CSV.chmod(0o644)
    except OSError as exc:
        _error(seq, f"Rapor okunamadı: {exc}")
        return False
    return True


def _exec_power_take_over(seq: int, params: dict[str, str]) -> bool:
    """Güç yönetimini Linwas'a verir: çakışan araçların servislerini kapatır (paketleri silmez),
    Linwas güç servisini açar ve etkin planı uygular. Kapatılan birimler geri vermek için
    kaydedilir.
    """
    from linwas.core import power_apply

    try:
        disabled = set(json.loads(power_apply.TAKEOVER_PATH.read_text(encoding="utf-8")))
    except (OSError, ValueError, TypeError):
        disabled = set()
    for name, unit, _pkg in power_apply.CONFLICTING_TOOLS:
        if not power_apply.unit_enabled(unit):
            continue
        _send({"seq": seq, "status": "ok", "message": f"{name} kapatılıyor…"})
        if not _run(["systemctl", "disable", "--now", "--", unit], seq):
            return False
        disabled.add(unit)
    try:
        power_apply.TAKEOVER_PATH.parent.mkdir(parents=True, exist_ok=True)
        _write_system_file(power_apply.TAKEOVER_PATH, json.dumps(sorted(disabled)) + "\n")
    except OSError as exc:
        _error(seq, f"Kayıt yazılamadı: {exc}")
        return False
    if power_apply.SERVICE_UNIT.exists():
        name = power_apply.SERVICE_NAME
        if not _run(["systemctl", "enable", "--now", "--", name], seq):
            return False
        return _run(["systemctl", "restart", "--", name], seq)
    # Kaynak koddan çalıştırma: servis yok, plan bir kez uygulanır
    power_apply.apply_once()
    return True


def _exec_power_give_back(seq: int, params: dict[str, str]) -> bool:
    """Devralmayı geri alır: Linwas güç servisini kapatır, kapatılan araçları yeniden açar."""
    from linwas.core import power_apply

    try:
        units = json.loads(power_apply.TAKEOVER_PATH.read_text(encoding="utf-8"))
    except (OSError, ValueError):
        units = []
    known = {unit for _n, unit, _p in power_apply.CONFLICTING_TOOLS}
    if power_apply.SERVICE_UNIT.exists() and not _run(
        ["systemctl", "disable", "--now", "--", power_apply.SERVICE_NAME], seq
    ):
        return False
    power_apply.release_ppd_now()  # servis ppd'yi durdurmuşsa (özel planda) geri açılır
    for unit in units if isinstance(units, list) else []:
        # Yalnızca bilinen araç birimleri (kayıt dosyası değiştirilmiş olsa bile)
        if unit in known and not _run(["systemctl", "enable", "--now", "--", unit], seq):
            return False
    power_apply.TAKEOVER_PATH.unlink(missing_ok=True)
    return True


def _capture(cmd: list[str], timeout: int = 60) -> str | None:
    """Komutun standart çıktısı; başarısızsa None."""
    try:
        r = subprocess.run(cmd, capture_output=True, text=True, timeout=timeout, shell=False)
    except (FileNotFoundError, subprocess.TimeoutExpired):
        return None
    return r.stdout if r.returncode == 0 else None


def _write_system_file(path: Path, text: str) -> None:
    """Yarım dosya kalmasın: geçici dosyaya yazıp yerine koyar (izin 644)."""
    tmp = path.with_name(path.name + ".linwas-tmp")
    tmp.write_text(text, encoding="utf-8")
    tmp.chmod(0o644)
    os.replace(tmp, path)


def _update_boot(seq: int) -> bool:
    """initramfs ve GRUB menüsünü yeniden oluşturur (yeni çekirdek satırı açılışta geçerli olur)."""
    if not _run(["update-initramfs", "-u"], seq):
        return False
    grub = shutil.which("update-grub")
    return _run([grub] if grub else ["grub-mkconfig", "-o", "/boot/grub/grub.cfg"], seq)


def _exec_hibernate_setup(seq: int, params: dict[str, str]) -> bool:
    """/swapfile oluşturur, etkinleştirir, fstab'a ve GRUB çekirdek satırına (resume) ekler.

    Herhangi bir adım başarısız olursa yapılanlar geri alınır (dosya silinir, fstab ve GRUB eski
    hâline döner).
    """
    from linwas.core import hibernate as hib

    size_gb = int(params["size_gb"])
    swap = hib.SWAPFILE
    try:
        fstab_old = hib.FSTAB.read_text(encoding="utf-8")
    except OSError as exc:
        _error(seq, f"/etc/fstab okunamadı: {exc}")
        return False
    if swap.exists() or hib.other_swapfile_entry(fstab_old) or hib.has_fstab_entry(fstab_old):
        _error(seq, f"{swap} zaten var; elle oluşturulmuş dosyaya dokunulmaz")
        return False
    fstype = (_capture(["findmnt", "-no", "FSTYPE", "/"]) or "").strip()
    fs_uuid = (_capture(["findmnt", "-no", "UUID", "/"]) or "").strip()
    if fstype not in hib.SUPPORTED_FS:
        _error(seq, f"Bu dosya sisteminde desteklenmiyor: {fstype or '?'}")
        return False
    if not re.fullmatch(r"[0-9A-Fa-f-]{8,64}", fs_uuid):
        _error(seq, "Kök dosya sisteminin UUID'si okunamadı")
        return False
    if shutil.disk_usage("/").free < (size_gb + hib.SPARE_GB) * 1024**3:
        _error(seq, "Diskte yeterli boş alan yok")
        return False

    def undo() -> None:
        subprocess.run(["swapoff", str(swap)], capture_output=True, shell=False)
        swap.unlink(missing_ok=True)
        hib.GRUB_DROPIN.unlink(missing_ok=True)
        with contextlib.suppress(OSError):
            if hib.FSTAB.read_text(encoding="utf-8") != fstab_old:
                _write_system_file(hib.FSTAB, fstab_old)

    try:
        _send({"seq": seq, "status": "ok", "message": f"{size_gb} GB swap dosyası yazılıyor…"})
        if fstype == "btrfs":
            # btrfs: kopyala-yaz kapalı, sıkıştırmasız dosya (btrfs-filesystem(8) mkswapfile)
            ok = _run(
                ["btrfs", "filesystem", "mkswapfile", "--size", f"{size_gb}g", str(swap)], seq
            )
            out = (
                _capture(["btrfs", "inspect-internal", "map-swapfile", "-r", str(swap)])
                if ok
                else None
            )
            offset = hib.parse_btrfs_offset(out or "")
        else:
            # mkswap(8): ext4/xfs'te fallocate yerine dd önerilir (dosyada boşluk kalmasın)
            ok = _run(
                [
                    "dd",
                    "if=/dev/zero",
                    f"of={swap}",
                    "bs=1M",
                    f"count={size_gb * 1024}",
                    "status=none",
                ],
                seq,
            )
            if ok:
                swap.chmod(0o600)
                ok = _run(["mkswap", str(swap)], seq)
            out = _capture(["filefrag", "-v", str(swap)]) if ok else None
            offset = hib.parse_filefrag_offset(out or "")
        if not ok or offset is None:
            undo()
            _error(seq, "Swap dosyası hazırlanamadı")
            return False
        if not _run(["swapon", str(swap)], seq):
            undo()
            return False
        _write_system_file(hib.FSTAB, hib.fstab_add(fstab_old))
        hib.GRUB_DROPIN.parent.mkdir(parents=True, exist_ok=True)
        _write_system_file(hib.GRUB_DROPIN, hib.grub_dropin_text(fs_uuid, offset))
        if not _update_boot(seq):
            undo()
            _update_boot(seq)
            return False
    except OSError as exc:
        undo()
        _error(seq, f"Hazırda bekletme kurulamadı: {exc}")
        return False
    return True


def _exec_hibernate_remove(seq: int, params: dict[str, str]) -> bool:
    """Linwas'ın kurduğu swap dosyasını ve resume ayarını kaldırır (elle kurulana dokunmaz)."""
    from linwas.core import hibernate as hib

    try:
        fstab = hib.FSTAB.read_text(encoding="utf-8")
    except OSError as exc:
        _error(seq, f"/etc/fstab okunamadı: {exc}")
        return False
    ours = hib.has_fstab_entry(fstab)
    if not ours and not hib.GRUB_DROPIN.exists():
        _error(seq, "Linwas'ın kurduğu hazırda bekletme ayarı bulunamadı")
        return False
    try:
        hib.GRUB_DROPIN.unlink(missing_ok=True)
        if ours:
            # Swap'taki sayfalar belleğe geri alınır; bellek yetmezse swapoff başarısız olur
            active = any(
                n == str(hib.SWAPFILE)
                for n, _k, _s in hib.parse_swaps(Path("/proc/swaps").read_text(encoding="utf-8"))
            )
            if active and not _run(["swapoff", str(hib.SWAPFILE)], seq):
                return False
            _write_system_file(hib.FSTAB, hib.fstab_remove(fstab))
            hib.SWAPFILE.unlink(missing_ok=True)
    except OSError as exc:
        _error(seq, f"Kaldırılamadı: {exc}")
        return False
    return _update_boot(seq)


def _exec_hardware_memory_report(seq: int, params: dict[str, str]) -> bool:
    """Bellek modüllerini okur (dmidecode); seri numarasız özeti herkesin okuyabileceği
    dosyaya yazar. Çıktı ilerleme olarak gönderilmez (seri numaraları içerir)."""
    from linwas.plugins.hardware_info import probe

    try:
        r = subprocess.run(
            ["dmidecode", "-t", "memory"], capture_output=True, text=True, timeout=30, shell=False
        )
    except (FileNotFoundError, subprocess.TimeoutExpired) as exc:
        _error(seq, f"dmidecode çalıştırılamadı: {exc}")
        return False
    if r.returncode != 0:
        _error(seq, f"dmidecode başarısız (kod {r.returncode})")
        return False
    report = probe.parse_dmidecode_memory(r.stdout)
    target = probe.MEMORY_REPORT
    try:
        target.parent.mkdir(parents=True, exist_ok=True)
        target.parent.chmod(0o755)
        target.write_text(probe.report_to_json(report), encoding="utf-8")
        target.chmod(0o644)
    except OSError as exc:
        _error(seq, f"Rapor yazılamadı: {exc}")
        return False
    _ok(seq, f"{len(report.modules)} modül")
    return True


def _exec_fonts_install_microsoft(seq: int, params: dict[str, str]) -> bool:
    """Kullanıcı lisansı Linwas penceresinde kabul etti; Ubuntu'daki debconf sorusu
    önceden yanıtlanır (Debian/Pardus paketinde bu soru yok, satır yok sayılır)."""
    answer = "ttf-mscorefonts-installer msttcorefonts/accepted-mscorefonts-eula select true\n"
    with contextlib.suppress(FileNotFoundError, subprocess.TimeoutExpired):
        subprocess.run(["debconf-set-selections"], input=answer, text=True, timeout=30, shell=False)
    cmd = ["apt-get", "install", "-y", "--", "ttf-mscorefonts-installer"]
    return _run(cmd, seq, {"DEBIAN_FRONTEND": "noninteractive"})


def _exec_autoupdate_configure(seq: int, params: dict[str, str]) -> bool:
    """Otomatik güncelleme ayarını yazar (/etc/linwas/autoupdate.json; zamanlayıcı okur)."""
    from linwas.core import autoupdate

    cfg = autoupdate.config_with(
        autoupdate.load_config(),
        enabled=params["enabled"] == "true",
        snapshot=params["snapshot"] == "true",
        pause_weeks=int(params["pause_weeks"]),
    )
    try:
        autoupdate.write_config(cfg)
    except OSError as exc:
        _error(seq, f"Ayar yazılamadı: {exc}")
        return False
    return True


def _exec_power_schedule_reboot(seq: int, params: dict[str, str]) -> bool:
    return _run(["shutdown", "-r", params["time"]], seq)


def _exec_power_cancel_reboot(seq: int, params: dict[str, str]) -> bool:
    return _run(["shutdown", "-c"], seq)


def _exec_driver_remove_nvidia(seq: int, params: dict[str, str]) -> bool:
    """NVIDIA sürücüsünü tamamen kaldırır; açılışta açık kaynak sürücü (nouveau) kullanılır.

    apt-get, eşleşen paket yoksa ve ifadede ".", "?" ya da "*" varsa onu düzenli ifade sayar
    (apt-get(8)); ".*nvidia.*" adında nvidia geçen kurulu paketleri seçer.
    """
    if not _run(["apt-get", "purge", "-y", "--", ".*nvidia.*"], seq, _APT_ENV):
        return False
    return _run(["apt-get", "autoremove", "-y"], seq, _APT_ENV)


def _exec_driver_rebuild_modules(seq: int, params: dict[str, str]) -> bool:
    """DKMS modüllerini çalışan çekirdek için yeniden derleyip kurar (`dkms autoinstall`).

    Çekirdek sürümü parametre olarak alınmaz; helper'ın çalıştığı çekirdekten okunur.
    """
    return _run(["dkms", "autoinstall", "-k", os.uname().release], seq)


def _exec_prime_select(seq: int, params: dict[str, str]) -> bool:
    """Ubuntu nvidia-prime kipi; oturum yeniden açılınca (ya da yeniden başlatınca) geçerli."""
    return _run(["prime-select", params["mode"]], seq)


def _exec_firmware_refresh(seq: int, params: dict[str, str]) -> bool:
    return _run(["fwupdmgr", "refresh", "--force"], seq)


def _exec_firmware_update_device(seq: int, params: dict[str, str]) -> bool:
    return _run(["fwupdmgr", "update", params["device_id"], "-y", "--no-reboot-check"], seq)


def _exec_kernel_install_backports(seq: int, params: dict[str, str]) -> bool:
    """Backports'taki çekirdeği kurar (paket adı mimariden: linux-image-<mimari>)."""
    try:
        arch = subprocess.run(
            ["dpkg", "--print-architecture"], capture_output=True, text=True, timeout=10
        ).stdout.strip()
    except (FileNotFoundError, subprocess.TimeoutExpired):
        arch = ""
    if not re.match(r"^[a-z0-9]+$", arch):
        _error(seq, "Sistem mimarisi okunamadı")
        return False
    cmd = ["apt-get", "install", "-y", "-t", params["suite"], "--", f"linux-image-{arch}"]
    return _run(cmd, seq, _APT_ENV)


# DKMS modül imza anahtarı: Ubuntu (shim-signed) ve Debian (dkms)
_MOK_KEYS = ("/var/lib/shim-signed/mok/MOK.der", "/var/lib/dkms/mok.pub")


def _exec_secureboot_enroll_mok(seq: int, params: dict[str, str]) -> bool:
    """İmza anahtarını kayda alır; yeniden başlatmada MOK ekranında aynı şifre istenir.

    mokutil şifreyi terminal yokken standart girdiden iki kez okur (komut satırında görünmez).
    """
    key = next((k for k in _MOK_KEYS if Path(k).is_file()), "")
    if not key:
        _error(seq, "Sürücü imza anahtarı bulunamadı (sürücü kurulduktan sonra oluşur).")
        return False
    password = params["password"]
    try:
        r = subprocess.run(
            ["mokutil", "--import", key],
            input=f"{password}\n{password}\n",
            capture_output=True,
            text=True,
            timeout=60,
            shell=False,
        )
    except (FileNotFoundError, subprocess.TimeoutExpired) as exc:
        _error(seq, f"mokutil çalıştırılamadı: {exc}")
        return False
    if r.returncode != 0:
        _error(seq, (r.stdout + r.stderr).strip() or "mokutil başarısız oldu")
        return False
    return True


# Flathub'ın resmi kurulum adresi (flathub.org/setup)
_FLATHUB_REPO = "https://dl.flathub.org/repo/flathub.flatpakrepo"


def _exec_flatpak_setup(seq: int, params: dict[str, str]) -> bool:
    """Flatpak'ı dağıtım deposundan kurar ve Flathub deposunu sistem geneline ekler."""
    new = not _apt_installed("flatpak")
    if new and not _run(["apt-get", "install", "-y", "--", "flatpak"], seq, _APT_ENV):
        return False
    if new:
        _save_rollback(RollbackRecord(task_label="Flatpak", packages_to_install=["flatpak"]), seq)
    return _run(
        ["flatpak", "remote-add", "--if-not-exists", "--system", "flathub", _FLATHUB_REPO], seq
    )


def _exec_wine_setup(seq: int, params: dict[str, str]) -> bool:
    """Wine'ı dağıtım deposundan kurar. 32 bit Windows programları için i386 mimarisi
    etkinleştirilir (dpkg --add-architecture) ve wine32:i386 kurulur."""
    try:
        r = subprocess.run(
            ["dpkg", "--print-foreign-architectures"],
            capture_output=True,
            text=True,
            timeout=30,
            shell=False,
        )
        foreign = r.stdout.split()
    except (FileNotFoundError, subprocess.TimeoutExpired):
        foreign = []
    if "i386" not in foreign:
        if not _run(["dpkg", "--add-architecture", "i386"], seq, _APT_ENV):
            return False
        if not _run(["apt-get", "update"], seq, _APT_ENV):
            return False
    new = [name for name in ("wine", "wine64") if not _apt_installed(name)]
    cmd = ["apt-get", "install", "-y", "--", "wine", "wine64", "wine32:i386"]
    if not _run(cmd, seq, _APT_ENV):
        return False
    if new:
        _save_rollback(RollbackRecord(task_label="Wine", packages_to_install=new), seq)
    return True


# --- Dosya yedeği ve geri yükleme ---

# Helper'ın yedekleyip geri yükleyebileceği yollar (yazdığı dosyalarla sınırlı)
_RESTORABLE_PREFIXES = (
    "/etc/apt/sources.list.d/linwas-",
    "/usr/share/keyrings/linwas-",
    "/etc/systemd/logind.conf.d/90-linwas",
    "/etc/udev/rules.d/90-linwas-",
    "/etc/linwas/",
    "/usr/local/share/linwas/",
    "/usr/share/linwas/",
)


def _restorable(path: Path) -> bool:
    text = str(path)
    return ".." not in path.parts and any(text.startswith(p) for p in _RESTORABLE_PREFIXES)


def _with_file_backup(seq: int, label: str, paths: list[Path], write: Any) -> bool:
    """Dosyaları yedekler, `write()` çalıştırır, başarılıysa geri alma kaydını yazar."""
    record = RollbackRecord(task_label=label)
    files_dir = ROLLBACK_DIR / record.id / "files"
    for i, path in enumerate(paths):
        backup = ""
        if path.is_file() and not path.is_symlink():
            try:
                files_dir.mkdir(parents=True, exist_ok=True)
                dest = files_dir / str(i)
                shutil.copy2(path, dest)
                backup = str(dest)
            except OSError as exc:
                _error(seq, f"Yedek alınamadı: {exc}")
                return False
        record.file_backups.append(FileBackup(str(path), backup))
    if not write():
        shutil.rmtree(ROLLBACK_DIR / record.id, ignore_errors=True)
        return False
    _save_rollback(record, seq)
    return True


def _exec_rollback_restore_files(seq: int, params: dict[str, str]) -> bool:
    try:
        record = load_record(params["record_id"])
    except (OSError, ValueError, KeyError, TypeError) as exc:
        _error(seq, f"Geri alma kaydı okunamadı: {exc}")
        return False
    record_dir = (ROLLBACK_DIR / record.id).resolve()
    for fb in record.file_backups:
        original = Path(fb.original_path)
        if not _restorable(original):
            _error(seq, f"Bu dosya geri yüklenemez: {original}")
            return False
        try:
            if fb.backup_path:
                backup = Path(fb.backup_path).resolve()
                if record_dir not in backup.parents:
                    _error(seq, f"Yedek kayıt dizini dışında: {backup}")
                    return False
                shutil.copy2(backup, original)
            else:
                original.unlink(missing_ok=True)
        except OSError as exc:
            _error(seq, f"Geri yüklenemedi ({original}): {exc}")
            return False
        _send({"seq": seq, "status": "ok", "message": f"Geri yüklendi: {original}"})
    return True


def _exec_file_write_text(seq: int, params: dict[str, str]) -> bool:
    path = Path(params["path"])

    def write() -> bool:
        try:
            path.parent.mkdir(parents=True, exist_ok=True)
            path.write_text(params["content"], encoding="utf-8")
            path.chmod(0o644)
        except OSError as exc:
            _error(seq, f"Dosya yazılamadı: {exc}")
            return False
        return True

    return _with_file_backup(seq, str(path), [path], write)


def _exec_not_implemented(seq: int, params: dict[str, str]) -> bool:
    _error(seq, "Bu işlem henüz uygulanmadı")
    return False


_EXECUTORS: dict[str, Any] = {
    "package.install": _exec_package_install,
    "package.remove": _exec_package_remove,
    "app.remove_apt": _exec_app_remove_apt,
    "app.remove_apt_purge": _exec_app_remove_apt_purge,
    "app.remove_flatpak": _exec_app_remove_flatpak,
    "app.remove_flatpak_data": _exec_app_remove_flatpak_data,
    "app.remove_snap": _exec_app_remove_snap,
    "app.remove_snap_purge": _exec_app_remove_snap_purge,
    "package.upgrade_one": _exec_package_upgrade_one,
    "flatpak.update": _exec_flatpak_update,
    "flatpak.install": _exec_flatpak_install,
    "snap.refresh": _exec_snap_refresh,
    "flatpak.update_all": _exec_flatpak_update_all,
    "snap.refresh_all": _exec_snap_refresh_all,
    "snap.install": _exec_snap_install,
    "snap.install_classic": _exec_snap_install_classic,
    "power.set_lid_action": lambda seq, p: _with_file_backup(
        seq, "lid", [_LID_DROPIN], lambda: _exec_power_set_lid_action(seq, p)
    ),
    "power.save_config": lambda seq, p: _with_file_backup(
        seq, "power", _POWER_FILES, lambda: _exec_power_save_config(seq, p)
    ),
    "power.powertop_report": _exec_power_powertop_report,
    "power.take_over": _exec_power_take_over,
    "power.give_back": _exec_power_give_back,
    "hibernate.setup": _exec_hibernate_setup,
    "hibernate.remove": _exec_hibernate_remove,
    "hardware.memory_report": _exec_hardware_memory_report,
    "fonts.install_microsoft": _exec_fonts_install_microsoft,
    "package.update_index": _exec_package_update_index,
    "clock.fix": _exec_clock_fix,
    "package.autoremove": _exec_package_autoremove,
    "package.fix_broken": _exec_package_fix_broken,
    "package.update_all": _exec_package_update_all,
    "service.enable": _exec_service_enable,
    "service.disable": _exec_service_disable,
    "service.restart": _exec_service_restart,
    # Dosya yazan işlemler önce yedek alır (hızlı geri alma)
    "apt.add_key": lambda seq, p: _with_file_backup(
        seq, p["keyring_path"], [Path(p["keyring_path"])], lambda: _exec_apt_add_key(seq, p)
    ),
    "apt.add_source": lambda seq, p: _with_file_backup(
        seq,
        p["list_name"],
        [Path("/etc/apt/sources.list.d") / p["list_name"]],
        lambda: _exec_apt_add_source(seq, p),
    ),
    "deb.install": _exec_deb_install,
    "file.write_text": _exec_file_write_text,
    "rollback.restore_files": _exec_rollback_restore_files,
    "snapshot.timeshift_create": _exec_snapshot_timeshift_create,
    "wine.setup": _exec_wine_setup,
    "flatpak.setup": _exec_flatpak_setup,
    "driver.remove_nvidia": _exec_driver_remove_nvidia,
    "driver.rebuild_modules": _exec_driver_rebuild_modules,
    "prime.select": _exec_prime_select,
    "firmware.refresh": _exec_firmware_refresh,
    "firmware.update_device": _exec_firmware_update_device,
    "kernel.install_backports": _exec_kernel_install_backports,
    "secureboot.enroll_mok": _exec_secureboot_enroll_mok,
    "autoupdate.configure": _exec_autoupdate_configure,
    "power.schedule_reboot": _exec_power_schedule_reboot,
    "power.cancel_reboot": _exec_power_cancel_reboot,
    "snapshot.timeshift_restore": _exec_snapshot_timeshift_restore,
    "snapshot.timeshift_delete": _exec_snapshot_timeshift_delete,
    "firmware.fwupd_update": _exec_firmware_fwupd_update,
    "apt.clean": _exec_apt_clean,
    "journal.vacuum": _exec_journal_vacuum,
}


def _handle(request: dict[str, Any]) -> bool:
    """Tek isteği işler. False dönerse bağlantı kesilmeli."""
    seq = request.get("seq", 0)
    op_id = request.get("op_id", "")
    raw_params = request.get("params", {})

    try:
        params = validate(op_id, raw_params)
    except ValidationError as exc:
        _error(seq, f"Doğrulama hatası: {exc}")
        return False

    executor = _EXECUTORS.get(op_id)
    if executor is None:
        _error(seq, f"Uygulayıcı bulunamadı: {op_id!r}")
        return False

    success = executor(seq, params)
    if success:
        _ok(seq, "Tamamlandı")
    return success


def main() -> None:
    """Root helper giriş noktası; root olarak çalışmalıdır."""
    for raw_line in sys.stdin:
        line = raw_line.strip()
        if not line:
            continue
        try:
            request = json.loads(line)
        except json.JSONDecodeError as exc:
            _send({"seq": 0, "status": "error", "message": f"JSON hatası: {exc}", "progress": 0.0})
            sys.exit(1)

        ok = _handle(request)
        if not ok:
            sys.exit(1)


if __name__ == "__main__":
    main()
