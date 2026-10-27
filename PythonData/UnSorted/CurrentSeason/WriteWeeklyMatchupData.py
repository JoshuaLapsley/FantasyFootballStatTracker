import glob
import json
import os


def week_filename(week, OUTPUT_DIR):
    return os.path.join(OUTPUT_DIR, f"Week{int(week):02d}.json")
 
 
def write_week_files(lg, OUTPUT_DIR):
    os.makedirs(OUTPUT_DIR, exist_ok=True)
 
    current_week = lg.current_week()
    written, skipped = [], []
 
    for week in range(1, current_week):
        path = week_filename(week, OUTPUT_DIR)
        if os.path.exists(path):
            skipped.append(week)
            continue
 
        raw = lg.matchups(week)
        matchups = parse_week_matchups(raw, week)
 
        with open(path, "w") as f:
            json.dump(matchups, f, indent=2)
        written.append(week)
 
    print(f"Weeks written: {written or 'none'}")
    print(f"Weeks already present, skipped: {skipped or 'none'}")
    return written

def parse_week_matchups(raw_json, week):
    """Turn the raw dict from lg.matchups(week) into a clean list of
    matchup dicts."""
    try:
        scoreboard = raw_json["fantasy_content"]["league"][1]["scoreboard"]
        sb_key = next(k for k in scoreboard.keys() if k.isdigit())
        matchups_raw = scoreboard[sb_key]["matchups"]
        count = int(matchups_raw["count"])
    except (KeyError, IndexError, StopIteration, TypeError) as e:
        raise RuntimeError(
            f"Unexpected Yahoo scoreboard JSON shape for week {week}: {e}"
        )
 
    matchups = []
    for i in range(count):
        matchup = matchups_raw[str(i)]["matchup"]
        is_playoffs = matchup.get("is_playoffs") == "1"
        is_consolation = matchup.get("is_consolation") == "1"
        status = matchup.get("status")
 
        teams_raw = matchup["0"]["teams"]
        team_count = int(teams_raw["count"])
        teams = [_extract_team(teams_raw[str(j)]["team"]) for j in range(team_count)]
 
        winner_team_key = None
        if len(teams) == 2 and all(t["points"] is not None for t in teams):
            if teams[0]["points"] > teams[1]["points"]:
                winner_team_key = teams[0]["team_key"]
            elif teams[1]["points"] > teams[0]["points"]:
                winner_team_key = teams[1]["team_key"]
            # equal points -> tie, winner_team_key stays None
 
        matchups.append({
            "week": int(week),
            "status": status,
            "is_playoffs": is_playoffs,
            "is_consolation": is_consolation,
            "teams": teams,
            "winner_team_key": winner_team_key,
        })
 
    return matchups

def _team_meta_field(meta_list, field):
    for item in meta_list:
        if isinstance(item, dict) and field in item:
            return item[field]
    return None
 
 
def _extract_team(team_raw):
    meta = team_raw[0]
    team_key = _team_meta_field(meta, "team_key")
    name = _team_meta_field(meta, "name")
 
    points = None
    projected_points = None
    for chunk in team_raw[1:]:
        if not isinstance(chunk, dict):
            continue
        if "team_points" in chunk:
            try:
                points = float(chunk["team_points"]["total"])
            except (KeyError, TypeError, ValueError):
                pass
        if "team_projected_points" in chunk:
            try:
                projected_points = float(chunk["team_projected_points"]["total"])
            except (KeyError, TypeError, ValueError):
                pass
 
    return {
        "team_key": team_key,
        "name": name,
        "points": points,
        "projected_points": projected_points,
    }