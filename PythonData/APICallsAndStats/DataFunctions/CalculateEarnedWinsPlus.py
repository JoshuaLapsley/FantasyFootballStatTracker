"""
Calculate "Earned Wins Plus" (EW+), an upgraded version of Earned Wins (EW).

EW+_week(team i) = mean over all other teams j of
                   Phi((score_i - score_j) / sigma)

where Phi is the standard normal CDF and sigma is the standard deviation
of the margin between two team-week scores, fit empirically from this
year's K/DEF-excluded team-week scores (std of a single team-week
score * sqrt(2)).

K/DEF points are excluded from every team's weekly score. Scores are
rebuilt from each team's weekly roster: the sum of points for every
player whose selected_position is not a bench/IR/NA slot and not K/DEF.

Input (relative to this script):
    ../APIData/{year}/RosterPoints.json
        {week: {team_key: [{player_id, selected_position, points}, ...]}}
    ../APIData/{year}/MatchupData/*.json  (only used for team names)

Output:
    ../Data/{year}/EarnedWinsPlus.json

Usage:
    write_earned_wins_plus(2026)
"""

import json
import os

import numpy as np
from scipy.stats import norm

SCRIPT_DIR = os.path.dirname(os.path.abspath(__file__))

# selected_position values that mean "did not start" this week.
NON_STARTER_SLOTS = {"BN", "IR", "IR+", "NA"}
# Slots excluded from every team's score for EW+ purposes.
KDEF_SLOTS = {"K", "DEF"}


def _year_dir(year):
    return os.path.join(SCRIPT_DIR, "..", "APIData", str(year))


# --------------------------------------------------------------------------
# K/DEF-EXCLUDED TEAM SCORES (from disk)
# --------------------------------------------------------------------------
def load_team_week_scores(year):
    """
    Returns {week: {team_key: kdef_excluded_score}} (week is an int) from
    ../APIData/{year}/RosterPoints.json.

    Teams with an empty roster list are skipped: that looks like a failed
    pull, not a real all-bench/zero-point week, and a fake 0.0 would
    contaminate both sigma and the EW+ totals.
    """
    roster_path = os.path.join(_year_dir(year), "RosterPoints.json")
    if not os.path.isfile(roster_path):
        raise FileNotFoundError(f"Roster data not found: {roster_path}")

    with open(roster_path, "r", encoding="utf-8") as f:
        rosters_by_week = json.load(f)

    scores_by_week = {}
    skipped = []

    for week_key in sorted(rosters_by_week, key=int):
        week = int(week_key)
        week_scores = {}

        for team_key, roster in rosters_by_week[week_key].items():
            if not roster:
                skipped.append(f"week {week}: {team_key}")
                continue

            total = 0.0
            for player in roster:
                slot = player.get("selected_position")
                if slot in NON_STARTER_SLOTS or slot in KDEF_SLOTS:
                    continue
                try:
                    total += float(player["points"])
                except (KeyError, TypeError, ValueError):
                    continue
            week_scores[team_key] = total

        scores_by_week[week] = week_scores

    if skipped:
        print(f"  Skipped {len(skipped)} empty roster(s) for {year} "
              f"(likely failed pulls): {skipped}")

    return scores_by_week


def load_team_names(year):
    """Returns {team_key: name} from the matchup data (falls back to team_key)."""
    matchup_dir = os.path.join(_year_dir(year), "MatchupData")
    names = {}
    if not os.path.isdir(matchup_dir):
        return names

    for filename in sorted(os.listdir(matchup_dir)):
        if not filename.lower().endswith(".json"):
            continue
        with open(os.path.join(matchup_dir, filename), "r", encoding="utf-8") as f:
            matchups = json.load(f)
        for matchup in matchups:
            for team in matchup["teams"]:
                names[team["team_key"]] = team["name"]
    return names


