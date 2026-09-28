"""Target owners and tolerant matching against a ROR's `names` list."""
import re
import unicodedata

import config

# (name, father/husband) pairs from the data directory's config.json; address is not used for matching.
TARGETS = [tuple(t) for t in config.load()["targets"]]

# Spelling variants common in UP land records, folded to one form.
_FOLD = [
    ("ी", "ि"), ("ू", "ु"), ("ं", "न"), ("ँ", "न"), ("ॉ", "ा"),
    ("ष", "श"), ("स", "श"), ("व", "ब"), ("ण", "न"),
    ("क्ष", "छ"), ("्", ""),
]
# Suffixes/honorifics that come and go between records ("राम सिंह" vs "रामसिंह", "सीता" vs "सीता देवी").
_DROP_SUFFIXES = ("देवी", "सिंह", "सिह", "प्रसाद")
_DROP_WORDS = {"श्री", "स्व", "मृतक"}


def norm(s: str | None) -> str:
    if not s:
        return ""
    s = unicodedata.normalize("NFC", s)
    s = re.sub(r"[\s.०0()\-/]+", " ", s).strip()
    return s


def key(s: str | None, drop_common: bool = True) -> str:
    """Compact comparison key: folded spellings, no spaces, optional honorific/suffix words removed."""
    words = [w for w in norm(s).split() if w not in _DROP_WORDS]
    k = "".join(words)
    if drop_common:
        for suf in _DROP_SUFFIXES:
            if k.endswith(suf) and len(k) > len(suf):
                k = k[: -len(suf)]
    for a, b in _FOLD:
        k = k.replace(a, b)
    return k


def match_owner(name: str | None, father: str | None):
    """Return (target, strength): 'exact' (name+father), 'fuzzy' (father contains target father), or 'name_only'."""
    nk, fk = key(name), key(father)
    for t_name, t_father in TARGETS:
        if nk and nk == key(t_name):
            tk = key(t_father)
            if fk and (fk == tk or key(father, False) == key(t_father, False)):
                return (t_name, t_father), "exact"
            if fk and len(tk) >= 3 and (tk in fk or (len(fk) >= 3 and fk in tk)):
                return (t_name, t_father), "fuzzy"  # typo'd / padded father name
            return (t_name, t_father), "name_only"
    return None


def _people(ror: dict):
    """(source, name, father, address, hissa) for everyone a ROR mentions.

    Sole-owner khatas list owners in `names`; shared (`ansh`) khatas use `response1.data`.
    `rname` are owners struck off by a mutation (खारिज), `aname` are owners added by one (दर्ज).
    """
    for o in ror.get("names") or []:
        yield "owner", o.get("name"), o.get("father"), o.get("address"), None
    for o in ((ror.get("response1") or {}).get("data")) or []:
        yield "owner", o.get("name"), o.get("father"), o.get("address"), o.get("hissa")
    for row in ror.get("rname") or []:
        o = row.get("data") or {}
        yield "removed", o.get("rname"), o.get("rfather"), o.get("r_address"), o.get("r_hissa")
    for row in ror.get("aname") or []:
        o = row.get("data") or {}
        yield "added", o.get("aname"), o.get("afather"), o.get("a_address"), o.get("a_hissa")


def match_ror(ror: dict):
    """All target hits in a ROR response, de-duplicated per (source, name, father)."""
    hits, seen = [], set()
    for source, name, father, address, hissa in _people(ror):
        m = match_owner(name, father)
        if not m or (source, name, father) in seen:
            continue
        seen.add((source, name, father))
        hits.append({"target": m[0][0], "target_father": m[0][1], "strength": m[1], "source": source,
                     "name": name, "father": father, "address": address, "hissa": hissa})
    return hits


DOWNLOAD_STRENGTHS = ("exact", "fuzzy")


def should_download(hits) -> bool:
    return any(h["strength"] in DOWNLOAD_STRENGTHS for h in hits)
