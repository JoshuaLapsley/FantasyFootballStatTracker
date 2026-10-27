import json
import os
from pathlib import Path

# .../Functions/APIFunctions/ -> parents[1] = Functions -> .../Functions/APIData/{Year}
API_DATA_ROOT = Path(__file__).resolve().parents[1] / "APIData"

BATCH_SIZE = 25  # Yahoo caps how many players you can request at once
POINT_KEYS = ("total_points", "points", "fantasy_points")  # adjust after checking one raw entry

FINAL_WEEK = 17


def roster_points_filename(year, root=API_DATA_ROOT):
    return os.path.join(str(root), str(year), "RosterPoints.json")


def _extract_points(player_stats):
    for key in POINT_KEYS:
        if key in player_stats:
            try:
                return float(player_stats[key])
            except (TypeError, ValueError):
                return None
    return None


def _fetch_week_points(lg, player_ids, week):
    """Returns {player_id (str): points} for the given players and week."""
    points = {}
    ids = sorted(player_ids)

    for i in range(0, len(ids), BATCH_SIZE):
        batch = ids[i:i + BATCH_SIZE]
        try:
            stats = lg.player_stats([int(x) for x in batch], "week", week=int(week))
        except Exception as e:
            print(f"Warning: week {week} stats batch {i} failed: {e}")
            continue

        for s in stats:
            points[str(s.get("player_id"))] = _extract_points(s)

    return points


def write_roster_points_file(lg, year, root=API_DATA_ROOT, through_week=None):
    """Writes {week: {team_key: [{player_id, selected_position, points}, ...]}}.
    Resumes from an existing file and only fetches weeks that are missing.

    through_week: last week to fetch. Defaults to current_week - 1. For a finished
    season pass the final week, e.g. lg.end_week().
    """
    path = roster_points_filename(year, root)
    os.makedirs(os.path.dirname(path), exist_ok=True)

    data = {}
    if os.path.exists(path):
        with open(path, encoding="utf-8") as f:
            data = json.load(f)

    if through_week is None:
        current = lg.current_week()
        through_week = FINAL_WEEK if current == FINAL_WEEK else current - 1

    team_keys = list(lg.teams().keys())
    written = []

    for week in range(1, int(through_week) + 1):
        if str(week) in data:
            continue

        # 1) rosters for every team
        rosters = {}
        for team_key in team_keys:
            try:
                rosters[team_key] = lg.to_team(team_key).roster(week)
            except Exception as e:
                print(f"Warning: roster fetch failed for {team_key} week {week}: {e}")

        if len(rosters) != len(team_keys):
            print(f"[{year}] Week {week}: missing rosters, not saved (will retry next run).")
            continue

        # 2) points for every player who appeared on any roster
        all_ids = {str(p.get("player_id")) for roster in rosters.values() for p in roster}
        points = _fetch_week_points(lg, all_ids, week)

        if len(points) < len(all_ids):
            print(f"[{year}] Week {week}: points incomplete ({len(points)}/{len(all_ids)}), not saved.")
            continue

        # 3) merge
        week_data = {}
        for team_key, roster in rosters.items():
            week_data[team_key] = [
                {
                    "player_id": str(p.get("player_id")),
                    "selected_position": p.get("selected_position"),
                    "points": points.get(str(p.get("player_id"))),
                }
                for p in roster
            ]

        data[str(week)] = week_data
        written.append(week)
        with open(path, "w", encoding="utf-8") as f:  # save progress after every week
            json.dump(data, f, indent=2, ensure_ascii=False)

    print(f"[{year}] Roster-points weeks written: {written or 'none'}")
    return written