"""Reject listings that are not the actual product (parts, boxes, bundles, wrong variant)."""
import re

# phrases that contain an excluded word but are fine ("non-ECC" desktop RAM is what we want)
_SAFE = [r"non[\s-]?ecc", r"non[\s-]?registered", r"unbuffered"]


def _norm(s: str) -> str:
    s = re.sub(r"\s+", " ", s.lower())
    for pat in _SAFE:
        s = re.sub(pat, " ", s)
    return s


def _has_word(title: str, word: str) -> bool:
    w = word.lower()
    if re.search(r"(?<![a-z0-9])" + re.escape(w) + r"s?(?![a-z0-9])", title):
        return True
    # "3060ti" should match exclude "3060 ti"
    if " " in w and w.replace(" ", "") in title.replace(" ", ""):
        return True
    return False


def keep(listing: dict, model: dict, global_exclude: list[str]) -> bool:
    title = _norm(listing.get("title", ""))
    compact = title.replace(" ", "")
    for word in model.get("must", []):  # substring match: "12" matches "12gb"
        w = word.lower()
        if w not in title and w.replace(" ", "") not in compact:
            return False
    for word in list(global_exclude) + model.get("exclude", []):  # whole-word match
        if _has_word(title, word):
            return False
    return model["min"] <= listing["total"] <= model["max"] * 1.15
