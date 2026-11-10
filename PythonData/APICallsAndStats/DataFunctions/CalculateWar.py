"""
Calculate each drafted player's WAR (Wins Above Replacement) for a season
and write it to a JSON file. No API calls, no images.

Input (relative to this script):
    ../APIData/{year}/DraftedPlayerWeeklyPoints.json
        list of drafted players:
        {pick, round, team_key, team_name, player_id, player_name,
         position, bye_week, weekly_points: [{week, points}, ...]}
        Source of every drafted player's actual points (only completed
        weeks are in this file, so those are the weeks WAR uses).
    ../APIData/{year}/RosterPoints.json
        {week: {team_key: [{player_id, selected_position, points}, ...]}}
        Only used to learn who was in a starting lineup each week (for D).
    Sleeper projection files (read through ProjectionTranslation.py)
        Used to decide whether a player actually played.

Output:
    ../Data/{year}/WAR.json

--------------------------------------------------------------------------
WHAT "WAR" MEANS HERE
--------------------------------------------------------------------------
For a given player in a given week:

    P = credited points - position replacement level, where credited
        points = actual points if the player played, replacement level
        if they didn't. No week is ever skipped.

    D = season-long average points scored by STARTERS at the player's
        position (selected_position not BN/IR/IR+/NA; FLEX "W/R/T"
        counts toward the player's own RB/WR/TE position). One value per
        position per run, applied to every week. Converted to
        D_relative = D - replacement so it is on the same
        points-above-replacement basis as P.

        A starter who did not play is left out of D, using the same rule
        as P. Set EXCLUDE_DNP_FROM_D = False to count those weeks in D
        at their actual points instead.

    WAR_week = Phi((P - D_relative) / MARGIN_SIGMA)
             - Phi((-D_relative) / MARGIN_SIGMA)

Phi is the standard normal CDF and MARGIN_SIGMA (~33) is the league's
empirical standard deviation of the margin between two team scores
(single-team sigma 23.3 * sqrt(2)). A player's season WAR is the sum of
WAR_week across every week in DraftedPlayerWeeklyPoints.json.

DID-NOT-PLAY RULE
    A player is treated as NOT having played when any of these is true:
      * it is their bye week
      * Yahoo returned no points for them that week
      * their Sleeper projected points (projection_ppr) are 0, null, or
        the player isn't found in that week's Sleeper projections

Usage:
    write_war(2026)
"""

import json
import os

import numpy as np
from scipy.stats import norm

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

# selected_position values that mean "did not start" this week.
NON_STARTER_SLOTS = {"BN", "IR", "IR+", "NA"}

# Leave starters who didn't play (per the DNP rule) out of D.
EXCLUDE_DNP_FROM_D = True

GAME_SIGMA = 23.3
MARGIN_SIGMA = GAME_SIGMA * np.sqrt(2)


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


def load_starters_by_week(year):
    """Returns {week (int): set(player_id)} of everyone in a starting slot."""
    path = os.path.join(_year_dir(year), "RosterPoints.json")
    if not os.path.isfile(path):
        raise FileNotFoundError(f"Roster data not found: {path}")

    with open(path, "r", encoding="utf-8") as f:
        rosters_by_week = json.load(f)

    starters_by_week = {}
    for week_key, teams in rosters_by_week.items():
        starters = set()
        for team_key, roster in teams.items():
            for player in roster:
                if player.get("selected_position") not in NON_STARTER_SLOTS:
                    starters.add(str(player.get("player_id")))
        starters_by_week[int(week_key)] = starters
    return starters_by_week


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
# PER-WEEK CREDITED POINTS
# --------------------------------------------------------------------------
def par_for_week(week, board, actuals, year):
    """Returns {player_id: credited_points - replacement} for one week."""
    par = {}
    for p in board:
        pid = p["player_id"]
        replacement = REPLACEMENT_LEVEL.get(p["position"])
        if replacement is None:
            continue

        actual = actuals.get(pid)
        dnp = player_did_not_play(
            p["player_name"], actual, p.get("bye_week"), week, year
        )
        credited = replacement if dnp else actual
        par[pid] = credited - replacement
    return par


