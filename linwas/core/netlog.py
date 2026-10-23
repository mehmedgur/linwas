"""Ağ kalitesi kaydı (yerel, açık rızayla): örnekleri saklar ve özetler. Qt'ye bağımlı değildir.

Dosya: ~/.local/share/linwas/net_quality.jsonl — her satır bir örnek (JSON). Örnekler
`RETENTION_DAYS` günden sonra silinir. Yalnızca ağ/cihaz adı ve sayılar tutulur; site, trafik
içeriği ya da ekran bilgisi yoktur. Ölçüm Ayarlar'dan kapatılınca yeni örnek yazılmaz;
"Kullanıcı verileri" sayfasından dosya silinebilir.
"""

from __future__ import annotations

import json
import time
from dataclasses import asdict, dataclass, fields
from pathlib import Path

from linwas.core import user_data

RETENTION_DAYS = 7
FILE_NAME = "net_quality.jsonl"
# İki örnek arası bu süreyi aşarsa (Linwas kapalıydı, bilgisayar uyudu) aradaki zaman "veri yok"
# sayılır; kopma saymak için eşik örnek aralığının bu katıdır.
GAP_FACTOR = 3
DEFAULT_INTERVAL = 60  # saniye

KIND_WIFI = "wifi"
KIND_BT = "bt"

# Gecikme (ms) ve kayıp eşikleri — sezgisel; ev Wi-Fi'ında geçit (router) gecikmesi için
GOOD_RTT_MS = 30.0
FAIR_RTT_MS = 100.0
GOOD_LOSS = 0.02
FAIR_LOSS = 0.10


def default_path() -> Path:
    return user_data.data_dir() / FILE_NAME


@dataclass(frozen=True)
class Sample:
    ts: int  # unix saniye
    kind: str  # KIND_WIFI | KIND_BT
    name: str  # Wi-Fi: ağ adı; Bluetooth: cihaz adı
    ident: str = ""  # Wi-Fi: BSSID; Bluetooth: MAC (aygıtı ayırt etmek için)
    connected: bool = True
    signal: int | None = None  # Wi-Fi: 0-100; Bluetooth: RSSI (dBm)
    rtt_ms: float | None = None  # ağ geçidine gecikme
    loss: float | None = None  # 0-1, geçide giden denemelerde kayıp
    band: str = ""  # "2.4" | "5" | "6" (Wi-Fi)
    battery: int | None = None  # Bluetooth pil yüzdesi
    user: bool = False  # kullanıcı Linwas'tan bağlantıyı kendisi kesti/kapattı (kopma sayılmaz)

    @classmethod
    def from_dict(cls, data: object) -> Sample | None:
        """Bozuk/eksik satırda None; tip hatalı alanlar varsayılana düşer."""
        if not isinstance(data, dict):
            return None
        ts, kind = data.get("ts"), data.get("kind")
        if not isinstance(ts, int) or isinstance(ts, bool) or kind not in (KIND_WIFI, KIND_BT):
            return None
        defaults = cls(ts=ts, kind=kind, name="")
        values: dict[str, object] = {"ts": ts, "kind": kind}
        for f in fields(cls):
            if f.name in values or f.name not in data:
                continue
            value, default = data[f.name], getattr(defaults, f.name)
            if f.name in ("signal", "battery"):
                ok = value is None or (isinstance(value, int) and not isinstance(value, bool))
            elif f.name in ("rtt_ms", "loss"):
                ok = value is None or (
                    isinstance(value, (int, float)) and not isinstance(value, bool)
                )
            else:
                ok = isinstance(value, type(default))
            values[f.name] = value if ok else default
        return cls(**values)  # type: ignore[arg-type]


# --- Saklama ---


def append(sample: Sample, path: Path | None = None) -> None:
    target = path or default_path()
    try:
        target.parent.mkdir(parents=True, exist_ok=True)
        with target.open("a", encoding="utf-8") as fh:
            fh.write(json.dumps(asdict(sample), ensure_ascii=False, separators=(",", ":")) + "\n")
    except OSError:
        pass


