"""
Measurement engine for the HexFox Load Time Comparator.

Methodology
-----------
This tool does not drive a real browser engine (no Chromium/JS execution),
so it approximates the two metrics the way a plain HTTP client can measure
them honestly:

1. TIME TO FIRST LOAD
   Wall-clock time from the moment the request is sent until the initial
   HTML document has been fully received (DNS + connect + TLS + TTFB +
   document download). This is the earliest point a real browser could
   start painting the page, since it needs the HTML before it can build
   the DOM.

2. TIME TO LOAD ALL ELEMENTS
   Wall-clock time from the same start point until every discoverable
   sub-resource referenced by the page (images, stylesheets, scripts,
   fonts, icons, media, and resources referenced *inside* those
   stylesheets) has finished downloading. Resources are fetched
   concurrently with a worker pool, mirroring how a browser opens several
   parallel connections per host.

Known limitation: resources injected purely via JavaScript at runtime
(lazy-loaded images, client-side fetch/XHR calls, dynamic imports) are
invisible to a static HTML/CSS parser and are not counted. Results are
therefore a strong, reproducible *approximation* -- not a substitute for
a real-browser trace (e.g. Lighthouse/DevTools) -- but are consistent and
great for side-by-side comparisons.

Raw (connection-excluded) timing
---------------------------------
Both headline metrics above bundle in DNS lookup + TCP handshake + TLS
negotiation for the first connection made to the site -- overhead that's
about the *server/network path*, not the HTML/assets themselves. To let
this tool answer "is the markup/content itself fast?" independently of
that, every result also reports a "raw" variant with that one-time
connection-establishment cost subtracted out:

    raw_time_to_first_load    = time_to_first_load    - connect_time
    raw_time_to_all_elements  = time_to_all_elements  - connect_time

`connect_time` is measured precisely (not estimated) by timing the actual
DNS+TCP+TLS handshake of the real request via a small urllib3 hook -- see
`_install_connection_timing_patch()` below -- so it reflects exactly what
happened on the wire for that request, not a separate probe connection.
Both the raw and total (including connection) numbers are kept around so
the UI can show either or both.
"""

from __future__ import annotations

import re
import statistics
import threading
import time
from concurrent.futures import ThreadPoolExecutor, as_completed
from dataclasses import dataclass, field
from typing import Callable, Optional
from urllib.parse import urljoin, urlparse

import requests
from bs4 import BeautifulSoup

try:
    from urllib3.connection import HTTPConnection, HTTPSConnection
except ImportError:  # pragma: no cover - requests always ships urllib3
    HTTPConnection = HTTPSConnection = None

_connect_timing_local = threading.local()
_connect_timing_installed = False


def _install_connection_timing_patch() -> None:
    """Instrument urllib3 so we can read exactly how long the most recent
    connection handshake (DNS + TCP + TLS) took, per-thread.

    This patches `connect()` once per process. It's additive (wraps, doesn't
    replace, the original implementation) and safe to call multiple times.
    When a pooled/keep-alive connection is reused, `connect()` isn't called
    again, so the thread-local value correctly comes back empty for that
    request -- which is exactly right, since no new handshake happened.
    """
    global _connect_timing_installed
    if _connect_timing_installed or HTTPConnection is None:
        return

    def _wrap(cls):
        original = cls.connect

        def timed_connect(self, _original=original):
            start = time.perf_counter()
            _original(self)
            _connect_timing_local.duration = time.perf_counter() - start

        cls.connect = timed_connect

    _wrap(HTTPConnection)
    if HTTPSConnection is not HTTPConnection:
        _wrap(HTTPSConnection)
    _connect_timing_installed = True


def _measure_with_connect_time(fn):
    """Call fn() and return (result, connect_time_or_0.0) for the request(s)
    fn performs, reading the thread-local set by the urllib3 patch above."""
    _connect_timing_local.duration = None
    result = fn()
    connect_time = getattr(_connect_timing_local, "duration", None) or 0.0
    return result, connect_time

DEFAULT_USER_AGENT = (
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
    "(KHTML, like Gecko) Chrome/124.0.0.0 Safari/537.36 HexFoxLoadTime/1.0"
)

