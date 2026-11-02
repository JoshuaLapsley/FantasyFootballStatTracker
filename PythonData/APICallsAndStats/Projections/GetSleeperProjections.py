"""
Pull weekly NFL projections AND actual points from Sleeper (free, no API key)
and save them as JSON.

    from sleeper_projections import get_projections

    get_projections(2026)                                          # weeks 1-17
    get_projections(2026, 7)                                       # weeks 7-17
    get_projections(2026, 7, "FantasyProsProjections")             # weeks 7-17, custom folder

Each file holds one record per player:
    {"name": ..., "position": ..., "projection_ppr": ..., "pts_ppr": ...}
    {out_dir}/{year}/projections/week_07.json

Notes:
  * The Sleeper projections/stats endpoints are undocumented and could change.
  * Each is requested once per position (12 requests per week, 204 per season).
  * projection_ppr is Sleeper's own projection, not Yahoo's.
  * pts_ppr is the points the player actually scored. It is 0 when Sleeper has
    no points for the player (including games not yet played). During a live
    game it is a partial total.
  * projection_ppr stays null when Sleeper has no projection.
  * Re-running a week keeps values already saved in that week's file when the
    new pull has none, so run it before kickoff to lock in projections.
    Pass keep_previous=False for a clean overwrite with only the new pull.
"""

import json
import time
from pathlib import Path

import requests

PROJ_URL = "https://api.sleeper.app/projections/nfl/{year}/{week}"
STATS_URL = "https://api.sleeper.app/stats/nfl/{year}/{week}"
PLAYERS_URL = "https://api.sleeper.app/v1/players/nfl"
POSITIONS = ["QB", "RB", "WR", "TE", "K", "DEF"]
LAST_WEEK = 17
FIELDS = ["name", "position", "projection_ppr", "pts_ppr"]


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


def _fetch_by_position(url, delay):
    raw = []
    for pos in POSITIONS:
        params = {"season_type": "regular", "position[]": pos}
        raw.extend(_get(url, params) or [])
        time.sleep(delay)
    return raw


def _pid(item):
    pid = item.get("player_id") or (item.get("player") or {}).get("player_id")
    return str(pid) if pid is not None else None


def _index(raw):
    idx = {}
    for r in raw:
        pid = _pid(r)
        if pid and pid not in idx:
            idx[pid] = r
    return idx


def _needs_directory(raw):
    return any(not ((r.get("player") or {}).get("first_name")
                    and (r.get("player") or {}).get("position")) for r in raw)


def _build_players(proj_raw, stats_raw, names):
    """
    Merge projections and actual stats into clean records.
    Walks the UNION of both endpoints, so a player who scored points still
    appears even if the projections endpoint dropped or blanked him.
    """
    names = names or {}
    proj, stats = _index(proj_raw), _index(stats_raw)
    out = []
    for pid in dict.fromkeys([*proj, *stats]):
        p_item, s_item = proj.get(pid) or {}, stats.get(pid) or {}
        projection = (p_item.get("stats") or {}).get("pts_ppr")
        actual = (s_item.get("stats") or {}).get("pts_ppr")
        if projection is None and actual is None:
            continue  # nothing projected and nothing scored

        embedded = p_item.get("player") or s_item.get("player") or {}
        info = names.get(pid) or {}
        first = embedded.get("first_name") or info.get("first_name") or ""
        last = embedded.get("last_name") or info.get("last_name") or ""
        out.append({
            "name": f"{first} {last}".strip() or None,
            "position": embedded.get("position") or info.get("position"),
            "projection_ppr": projection,
            "pts_ppr": actual,
        })
    return out


def _key(p):
    return (p.get("name"), p.get("position"))


