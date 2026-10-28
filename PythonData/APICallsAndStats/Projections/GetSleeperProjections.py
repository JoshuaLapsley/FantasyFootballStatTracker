"""
Pull weekly NFL projections from Sleeper (free, no API key) and save them as JSON.

    from sleeper_projections import get_projections

    get_projections(2026, 7, "FantasyProsProjections")   # one week
    get_projections(2026, None, "FantasyProsProjections")  # weeks 1-17

Each file holds players and their projected points:
    {out_dir}/{year}/projections/week_07.json

Notes:
  * The Sleeper projections endpoint is undocumented and could change without notice.
  * It is requested once per position (6 requests per week, 102 for a full season).
  * Projections are Sleeper's own numbers, not Yahoo's.
"""

import json
import time
from pathlib import Path

import requests

PROJ_URL = "https://api.sleeper.app/projections/nfl/{year}/{week}"
PLAYERS_URL = "https://api.sleeper.app/v1/players/nfl"
POSITIONS = ["QB", "RB", "WR", "TE", "K", "DEF"]
LAST_WEEK = 17
POINT_FIELDS = ["pts_std", "pts_half_ppr", "pts_ppr"]


def _get(url, params=None, retries=3):
    for attempt in range(1, retries + 1):
        resp = requests.get(url, params=params, timeout=30)
        if resp.status_code == 429:  # rate limited: back off and retry
            time.sleep(2 * attempt)
            continue
        resp.raise_for_status()
        return resp.json()
    raise RuntimeError("rate limited after retries")


def _load_player_names(cache_file):
    """Sleeper's full player list (large). Downloaded once and cached on disk."""
    cache_file = Path(cache_file)
    if cache_file.exists():
        return json.loads(cache_file.read_text())
    players = _get(PLAYERS_URL)
    cache_file.parent.mkdir(parents=True, exist_ok=True)
    cache_file.write_text(json.dumps(players))
    return players


def _clean(item, names):
    """Reduce one raw Sleeper record to name, team, position and projected points."""
    stats = item.get("stats") or {}
    points = {f: stats.get(f) for f in POINT_FIELDS}
    if all(v is None for v in points.values()):
        return None  # no projection for this player

    info = item.get("player") or {}
    pid = item.get("player_id") or info.get("player_id")
    if not info.get("first_name") and names:
        info = names.get(str(pid)) or {}

    full = f"{info.get('first_name', '')} {info.get('last_name', '')}".strip()
    return {
        "player_id": pid,
        "name": full or None,
        "team": item.get("team") or info.get("team"),
        "position": info.get("position"),
        **points,
    }


def get_projections(year, week=None, out_dir="Functions/APIData", delay=0.3):
    """
    Save Sleeper weekly projections as JSON.

    year:    season year, e.g. 2026
    week:    a single week (1-17), or None/blank for every week 1-17
    out_dir: root output folder; files go to {out_dir}/{year}/projections/

    Returns the list of file paths written.
    """
    weeks = [week] if week else range(1, LAST_WEEK + 1)
    folder = Path(out_dir) / str(year) / "projections"
    folder.mkdir(parents=True, exist_ok=True)
    names = None  # only downloaded if the projection records lack player names

    written, failed = [], []
    for wk in weeks:
        raw = []
        try:
            for pos in POSITIONS:
                params = {"season_type": "regular", "position[]": pos}
                raw.extend(_get(PROJ_URL.format(year=year, week=wk), params))
                time.sleep(delay)

            if names is None and any(not (r.get("player") or {}).get("first_name") for r in raw):
                names = _load_player_names(Path(out_dir) / "sleeper_players.json")

            players = [p for p in (_clean(r, names) for r in raw) if p]
            players.sort(key=lambda p: p["pts_ppr"] or 0, reverse=True)

            path = folder / f"week_{wk:02d}.json"
            path.write_text(json.dumps(
                {"year": year, "week": wk, "source": "sleeper", "players": players}, indent=2))
            written.append(path)
            print(f"saved week {wk} ({len(players)} players) -> {path}")
        except Exception as e:
            failed.append(wk)
            print(f"FAILED week {wk}: {e}")

    if failed:
        print(f"weeks that failed: {failed}")
    return written


if __name__ == "__main__":
    get_projections(2026)