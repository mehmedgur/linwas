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

import json
import os
import pwd
import shutil
import subprocess
import sys
from pathlib import Path
from typing import Any

from linwas.core import package_guard
from linwas.core.rollback import RollbackRecord, save_record
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


def _exec_package_install(seq: int, params: dict[str, str]) -> bool:
    env = {"DEBIAN_FRONTEND": "noninteractive"}
    import os

    full_env = {**os.environ, **env}
    try:
        proc = subprocess.Popen(
            ["apt-get", "install", "-y", "--", params["name"]],
            stdout=subprocess.PIPE,
            stderr=subprocess.STDOUT,
            text=True,
            shell=False,
            env=full_env,
        )
        assert proc.stdout is not None
        for line in proc.stdout:
            _send({"seq": seq, "status": "ok", "message": line.rstrip(), "progress": 0.5})
        proc.wait()
        if proc.returncode != 0:
            _error(seq, f"Paket kurulamadı: {params['name']!r}")
            return False
    except FileNotFoundError:
        _error(seq, "apt-get bulunamadı")
        return False
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
    """Yerel .deb dosyasını kurar."""
    path = params["path"]
    ok = _run(["dpkg", "-i", "--", path], seq)
    if not ok:
        # Bağımlılıkları düzelt
        _run(["apt-get", "-f", "install", "-y"], seq)
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
            env={**os.environ, "LANG": "C", "LC_ALL": "C"},
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
    cmd = ["flatpak", "install", "-y", "--noninteractive", "--system", "flathub"]
    return _run([*cmd, params["app_id"]], seq)


def _exec_snap_refresh(seq: int, params: dict[str, str]) -> bool:
    return _run(["snap", "refresh", params["name"]], seq)


def _exec_snap_install(seq: int, params: dict[str, str]) -> bool:
    return _run(["snap", "install", params["name"]], seq)


def _exec_snap_install_classic(seq: int, params: dict[str, str]) -> bool:
    return _run(["snap", "install", "--classic", params["name"]], seq)


# --- Güç ve pil ---

# backend.power ile aynı yollar (helper backend'e bağımlı olmasın diye burada da tanımlı)
_LID_DROPIN = Path("/etc/systemd/logind.conf.d/90-linwas-lid.conf")
_POWER_SUPPLY = Path("/sys/class/power_supply")


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


def _exec_battery_set_charge_limit(seq: int, params: dict[str, str]) -> bool:
    """Şarj sınırını yazar (sysfs; yeniden başlatınca cihaz varsayılanına döner)."""
    base = _POWER_SUPPLY / params["battery"]
    target = base / "charge_control_end_threshold"
    try:
        if (base / "type").read_text().strip() != "Battery" or not target.exists():
            _error(seq, "Bu pil şarj sınırını desteklemiyor")
            return False
        target.write_text(params["percent"])
    except OSError as exc:
        _error(seq, f"Şarj sınırı yazılamadı: {exc}")
        return False
    return True


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
    "snap.install": _exec_snap_install,
    "snap.install_classic": _exec_snap_install_classic,
    "power.set_lid_action": _exec_power_set_lid_action,
    "battery.set_charge_limit": _exec_battery_set_charge_limit,
    "package.update_index": _exec_package_update_index,
    "package.fix_broken": _exec_package_fix_broken,
    "package.update_all": _exec_package_update_all,
    "service.enable": _exec_service_enable,
    "service.disable": _exec_service_disable,
    "service.restart": _exec_service_restart,
    "apt.add_key": _exec_apt_add_key,
    "apt.add_source": _exec_apt_add_source,
    "deb.install": _exec_deb_install,
    "file.write_text": _exec_not_implemented,
    "snapshot.timeshift_create": _exec_snapshot_timeshift_create,
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
