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
    ../APIData/{year}/ZeroScoreReview.json   (optional, read/write)
        {week: {player_id: {"name", "position", "played": true/false}}}

Output:
    ../Data/{year}/WAR.json

--------------------------------------------------------------------------
WHAT "WAR" MEANS HERE
--------------------------------------------------------------------------
For a given player in a given week:

    P = credited points - position replacement level, where credited
        points = actual points if the player played, replacement level
        if they didn't (bye, no points returned, or a 0.0 that isn't
        confirmed as a real zero). No week is ever skipped.

    D = season-long average points scored by STARTERS at the player's
        position (selected_position not BN/IR/IR+/NA; FLEX "W/R/T"
        counts toward the player's own RB/WR/TE position). One value per
        position per run, applied to every week. Converted to
        D_relative = D - replacement so it is on the same
        points-above-replacement basis as P.

        A starter who did not play (bye, or a 0.0 not confirmed as a
        real zero in ZeroScoreReview.json) is left out of D, using the
        same rule as P. Set EXCLUDE_DNP_FROM_D = False to count those
        0.0s in D instead.

    WAR_week = Phi((P - D_relative) / MARGIN_SIGMA)
             - Phi((-D_relative) / MARGIN_SIGMA)

Phi is the standard normal CDF and MARGIN_SIGMA (~33) is the league's
empirical standard deviation of the margin between two team scores
(single-team sigma 23.3 * sqrt(2)). A player's season WAR is the sum of
WAR_week across every week in DraftedPlayerWeeklyPoints.json.

ZeroScoreReview.json
    Every non-bye 0.0 is auto-logged with "played": false (same as the
    PAR script). To mark a player who genuinely played and scored a real
    0, flip that entry to true and re-run:
        {"<week>": {"<player_id>": {"played": true}}}

Usage:
    write_war(2026)
"""

import json
import os

import numpy as np
from scipy.stats import norm

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
# PER-WEEK CREDITED POINTS
# --------------------------------------------------------------------------
def par_for_week(week, board, actuals, review):
    """Returns {player_id: credited_points - replacement} for one week."""
    par = {}
    for p in board:
        pid = p["player_id"]
        replacement = REPLACEMENT_LEVEL.get(p["position"])
        if replacement is None:
            continue

        actual = actuals.get(pid)
        dnp = player_did_not_play(actual, p.get("bye_week"), week, pid, review)
        credited = replacement if dnp else actual
        par[pid] = credited - replacement
    return par


# --------------------------------------------------------------------------
# D: season-long starter average per position
# --------------------------------------------------------------------------
def calculate_position_averages(board, starters_by_week, actuals_by_week, review):
    position_by_id = {p["player_id"]: p["position"] for p in board}
    bye_by_id = {p["player_id"]: p.get("bye_week") for p in board}

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
                    actual, bye_by_id.get(pid), week, pid, review):
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
    review = load_zero_score_review(year)

    weeks = sorted(actuals_by_week.keys())
    print(f"Completed weeks in weekly points file: {weeks or 'none yet'}")

    # Log this week's zero-scorers before anything reads the review.
    for week in weeks:
        review = auto_flag_zero_scores(year, week, board, actuals_by_week[week], review)

    position_averages = calculate_position_averages(
        board, starters_by_week, actuals_by_week, review
    )
    print(f"Season-long starter averages (D, raw points): "
          f"{ {pos: round(d, 2) for pos, d in position_averages.items()} }")

    d_relative_by_pos = {
        pos: d - REPLACEMENT_LEVEL[pos]
        for pos, d in position_averages.items()
    }

    war_by_id = {p["player_id"]: 0.0 for p in board}
    for week in weeks:
        par_this_week = par_for_week(week, board, actuals_by_week[week], review)
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