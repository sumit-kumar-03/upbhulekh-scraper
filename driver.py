"""Long-running headed browser that Claude (or you) can script while it stays logged in.

The user solves the home-page captcha by hand once. After that, any file dropped in
<data>/out/cmd/<name>.py is run as the body of `async def f(page, ctx, state)`; its return
value (JSON-serialisable) or traceback is written to <data>/out/cmd/<name>.out. Decrypted API
traffic (via hooks.js) is appended to <data>/out/traffic.jsonl, and browser downloads are saved
under <data>/out/pdf/ using state["next_download_name"] when set.
"""
import asyncio
import json
import os
import textwrap
import traceback
from pathlib import Path

from playwright.async_api import async_playwright

import config

ROOT = Path(__file__).parent
OUT = config.OUT
CMD = OUT / "cmd"
PDF = OUT / "pdf"


async def main():
    for d in (OUT, CMD, PDF):
        d.mkdir(parents=True, exist_ok=True)
    traffic = (OUT / "traffic.jsonl").open("a", encoding="utf-8")
    state = {"next_download_name": None, "downloads": []}

    def record(line: str):
        traffic.write(line + "\n")
        traffic.flush()

    async def on_download(d):
        name = state.pop("next_download_name", None) or d.suggested_filename
        state["next_download_name"] = None
        target = PDF / name
        try:
            await d.save_as(target)
            state["downloads"].append(str(target))
        except Exception as e:  # a failed save must not take the driver down
            print(f"download of {name} failed: {e}", flush=True)

    async with async_playwright() as p:
        ctx = await p.chromium.launch_persistent_context(
            str(config.DATA / "profile-driver"),
            headless=os.environ.get("HEADLESS", "0") == "1",
            accept_downloads=True,
            viewport={"width": 1400, "height": 950},
        )
        # The site's static bundle (7.4 MB main.js) is sometimes served so slowly the app never
        # boots. Serve hashed JS/CSS from <data>/asset_cache/ when present, caching anything new.
        cache = config.DATA / "asset_cache"
        cache.mkdir(exist_ok=True)

        async def serve_static(route):
            name = route.request.url.split("?")[0].rsplit("/", 1)[-1]
            local = cache / name
            if local.exists():
                ctype = "text/css" if name.endswith(".css") else "application/javascript"
                await route.fulfill(path=str(local), content_type=ctype)
                return
            resp = await route.fetch(timeout=300000)
            if resp.ok:
                local.write_bytes(await resp.body())
            await route.fulfill(response=resp)

        await ctx.route("https://upbhulekh.gov.in/*.js", serve_static)
        await ctx.route("https://upbhulekh.gov.in/*.css", serve_static)
        await ctx.expose_function("__bhuLog", record)
        await ctx.add_init_script(path=str(ROOT / "hooks.js"))
        page = ctx.pages[0] if ctx.pages else await ctx.new_page()
        page.on("download", lambda d: asyncio.ensure_future(on_download(d)))
        await page.goto("https://upbhulekh.gov.in/#/home", timeout=90000, wait_until="domcontentloaded")
        print(">>> driver ready", flush=True)

        while True:
            if not ctx.pages:  # the site's PDF step can take the tab down; keep the session alive
                page = await ctx.new_page()
                page.on("download", lambda d: asyncio.ensure_future(on_download(d)))
            page = ctx.pages[-1]
            for f in sorted(CMD.glob("*.py")):
                src = f.read_text(encoding="utf-8")
                f.rename(f.with_suffix(".done"))
                body = textwrap.indent(src, "    ")
                ns = {"asyncio": asyncio, "json": json, "Path": Path, "OUT": OUT}
                try:
                    exec(f"async def __f(page, ctx, state):\n{body}\n    return None", ns)
                    result = await ns["__f"](page, ctx, state)
                    text = json.dumps(result, ensure_ascii=False, indent=1, default=str)
                except Exception:
                    text = "ERROR\n" + traceback.format_exc()
                f.with_suffix(".out").write_text(text, encoding="utf-8")
            await asyncio.sleep(0.5)
    traffic.close()


if __name__ == "__main__":
    asyncio.run(main())