def _merge_previous(new_players, path):
    """
    If this week's file already exists (e.g. saved before kickoff), keep its
    values wherever the new pull has nothing. This preserves pre-game
    projections that Sleeper may remove once a player is hurt, and keeps
    players who vanished from the endpoints.
    """
    merged = {}
    if path.exists():
        try:
            for old in json.loads(path.read_text()).get("players", []):
                if "projection_ppr" not in old:
                    # file from an older version of this script, where
                    # pts_ppr was the projection and actual_pts_ppr the result
                    old = {"name": old.get("name"), "position": old.get("position"),
                           "projection_ppr": old.get("pts_ppr"),
                           "pts_ppr": old.get("actual_pts_ppr")}
                merged[_key(old)] = {k: old.get(k) for k in FIELDS}
        except Exception as e:
            print(f"  could not read previous {path.name} ({e}); not merging")
    for p in new_players:
        prev = merged.get(_key(p))
        if prev:
            for k in ("projection_ppr", "pts_ppr"):
                if p[k] is None:
                    p[k] = prev[k]
        merged[_key(p)] = p
    return list(merged.values())


def get_projections(year, current_week=None, out_dir="Functions/APIData", delay=0.3,
                    keep_previous=True):
    """
    Save Sleeper weekly projections and actual points as JSON.

    year:         season year, e.g. 2026
    current_week: optional. If given, weeks current_week through 17 are pulled
                  and rewritten; earlier weeks' files are left alone.
                  If None/blank, every week 1-17 is pulled and rewritten.
    out_dir:      root output folder; files go to {out_dir}/{year}/projections/
    keep_previous: if a week's file already exists, keep its values where the
             new pull has none (locks in pre-game projections). Set False to
             overwrite files with only the new pull.

    Returns the list of file paths written.
    """
    if current_week is not None and not 1 <= current_week <= LAST_WEEK:
        raise ValueError(f"current_week must be between 1 and {LAST_WEEK}")
    start = current_week if current_week is not None else 1
    weeks = range(start, LAST_WEEK + 1)
    folder = Path(out_dir) / str(year) / "projections"
    folder.mkdir(parents=True, exist_ok=True)
    names = None  # only downloaded if the records lack player names

    written, failed = [], []
    for wk in weeks:
        try:
            proj_raw = _fetch_by_position(PROJ_URL.format(year=year, week=wk), delay)
            try:
                stats_raw = _fetch_by_position(STATS_URL.format(year=year, week=wk), delay)
            except Exception as e:  # e.g. future week with no stats yet
                print(f"  no actual stats for week {wk} ({e}); pts_ppr will be null")
                stats_raw = []

            if names is None and _needs_directory(proj_raw + stats_raw):
                names = _load_player_names(Path(out_dir) / "sleeper_players.json")

            players = _build_players(proj_raw, stats_raw, names)
            path = folder / f"week_{wk:02d}.json"
            if keep_previous:
                players = _merge_previous(players, path)
            for p in players:
                if p["pts_ppr"] is None:
                    p["pts_ppr"] = 0.0
            players.sort(key=lambda p: (p["projection_ppr"] if p["projection_ppr"] is not None else -1,
                                        p["pts_ppr"] if p["pts_ppr"] is not None else -1),
                         reverse=True)

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


def debug_player(year, week, last_name, first_name=None, out_dir="Functions/APIData", delay=0.3):
    """
    Print the RAW projection and stats records Sleeper returns for one player,
    to see whether the endpoint omits him or returns him with empty stats.
        debug_player(2026, 4, "Barkley", "Saquon")
    """
    directory = _load_player_names(Path(out_dir) / "sleeper_players.json")
    matches = [(pid, i) for pid, i in directory.items()
               if (i.get("last_name") or "").lower() == last_name.lower()
               and (not first_name or (i.get("first_name") or "").lower() == first_name.lower())
               and i.get("team")]
    if not matches:
        print("no matching player in directory")
        return
    for pid, i in matches:
        pos = i.get("position")
        print(f"=== {i.get('first_name')} {i.get('last_name')} ({pos}, {i.get('team')}, id {pid})")
        for label, url in (("projections", PROJ_URL), ("stats", STATS_URL)):
            raw = _get(url.format(year=year, week=week),
                       {"season_type": "regular", "position[]": pos}) or []
            hits = [r for r in raw if _pid(r) == pid]
            print(f"--- {label}: " + (json.dumps(hits, indent=2) if hits
                                      else "NOT RETURNED by endpoint"))
            time.sleep(delay)


if __name__ == "__main__":
    get_projections(2026)