"""
Calculate each drafted player's PAR (Points Above Replacement) for a
season and write it to a JSON file. No API calls, no images.

Uses the exact same PAR rules as run_draft_par() in RunWeekly.py, but
reads each drafted player's weekly points from the JSON produced by
GetDraftedPlayerWeeklyPoints.py instead of calling Yahoo.

Input (relative to this script):
    ../APIData/{year}/DraftedPlayerWeeklyPoints.json
        list of drafted players:
        {pick, round, team_key, team_name, manager_nickname, player_id,
         player_name, position, bye_week,
         weekly_points: [{week, points}, ...]}
        (only completed weeks are in this file)
    ../APIData/{year}/ZeroScoreReview.json   (optional, read/write)
        {week: {player_id: {"name", "position", "played": true/false}}}

Output:
    ../Data/{year}/PAR.json

--------------------------------------------------------------------------
WHAT "PAR" MEANS HERE
--------------------------------------------------------------------------
Replacement level (per position, season-long flat baseline):
    QB = 15, RB = 5, WR = 7, TE = 6, K = 7, DEF = 5

For every completed week, every drafted player uses the same ungated rule:
  * If the player played that week, they're credited their ACTUAL points,
    however low.
  * If the player did NOT play (bye week, no points returned, or an exact
    0.0 that isn't confirmed as a real zero), they're credited
    replacement level instead.
  * A player's PAR for the season is the sum of
    (credited points - replacement level) across every week in the file.
    No week is ever skipped.

An exact 0.0 defaults to "did not play". Every non-bye 0.0 is auto-logged
in ZeroScoreReview.json with "played": false. To mark a player who
genuinely played and scored a real 0, flip that entry to true:
    {"<week>": {"<player_id>": {"played": true}}}
and re-run.

Usage:
    write_par(2026)
"""

import json
import os

SCRIPT_DIR = os.path.dirname(os.path.abspath(__file__))

REPLACEMENT_LEVEL = {
    "QB": 15,
    "WR": 7,
    "RB": 5,
    "TE": 6,
    "K": 7,
    "DEF": 5,
}

POSITION_ALIASES = {"DST": "DEF"}


def _year_dir(year):
    return os.path.join(SCRIPT_DIR, "..", "APIData", str(year))


# --------------------------------------------------------------------------
# LOAD DATA FROM DISK
# --------------------------------------------------------------------------
def load_drafted_players(year):
    """
    Returns (board, actuals_by_week).

    board: list of picks sorted by pick number.
    actuals_by_week: {week (int): {player_id (str): points or None}}
    """
    path = os.path.join(_year_dir(year), "DraftedPlayerWeeklyPoints.json")
    if not os.path.isfile(path):
        raise FileNotFoundError(
            f"Weekly points not found: {path}. "
            f"Run GetDraftedPlayerWeeklyPoints.py for {year} first."
        )

    with open(path, "r", encoding="utf-8") as f:
        players = json.load(f)

    board = []
    actuals_by_week = {}
    for p in players:
        pid = str(p.get("player_id"))
        position = POSITION_ALIASES.get(p.get("position"), p.get("position"))

        board.append({
            "pick": p.get("pick"),
            "round": p.get("round"),
            "team_key": p.get("team_key"),
            "team_name": p.get("team_name"),
            "manager_nickname": p.get("manager_nickname"),
            "player_id": pid,
            "player_name": p.get("player_name"),
            "position": position,
            "bye_week": p.get("bye_week"),
        })

        for entry in p.get("weekly_points") or []:
            week = int(entry["week"])
            actuals_by_week.setdefault(week, {})[pid] = entry.get("points")

    board.sort(key=lambda p: p["pick"])
    return board, actuals_by_week


# --------------------------------------------------------------------------
# ZERO-SCORE MANUAL REVIEW LOG
# --------------------------------------------------------------------------
def _review_path(year):
    return os.path.join(_year_dir(year), "ZeroScoreReview.json")