RESOURCE_ATTR_RULES = [
    ("img", "src", "image"),
    ("img", "data-src", "image"),
    ("source", "src", "media"),
    ("video", "src", "media"),
    ("video", "poster", "image"),
    ("audio", "src", "media"),
    ("script", "src", "script"),
    ("iframe", "src", "iframe"),
    ("embed", "src", "embed"),
    ("object", "data", "object"),
    ("track", "src", "media"),
]

CSS_URL_RE = re.compile(r"url\(\s*(['\"]?)([^'\")]+)\1\s*\)", re.IGNORECASE)
CSS_IMPORT_RE = re.compile(r"@import\s+(?:url\()?['\"]?([^'\");\s]+)['\"]?\)?", re.IGNORECASE)
IGNORED_SCHEMES = ("data:", "mailto:", "tel:", "javascript:", "blob:", "about:")


def _is_fetchable(url: str) -> bool:
    if not url:
        return False
    lowered = url.strip().lower()
    return not any(lowered.startswith(scheme) for scheme in IGNORED_SCHEMES)


@dataclass
class ResourceResult:
    url: str
    kind: str
    ok: bool = False
    status_code: Optional[int] = None
    size_bytes: int = 0
    finished_at: float = 0.0  # seconds relative to the run's t0
    connect_time: float = 0.0  # DNS+TCP+TLS handshake time for this request (0 if connection was reused)
    error: Optional[str] = None
    text: Optional[str] = None  # decoded body, only kept for stylesheets (needed to find nested urls)


@dataclass
class SiteRunResult:
    requested_url: str
    final_url: str = ""
    ok: bool = False
    error: Optional[str] = None
    ttfb: float = 0.0
    connect_time: float = 0.0  # DNS+TCP+TLS handshake time for the document request
    time_to_first_load: float = 0.0
    time_to_all_elements: float = 0.0
    raw_time_to_first_load: float = 0.0  # time_to_first_load with connect_time subtracted
    raw_time_to_all_elements: float = 0.0  # time_to_all_elements with connect_time subtracted
    status_code: Optional[int] = None
    total_bytes: int = 0
    resource_count: int = 0
    failed_count: int = 0
    resources: list = field(default_factory=list)


@dataclass
class SiteTestSummary:
    label: str
    url: str
    runs: list
    error: Optional[str] = None

    def _successful(self):
        return [r for r in self.runs if r.ok]

    @property
    def ok(self) -> bool:
        return len(self._successful()) > 0

    def _median(self, attr: str) -> Optional[float]:
        vals = [getattr(r, attr) for r in self._successful()]
        return statistics.median(vals) if vals else None

    @property
    def median_first_load(self) -> Optional[float]:
        return self._median("time_to_first_load")

    @property
    def median_all_elements(self) -> Optional[float]:
        return self._median("time_to_all_elements")

    @property
    def median_raw_first_load(self) -> Optional[float]:
        return self._median("raw_time_to_first_load")

    @property
    def median_raw_all_elements(self) -> Optional[float]:
        return self._median("raw_time_to_all_elements")

    @property
    def median_connect_time(self) -> Optional[float]:
        return self._median("connect_time")

    @property
    def median_ttfb(self) -> Optional[float]:
        return self._median("ttfb")

    @property
    def avg_resource_count(self) -> Optional[float]:
        vals = [r.resource_count for r in self._successful()]
        return statistics.mean(vals) if vals else None

    @property
    def avg_total_bytes(self) -> Optional[float]:
        vals = [r.total_bytes for r in self._successful()]
        return statistics.mean(vals) if vals else None

    @property
    def avg_failed_count(self) -> Optional[float]:
        vals = [r.failed_count for r in self._successful()]
        return statistics.mean(vals) if vals else None


ProgressCallback = Callable[[dict], None]


