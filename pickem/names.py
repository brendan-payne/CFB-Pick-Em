"""Canonical player names and matchup parsing."""

from __future__ import annotations

import re
import unicodedata

PLAYERS = [
    {"id": "mark", "name": "Mark"},
    {"id": "micah", "name": "Micah"},
    {"id": "max", "name": "Max"},
    {"id": "brendan", "name": "Brendan"},
    {"id": "murph", "name": "Murph"},
    {"id": "jacob", "name": "Jacob"},
    {"id": "weston", "name": "Weston"},
    {"id": "will", "name": "Will"},
    {"id": "mason", "name": "Mason"},
    {"id": "charlie", "name": "Charlie"},
    {"id": "nathan", "name": "Nathan"},
    {"id": "buck", "name": "Buck"},
]

ALIAS_TO_ID = {
    "mark": "mark",
    "mark mcmanus": "mark",
    "micah": "micah",
    "micah shelton": "micah",
    "max": "max",
    "brendan": "brendan",
    "murph": "murph",
    "murphy": "murph",
    "murphy garner": "murph",
    "jacob": "jacob",
    "jacob walker": "jacob",
    "weston": "weston",
    "weston akin": "weston",
    "will": "will",
    "mason": "mason",
    "mason williams": "mason",
    "charlie": "charlie",
    "nathan": "nathan",
    "buck": "buck",
    "buck ralston": "buck",
}

TEAM_ALIASES = {
    "florida st.": "florida state",
    "florida st": "florida state",
    "washington st.": "washington state",
    "washington st": "washington state",
    "oklahoma st": "oklahoma state",
    "oklahoma st.": "oklahoma state",
    "boston college": "boston college",
    "unc": "north carolina",
    "nc state": "nc state",
    "n.c. state": "nc state",
    "north dakota state": "north dakota state",
    "jacksonville state": "jacksonville state",
    "san jose state": "san josé state",
    "san josé state": "san josé state",
    "ole miss": "ole miss",
    "cal": "california",
    "ucla": "ucla",
    "lsu": "lsu",
    "usc": "usc",
    "tcu": "tcu",
    "smu": "smu",
    "unlv": "unlv",
    "ndsu": "north dakota state",
    "bama": "alabama",
    "uga": "georgia",
    "miami": "miami",
    "ohio state": "ohio state",
    "ohio st": "ohio state",
    "notre dame": "notre dame",
    "texas tech": "texas tech",
    "jmu": "james madison",
}


def fold(text: str) -> str:
    text = unicodedata.normalize("NFKD", text or "")
    text = "".join(ch for ch in text if not unicodedata.combining(ch))
    text = text.lower().strip()
    text = text.replace("&", "and")
    text = re.sub(r"\s+", " ", text)
    return text


def player_id_from_name(raw: str) -> str | None:
    key = fold(raw)
    return ALIAS_TO_ID.get(key)


def normalize_team(raw: str) -> str:
    key = fold(raw)
    key = key.replace(".", "")
    if key in TEAM_ALIASES:
        return TEAM_ALIASES[key]
    # Florida St / Washington St after stripping periods
    key = re.sub(r"\bst\b", "state", key)
    if key in TEAM_ALIASES:
        return TEAM_ALIASES[key]
    return key


def teams_match(a: str, b: str) -> bool:
    na, nb = normalize_team(a), normalize_team(b)
    if na == nb:
        return True
    if na in nb or nb in na:
        return True
    return False


def parse_matchup(label: str) -> tuple[str, str]:
    """Return (away, home). '@' means left is away; 'vs' lists home-ish first as left."""
    raw = re.sub(r"\s+", " ", (label or "").strip())
    at = re.split(r"\s+@\s+", raw, maxsplit=1)
    if len(at) == 2:
        return at[0].strip(), at[1].strip()
    vs = re.split(r"\s+vs\.?\s+", raw, maxsplit=1, flags=re.I)
    if len(vs) == 2:
        # "Auburn vs. Baylor" — first team treated as home
        return vs[1].strip(), vs[0].strip()
    return raw, raw


def is_auburn_team(raw: str) -> bool:
    n = normalize_team(raw)
    return n == "auburn" or n.startswith("auburn ")


def is_auburn_game(away: str, home: str) -> bool:
    return is_auburn_team(away) or is_auburn_team(home)


def point_value_for(away: str, home: str) -> int:
    return 15 if is_auburn_game(away, home) else 5


def slug_game(week_slug: str, away: str, home: str) -> str:
    def tok(s: str) -> str:
        s = normalize_team(s)
        s = re.sub(r"[^a-z0-9]+", "-", s).strip("-")
        return s or "team"

    return f"{week_slug}-{tok(away)}-at-{tok(home)}"
