# upbhulekh-scraper

A Playwright-based scraper for **UP Bhulekh** ([upbhulekh.gov.in](https://upbhulekh.gov.in)), Uttar Pradesh's public land-record portal. It sweeps a village's खसरा/गाटा numbers, reads each khata's उद्धरण खतौनी (record of rights), matches owners against a list of names with spelling-tolerant Hindi matching, and saves the JSON records and PDFs for the matches.

![Python](https://img.shields.io/badge/Python-3.12-blue.svg)
![Playwright](https://img.shields.io/badge/Playwright-1.63-2EAD33.svg)
![Docker](https://img.shields.io/badge/Docker-Ready-2496ED.svg)

## ✨ Features

- 🔓 **Readable API traffic without breaking crypto.** The site AES-encrypts every request and response (`{"edata": …}`). `hooks.js` wraps `JSON.parse`/`JSON.stringify` inside the page, so plaintext is logged before encryption and after decryption.
- 🧭 **Scriptable long-running browser.** You solve the captcha once. After that, drop Python snippets into a command folder and `driver.py` runs them against the live page.
- 🔎 **Khasra sweep.** `scrape_khasra.py` tries gata numbers 1…N on the no-captcha `#/khatauni_rtk` page and opens every new khata. It resumes from `progress.json` and stops after 150 empty numbers in a row.
- 🪪 **Spelling-tolerant owner matching.** `names.py` folds common Devanagari variants (ी/ि, ष/श/स, व/ब, ं/न …) and drops honorifics (श्री, स्व०, देवी, सिंह). It checks current owners, shared-khata (अंश) owners, and owners added or removed by mutation.
- 📄 **PDF capture.** It uses the site's own "Download PDF" button. Where that crashes the browser, `page_to_pdf` screenshots the page and writes an image PDF.
- 📊 **Reports.** `report.py` builds a CSV/XLSX summary of all matches, and `md_to_pdf.py` renders a Hindi/English Markdown report to a styled A4 PDF.
- 🐳 **Docker ready.** A headed Chromium runs on a virtual display, reachable in your browser through noVNC.
- 🔒 **Personal data stays out of git.** Everything specific to you (names, village, scraped records, browser profile) lives in the gitignored `private/` folder.

## 📁 Project Structure

```
upbhulekh-scraper/
├── config.py              # Data-dir paths (BHULEKH_DATA) and config.json loader
├── config.example.json    # Template: district / tehsil / village + target (name, father) pairs
├── driver.py              # Long-running headed browser; runs queued command files
├── hooks.js               # Injected before the Angular app boots; logs decrypted API traffic
├── run_cmd.sh             # Queue a command for the driver and wait for its output
├── scrape_khasra.py       # Village search, khasra sweep, catch-up pass, page-to-PDF
├── names.py               # Devanagari name folding and owner matching against a ROR
├── report.py              # summary.csv / summary.xlsx from the saved khata JSON
├── md_to_pdf.py           # Markdown → A4 PDF (Noto Devanagari)
├── discover.py            # One-off manual session that records API traffic
├── Dockerfile             # Playwright image + Xvfb + noVNC
├── docker-compose.yml
├── scripts/entrypoint.sh  # Starts the virtual display, VNC, noVNC, then driver.py
└── private/               # (gitignored) config.json, out/, browser profiles, asset cache
```

## 🚀 Quick Start (Docker)

```bash
git clone https://github.com/sumit-kumar-03/upbhulekh-scraper.git
cd upbhulekh-scraper

mkdir -p private
cp config.example.json private/config.json   # then edit: your district, tehsil, village, names

docker compose up -d --build
```

1. Open **http://localhost:6080/vnc.html** and click *Connect*. You'll see Chromium on upbhulekh.gov.in.
2. From the host, open the village search page and start the sweep:

```bash
./run_cmd.sh open <<'EOF'
import importlib, scrape_khasra; importlib.reload(scrape_khasra)
await scrape_khasra.open_search_page(page)
return page.url
EOF

WAIT=86400 ./run_cmd.sh sweep <<'EOF'
import scrape_khasra
return await scrape_khasra.run(page, state)
EOF
```

3. Follow progress in `private/out/status.txt`. If the site asks for a captcha, the log shows `NEED_USER`: solve it in the noVNC tab and the sweep carries on.
4. Build the summary with `docker compose exec scraper python report.py`.

`./run_cmd.sh` works from the host because `private/` is mounted into the container.

## 💻 Quick Start (local)

```bash
python3 -m venv .venv
.venv/bin/pip install -r requirements.txt
.venv/bin/playwright install chromium

mkdir -p private && cp config.example.json private/config.json
.venv/bin/python driver.py        # opens a visible browser
```

Then queue commands with `./run_cmd.sh` as above.

## ⚙️ Configuration

`private/config.json`:

```json
{
  "district": "Lucknow",
  "tehsil": "Lucknow",
  "village": "Example Village",
  "targets": [["राम कुमार", "श्याम लाल"], ["सीता देवी", "राम कुमार"]]
}
```

- **district / tehsil / village**: the English labels shown in the site's dropdowns.
- **targets**: `(owner name, father/husband name)` pairs, written as they appear on a khatauni.

| Env var | Default | Purpose |
|---|---|---|
| `BHULEKH_DATA` | `./private` | Root for config, outputs, browser profiles, asset cache |
| `HEADLESS` | `0` | `1` runs the driver without a window. The captcha needs a window, so leave it at `0` |
| `CHROMIUM_PATH` | *(bundled)* | Use a system Chromium for `discover.py` |

## 🗂️ Output (`private/out/`)

| Path | Contents |
|---|---|
| `json/khata_<n>.json` | Decrypted `ror` response per khata plus the khasra row it came from |
| `pdf/khata_<n>.pdf` | उद्धरण खतौनी for matched khatas |
| `progress.json` | Sweep state (next khasra, rows seen, matches). Reruns resume from here |
| `status.txt` | Human-readable log: matches, errors, `NEED_USER` prompts |
| `traffic.jsonl` | Every decrypted request/response seen by `hooks.js` |
| `summary.csv`, `summary.xlsx` | Output of `report.py` |

## 🔌 Site API notes

Every call is `POST /PublicBhuApi/api/<endpoint>` with an encrypted `{"edata"}` body. With `hooks.js` in place you see the plaintext:

| Endpoint | Returns |
|---|---|
| `uniqueCode` / `uniqueCodek` | Khata rows for a khasra number (current fasli) |
| `ror` | Full record of rights: `names`, `response1.data` (shared-khata owners with hissa), `rname`/`aname` (removed/added by mutation), `cnameResponse1` (mutation orders), `khasra` |
| `uniqueCodeB` / `uniqueCodekB` / `rorBackup` | The same for older faslis (`#fasliSelect`: 1423–1428, 1417–1422) |
| `ownerMasterDetails` / `getOwnerDetails` | Village-wide owner list, and khatas for one owner |
| `fasliParts`, `r6Details` | Fasli periods and the mutation register (R6) |

Known quirks:
- The site's jsPDF download sometimes takes the tab down. The driver reopens a tab, and `page_to_pdf` is the fallback.
- The 7 MB `main.js` is sometimes throttled so hard the app never boots. The driver serves hashed JS/CSS from `private/asset_cache/` once it has seen them.
- The khasra keypad input is read-only. Numbers are typed by clicking `table.keyboard1 a[data-value=N]`.

## ⚖️ Responsible use

The records shown on UP Bhulekh are public, but they name real people. This tool:
- sends requests one at a time with 1–2 s pauses;
- leaves the captcha to a human;
- keeps all scraped data local in `private/`.

Use it for records you have a legitimate interest in, respect the portal's terms, and treat downloaded copies as unofficial: get certified copies from the tehsil before any legal step.
