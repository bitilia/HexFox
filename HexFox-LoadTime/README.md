# HexFox Load Time Comparator

A local desktop tool (Python + [customtkinter](https://github.com/TomSchimansky/CustomTkinter)) for
comparing two website performance metrics, side by side, across one or more sites:

- **TIME TO FIRST LOAD** — how long it takes for the site to start showing something
  (time until the initial HTML document is fully downloaded).
- **TIME TO LOAD ALL ELEMENTS** — how long it takes for *everything* on the page to finish loading
  (time until every discoverable image, stylesheet, script, font, and icon referenced by the page —
  including assets referenced from inside CSS — has finished downloading).

Both metrics are reported two ways:

- **RAW** (the headline number) — just the HTML/asset transfer itself, with connection setup
  (DNS lookup + TCP handshake + TLS negotiation) subtracted out. This is a test of *the content*,
  not the server or network path to it.
- **Total, incl. connection** — what actually happened on the wire, connection overhead included.
  Shown alongside the raw number so you can see how much of the total is "the server/network being
  slow to connect" vs. "the page being heavy."

Connection time is measured precisely per request (not estimated) by timing the real DNS+TCP+TLS
handshake of the actual connection used — see the "Methodology" section below.

This is a standalone internal tool and is **not** part of the hexfox.com website codebase.
It's meant to be run locally on your own machine.

## 1. Install

Requires **Python 3.10+** on Windows (get it from [python.org](https://www.python.org/downloads/) —
tick "Add python.exe to PATH" during install).

1. Copy this whole folder to `C:\AI_CURSOR\HexFox-LoadTime` (or wherever you like).
2. Double-click **`run_windows.bat`**.
   - First run: it creates a local virtual environment in `.venv` and installs the dependencies
     listed in `requirements.txt` (customtkinter, requests, beautifulsoup4, Pillow).
   - Every run after that just launches the app immediately.

Prefer doing it by hand instead of the `.bat` file?

```bat
cd C:\AI_CURSOR\HexFox-LoadTime
py -3 -m venv .venv
.venv\Scripts\pip install -r requirements.txt
.venv\Scripts\python main.py
```

## 2. Using it

1. **Websites to test** — enter one or more URLs (with an optional label for each). Click
   **+ Add site to compare** to test several sites side by side.
2. **Test settings**:
   - **Trials per site** — run each site 1, 3, or 5 times and report the median, since network
     conditions vary run to run. 3 is a good default.
   - **Simulated device** — sends a Desktop Chrome or Mobile Safari `User-Agent` header, in case a
     site serves different HTML per device.
   - **Timeout / Concurrency** — per-request timeout, and how many resources are downloaded in
     parallel (browsers typically open ~6-8 connections per host, so 8 is a realistic default).
   - **Include CSS-referenced assets** — also follow `url(...)` / `@import` references inside
     stylesheets (fonts, background images) so "Time to Load All Elements" is more complete.
3. Click **Run Comparison**. Progress streams live into the log panel.
4. Results appear as cards per site — a big **RAW** number (content-only, connection setup
   subtracted) with the **total incl. connection** shown just underneath — plus resource counts,
   transferred size, and failures. The comparison chart draws each metric as a stacked bar: a grey
   "connection setup" segment followed by the raw content segment, so both pieces are visible at a
   glance. Results can be exported to CSV, which includes both the raw and total figures.

## 3. Methodology & limitations

This tool uses plain HTTP requests (via `requests` + `BeautifulSoup`) rather than driving a real
browser engine — there's no Chromium and no JavaScript execution involved. That keeps it fast,
dependency-light, and easy to run anywhere, but it does mean:

- Resources injected **purely by JavaScript at runtime** (lazy-loaded images, client-side
  `fetch`/XHR calls, analytics/ad scripts that inject more scripts, infinite scroll, etc.) are not
  discovered or counted, because nothing is executed.
- "Time to First Load" approximates the earliest point a browser *could* start rendering (as soon
  as it has the HTML), not a pixel-perfect First Contentful Paint measurement from DevTools.
- Nested `@import` stylesheets are only followed one level deep.

**Raw vs. total timing.** Every request's connection setup (DNS lookup + TCP handshake + TLS
negotiation) is timed precisely by hooking the real `urllib3` connection object used for that
request — not estimated or measured via a separate probe connection. That measured connect time is
then subtracted from the total to produce the "raw" number:

```
raw_time_to_first_load   = time_to_first_load   - connect_time
raw_time_to_all_elements = time_to_all_elements - connect_time
```

`connect_time` reflects the *document* request's handshake. If a connection is reused (HTTP
keep-alive, e.g. for a second trial in the same run or for same-host resources after the first),
no new handshake happens and `connect_time` for that request is correctly `0`. Individual resources
also record their own connect time (visible in the live log for failures/successes), but the
headline "raw" adjustment always uses the document's connection cost, since that's the one
unavoidable prerequisite before any HTML/asset content can flow at all.

In exchange, the numbers are cheap to produce, fully reproducible, and great for **relative**
comparisons — "is site A's markup + first-party assets lighter/faster than site B's?" — which is
exactly the comparison this tool is built for. For pixel-perfect, JS-inclusive metrics (real First
Contentful Paint, Largest Contentful Paint, Time to Interactive, etc.) reach for Chrome DevTools,
Lighthouse, or WebPageTest instead.

## 4. Project structure

```
HexFox-LoadTime/
├── main.py                    # entry point (python main.py)
├── run_windows.bat            # one-click setup + launch for Windows
├── requirements.txt
├── hexfox_loadtime/
│   ├── app.py                 # customtkinter GUI
│   ├── network.py             # measurement engine (the actual timing logic)
│   ├── widgets.py             # branded reusable widgets (site rows, result cards)
│   ├── charts.py              # dependency-free comparison bar chart
│   ├── theme.py                # HexFox brand colors / fonts
│   ├── fonts.py                # loads bundled Boldonse/Montserrat brand fonts
│   └── utils.py
└── assets/                    # HexFox logo + brand fonts (internal use)
```

## 5. Branding

Colors, the Boldonse/Montserrat typefaces, and the logo mark are pulled directly from the
`hexfox.com` brand kit for a first-party look and feel. This tool is for internal/local use only
and is intentionally kept out of the public `hexfox` repository.
