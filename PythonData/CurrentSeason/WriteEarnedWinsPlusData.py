"""
Calculate "Earned Wins Plus" (EW+), an upgraded version of the existing
Earned Wins (EW) stat (see WriteEarnedWinsData.py).

--------------------------------------------------------------------------
WHY EW+ EXISTS
--------------------------------------------------------------------------
Plain EW already fixes strength-of-schedule (a team's result depends on
how it did relative to the WHOLE league that week, not just its one
opponent), but it's purely rank-based: a team that finishes 2nd out of
14 by 0.1 points gets the exact same credit as a team that finishes 2nd
out of 14 by 60 points. Margin doesn't matter, only order does.

EW+ fixes that by replacing "rank that week" with the AVERAGE PAIRWISE
WIN PROBABILITY against every other team that week:

    EW+_week(team i) = mean over all other teams j of
                       Phi((score_i - score_j) / sigma)

where Phi is the standard normal CDF and sigma is this league's own
empirical standard deviation of a single team-week score (see below).
This literally answers "what fraction of the other teams would this
team's score have beaten, accounting for how close or blown-out those
results actually were" -- a 1-point win counts for barely more than a
coin flip against that opponent, a 60-point win counts as an almost-sure
win against that opponent, exactly as intuition suggests.

K/DEF POINTS ARE EXCLUDED
--------------------------------------------------------------------------
Per instruction, kicker and defense/special-teams scoring is excluded
from every team's weekly score before any of the above runs -- both
positions are high-variance/low-skill relative to the rest of a lineup
and mostly add noise rather than signal to who "should" have won a
week. This requires each team's actual weekly ROSTER (not just their
final Yahoo-reported team total), so this score can be recomputed as
sum(player.total_points for player in roster if player started AND
player.selected_position not in {"K", "DEF"}).

SIGMA (the margin standard deviation used in Phi)
--------------------------------------------------------------------------
sigma is fit empirically from this league's own real K/DEF-excluded
team-week scores, POOLED across the 2025 and 2026 seasons (both 14-team
seasons, unlike 2023/2024 which had fewer teams and would shift the
scoring distribution). 2025 comes from the already-cached
PythonData/team_rosters_weekly_stats_week_{1..13}/*.json roster+score
snapshots (14 teams x 13 weeks, already on disk, no API calls needed).
2026 comes from a live pull, same shape, for whatever weeks are already
final. sigma is computed once per run from that pooled sample (the
standard deviation of individual team-week scores, then multiplied by
sqrt(2) to get the standard deviation of the DIFFERENCE between two
independent such scores, matching the margin convention already used
by CalculateWAR.py's WAR formula and RunWeekly.py's game simulator).

SCOPE
--------------------------------------------------------------------------
EW+ is only OUTPUT for the current 2026 season (matching the scope of
WAR/PAR), using every week strictly before the league's current week --
no weeks are skipped. 2025 is only used as extra data to help calibrate
sigma, not as a season EW+ is computed/output for.

Output: EarnedWinsPlus.json, written next to EarnedWins.json (same
output_directory convention as WriteEarnedWinsData.py's
calculate_earned_wins()).
"""

import json
import os
from pathlib import Path

import numpy as np
from scipy.stats import norm

import yahoo_fantasy_api as yfa

SCRIPT_DIR = os.path.dirname(os.path.abspath(__file__))
PYTHON_DATA_DIR = Path(SCRIPT_DIR) / ".."

# 2025's already-pulled roster+score snapshots (14 teams x 13 weeks),
# used only to help calibrate sigma -- see module docstring.
HISTORICAL_ROSTER_DIRS_2025 = sorted(
    PYTHON_DATA_DIR.glob("team_rosters_weekly_stats_week_*")
)

# Yahoo's selected_position values that mean "did not start" this week.
NON_STARTER_SLOTS = {"BN", "IR", "IR+", "NA"}
# Slots excluded from every team's score for EW+ purposes.
KDEF_SLOTS = {"K", "DEF"}