def load(
    since: int | None = None, kind: str | None = None, path: Path | None = None
) -> list[Sample]:
    """Örnekleri zamana göre sıralı döndürür; bozuk satırlar atlanır."""
    target = path or default_path()
    try:
        lines = target.read_text(encoding="utf-8").splitlines()
    except OSError:
        return []
    samples: list[Sample] = []
    for line in lines:
        try:
            sample = Sample.from_dict(json.loads(line))
        except json.JSONDecodeError:
            continue
        if sample is None or (since is not None and sample.ts < since):
            continue
        if kind is not None and sample.kind != kind:
            continue
        samples.append(sample)
    return sorted(samples, key=lambda s: s.ts)


def prune(now: int | None = None, path: Path | None = None) -> int:
    """Saklama süresinden eski örnekleri siler; silinen satır sayısını döndürür."""
    target = path or default_path()
    cutoff = (int(time.time()) if now is None else now) - RETENTION_DAYS * 86400
    try:
        lines = target.read_text(encoding="utf-8").splitlines()
    except OSError:
        return 0
    kept: list[str] = []
    for line in lines:
        try:
            sample = Sample.from_dict(json.loads(line))
        except json.JSONDecodeError:
            continue
        if sample is not None and sample.ts >= cutoff:
            kept.append(line)
    removed = len(lines) - len(kept)
    if removed:
        try:
            tmp = target.with_suffix(".tmp")
            tmp.write_text("".join(line + "\n" for line in kept), encoding="utf-8")
            tmp.replace(target)
        except OSError:
            return 0
    return removed


# --- Özetleme ---


def classify(rtt_ms: float | None, loss: float | None) -> str:
    """ "good" | "fair" | "bad"; gecikme ve kayıp bilinmiyorsa (ping yok) "unknown"."""
    if rtt_ms is None and loss is None:
        return "unknown"
    if loss is not None and loss >= 1.0:
        return "bad"
    if (rtt_ms is not None and rtt_ms > FAIR_RTT_MS) or (loss is not None and loss > FAIR_LOSS):
        return "bad"
    if (rtt_ms is not None and rtt_ms > GOOD_RTT_MS) or (loss is not None and loss > GOOD_LOSS):
        return "fair"
    return "good"


@dataclass(frozen=True)
class Bucket:
    start: int
    state: str  # "nodata" | "offline" | "unknown" | "good" | "fair" | "bad"
    rtt_ms: float | None = None
    signal: int | None = None


_STATE_ORDER = {"good": 0, "unknown": 1, "fair": 2, "bad": 3, "offline": 4}


