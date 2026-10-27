import json
import os
from pathlib import Path

# Lives next to GetDraftData.py, so the same root applies:
# parents[1] = Functions  ->  .../Functions/APIData/{Year}
API_DATA_ROOT = Path(__file__).resolve().parents[1] / "APIData"

PLAYER_BATCH_SIZE = 25  # Yahoo caps how many players you can request at once


def year_dir(year, root=API_DATA_ROOT):
    return os.path.join(str(root), str(year))


def draft_filename(year, root=API_DATA_ROOT):
    return os.path.join(year_dir(year, root), "DraftData.json")


def weekly_points_filename(year, root=API_DATA_ROOT):
    return os.path.join(year_dir(year, root), "DraftedPlayerWeeklyPoints.json")


def load_draft_data(year, root=API_DATA_ROOT):
    path = draft_filename(year, root)
    if not os.path.exists(path):
        raise FileNotFoundError(
            f"{path} not found. Run the draft data script for {year} first."
        )
    with open(path) as f:
        return json.load(f)


def _to_float(value):
    """Yahoo returns '-' (or None) for bye weeks / no stats; map those to None."""
    try:
        return float(value)
    except (TypeError, ValueError):
        return None


def _last_week_to_fetch(lg):
    """Last COMPLETED week.
    Finished season: end_week. In-progress season: current_week - 1, since
    Yahoo's current_week is the week being played right now."""
    end = int(lg.end_week())
    try:
        settings = lg.settings()
        if str(settings.get("is_finished", 0)) == "1":
            return end
        current = int(settings.get("current_week") or lg.current_week())
    except Exception:
        try:
            current = int(lg.current_week())
        except Exception:
            return end
    return max(0, min(end, current - 1))


def _fetch_week_points(lg, player_ids, week):
    """Returns {player_id (str): points or None} for a single week."""
    points = {}
    for i in range(0, len(player_ids), PLAYER_BATCH_SIZE):
        batch = player_ids[i:i + PLAYER_BATCH_SIZE]
        try:
            stats = lg.player_stats(batch, "week", week=week)
        except Exception as e:
            print(f"Warning: player_stats failed (week {week}, batch {i}): {e}")
            continue

        for p in stats:
            pid = str(p.get("player_id"))
            points[pid] = _to_float(p.get("total_points"))
    return points


def build_weekly_points(lg, draft_picks):
    """Builds one entry per drafted player with a list of weekly points."""
    player_ids = list(dict.fromkeys(str(p["player_id"]) for p in draft_picks))
    last_week = _last_week_to_fetch(lg)
    print(str(last_week) + "BUM")
    print(f"  Completed weeks to fetch: 1-{last_week}" if last_week else
          "  No completed weeks yet.")

    # {week: {player_id: points}}
    by_week = {}
    for week in range(1, last_week + 1):
        print(f"  Fetching week {week}/{last_week}...")
        by_week[week] = _fetch_week_points(lg, player_ids, week)

    results = []
    for pick in draft_picks:
        pid = str(pick["player_id"])
        weekly = [
            {"week": week, "points": by_week[week].get(pid)}
            for week in range(1, last_week + 1)
        ]
        total = round(sum(w["points"] for w in weekly if w["points"] is not None), 2)

        results.append({
            "pick": pick.get("pick"),
            "round": pick.get("round"),
            "team_key": pick.get("team_key"),
            "team_name": pick.get("team_name"),
            "manager_nickname": pick.get("manager_nickname"),
            "player_id": pid,
            "player_name": pick.get("player_name"),
            "position": pick.get("position"),
            "bye_week": pick.get("bye_week"),
            "total_points": total,
            "weekly_points": weekly,
        })
    return results


def write_weekly_points_file(lg, year, root=API_DATA_ROOT):
    path = weekly_points_filename(year, root)

    draft_picks = load_draft_data(year, root)
    if not draft_picks:
        print(f"[{year}] DraftData.json is empty, nothing to fetch.")
        return None

    os.makedirs(year_dir(year, root), exist_ok=True)

    results = build_weekly_points(lg, draft_picks)

    with open(path, "w") as f:
        json.dump(results, f, indent=2)

    print(f"[{year}] Wrote weekly points for {len(results)} players to {path}")
    return path