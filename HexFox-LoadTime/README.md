# HexFox Load Time Comparator

A local desktop tool (Python + [customtkinter](https://github.com/TomSchimansky/CustomTkinter)) for
comparing two website performance metrics, side by side, across one or more sites:

- **TIME TO FIRST LOAD** — how long it takes for the site to start showing something
  (time until the initial HTML document is fully downloaded: DNS + connect + TLS + TTFB + HTML transfer).
- **TIME TO LOAD ALL ELEMENTS** — how long it takes for *everything* on the page to finish loading
  (time until every discoverable image, stylesheet, script, font, and icon referenced by the page —
  including assets referenced from inside CSS — has finished downloading).

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
4. Results appear as cards per site (median time + range across trials, resource counts,
   transferred size, failures) plus a comparison bar chart, and can be exported to CSV.

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
