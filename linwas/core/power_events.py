"""Güç olaylarını beklemek: priz/pil (UPower) ve güç kipi (power-profiles-daemon) değişimi.

Sürekli yoklamak yerine `gdbus monitor` ile D-Bus sinyalleri dinlenir; her sinyal satırı
bekleyeni uyandırır. gdbus çıktısı boruya yazınca tamponlandığı için `stdbuf -oL` ile satır
satır alınır. UPower ya da ppd yoksa (ya da gdbus kurulu değilse) bekleyen yalnızca süre
dolunca uyanır; yani sinyal yalnızca hızlandırır, doğruluk her uyanışta yeniden okumaya
dayanır.

Kaynaklar: gdbus(1) `monitor --system --dest`; UPower ve ppd `PropertiesChanged` yayar
(net.hadess.PowerProfiles adı ppd 0.12–0.30'un hepsinde var).
"""

from __future__ import annotations

import contextlib
import shutil
import subprocess
import threading
import time

UPOWER_BUS = "org.freedesktop.UPower"
PPD_BUS = "net.hadess.PowerProfiles"
# Arka arkaya gelen sinyalleri tek uyanışta toplamak için kısa bekleme
DEBOUNCE_SECONDS = 1.0


class EventWatcher:
    """Sinyal gelince `wake` olayını kurar. `stop()` alt süreçleri kapatır."""

    def __init__(self, wake: threading.Event, buses: tuple[str, ...] = (UPOWER_BUS, PPD_BUS)):
        self.wake = wake
        self._buses = buses
        self._procs: list[subprocess.Popen[str]] = []
        self._stopped = threading.Event()

    def start(self) -> bool:
        """Dinlemeyi başlatır; gdbus yoksa False (çağıran süreli beklemeye düşer)."""
        gdbus = shutil.which("gdbus")
        stdbuf = shutil.which("stdbuf")
        if not gdbus:
            return False
        for bus in self._buses:
            cmd = [gdbus, "monitor", "--system", "--dest", bus]
            if stdbuf:
                cmd = [stdbuf, "-oL", *cmd]
            threading.Thread(target=self._watch, args=(cmd,), daemon=True).start()
        return True

    def _watch(self, cmd: list[str]) -> None:
        # Süreç kapanırsa (ör. servis yeniden başladı) biraz bekleyip yeniden açılır
        while not self._stopped.is_set():
            try:
                proc = subprocess.Popen(
                    cmd,
                    stdout=subprocess.PIPE,
                    stderr=subprocess.DEVNULL,
                    text=True,
                    shell=False,
                    env={"PATH": "/usr/sbin:/usr/bin:/sbin:/bin", "LC_ALL": "C.UTF-8"},
                )
            except OSError:
                return
            self._procs.append(proc)
            assert proc.stdout is not None
            for line in proc.stdout:
                # Sinyal satırları nesne yoluyla başlar; "Monitoring…", "The name…" bilgi satırı
                if line.startswith("/"):
                    self.wake.set()
            proc.wait()
            with contextlib.suppress(ValueError):
                self._procs.remove(proc)
            self._stopped.wait(10)

    def stop(self) -> None:
        self._stopped.set()
        for proc in list(self._procs):
            with contextlib.suppress(OSError):
                proc.terminate()


def wait(wake: threading.Event, timeout: float) -> bool:
    """`timeout` saniyeye kadar bekler; olay geldiyse kısa bir süre daha toplar. Olay geldiyse
    True."""
    hit = wake.wait(max(0.0, timeout))
    if hit:
        time.sleep(DEBOUNCE_SECONDS)
    wake.clear()
    return hit
