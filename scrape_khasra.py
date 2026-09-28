"""Sweep खसरा/गाटा numbers 1..N on the khatauni_rtk page and download matching khatas.

Runs inside driver.py (the page must already be on #/khatauni_rtk with the configured
district / tehsil / village selected; see open_search_page). Start it with a driver command:

    import importlib, scrape_khasra; importlib.reload(scrape_khasra)
    return await scrape_khasra.run(page, state, start=1, stop=None)

Per khasra: type it on the site's keypad, search, read the decrypted `uniqueCode` rows,
and for each khata not seen before open its उद्धरण (the `ror` call), save the JSON, match
the configured target owners, and click "Download PDF" on a match. Progress lives in
<data>/out/progress.json so a rerun resumes where it stopped.
"""
import asyncio
import json
import random
import time
from pathlib import Path

import config
from names import match_ror, should_download

OUT = config.OUT
JSON_DIR = OUT / "json"
PDF_DIR = OUT / "pdf"
TRAFFIC = OUT / "traffic.jsonl"
PROGRESS = OUT / "progress.json"
STATUS = OUT / "status.txt"
SEARCH_PAGE = "#/khatauni_rtk"
RESULT_PAGE = "#/udran_khatauni"
PLACEHOLDER = "खसरा/गाटा संख्या द्वारा खोजें..."
EMPTY_STREAK_STOP = 150  # consecutive khasra numbers with no records => past the village's last number


def log(msg: str):
    line = time.strftime("%H:%M:%S ") + msg
    print(line, flush=True)
    with STATUS.open("a", encoding="utf-8") as f:
        f.write(line + "\n")


def load_progress():
    if PROGRESS.exists():
        return json.loads(PROGRESS.read_text(encoding="utf-8"))
    return {"next_khasra": 1, "empty_streak": 0, "khasra_rows": {}, "khatas": {}}


def save_progress(p):
    tmp = PROGRESS.with_suffix(".tmp")
    tmp.write_text(json.dumps(p, ensure_ascii=False, indent=1), encoding="utf-8")
    tmp.replace(PROGRESS)


class Traffic:
    """Tail of out/traffic.jsonl (decrypted API traffic written by hooks.js via driver.py)."""

    def __init__(self):
        self.pos = TRAFFIC.stat().st_size if TRAFFIC.exists() else 0

    def mark(self):
        self.pos = TRAFFIC.stat().st_size

    def since_mark(self):
        with TRAFFIC.open("rb") as f:
            f.seek(self.pos)
            chunk = f.read().decode("utf-8", "ignore")
        out = []
        for line in chunk.splitlines():
            try:
                out.append(json.loads(line))
            except json.JSONDecodeError:
                pass
        return out

    async def wait_done(self, endpoint: str, timeout=45.0):
        """Wait for an XHR to `endpoint` to finish; return (status, events since mark)."""
        deadline = time.monotonic() + timeout
        while time.monotonic() < deadline:
            events = self.since_mark()
            for e in events:
                d = e["data"]
                if e["kind"] == "xhr" and d.get("phase") == "done" and d["url"].endswith("/" + endpoint):
                    await asyncio.sleep(0.3)  # let the matching JSON.parse land in the log
                    return d.get("status"), self.since_mark()
            await asyncio.sleep(0.25)
        raise TimeoutError(f"no {endpoint} response within {timeout}s")


def parsed(events, predicate):
    for e in events:
        if e["kind"] == "parse":
            try:
                v = json.loads(e["data"])
            except json.JSONDecodeError:
                continue
            if predicate(v):
                return v
    return None


def is_unique_rows(v):
    return isinstance(v, list) and v and isinstance(v[0], dict) and "unique_code" in v[0] and "khata_number" in v[0]


def is_ror(v):
    return isinstance(v, dict) and "names" in v and "khasra" in v


async def dismiss_popups(page):
    for sel in ("button.swal2-confirm:visible", ".modal.show button:has-text('Close'):visible"):
        btn = page.locator(sel)
        if await btn.count():
            await btn.first.click()
            await page.wait_for_timeout(300)


async def open_search_page(page, district=None, tehsil=None, village=None):
    """Open #/khatauni_rtk directly (no captcha needed there) and pick district / tehsil / village.

    Names are matched against the dropdown's English labels; defaults come from config.json.
    """
    cfg = config.load()
    district, tehsil, village = district or cfg["district"], tehsil or cfg["tehsil"], village or cfg["village"]
    await page.goto("https://upbhulekh.gov.in/" + SEARCH_PAGE, timeout=90000, wait_until="domcontentloaded")
    await page.wait_for_timeout(5000)
    # the app's full-page spinner swallows clicks until its first API calls finish
    await page.locator("#preloader").wait_for(state="hidden", timeout=120000)
    for sel_id, text in (("districtSelect", district), ("tehsilSelect", tehsil), ("villageSelect", village)):
        box = page.locator(f"#{sel_id}")
        # each dropdown stays disabled until the previous choice has loaded its list
        await page.wait_for_function(
            "id => { const i = document.querySelector('#' + id + ' input'); return i && !i.disabled; }",
            arg=sel_id, timeout=90000)
        await box.click()
        await box.locator("input").fill(text)
        await page.wait_for_timeout(1200)
        await page.locator(".ng-dropdown-panel .ng-option", has_text=text).first.click()
        await page.wait_for_timeout(2500)