# --------------------------------------------------------------------------
# SIGMA CALIBRATION
# --------------------------------------------------------------------------
def calculate_sigma(scores_by_week):
    """
    Std of a single team-week's K/DEF-excluded score for the year,
    converted to the std of the MARGIN between two independent such
    scores (times sqrt(2)).
    """
    pooled = []
    for week_scores in scores_by_week.values():
        pooled.extend(week_scores.values())

    pooled_arr = np.array(pooled, dtype=float)
    single_team_sigma = float(np.std(pooled_arr))
    margin_sigma = single_team_sigma * np.sqrt(2)

    print(f"\nSigma calibration: {len(pooled_arr):,} team-week scores. "
          f"mean={pooled_arr.mean():.2f}  single-team sigma={single_team_sigma:.2f}  "
          f"margin sigma={margin_sigma:.2f}")

    return margin_sigma


# --------------------------------------------------------------------------
# EW+ CALCULATION
# --------------------------------------------------------------------------
def calculate_earned_wins_plus_for_week(week_scores, margin_sigma):
    """
    Returns {team_key: EW+_this_week}: each team's average pairwise win
    probability against every other team that week.
    """
    team_keys = list(week_scores.keys())
    ew_plus = {}
    for team_key in team_keys:
        score_i = week_scores[team_key]
        others = [week_scores[tk] for tk in team_keys if tk != team_key]
        if not others:
            ew_plus[team_key] = 0.0
            continue
        win_probs = [norm.cdf((score_i - score_j) / margin_sigma) for score_j in others]
        ew_plus[team_key] = float(np.mean(win_probs))
    return ew_plus


def calculate_earned_wins_plus(year):
    """
    Returns (results, weeks_used, margin_sigma) for the given year.
    results is sorted by Earned Wins Plus, descending.
    """
    scores_by_week = load_team_week_scores(year)
    names = load_team_names(year)
    margin_sigma = calculate_sigma(scores_by_week)

    season_totals = {}
    kdef_excluded_points_for = {}

    for week, week_scores in scores_by_week.items():
        ew_plus_this_week = calculate_earned_wins_plus_for_week(week_scores, margin_sigma)
        for team_key, ew in ew_plus_this_week.items():
            season_totals[team_key] = season_totals.get(team_key, 0.0) + ew
        for team_key, score in week_scores.items():
            kdef_excluded_points_for[team_key] = (
                kdef_excluded_points_for.get(team_key, 0.0) + score
            )

    results = []
    for team_key, total in season_totals.items():
        results.append({
            "Team": names.get(team_key, team_key),
            "Earned Wins Plus": round(total, 4),
            "Points For (K/DEF excluded)": round(kdef_excluded_points_for[team_key], 2),
        })

    results.sort(key=lambda t: t["Earned Wins Plus"], reverse=True)
    for rank, team in enumerate(results, start=1):
        team["Earned Wins Plus Rank"] = rank

    return results, list(scores_by_week.keys()), margin_sigma


def write_earned_wins_plus(year):
    results, weeks_used, margin_sigma = calculate_earned_wins_plus(year)

    output_directory = os.path.join(SCRIPT_DIR, "..", "Data", str(year))
    os.makedirs(output_directory, exist_ok=True)
    output_path = os.path.join(output_directory, "EarnedWinsPlus.json")

    with open(output_path, "w", encoding="utf-8") as f:
        json.dump(results, f, indent=4)

    print(f"\nWeeks included: {weeks_used}")
    print(f"Margin sigma used: {margin_sigma:.2f}")
    print(f"Created: {output_path}\n")
    for team in results:
        print(f"  #{team['Earned Wins Plus Rank']:>2}  {team['Team']:<28} "
              f"EW+ {team['Earned Wins Plus']:.4f}   "
              f"(K/DEF-excluded PF: {team['Points For (K/DEF excluded)']:.2f})")


if __name__ == "__main__":
    write_earned_wins_plus(2026)