def load_zero_score_review(year):
    path = _review_path(year)
    if os.path.isfile(path):
        with open(path, "r", encoding="utf-8") as f:
            return json.load(f)
    return {}


def save_zero_score_review(year, review):
    path = _review_path(year)
    os.makedirs(os.path.dirname(path), exist_ok=True)
    with open(path, "w", encoding="utf-8") as f:
        json.dump(review, f, indent=2)


def auto_flag_zero_scores(year, week, board, actuals, review):
    """
    Adds a default "played": false entry to the review log for every
    drafted player who scored exactly 0.0 this week (excluding a bye,
    which is unambiguous). Never touches an existing entry.
    """
    week_review = review.setdefault(str(week), {})
    added = []

    for p in board:
        pid = p["player_id"]
        if p["bye_week"] == week:
            continue
        if actuals.get(pid) != 0.0:
            continue
        if pid in week_review:
            continue

        week_review[pid] = {
            "name": p["player_name"],
            "position": p["position"],
            "played": False,
        }
        added.append(p["player_name"])

    if added:
        save_zero_score_review(year, review)
        print(f"  Auto-flagged {len(added)} zero-score player(s) for week {week} "
              f"review (default played=false): {added}")

    return review


def player_did_not_play(actual_points, bye_week, week, player_id, review):
    """Bye weeks and missing actuals are always DNP; an exact 0.0 defaults
    to DNP unless the review log confirms the player genuinely played."""
    if bye_week is not None and bye_week == week:
        return True
    if actual_points is None:
        return True
    if actual_points != 0.0:
        return False

    entry = review.get(str(week), {}).get(player_id)
    if entry and entry.get("played") is True:
        return False
    return True


# --------------------------------------------------------------------------
# PAR CALCULATION
# --------------------------------------------------------------------------
def calculate_par(year):
    """
    Returns (results, weeks_used).
    results is a list of per-player dicts sorted by PAR, descending.
    """
    board, actuals_by_week = load_drafted_players(year)
    review = load_zero_score_review(year)

    weeks = sorted(actuals_by_week.keys())
    print(f"Completed weeks in weekly points file: {weeks or 'none yet'}")

    par_by_id = {p["player_id"]: 0.0 for p in board}

    for week in weeks:
        actuals = actuals_by_week[week]
        review = auto_flag_zero_scores(year, week, board, actuals, review)

        print(f"Processing week {week} (ungated rule: credit actual points "
              f"if played, replacement level if not)...")
        for p in board:
            pid = p["player_id"]
            replacement = REPLACEMENT_LEVEL.get(p["position"])
            if replacement is None:
                continue

            actual = actuals.get(pid)
            dnp = player_did_not_play(actual, p["bye_week"], week, pid, review)
            credited = replacement if dnp else actual
            par_by_id[pid] += credited - replacement

    results = []
    for p in board:
        pid = p["player_id"]
        results.append({
            "Player": p["player_name"],
            "Player ID": pid,
            "Position": p["position"],
            "Pick": p["pick"],
            "Round": p["round"],
            "Drafted By": p.get("team_name") or p["team_key"],
            "PAR": round(par_by_id[pid], 2) + 0.0,  # + 0.0 turns -0.0 into 0.0
        })

    results.sort(key=lambda r: r["PAR"], reverse=True)
    for rank, row in enumerate(results, start=1):
        row["PAR Rank"] = rank

    return results, weeks


def write_par(year):
    results, weeks_used = calculate_par(year)

    output_directory = os.path.join(SCRIPT_DIR, "..", "Data", str(year))
    os.makedirs(output_directory, exist_ok=True)
    output_path = os.path.join(output_directory, "PAR.json")

    with open(output_path, "w", encoding="utf-8") as f:
        json.dump(results, f, indent=4)

    print(f"Weeks included: {weeks_used}")
    print(f"Created: {output_path}")


if __name__ == "__main__":
    write_par(2026)