async def ensure_search_page(page):
    if SEARCH_PAGE in page.url:
        return
    if RESULT_PAGE in page.url:
        await page.get_by_role("button", name="Back").first.click()
        await page.wait_for_url("**" + SEARCH_PAGE, timeout=30000)
        await page.wait_for_timeout(800)
        return
    log(f"NEED_USER: browser is on {page.url}. Solve the captcha and reopen the village's search page; waiting…")
    await page.wait_for_url("**" + SEARCH_PAGE, timeout=0)
    await page.wait_for_timeout(1500)
    log("search page is back, continuing")


async def search_khasra(page, traffic: Traffic, number: int):
    """Type `number` on the keypad and search. Returns the uniqueCode rows (possibly [])."""
    await ensure_search_page(page)
    await dismiss_popups(page)
    kb = page.locator("table.keyboard1:visible").first
    await kb.get_by_text("clear", exact=True).click()
    for digit in str(number):
        await kb.locator(f'a[data-value="{digit}"]').click()
    field = page.get_by_placeholder(PLACEHOLDER)
    for _ in range(20):  # Angular updates the readonly field a moment after the key click
        typed = await field.input_value()
        if typed == str(number):
            break
        await page.wait_for_timeout(100)
    else:
        raise RuntimeError(f"keypad typed {typed!r} instead of {number}")
    traffic.mark()
    await page.locator("button:visible", has_text="खोजें").first.click()
    status, events = await traffic.wait_done("uniqueCode")
    if status != 200:
        raise RuntimeError(f"uniqueCode HTTP {status}")
    await dismiss_popups(page)
    return parsed(events, is_unique_rows) or []


async def open_row(page, traffic: Traffic, row_index: int):
    """Select the row_index-th radio of the current results and open its उद्धरण; return the ROR dict."""
    radios = page.locator("input[type=radio]:visible")
    await radios.nth(row_index).check()
    traffic.mark()
    await page.locator("button:visible", has_text="उद्धरण देखें").first.click()
    status, events = await traffic.wait_done("ror", timeout=60)
    if status != 200:
        raise RuntimeError(f"ror HTTP {status}")
    await page.wait_for_url("**" + RESULT_PAGE, timeout=30000)
    ror = parsed(events, is_ror)
    if ror is None:
        raise RuntimeError("ror response not captured")
    return ror


async def download_pdf(page, state, filename: str, timeout=300.0):
    before = len(state["downloads"])
    state["next_download_name"] = filename
    await page.wait_for_timeout(1500)  # let the khatauni finish rendering before jsPDF snapshots it
    await page.get_by_role("button", name="Download PDF").first.click()
    deadline = time.monotonic() + timeout
    while len(state["downloads"]) == before:
        if time.monotonic() > deadline:
            raise TimeoutError("PDF download did not start")
        await asyncio.sleep(0.5)
    return state["downloads"][-1]


async def process_khasra(page, state, traffic, prog, number):
    rows = await search_khasra(page, traffic, number)
    prog["khasra_rows"][str(number)] = [
        {k: r.get(k) for k in ("khasra_no", "unique_code", "khata_number", "area")} for r in rows]
    if not rows:
        prog["empty_streak"] += 1
        return
    prog["empty_streak"] = 0
    for i, row in enumerate(rows):
        khata = row["khata_number"]
        if khata in prog["khatas"]:
            continue
        if i > 0 or RESULT_PAGE in page.url:
            # Back from the result page resets the search, so search again before picking row i.
            again = await search_khasra(page, traffic, number)
            if [r["unique_code"] for r in again] != [r["unique_code"] for r in rows]:
                raise RuntimeError(f"khasra {number}: result rows changed between searches")
        ror = await open_row(page, traffic, i)
        (JSON_DIR / f"khata_{khata}.json").write_text(
            json.dumps({"khata_number": khata, "via_khasra": row, "ror": ror}, ensure_ascii=False, indent=1),
            encoding="utf-8")
        hits = match_ror(ror)
        entry = {"via_khasra": row["khasra_no"], "search_number": number, "unique_code": row["unique_code"],
                 "hits": hits, "pdf": None}
        if should_download(hits):
            entry["pdf"] = await download_pdf(page, state, f"khata_{khata}.pdf")
            log(f"MATCH khata {khata} (khasra {row['khasra_no']}): "
                + ", ".join(f"{h['name']}/{h['father']} [{h['source']},{h['strength']}]" for h in hits))
        elif hits:
            log(f"name-only hit on khata {khata} (khasra {row['khasra_no']}), not downloaded: "
                + ", ".join(f"{h['name']}/{h['father']}" for h in hits))
        prog["khatas"][khata] = entry
        save_progress(prog)
        await page.get_by_role("button", name="Back").first.click()
        await page.wait_for_url("**" + SEARCH_PAGE, timeout=30000)
        await page.wait_for_timeout(random.uniform(1.0, 2.0))


