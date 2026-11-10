"""
Translate Yahoo player names into Sleeper names and look up a player's
Sleeper projection record for a given week.

Place this file in the same folder as the script it was extracted from, so
the relative PROJECTIONS_DIR path below still resolves correctly.

Public API:
    PROJECTIONS_DIR
    normalize_name(name)
    to_sleeper_name(yahoo_name)
    load_sleeper_week(year, week)   -> (exact_index, normalized_index) or None
    lookup_player(name, year, week) -> Sleeper projection record (dict) or None
"""

import json
import re
import unicodedata
from functools import lru_cache
from pathlib import Path

PROJECTIONS_DIR = Path(__file__).resolve().parent.parent / "Projections" / "SleeperProjections"

# Yahoo uses the team nickname for defenses, Sleeper uses the full name.
DEF_NAMES = {
    "Cardinals": "Arizona Cardinals", "Falcons": "Atlanta Falcons",
    "Ravens": "Baltimore Ravens", "Bills": "Buffalo Bills",
    "Panthers": "Carolina Panthers", "Bears": "Chicago Bears",
    "Bengals": "Cincinnati Bengals", "Browns": "Cleveland Browns",
    "Cowboys": "Dallas Cowboys", "Broncos": "Denver Broncos",
    "Lions": "Detroit Lions", "Packers": "Green Bay Packers",
    "Texans": "Houston Texans", "Colts": "Indianapolis Colts",
    "Jaguars": "Jacksonville Jaguars", "Chiefs": "Kansas City Chiefs",
    "Raiders": "Las Vegas Raiders", "Chargers": "Los Angeles Chargers",
    "Rams": "Los Angeles Rams", "Dolphins": "Miami Dolphins",
    "Vikings": "Minnesota Vikings", "Patriots": "New England Patriots",
    "Saints": "New Orleans Saints", "Giants": "New York Giants",
    "Jets": "New York Jets", "Eagles": "Philadelphia Eagles",
    "Steelers": "Pittsburgh Steelers", "49ers": "San Francisco 49ers",
    "Seahawks": "Seattle Seahawks", "Buccaneers": "Tampa Bay Buccaneers",
    "Titans": "Tennessee Titans", "Commanders": "Washington Commanders",
}

# Manual fixes for one-off name differences: {"Yahoo name": "Sleeper name"}
NAME_OVERRIDES = {
}

_SUFFIXES = {"jr", "sr", "ii", "iii", "iv", "v"}


# --------------------------------------------------------------------------
# Name translation
# --------------------------------------------------------------------------
def normalize_name(name):
    """Lowercase, strip accents/punctuation and generational suffixes."""
    name = unicodedata.normalize("NFKD", name).encode("ascii", "ignore").decode()
    name = re.sub(r"[.'’,]", "", name.lower()).replace("-", " ")
    parts = name.split()
    while len(parts) > 1 and parts[-1] in _SUFFIXES:
        parts.pop()
    return " ".join(parts)


def to_sleeper_name(yahoo_name):
    """Translate a Yahoo player name into the name Sleeper uses."""
    if yahoo_name in NAME_OVERRIDES:
        return NAME_OVERRIDES[yahoo_name]
    if yahoo_name in DEF_NAMES:
        return DEF_NAMES[yahoo_name]
    return yahoo_name


# --------------------------------------------------------------------------
# Sleeper data
# --------------------------------------------------------------------------
@lru_cache(maxsize=None)
def load_sleeper_week(year, week):
    """Returns (exact_index, normalized_index) for a week, or None if no file."""
    path = PROJECTIONS_DIR / str(year) / "projections" / f"week_{week:02d}.json"
    if not path.exists():
        return None
    with open(path, encoding="utf-8") as f:
        data = json.load(f)
    exact, norm = {}, {}
    for p in data.get("players", []):
        exact.setdefault(p["name"], p)
        norm.setdefault(normalize_name(p["name"]), p)
    return exact, norm


def lookup_player(name, year, week):
    """Yahoo name -> Sleeper projection record for that week, or None."""
    idx = load_sleeper_week(year, week)
    if idx is None:
        return None
    exact, norm = idx
    sleeper_name = to_sleeper_name(name)
    return exact.get(sleeper_name) or norm.get(normalize_name(sleeper_name))