# --------------------------------------------------------------------------
# D: season-long starter average per position
# --------------------------------------------------------------------------
def calculate_position_averages(board, starters_by_week, actuals_by_week, year):
    position_by_id = {p["player_id"]: p["position"] for p in board}
    bye_by_id = {p["player_id"]: p.get("bye_week") for p in board}
    name_by_id = {p["player_id"]: p["player_name"] for p in board}

    totals = {}
    counts = {}
    excluded = 0

    for week, actuals in actuals_by_week.items():
        for pid in starters_by_week.get(week, ()):
            pos = position_by_id.get(pid)
            if pos not in REPLACEMENT_LEVEL:
                continue
            actual = actuals.get(pid)
            if actual is None:
                continue
            if EXCLUDE_DNP_FROM_D and player_did_not_play(
                    name_by_id[pid], actual, bye_by_id.get(pid), week, year):
                excluded += 1
                continue
            totals[pos] = totals.get(pos, 0.0) + actual
            counts[pos] = counts.get(pos, 0) + 1

    if excluded:
        print(f"Left {excluded} did-not-play starter-week(s) out of D.")

    return {pos: totals[pos] / counts[pos] for pos in totals if counts.get(pos)}


# --------------------------------------------------------------------------
# WAR CALCULATION
# --------------------------------------------------------------------------
def win_probability_added(p, d_relative):
    return norm.cdf((p - d_relative) / MARGIN_SIGMA) - norm.cdf((-d_relative) / MARGIN_SIGMA)


def calculate_war(year):
    """
    Returns (results, weeks_used, position_averages).
    results is a list of per-player dicts sorted by WAR, descending.
    """
    board, actuals_by_week = load_drafted_players(year)
    starters_by_week = load_starters_by_week(year)

    weeks = sorted(actuals_by_week.keys())
    print(f"Completed weeks in weekly points file: {weeks or 'none yet'}")

    for week in weeks:
        if load_sleeper_week(year, week) is None:
            print(f"  WARNING: no Sleeper projections file for week {week}; "
                  f"every player will be treated as did-not-play that week.")

    position_averages = calculate_position_averages(
        board, starters_by_week, actuals_by_week, year
    )
    print(f"Season-long starter averages (D, raw points): "
          f"{ {pos: round(d, 2) for pos, d in position_averages.items()} }")

    d_relative_by_pos = {
        pos: d - REPLACEMENT_LEVEL[pos]
        for pos, d in position_averages.items()
    }

    war_by_id = {p["player_id"]: 0.0 for p in board}
    for week in weeks:
        par_this_week = par_for_week(week, board, actuals_by_week[week], year)
        for p in board:
            pid = p["player_id"]
            d_relative = d_relative_by_pos.get(p["position"])
            if d_relative is None:
                continue
            par = par_this_week.get(pid)
            if par is None:
                continue
            war_by_id[pid] += win_probability_added(par, d_relative)

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
            "WAR": round(war_by_id[pid], 4) + 0.0,  # + 0.0 turns -0.0 into 0.0
        })

    results.sort(key=lambda r: r["WAR"], reverse=True)
    for rank, row in enumerate(results, start=1):
        row["WAR Rank"] = rank

    return results, weeks, position_averages


def write_war(year):
    results, weeks_used, _ = calculate_war(year)

    output_directory = os.path.join(SCRIPT_DIR, "..", "Data", str(year))
    os.makedirs(output_directory, exist_ok=True)
    output_path = os.path.join(output_directory, "WAR.json")

    with open(output_path, "w", encoding="utf-8") as f:
        json.dump(results, f, indent=4)

    print(f"Weeks included: {weeks_used}")
    print(f"Created: {output_path}")


if __name__ == "__main__":
    write_war(2026)