async def run(page, state, start=None, stop=None):
    JSON_DIR.mkdir(parents=True, exist_ok=True)
    PDF_DIR.mkdir(parents=True, exist_ok=True)
    prog = load_progress()
    number = start or prog["next_khasra"]
    traffic = Traffic()
    log(f"sweep starting at khasra {number}")
    failures = 0
    while True:
        if stop and number > stop:
            break
        if not stop and prog["empty_streak"] >= EMPTY_STREAK_STOP:
            log(f"{EMPTY_STREAK_STOP} empty khasra numbers in a row, stopping at {number - 1}")
            break
        try:
            await process_khasra(page, state, traffic, prog, number)
            failures = 0
        except Exception as e:  # retry the same number a few times, then skip it
            failures += 1
            log(f"khasra {number}: error {type(e).__name__}: {e} (attempt {failures})")
            await dismiss_popups(page)
            if failures < 3:
                await page.wait_for_timeout(5000 * failures)
                continue
            prog.setdefault("failed", []).append(number)
            failures = 0
        number += 1
        prog["next_khasra"] = number
        save_progress(prog)
        if number % 25 == 0:
            matched = sum(1 for k in prog["khatas"].values() if k["pdf"])
            log(f"progress: next khasra {number}, khatas seen {len(prog['khatas'])}, matched {matched}")
        await page.wait_for_timeout(random.uniform(800, 1600))
    save_progress(prog)
    return {"next_khasra": number, "khatas": len(prog["khatas"]),
            "matched": [k for k, v in prog["khatas"].items() if v["pdf"]], "failed": prog.get("failed", [])}


async def catch_up(page, state, skip=None):
    """Re-match every saved khata JSON with the current names.py and download any matched PDF still missing."""
    prog = load_progress()
    traffic = Traffic()
    number_for_code = {r["unique_code"]: int(n) for n, rows in prog["khasra_rows"].items() for r in rows}
    done, failed = [], []
    for f in sorted(JSON_DIR.glob("khata_*.json")):
        saved = json.loads(f.read_text(encoding="utf-8"))
        khata, ror = saved["khata_number"], saved["ror"]
        hits = match_ror(ror)
        entry = prog["khatas"].setdefault(khata, {"via_khasra": saved["via_khasra"]["khasra_no"],
                                                  "unique_code": saved["via_khasra"]["unique_code"], "pdf": None})
        entry["hits"] = hits
        pdf = PDF_DIR / f"khata_{khata}.pdf"
        if not should_download(hits) or pdf.exists():
            if pdf.exists():
                entry["pdf"] = str(pdf)
            continue
        code = entry["unique_code"]
        number = number_for_code.get(code)
        if number is None:
            log(f"catch-up: khata {khata} has no recorded search number, skipping")
            continue
        if khata in (skip or ()):
            continue
        try:
            rows = await search_khasra(page, traffic, number)
            idx = next((i for i, r in enumerate(rows) if r["unique_code"] == code), None)
            if idx is None:
                log(f"catch-up: khata {khata} not in khasra {number} results any more, skipping")
                continue
            await open_row(page, traffic, idx)
            entry["pdf"] = await download_pdf(page, state, pdf.name, timeout=180)
        except Exception as e:
            log(f"catch-up: khata {khata} failed: {type(e).__name__}: {e}")
            failed.append(khata)
            if page.is_closed():
                raise
            await open_search_page(page)
            continue
        log(f"catch-up MATCH khata {khata}: " + ", ".join(f"{h['name']}/{h['father']} [{h['source']},{h['strength']}]" for h in hits))
        done.append(khata)
        save_progress(prog)
        await page.get_by_role("button", name="Back").first.click()
        await page.wait_for_url("**" + SEARCH_PAGE, timeout=30000)
        await page.wait_for_timeout(random.uniform(1.0, 2.0))
    save_progress(prog)
    return {"downloaded": done, "failed": failed}


async def page_to_pdf(page, pdf_path, page_height=2200):
    """Save the rendered page as an image PDF (screenshot sliced into pages).

    Used where the site's own "Download PDF" (jsPDF) takes the browser down.
    """
    import io
    from PIL import Image
    await page.wait_for_timeout(1500)
    png = await page.screenshot(full_page=True)
    img = Image.open(io.BytesIO(png)).convert("RGB")
    w, h = img.size
    parts = [img.crop((0, top, w, min(top + page_height, h))) for top in range(0, h, page_height)]
    Path(pdf_path).parent.mkdir(parents=True, exist_ok=True)
    parts[0].save(pdf_path, "PDF", resolution=150, save_all=True, append_images=parts[1:])
    return str(pdf_path), len(parts)
