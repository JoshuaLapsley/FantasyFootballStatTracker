import json
import os
from pathlib import Path

# GetDraftData.py is at .../Functions/APIFunctions/
# parents[1] = Functions  ->  .../Functions/APIData/{Year}
API_DATA_ROOT = Path(__file__).resolve().parents[1] / "APIData"

PLAYER_BATCH_SIZE = 25  # Yahoo caps how many players you can request at once


def draft_dir(year, root=API_DATA_ROOT):
    return os.path.join(str(root), str(year))


def draft_filename(year, root=API_DATA_ROOT):
    return os.path.join(draft_dir(year, root), "DraftData.json")


def _extract_manager_nickname(team):
    """lg.teams() entries hold managers as [{'manager': {...}}, ...]."""
    managers = team.get("managers") or []
    if isinstance(managers, dict):
        managers = [managers]
    for m in managers:
        if isinstance(m, dict):
            manager = m.get("manager", m)
            nickname = manager.get("nickname")
            if nickname:
                return nickname
    return None


def _build_team_lookup(lg):
    """Returns {team_key: {"name": ..., "manager_nickname": ...}}."""
    lookup = {}
    for key, team in lg.teams().items():
        lookup[key] = {
            "name": team.get("name"),
            "manager_nickname": _extract_manager_nickname(team),
        }
    return lookup


def _extract_bye_week(player):
    bye = player.get("bye_weeks")
    if isinstance(bye, dict):
        bye = bye.get("week")
    try:
        return int(bye)
    except (TypeError, ValueError):
        return None


def _fetch_player_info(lg, player_ids):
    """Look up name/position/bye week for each drafted player id.
    Returns {player_id (str): {"name": ..., "position": ..., "bye_week": ...}}."""
    info = {}
    unique_ids = list(dict.fromkeys(player_ids))  # dedupe, keep order

    for i in range(0, len(unique_ids), PLAYER_BATCH_SIZE):
        batch = unique_ids[i:i + PLAYER_BATCH_SIZE]
        try:
            details = lg.player_details(batch)
        except Exception as e:
            print(f"Warning: player_details failed for batch starting at {i}: {e}")
            continue

        for p in details:
            pid = str(p.get("player_id"))
            name = p.get("name")
            if isinstance(name, dict):
                name = name.get("full")
            info[pid] = {
                "name": name,
                "position": p.get("display_position") or p.get("primary_position"),
                "bye_week": _extract_bye_week(p),
            }
    return info


def parse_draft_results(raw_picks, team_lookup, player_info):
    """Turn lg.draft_results() into a clean list of pick dicts."""
    picks = []
    for pick in raw_picks:
        team_key = pick.get("team_key")
        player_id = str(pick.get("player_id"))
        team = team_lookup.get(team_key, {})
        pinfo = player_info.get(player_id, {})
        picks.append({
            "pick": pick.get("pick"),
            "round": pick.get("round"),
            "team_key": team_key,
            "team_name": team.get("name"),
            "manager_nickname": team.get("manager_nickname"),
            "player_id": player_id,
            "player_name": pinfo.get("name"),
            "position": pinfo.get("position"),
            "bye_week": pinfo.get("bye_week"),
        })
    return picks


def write_draft_file(lg, year, root=API_DATA_ROOT, overwrite=False):
    path = draft_filename(year, root)
    if os.path.exists(path) and not overwrite:
        print(f"[{year}] Draft file already exists, skipped: {path}")
        return None

    os.makedirs(draft_dir(year, root), exist_ok=True)

    raw_picks = lg.draft_results()
    if not raw_picks:
        print(f"[{year}] No draft results returned (draft may not have happened yet).")
        return None

    team_lookup = _build_team_lookup(lg)
    player_info = _fetch_player_info(lg, [p.get("player_id") for p in raw_picks])
    picks = parse_draft_results(raw_picks, team_lookup, player_info)

    with open(path, "w") as f:
        json.dump(picks, f, indent=2)

    print(f"[{year}] Wrote {len(picks)} picks to {path}")
    return path