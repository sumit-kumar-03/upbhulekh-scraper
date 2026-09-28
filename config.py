"""Where personal data lives and what to look for.

Everything user-specific (scraped JSON/PDFs, browser profiles, the target location and
owner names) sits under the data directory, `private/` by default, which is gitignored.
Override it with the BHULEKH_DATA environment variable.
"""
import json
import os
from pathlib import Path

ROOT = Path(__file__).parent
DATA = Path(os.environ.get("BHULEKH_DATA", ROOT / "private"))
OUT = DATA / "out"
EXAMPLE = ROOT / "config.example.json"


def load() -> dict:
    """Read DATA/config.json, falling back to the committed example."""
    path = DATA / "config.json"
    return json.loads((path if path.exists() else EXAMPLE).read_text(encoding="utf-8"))