# --------------------------------------------------------------------------
# K/DEF-EXCLUDED TEAM SCORE -- 2025 (from disk, already-cached rosters)
# --------------------------------------------------------------------------
def load_2025_team_week_scores() -> list:
    """
    Returns a flat list of K/DEF-excluded team-week total scores, one
    per (team, week) found in the cached 2025 roster snapshots. Used
    only to help calibrate sigma.

    Skips any file with an empty roster list -- a couple of these exist
    in the cache (e.g. team_rosters_weekly_stats_week_2's
    "Hunter's Hunters" file is `{"...": []}`), which look like a failed
    API pull when this data was originally collected, not a real
    all-bench/zero-point week. Including a fake 0.0 for those would
    contaminate the sigma estimate with a data-quality artifact rather
    than a real observation.
    """
    scores = []
    skipped = []
    for week_dir in HISTORICAL_ROSTER_DIRS_2025:
        for team_file in sorted(week_dir.glob("*.json")):
            with open(team_file, "r", encoding="utf-8") as f:
                data = json.load(f)
            # Single top-level key, e.g. "Deej-lanta Falcons_week_1_roster".
            roster = next(iter(data.values()))

            if not roster:
                skipped.append(team_file.name)
                continue

            total = 0.0
            for player in roster:
                selected_pos = player.get("selected_position")
                if selected_pos in NON_STARTER_SLOTS or selected_pos in KDEF_SLOTS:
                    continue
                try:
                    total += float(player["weekly_stats"]["total_points"])
                except (KeyError, TypeError, ValueError):
                    continue
            scores.append(total)

    if skipped:
        print(f"  Skipped {len(skipped)} 2025 roster file(s) with an empty roster "
              f"(likely a failed historical pull, not a real 0-point week): {skipped}")

    return scores


# --------------------------------------------------------------------------
# K/DEF-EXCLUDED TEAM SCORE -- 2026 (live pull)
# --------------------------------------------------------------------------
def fetch_2026_team_week_scores(league, weeks: list) -> dict:
    """
    Returns {week: {team_key: kdef_excluded_score}} for the given weeks,
    pulled live: each team's actual roster (for selected_position) plus
    a batched player_stats() call (for each starter's actual points).
    """
    teams_info = league.teams()
    team_keys = list(teams_info.keys())

    scores_by_week = {}
    for week in weeks:
        print(f"Fetching week {week} rosters (2026)...")
        week_scores = {}
        for team_key in team_keys:
            team = yfa.Team(league.sc, team_key)
            try:
                roster = team.roster(week=week)
            except Exception as e:
                print(f"  \u26a0 could not fetch roster for {team_key} (week {week}): {e}")
                continue

            starter_ids = [
                p["player_id"] for p in roster
                if p.get("selected_position") not in NON_STARTER_SLOTS
                and p.get("selected_position") not in KDEF_SLOTS
            ]
            if not starter_ids:
                week_scores[team_key] = 0.0
                continue

            actuals = {}
            batch_size = 25
            for i in range(0, len(starter_ids), batch_size):
                batch = [int(pid) for pid in starter_ids[i:i + batch_size]]
                stats = league.player_stats(batch, "week", week=week)
                for row in stats:
                    pid = str(row.get("player_id"))
                    try:
                        actuals[pid] = float(row.get("total_points", 0.0))
                    except (TypeError, ValueError):
                        actuals[pid] = 0.0

            week_scores[team_key] = sum(actuals.get(str(pid), 0.0) for pid in starter_ids)

        scores_by_week[week] = week_scores

    return scores_by_week