def bucketize(
    samples: list[Sample], start: int, end: int, bucket_seconds: int = 900
) -> list[Bucket]:
    """[start, end) aralığını eşit dilimlere böler; her dilimin durumu en kötü örneğe göre.

    Dilimde örnek yoksa "nodata" (Linwas kapalıydı ya da ölçüm kapalıydı).
    """
    if bucket_seconds <= 0 or end <= start:
        return []
    count = -(-(end - start) // bucket_seconds)
    groups: list[list[Sample]] = [[] for _ in range(count)]
    for s in samples:
        if s.kind == KIND_WIFI and start <= s.ts < end:
            groups[(s.ts - start) // bucket_seconds].append(s)
    buckets: list[Bucket] = []
    for i, group in enumerate(groups):
        t0 = start + i * bucket_seconds
        if not group:
            buckets.append(Bucket(t0, "nodata"))
            continue
        states = [
            "offline" if (not s.connected and not s.user) else classify(s.rtt_ms, s.loss)
            for s in group
            if s.connected or not s.user
        ]
        if not states:  # yalnızca kullanıcının kendi kestiği örnekler
            buckets.append(Bucket(t0, "nodata"))
            continue
        worst = max(states, key=lambda st: _STATE_ORDER[st])
        rtts = sorted(s.rtt_ms for s in group if s.connected and s.rtt_ms is not None)
        signals = [s.signal for s in group if s.connected and s.signal is not None]
        buckets.append(
            Bucket(
                t0,
                worst,
                rtt_ms=rtts[len(rtts) // 2] if rtts else None,
                signal=round(sum(signals) / len(signals)) if signals else None,
            )
        )
    return buckets


@dataclass(frozen=True)
class WifiSummary:
    samples: int
    disconnects: int  # bağlıyken bağlantı koptu (kullanıcı kesmedi)
    stalls: int  # bağlı görünüyor ama geçide hiç ulaşılamadı
    avg_rtt_ms: float | None
    p95_rtt_ms: float | None
    avg_loss: float | None
    worst_hour: int | None  # 0-23 (yerel saat değil, çağıranın verdiği saat farkıyla)
    networks: tuple[str, ...]  # görülen ağ adları


def _stalled(s: Sample | None) -> bool:
    """Bağlı görünüyor ama ağ geçidine hiç ulaşılamıyor."""
    return s is not None and s.connected and s.loss is not None and s.loss >= 1.0


def _percentile(sorted_values: list[float], fraction: float) -> float:
    index = min(len(sorted_values) - 1, int(fraction * len(sorted_values)))
    return sorted_values[index]


def summarize_wifi(
    samples: list[Sample], interval: int = DEFAULT_INTERVAL, utc_offset: int = 0
) -> WifiSummary:
    """Wi-Fi örneklerinden sade bir özet. `utc_offset`: saniye (yerel saat için)."""
    wifi = [s for s in samples if s.kind == KIND_WIFI]
    disconnects = stalls = 0
    previous: Sample | None = None
    for s in wifi:
        adjacent = previous is not None and s.ts - previous.ts <= interval * GAP_FACTOR
        if adjacent and previous.connected and not s.connected and not s.user:
            disconnects += 1
        if _stalled(s) and not (adjacent and _stalled(previous)):
            stalls += 1  # art arda aynı kesinti tek sayılır
        previous = s
    rtts = sorted(s.rtt_ms for s in wifi if s.connected and s.rtt_ms is not None)
    losses = [s.loss for s in wifi if s.connected and s.loss is not None]
    by_hour: dict[int, list[float]] = {}
    for s in wifi:
        if s.connected and s.rtt_ms is not None:
            by_hour.setdefault(((s.ts + utc_offset) // 3600) % 24, []).append(s.rtt_ms)
    worst_hour = (
        max(by_hour, key=lambda h: sum(by_hour[h]) / len(by_hour[h])) if len(by_hour) > 1 else None
    )
    names: list[str] = []
    for s in wifi:
        if s.name and s.name not in names:
            names.append(s.name)
    return WifiSummary(
        samples=len(wifi),
        disconnects=disconnects,
        stalls=stalls,
        avg_rtt_ms=sum(rtts) / len(rtts) if rtts else None,
        p95_rtt_ms=_percentile(rtts, 0.95) if rtts else None,
        avg_loss=sum(losses) / len(losses) if losses else None,
        worst_hour=worst_hour,
        networks=tuple(names),
    )


@dataclass(frozen=True)
class BluetoothSummary:
    samples: int
    disconnects: int  # bağlıyken koptu (kullanıcı kesmedi)
    last_battery: int | None
    battery_drop: int | None  # dönemdeki düşüş (yüzde puanı); en az iki pil ölçümü varsa


def summarize_bluetooth(
    samples: list[Sample], ident: str, interval: int = DEFAULT_INTERVAL
) -> BluetoothSummary:
    dev = [s for s in samples if s.kind == KIND_BT and s.ident == ident]
    disconnects = 0
    previous: Sample | None = None
    for s in dev:
        if (
            previous is not None
            and s.ts - previous.ts <= interval * GAP_FACTOR
            and previous.connected
            and not s.connected
            and not s.user
        ):
            disconnects += 1
        previous = s
    batteries = [s.battery for s in dev if s.battery is not None]
    return BluetoothSummary(
        samples=len(dev),
        disconnects=disconnects,
        last_battery=batteries[-1] if batteries else None,
        battery_drop=batteries[0] - batteries[-1] if len(batteries) >= 2 else None,
    )
