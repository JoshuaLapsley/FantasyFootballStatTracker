"""
Calculate each drafted player's PAR (Points Above Replacement) for a
season and write it to a JSON file. No API calls, no images.

Reads each drafted player's weekly points from the JSON produced by
GetDraftedPlayerWeeklyPoints.py instead of calling Yahoo, and uses the
Sleeper projections (via ProjectionTranslation.py) to decide whether a
player actually played.

Input (relative to this script):
    ../APIData/{year}/DraftedPlayerWeeklyPoints.json
        list of drafted players:
        {pick, round, team_key, team_name, manager_nickname, player_id,
         player_name, position, bye_week,
         weekly_points: [{week, points}, ...]}
        (only completed weeks are in this file)
    Sleeper projection files (read through ProjectionTranslation.py)

Output:
    ../Data/{year}/PAR.json

--------------------------------------------------------------------------
WHAT "PAR" MEANS HERE
--------------------------------------------------------------------------
Replacement level (per position, season-long flat baseline):
    QB = 15, RB = 5, WR = 7, TE = 6, K = 7, DEF = 5

For every completed week, every drafted player uses the same rule:
  * If the player played that week, they're credited their ACTUAL points,
    however low (including a real 0.0).
  * If the player did NOT play, they're credited replacement level instead.
  * A player's PAR for the season is the sum of
    (credited points - replacement level) across every week in the file.
    No week is ever skipped.

A player is treated as NOT having played when any of these is true:
  * it is their bye week
  * Yahoo returned no points for them that week
  * their Sleeper projected points (projection_ppr) are 0, null, or the
    player isn't found in that week's Sleeper projections

Usage:
    write_par(2026)
"""

import json
import os

from PythonData.APICallsAndStats.DataFunctions.ProjectionTranslation import load_sleeper_week, lookup_player


# If you run this as part of the PythonData package, use the full path instead:
# from PythonData.APICallsAndStats.ProjectionTranslation import lookup_player, load_sleeper_week

SCRIPT_DIR = os.path.dirname(os.path.abspath(__file__))

REPLACEMENT_LEVEL = {
    "QB": 15,
    "WR": 7,
    "RB": 5,
    "TE": 8,
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
# DID-NOT-PLAY CHECK
# --------------------------------------------------------------------------
def player_did_not_play(player_name, actual_points, bye_week, week, year):
    """
    True if the player should be treated as not having played this week:
    bye week, no actual points, or Sleeper projection is 0 / null / missing.
    """
    if bye_week is not None and bye_week == week:
        return True
    if actual_points is None:
        return True

    record = lookup_player(player_name, year, week)
    if record is None:
        return True
    return not record.get("projection_ppr")   # None or 0 -> did not play


# --------------------------------------------------------------------------
# PAR CALCULATION
# --------------------------------------------------------------------------
def calculate_par(year):
    """
    Returns (results, weeks_used).
    results is a list of per-player dicts sorted by PAR, descending.
    """
    board, actuals_by_week = load_drafted_players(year)

    weeks = sorted(actuals_by_week.keys())
    print(f"Completed weeks in weekly points file: {weeks or 'none yet'}")

    par_by_id = {p["player_id"]: 0.0 for p in board}

    for week in weeks:
        actuals = actuals_by_week[week]

        if load_sleeper_week(year, week) is None:
            print(f"  WARNING: no Sleeper projections file for week {week}; "
                  f"every player will be treated as did-not-play that week.")

        print(f"Processing week {week} (credit actual points if played, "
              f"replacement level if not)...")
        for p in board:
            pid = p["player_id"]
            replacement = REPLACEMENT_LEVEL.get(p["position"])
            if replacement is None:
                continue

            actual = actuals.get(pid)
            dnp = player_did_not_play(
                p["player_name"], actual, p["bye_week"], week, year
            )
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