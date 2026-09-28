"""Render a Markdown report (Hindi/English) to a styled A4 PDF with headless Chromium.

Usage: .venv/bin/python md_to_pdf.py input.md output.pdf
"""
import asyncio
import sys
from datetime import date
from pathlib import Path

import markdown
from playwright.async_api import async_playwright

CSS = """
@page { size: A4; margin: 16mm 14mm 18mm; }
body { font: 10.5pt/1.55 "Noto Sans Devanagari", "Noto Sans", sans-serif; color: #1c2320; margin: 0; }
h1 { font: 600 18pt/1.25 "Noto Serif Devanagari", serif; margin: 0 0 4pt; color: #12302a; }
h2 { font: 600 12.5pt/1.3 "Noto Serif Devanagari", serif; margin: 16pt 0 6pt; padding-bottom: 3pt;
     border-bottom: 1.5pt solid #12302a; break-after: avoid; }
p, li { margin: 3pt 0; }
ul, ol { padding-left: 16pt; margin: 4pt 0; }
em { color: #5b6560; }
code { font: 9pt "JetBrains Mono", monospace; background: #eef1ec; padding: 0 3pt; border-radius: 2pt; }
table { border-collapse: collapse; width: 100%; margin: 6pt 0 8pt; font-size: 9.2pt; break-inside: avoid; }
th, td { border: 0.6pt solid #cfd6d0; padding: 4pt 6pt; text-align: left; vertical-align: top; }
th { background: #e8eee9; font-weight: 600; }
tr:nth-child(even) td { background: #f7f9f7; }
.meta { color: #5b6560; font-size: 9pt; margin-bottom: 10pt; }
"""


def normalise_lists(text: str) -> str:
    """Python-Markdown needs a blank line before a list and 4-space nesting; GitHub-style
    Markdown doesn't. Add the blank lines and double 2-space list indents."""
    out, prev = [], ""
    for line in text.splitlines():
        stripped = line.lstrip(" ")
        is_item = stripped[:2] in ("- ", "* ") or stripped[:3].rstrip(".").isdigit() and stripped[1:3] == ". "
        if is_item:
            indent = len(line) - len(stripped)
            line = " " * (indent * 2) + stripped
            if prev.strip() and not prev.lstrip(" ")[:2] in ("- ", "* ") and not prev.lstrip(" ")[:1].isdigit():
                out.append("")
        out.append(line)
        prev = line
    return "\n".join(out)


async def render(md_path: Path, pdf_path: Path):
    body = markdown.markdown(normalise_lists(md_path.read_text(encoding="utf-8")), extensions=["tables"])
    html = f"""<!doctype html><html lang="hi"><head><meta charset="utf-8">
<link href="https://fonts.googleapis.com/css2?family=Noto+Sans+Devanagari:wght@400;600&family=Noto+Serif+Devanagari:wght@600&display=swap" rel="stylesheet">
<style>{CSS}</style></head><body>{body}
<p class="meta">Prepared {date.today():%d %B %Y} from upbhulekh.gov.in and linked UP government portals.</p></body></html>"""
    async with async_playwright() as p:
        b = await p.chromium.launch()
        pg = await b.new_page()
        await pg.set_content(html, wait_until="networkidle")
        await pg.pdf(path=str(pdf_path), format="A4", print_background=True, display_header_footer=True,
                     header_template="<span></span>",
                     footer_template='<div style="font-size:8pt;color:#777;width:100%;text-align:center">'
                                     '<span class="pageNumber"></span> / <span class="totalPages"></span></div>',
                     margin={"top": "16mm", "bottom": "18mm", "left": "14mm", "right": "14mm"})
        await b.close()


if __name__ == "__main__":
    asyncio.run(render(Path(sys.argv[1]), Path(sys.argv[2])))
    print("wrote", sys.argv[2])
