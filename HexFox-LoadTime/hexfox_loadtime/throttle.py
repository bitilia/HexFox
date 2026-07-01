"""
Network + CPU throttling presets and helpers.

Network throttling
-------------------
Each profile has a download bandwidth cap (in Kbps, i.e. kilobits/sec -
the conventional "Mbps"/"Kbps" unit ISPs use) and an added round-trip
latency (ms). "Slow 4G" and "3G" use the same figures as Lighthouse's
`mobileSlow4G` / `mobileRegular3G` throttling profiles, which are the
closest thing to an industry-standard baseline for these labels. "Fast 5G"
and "Fast 4G" aren't standardized anywhere, so we use representative,
clearly-approximate numbers for a strong 5G connection and a solid LTE
connection respectively.

Bandwidth is enforced with a shared token-bucket-style `RateLimiter`: every
byte read (for the document *and* every concurrently-fetched resource in a
run) is charged against one limiter, so the aggregate throughput across all
parallel connections is capped at the target rate -- mirroring how a real
constrained last-mile connection is shared across a page's requests, not
throttled per-connection.

Latency is added once per HTTP request (document or resource) immediately
before it's sent, and is folded into that request's reported `connect_time`
-- it's a network-path cost, not a "content" cost, so it stays out of the
"raw" content-only metrics (see network.py).

CPU throttling
--------------
This tool has no rendering engine, so there's no real "main thread" to
slow down the way Chrome DevTools' CPU throttling does. Instead,
`estimate_cpu_delay()` adds a clearly-labelled *simulated* parse/execute
delay, proportional to page weight and the chosen multiplier, so slower
"devices" still produce meaningfully different (and honestly-approximate)
numbers. This is documented in the UI/README as a simulation, not a
measurement.
"""

from __future__ import annotations

import threading
import time
from dataclasses import dataclass
from typing import Optional


@dataclass(frozen=True)
class NetworkProfile:
    name: str
    download_kbps: Optional[float]  # None = unlimited
    latency_ms: float
    description: str = ""


NETWORK_PRESETS = {
    "No throttling": NetworkProfile("No throttling", None, 0.0, "Unthrottled local connection"),
    "Fast 5G": NetworkProfile("Fast 5G", 300_000.0, 10.0, "~300 Mbps, 10ms RTT (approximate)"),
    "Fast 4G": NetworkProfile("Fast 4G", 20_000.0, 40.0, "~20 Mbps, 40ms RTT (approximate LTE)"),
    "Slow 4G": NetworkProfile("Slow 4G", 1_600.0, 150.0, "~1.6 Mbps, 150ms RTT (Lighthouse mobileSlow4G)"),
    "3G": NetworkProfile("3G", 700.0, 300.0, "~700 Kbps, 300ms RTT (Lighthouse mobileRegular3G)"),
}

CPU_PRESETS = {
    "No throttling": 1.0,
    "2x slowdown": 2.0,
    "4x slowdown": 4.0,
    "6x slowdown": 6.0,
}

# Coarse, clearly-approximate assumption: a capable desktop CPU can parse,
# lay out, and execute roughly this many bytes of page weight per second.
_CPU_BASELINE_BYTES_PER_SEC = 8 * 1024 * 1024


def estimate_cpu_delay(byte_size: int, multiplier: float) -> float:
    """Extra simulated parse/execute time a `multiplier`x slower CPU would
    add for `byte_size` bytes of page weight. Returns 0 for multiplier<=1."""
    if multiplier is None or multiplier <= 1.0 or byte_size <= 0:
        return 0.0
    baseline_time = byte_size / _CPU_BASELINE_BYTES_PER_SEC
    return baseline_time * (multiplier - 1.0)


def sleep_respecting_stop(duration: float, stop_event: Optional[threading.Event] = None,
                           poll_interval: float = 0.1) -> None:
    """time.sleep(duration) but wakes up early (in small increments) if
    stop_event gets set, so Stop stays responsive during long throttled
    waits."""
    if duration <= 0:
        return
    deadline = time.perf_counter() + duration
    while True:
        remaining = deadline - time.perf_counter()
        if remaining <= 0:
            return
        if stop_event is not None and stop_event.is_set():
            return
        time.sleep(min(remaining, poll_interval))


class RateLimiter:
    """Thread-safe shared limiter capping aggregate download throughput.

    All consumers (the document request and every concurrent resource
    request in a single site run) share one instance, so the combined
    bandwidth across every in-flight connection is capped at the target
    rate -- not each connection individually.
    """

    def __init__(self, download_kbps: Optional[float]):
        self.bytes_per_sec = (download_kbps * 1000.0 / 8.0) if download_kbps else None
        self._lock = threading.Lock()
        self._start = time.perf_counter()
        self._bytes_sent = 0

    @property
    def enabled(self) -> bool:
        return self.bytes_per_sec is not None

    def consume(self, nbytes: int, stop_event: Optional[threading.Event] = None) -> None:
        if not self.bytes_per_sec or nbytes <= 0:
            return
        with self._lock:
            self._bytes_sent += nbytes
            expected_elapsed = self._bytes_sent / self.bytes_per_sec
            actual_elapsed = time.perf_counter() - self._start
            sleep_for = expected_elapsed - actual_elapsed
        sleep_respecting_stop(sleep_for, stop_event)
