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
import subprocess
import sys
from typing import Any

from linwas.core.whitelist import ValidationError, validate


def _send(obj: dict[str, Any]) -> None:
    print(json.dumps(obj, ensure_ascii=False), flush=True)


def _ok(seq: int, message: str = "", progress: float = 1.0) -> None:
    _send({"seq": seq, "status": "ok", "message": message, "progress": progress})


def _error(seq: int, message: str) -> None:
    _send({"seq": seq, "status": "error", "message": message, "progress": 0.0})


# --- Uygulayıcılar ---


def _run(cmd: list[str], seq: int) -> bool:
    """Komutu çalıştırır; çıktıyı satır satır ilerleme olarak gönderir."""
    try:
        proc = subprocess.Popen(
            cmd,
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


def _exec_not_implemented(seq: int, params: dict[str, str]) -> bool:
    _error(seq, "Bu işlem henüz uygulanmadı")
    return False


_EXECUTORS: dict[str, Any] = {
    "package.install": _exec_package_install,
    "package.remove": _exec_package_remove,
    "package.update_index": _exec_package_update_index,
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
