"""Discovery run: open the real site in a visible browser, record decrypted API traffic.

You drive the browser by hand: solve the captcha, pick a district → tehsil → village,
search by an owner name, and open one khata's उद्धरण खतौनी. Everything the
app encrypts or decrypts is written to <data>/out/discovery.jsonl. Close the browser window when done.
"""
import asyncio
import json
import os
from pathlib import Path

from playwright.async_api import async_playwright

import config

ROOT = Path(__file__).parent
OUT = config.OUT
LOG = OUT / "discovery.jsonl"


async def main():
    OUT.mkdir(exist_ok=True)
    log = LOG.open("a", encoding="utf-8")

    def record(line: str):
        log.write(line + "\n")
        log.flush()
        entry = json.loads(line)
        data = entry["data"]
        preview = data if isinstance(data, dict) else data[:160]
        print(entry["kind"], preview, flush=True)

    async with async_playwright() as p:
        ctx = await p.chromium.launch_persistent_context(
            str(config.DATA / "profile"),
            executable_path=os.environ.get("CHROMIUM_PATH") or None,
            headless=False,
            accept_downloads=True,
            viewport={"width": 1400, "height": 950},
        )
        await ctx.expose_function("__bhuLog", record)
        await ctx.add_init_script(path=str(ROOT / "hooks.js"))
        page = ctx.pages[0] if ctx.pages else await ctx.new_page()
        page.on("download", lambda d: asyncio.ensure_future(
            d.save_as(OUT / "discovery_download.pdf")))
        await page.goto("https://upbhulekh.gov.in/#/home")
        print(">>> Browser open. Solve the captcha and do one name search; close the window when finished.", flush=True)
        await ctx.wait_for_event("close", timeout=0)
    log.close()


if __name__ == "__main__":
    asyncio.run(main())