class LoadTimeTester:
    """Runs one or more timed fetch-and-render-simulation passes for a URL."""

    def __init__(
        self,
        timeout: float = 15.0,
        concurrency: int = 8,
        user_agent: str = DEFAULT_USER_AGENT,
        parse_css_for_subresources: bool = True,
        stop_event: Optional[threading.Event] = None,
    ):
        self.timeout = timeout
        self.concurrency = max(1, concurrency)
        self.user_agent = user_agent or DEFAULT_USER_AGENT
        self.parse_css_for_subresources = parse_css_for_subresources
        self.stop_event = stop_event or threading.Event()
        _install_connection_timing_patch()

    # -- public API ---------------------------------------------------

    def run(self, label: str, url: str, trials: int, progress: Optional[ProgressCallback] = None) -> SiteTestSummary:
        progress = progress or (lambda evt: None)
        runs = []
        for i in range(trials):
            if self.stop_event.is_set():
                break
            progress({"type": "trial_start", "label": label, "url": url, "trial": i + 1, "trials": trials})
            result = self._run_once(label, url, progress)
            runs.append(result)
            progress({"type": "trial_done", "label": label, "url": url, "trial": i + 1, "trials": trials, "result": result})
        return SiteTestSummary(label=label, url=url, runs=runs)

    # -- internals ------------------------------------------------------

    def _run_once(self, label: str, url: str, progress: ProgressCallback) -> SiteRunResult:
        session = requests.Session()
        session.headers.update({"User-Agent": self.user_agent, "Accept-Language": "en-US,en;q=0.9"})
        t0 = time.perf_counter()
        result = SiteRunResult(requested_url=url)

        try:
            _connect_timing_local.duration = None
            resp = session.get(url, timeout=self.timeout, stream=True, allow_redirects=True)
            result.connect_time = getattr(_connect_timing_local, "duration", None) or 0.0
            result.ttfb = time.perf_counter() - t0
            content = bytearray()
            for chunk in resp.iter_content(chunk_size=8192):
                if self.stop_event.is_set():
                    break
                if chunk:
                    content.extend(chunk)
            result.time_to_first_load = time.perf_counter() - t0
            result.final_url = resp.url
            result.status_code = resp.status_code
            result.total_bytes += len(content)

            html_text = content.decode(resp.encoding or "utf-8", errors="replace")
            progress({"type": "doc_loaded", "label": label, "url": url, "elapsed": result.time_to_first_load,
                      "connect_time": result.connect_time, "raw_elapsed": result.raw_time_to_first_load,
                      "status_code": resp.status_code})

            resource_urls = self._extract_resource_urls(html_text, resp.url)
            progress({"type": "resources_found", "label": label, "url": url, "count": len(resource_urls)})

            fetched = self._fetch_all(session, resource_urls, t0, label, url, progress)
            result.resources = fetched

            if self.parse_css_for_subresources:
                css_children = self._collect_css_subresources(fetched, resource_urls)
                if css_children:
                    progress({"type": "resources_found", "label": label, "url": url, "count": len(css_children), "nested": True})
                    fetched_children = self._fetch_all(session, css_children, t0, label, url, progress)
                    result.resources = result.resources + fetched_children

            all_finish_times = [result.time_to_first_load] + [r.finished_at for r in result.resources if r.ok]
            result.time_to_all_elements = max(all_finish_times) if all_finish_times else result.time_to_first_load
            result.resource_count = len(result.resources)
            result.failed_count = sum(1 for r in result.resources if not r.ok)
            result.total_bytes += sum(r.size_bytes for r in result.resources)
            result.raw_time_to_first_load = max(0.0, result.time_to_first_load - result.connect_time)
            result.raw_time_to_all_elements = max(0.0, result.time_to_all_elements - result.connect_time)
            result.ok = True

        except requests.exceptions.RequestException as exc:
            result.ok = False
            result.error = str(exc)
            progress({"type": "site_error", "label": label, "url": url, "error": str(exc)})
        except Exception as exc:  # pragma: no cover - defensive
            result.ok = False
            result.error = f"Unexpected error: {exc}"
            progress({"type": "site_error", "label": label, "url": url, "error": result.error})
        finally:
            session.close()

        return result

    def _extract_resource_urls(self, html: str, base_url: str) -> list:
        soup = BeautifulSoup(html, "html.parser")

        base_tag = soup.find("base", href=True)
        base = urljoin(base_url, base_tag["href"]) if base_tag else base_url

        found = {}  # url -> kind (dedup while preserving first-seen kind)

        def add(raw_url: str, kind: str):
            if not raw_url or not _is_fetchable(raw_url):
                return
            absolute = urljoin(base, raw_url.strip())
            if absolute not in found:
                found[absolute] = kind

        for tag, attr, kind in RESOURCE_ATTR_RULES:
            for el in soup.find_all(tag, attrs={attr: True}):
                add(el.get(attr), kind)

        for el in soup.find_all(["img", "source"], attrs={"srcset": True}):
            for candidate in el["srcset"].split(","):
                add(candidate.strip().split(" ")[0], "image")

        for link in soup.find_all("link", href=True):
            rel = " ".join(link.get("rel", [])).lower()
            if any(key in rel for key in ("stylesheet", "icon", "preload", "manifest", "font")):
                kind = "stylesheet" if "stylesheet" in rel else ("font" if "font" in rel else "asset")
                add(link.get("href"), kind)

        for style_tag in soup.find_all("style"):
            for match in CSS_URL_RE.finditer(style_tag.get_text() or ""):
                add(match.group(2), "asset")
            for match in CSS_IMPORT_RE.finditer(style_tag.get_text() or ""):
                add(match.group(1), "stylesheet")

        for el in soup.find_all(attrs={"style": True}):
            for match in CSS_URL_RE.finditer(el["style"]):
                add(match.group(2), "asset")

        return [{"url": u, "kind": k} for u, k in found.items()]

    def _fetch_all(self, session, resource_specs: list, t0: float, label: str, site_url: str,
                    progress: ProgressCallback) -> list:
        results = []
        if not resource_specs:
            return results

        def fetch_one(spec):
            url = spec["url"]
            kind = spec["kind"]
            if self.stop_event.is_set():
                return ResourceResult(url=url, kind=kind, ok=False, error="cancelled")
            try:
                _connect_timing_local.duration = None
                r = session.get(url, timeout=self.timeout, stream=True)
                connect_time = getattr(_connect_timing_local, "duration", None) or 0.0
                size = 0
                keep_body = kind == "stylesheet" and self.parse_css_for_subresources
                body = bytearray() if keep_body else None
                for chunk in r.iter_content(chunk_size=8192):
                    if self.stop_event.is_set():
                        break
                    if chunk:
                        size += len(chunk)
                        if keep_body and size <= 2_000_000:  # cap CSS parsing at 2MB/file
                            body.extend(chunk)
                finished_at = time.perf_counter() - t0
                ok = r.status_code < 400
                text = None
                if keep_body and body:
                    try:
                        text = body.decode(r.encoding or "utf-8", errors="replace")
                    except Exception:
                        text = None
                return ResourceResult(url=url, kind=kind, ok=ok, status_code=r.status_code,
                                       size_bytes=size, finished_at=finished_at, connect_time=connect_time,
                                       error=None if ok else f"HTTP {r.status_code}",
                                       text=text,
                                       )
            except requests.exceptions.RequestException as exc:
                return ResourceResult(url=url, kind=kind, ok=False, finished_at=time.perf_counter() - t0,
                                       error=str(exc))

        with ThreadPoolExecutor(max_workers=self.concurrency) as pool:
            futures = {pool.submit(fetch_one, spec): spec for spec in resource_specs}
            for future in as_completed(futures):
                res = future.result()
                results.append(res)
                progress({
                    "type": "resource_done" if res.ok else "resource_failed",
                    "label": label, "url": site_url,
                    "resource_url": res.url, "kind": res.kind,
                    "ok": res.ok, "size_bytes": res.size_bytes, "error": res.error,
                })
        return results

    def _collect_css_subresources(self, fetched: list, original_specs: list) -> list:
        original_urls = {spec["url"] for spec in original_specs}
        css_children = {}
        for res in fetched:
            if not res.ok or res.kind != "stylesheet" or not res.text:
                continue
            for match in CSS_URL_RE.finditer(res.text):
                self._add_css_child(css_children, original_urls, res.url, match.group(2), "font")
            for match in CSS_IMPORT_RE.finditer(res.text):
                self._add_css_child(css_children, original_urls, res.url, match.group(1), "stylesheet")
        return [{"url": u, "kind": k} for u, k in css_children.items()]

    @staticmethod
    def _add_css_child(bucket: dict, original_urls: set, css_url: str, raw_ref: str, default_kind: str):
        if not raw_ref or not _is_fetchable(raw_ref):
            return
        absolute = urljoin(css_url, raw_ref.strip())
        if absolute in original_urls or absolute in bucket:
            return
        ext = urlparse(absolute).path.lower().rsplit(".", 1)[-1] if "." in urlparse(absolute).path else ""
        if ext in ("woff", "woff2", "ttf", "otf", "eot"):
            kind = "font"
        elif ext in ("png", "jpg", "jpeg", "gif", "svg", "webp", "ico", "avif"):
            kind = "image"
        else:
            kind = default_kind
        bucket[absolute] = kind