# --------------------------------------------------------------------------
# SIGMA CALIBRATION
# --------------------------------------------------------------------------
def calculate_sigma(scores_2026_by_week: dict) -> float:
    """
    Empirical standard deviation of a single team-week's K/DEF-excluded
    score, pooled across 2025 (cached) and 2026 (live, weeks so far),
    then converted to the standard deviation of the MARGIN between two
    independent such scores (multiply by sqrt(2)) -- this is what the
    Phi() win-probability formula actually needs.
    """
    pooled = load_2025_team_week_scores()
    for week_scores in scores_2026_by_week.values():
        pooled.extend(week_scores.values())

    pooled_arr = np.array(pooled, dtype=float)
    single_team_sigma = float(np.std(pooled_arr))
    margin_sigma = single_team_sigma * np.sqrt(2)

    print(f"\nSigma calibration: pooled {len(pooled_arr):,} team-week scores "
          f"(2025 cached + 2026 so far). "
          f"mean={pooled_arr.mean():.2f}  single-team sigma={single_team_sigma:.2f}  "
          f"margin sigma={margin_sigma:.2f}")

    return margin_sigma


# --------------------------------------------------------------------------
# EW+ CALCULATION (2026 only)
# --------------------------------------------------------------------------
def calculate_earned_wins_plus_for_week(week_scores: dict, margin_sigma: float) -> dict:
    """
    Returns {team_key: EW+_this_week} for a single week's K/DEF-excluded
    scores: for each team, the average pairwise win probability against
    every other team that played this week.
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


def determine_weeks_to_process(league) -> list:
    """Every week strictly before the league's current week."""
    return list(range(1, league.current_week()))


def calculate_earned_wins_plus(league) -> tuple:
    """
    Returns (results, weeks_used, margin_sigma).

    results: list of {"Team": name, "Earned Wins Plus": season_sum, ...}
    sorted by Earned Wins Plus descending, for the 2026 season only.
    """
    weeks = determine_weeks_to_process(league)
    print(f"Current week per Yahoo: {league.current_week()}. Weeks to process: {weeks or 'none yet'}")

    scores_2026_by_week = fetch_2026_team_week_scores(league, weeks)
    margin_sigma = calculate_sigma(scores_2026_by_week)

    teams_info = league.teams()
    season_totals = {tk: 0.0 for tk in teams_info}
    kdef_excluded_points_for = {tk: 0.0 for tk in teams_info}

    for week in weeks:
        week_scores = scores_2026_by_week.get(week, {})
        ew_plus_this_week = calculate_earned_wins_plus_for_week(week_scores, margin_sigma)
        for team_key, ew in ew_plus_this_week.items():
            season_totals[team_key] += ew
        for team_key, score in week_scores.items():
            kdef_excluded_points_for[team_key] += score

    results = []
    for team_key, info in teams_info.items():
        results.append({
            "Team": info.get("name", team_key),
            "Earned Wins Plus": round(season_totals.get(team_key, 0.0), 4),
            "Points For (K/DEF excluded)": round(kdef_excluded_points_for.get(team_key, 0.0), 2),
        })

    results.sort(key=lambda t: t["Earned Wins Plus"], reverse=True)
    for rank, team in enumerate(results, start=1):
        team["Earned Wins Plus Rank"] = rank

    return results, weeks, margin_sigma


def write_earned_wins_plus(league, output_directory) -> None:
    results, weeks_used, margin_sigma = calculate_earned_wins_plus(league)

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


def main():
    from yahoo_oauth import OAuth2

    sc = OAuth2(None, None, from_file='../oauth2.json')
    gm = yfa.Game(sc, 'nfl')
    YEAR_ID = '470.l.205662'  # Change this every year, matches RunWeekly.py
    league = gm.to_league(YEAR_ID)

    CURRENT_SEASON_DATA_DIR = os.path.normpath(os.path.join(
        SCRIPT_DIR, "..", "..", "Website", "girderma-gridiron-website",
        "src", "league_stats_output", "CurrentSeason"
    ))

    write_earned_wins_plus(league, output_directory=CURRENT_SEASON_DATA_DIR)


if __name__ == "__main__":
    main()
