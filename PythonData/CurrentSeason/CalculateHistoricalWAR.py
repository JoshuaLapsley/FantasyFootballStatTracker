"""
Calculate each drafted player's standardized WAR (Wins Above
Replacement) stat for one or more COMPLETED past seasons (2023/2024/
2025 by default), using the exact same formula as CalculateWAR.py
(the live/current-season version) -- see that file's module docstring
for the full WAR derivation. This script exists only to backfill
historical pick-slot vs. WAR data (there's no need to re-derive the
formula here, just to run it against old league objects).

WHY THIS SCRIPT IS SEPARATE FROM CalculateWAR.py
--------------------------------------------------------------------------
CalculateWAR.py is wired for the live, in-progress 2026 league: it uses
`league.current_week()` to decide which weeks are "final" (everything
strictly before the current week), and hardcodes a single league_id/
WAR_YEAR pair. Neither of those is right for a season that already
ended:
  - `current_week()` on a completed Yahoo league does not reliably mean
    "the season's last week" (behavior is unconfirmed and risky to
    depend on) -- so this script instead reads the regular season's
    actual last week from `league.settings()["playoff_start_week"]`
    (same convention already used by pull_schedule.py / pull_projections
    .py's `get_regular_season_weeks`), and processes every regular
    season week, including the playoffs' lead-up week.
  - Each Yahoo season is a genuinely distinct league object with its
    own league_id (Yahoo does not let you pass a `year=` param to an
    existing league_id to get an old season) -- so this script loops
    over a YEAR -> league_id map (reusing the same ids already recorded
    in simulate_season.py's LEAGUE_IDS) and authenticates fresh for
    each one.

WHAT GETS WRITTEN (per year, all under PythonData/draftData/):
  draft_{YEAR}.json        enriched draft board cache (same shape as
                            CalculateWAR.py's live cache -- reused as-is
                            if it already exists for that year)
  par_zero_score_review_{YEAR}.json
                            manual "did they actually play?" log for
                            exact-0.0 scores (same semantics as the live
                            script). No historical season has had this
                            manually reviewed yet, so by default every
                            flagged 0.0 resolves to "did not play"
                            (replacement level) -- the same safe
                            fallback the live script already uses for
                            un-reviewed entries. Edit this file by hand
                            afterwards (set "played": true) for any
                            player you know genuinely scored a real 0.
  war_{YEAR}.json           the actual output this script exists to
                            produce: one row per drafted player with
                            {pick, round, player_id, player_name,
                            position, war}, sorted by pick -- this is
                            the pick-slot-vs-WAR dataset the isotonic
                            regression script consumes.

Usage:
    python3 CalculateHistoricalWAR.py                  # runs 2023-2025
    python3 CalculateHistoricalWAR.py --years 2023 2024
    python3 CalculateHistoricalWAR.py --years 2025 --force-refresh-draft
"""

import argparse
import json
import os
from pathlib import Path

import numpy as np
from scipy.stats import norm

from yahoo_oauth import OAuth2
import yahoo_fantasy_api as yfa

# Reuse the exact same formula constants as the live script, so
# historical and current-season WAR stay on an identical scale.
from CalculateWAR import (
    REPLACEMENT_LEVEL,
    POSITION_ALIASES,
    NON_STARTER_SLOTS,
    MARGIN_SIGMA,
    load_zero_score_review as _load_zero_score_review_at_path,
    save_zero_score_review as _save_zero_score_review_at_path,
    auto_flag_zero_scores,
    player_did_not_play,
    credited_points_for_week,
    calculate_position_averages,
    win_probability_added,
)


# --------------------------------------------------------------------------
# YEAR -> LEAGUE ID (same ids already recorded in simulate_season.py)
# --------------------------------------------------------------------------
LEAGUE_IDS = {
    2023: "423.l.902802",
    2024: "449.l.106896",
    2025: "461.l.111150",
    2026: "470.l.205662",
}

DEFAULT_YEARS = [2023, 2024, 2025]

SCRIPT_DIR = os.path.dirname(os.path.abspath(__file__))
PYTHON_DATA_DIR = Path(SCRIPT_DIR) / ".."
DRAFT_DATA_DIR = PYTHON_DATA_DIR / "draftData"
OAUTH_FILE = str(PYTHON_DATA_DIR / "oauth2.json")


def draft_cache_path(year: int) -> Path:
    return DRAFT_DATA_DIR / f"draft_{year}.json"


def zero_score_review_path(year: int) -> Path:
    return DRAFT_DATA_DIR / f"par_zero_score_review_{year}.json"


def war_output_path(year: int) -> Path:
    return DRAFT_DATA_DIR / f"war_{year}.json"


# --------------------------------------------------------------------------
# AUTH
# --------------------------------------------------------------------------
def get_league(year: int):
    league_id = LEAGUE_IDS.get(year)
    if not league_id:
        raise ValueError(
            f"No Yahoo league id configured for {year}. "
            f"Add it to LEAGUE_IDS at the top of this script."
        )
    sc = OAuth2(None, None, from_file=OAUTH_FILE)
    gm = yfa.Game(sc, "nfl")
    league = gm.to_league(league_id)
    return league


# --------------------------------------------------------------------------
# DRAFT BOARD (same enrichment as CalculateWAR.py's load_draft_board,
# just parameterized by year/cache-path instead of a module constant)
# --------------------------------------------------------------------------
def load_draft_board(league, year: int, force_refresh: bool = False) -> list:
    cache_path = draft_cache_path(year)
    if cache_path.exists() and not force_refresh:
        with open(cache_path, "r") as f:
            return json.load(f)

    print(f"[{year}] Pulling draft results from Yahoo...")
    draft_results = league.draft_results()
    teams = league.teams()

    player_ids = [pick["player_id"] for pick in draft_results if pick.get("player_id")]
    details_list = league.player_details(player_ids)
    details_by_id = {str(d.get("player_id")): d for d in details_list}

    board = []
    for pick in sorted(draft_results, key=lambda p: p["pick"]):
        pid = str(pick.get("player_id"))
        detail = details_by_id.get(pid, {})

        team_key = pick.get("team_key")
        team_info = teams.get(team_key, {})
        team_name = team_info.get("name", team_key)
        managers = team_info.get("managers", [])
        manager_nickname = None
        if managers:
            manager_nickname = managers[0].get("manager", {}).get("nickname")

        position = detail.get("display_position") or detail.get("primary_position")
        position = POSITION_ALIASES.get(position, position)

        name = detail.get("name", {})
        player_name = name.get("full") if isinstance(name, dict) else name

        bye_week = None
        bye_info = detail.get("bye_weeks")
        if isinstance(bye_info, dict) and bye_info.get("week"):
            try:
                bye_week = int(bye_info["week"])
            except (TypeError, ValueError):
                bye_week = None

        board.append({
            "pick": pick.get("pick"),
            "round": pick.get("round"),
            "team_key": team_key,
            "team_name": team_name,
            "manager_nickname": manager_nickname,
            "player_id": pid,
            "player_name": player_name,
            "position": position,
            "bye_week": bye_week,
        })

    DRAFT_DATA_DIR.mkdir(parents=True, exist_ok=True)
    with open(cache_path, "w") as f:
        json.dump(board, f, indent=2)

    return board


# --------------------------------------------------------------------------
# REGULAR SEASON WEEK RANGE (completed-season-safe, unlike current_week())
# --------------------------------------------------------------------------
def determine_weeks_to_process(league) -> list:
    """
    Every regular season week, 1 through (playoff_start_week - 1).
    Deliberately does NOT use league.current_week() -- that call means
    "today's week" and is meant for in-progress seasons; for a
    completed past season we want every week that was actually played,
    which playoff_start_week gives us reliably (same convention as
    pull_schedule.py / pull_projections.py's get_regular_season_weeks).
    """
    settings = league.settings()
    playoff_start = int(settings.get("playoff_start_week", 15))
    return list(range(1, playoff_start))


# --------------------------------------------------------------------------
# ACTUAL STATS / STARTERS (identical logic to CalculateWAR.py, just
# taking a zero_score_review dict + path instead of touching the
# module-level ZERO_SCORE_REVIEW_PATH constant, since that constant is
# year-specific here)
# --------------------------------------------------------------------------
def fetch_actuals_for_week(league, player_ids, week: int) -> dict:
    actuals = {}
    batch_size = 25
    for i in range(0, len(player_ids), batch_size):
        batch = [int(pid) for pid in player_ids[i:i + batch_size]]
        stats = league.player_stats(batch, "week", week=week)
        for row in stats:
            pid = str(row.get("player_id"))
            try:
                pts = float(row.get("total_points", 0.0))
            except (TypeError, ValueError):
                pts = 0.0
            actuals[pid] = pts
    return actuals


def fetch_starters_for_week(league, week: int) -> set:
    starters = set()
    teams_info = league.teams()
    for team_key in teams_info:
        team = yfa.Team(league.sc, team_key)
        try:
            roster = team.roster(week=week)
        except Exception as e:
            print(f"  \u26a0 could not fetch roster for {team_key} (week {week}): {e}")
            continue
        for player in roster:
            selected_pos = player.get("selected_position")
            if selected_pos in NON_STARTER_SLOTS:
                continue
            pid = str(player.get("player_id"))
            starters.add(pid)
    return starters


# --------------------------------------------------------------------------
# WAR CALCULATION (same formula as CalculateWAR.calculate_war, just
# driven by this file's year-aware helpers above)
# --------------------------------------------------------------------------
def calculate_war_for_year(league, year: int, board: list) -> tuple:
    """Returns (war_by_id, weeks_used, position_averages)."""
    player_ids = [p["player_id"] for p in board]
    position_by_id = {p["player_id"]: p["position"] for p in board}

    review_path = zero_score_review_path(year)
    zero_score_review = {}
    if review_path.exists():
        with open(review_path, "r") as f:
            zero_score_review = json.load(f)

    weeks = determine_weeks_to_process(league)
    print(f"[{year}] Regular season weeks to process: {weeks}")

    par_by_id_by_week = {}
    starters_by_week = {}
    actuals_by_week = {}

    for week in weeks:
        print(f"[{year}] Fetching actuals + starters for week {week}...")
        actuals = fetch_actuals_for_week(league, player_ids, week)
        actuals_by_week[week] = actuals

        week_key = str(week)
        week_review = zero_score_review.setdefault(week_key, {})
        added = []
        for p in board:
            pid = p["player_id"]
            if p["bye_week"] == week:
                continue
            actual = actuals.get(pid)
            if actual != 0.0:
                continue
            if pid in week_review:
                continue
            week_review[pid] = {"name": p["player_name"], "position": p["position"], "played": False}
            added.append(p["player_name"])
        if added:
            DRAFT_DATA_DIR.mkdir(parents=True, exist_ok=True)
            with open(review_path, "w") as f:
                json.dump(zero_score_review, f, indent=2)
            print(f"[{year}]   Auto-flagged {len(added)} zero-score player(s) for week {week} "
                  f"(default played=false): {added}")

        credited = credited_points_for_week(week, board, position_by_id, actuals, zero_score_review)
        par_this_week = {}
        for pid, credited_pts in credited.items():
            replacement = REPLACEMENT_LEVEL.get(position_by_id.get(pid))
            if replacement is None:
                continue
            par_this_week[pid] = credited_pts - replacement
        par_by_id_by_week[week] = par_this_week

        starters_by_week[week] = fetch_starters_for_week(league, week)

    position_averages = calculate_position_averages(board, weeks, starters_by_week, actuals_by_week)
    print(f"[{year}] D (raw points) by position: "
          f"{ {pos: round(d, 2) for pos, d in position_averages.items()} }")

    position_averages_relative = {
        pos: d - REPLACEMENT_LEVEL[pos]
        for pos, d in position_averages.items()
        if pos in REPLACEMENT_LEVEL
    }

    war_by_id = {pid: 0.0 for pid in player_ids}
    for week in weeks:
        par_this_week = par_by_id_by_week.get(week, {})
        for pid in player_ids:
            pos = position_by_id.get(pid)
            if pos not in REPLACEMENT_LEVEL:
                continue
            d_relative = position_averages_relative.get(pos)
            if d_relative is None:
                continue
            p = par_this_week.get(pid)
            if p is None:
                continue
            war_by_id[pid] += win_probability_added(p, d_relative)

    return war_by_id, weeks, position_averages


# --------------------------------------------------------------------------
# OUTPUT
# --------------------------------------------------------------------------
def write_war_output(year: int, board: list, war_by_id: dict) -> None:
    rows = []
    for p in board:
        pid = p["player_id"]
        rows.append({
            "year": year,
            "pick": p["pick"],
            "round": p["round"],
            "player_id": pid,
            "player_name": p["player_name"],
            "position": p["position"],
            "war": war_by_id.get(pid, 0.0),
        })
    rows.sort(key=lambda r: r["pick"])

    out_path = war_output_path(year)
    DRAFT_DATA_DIR.mkdir(parents=True, exist_ok=True)
    with open(out_path, "w") as f:
        json.dump(rows, f, indent=2)
    print(f"[{year}] Saved -> {out_path} ({len(rows)} players)")


def run_year(year: int, force_refresh_draft: bool = False) -> None:
    print(f"\n{'=' * 72}\n{year} SEASON\n{'=' * 72}")
    league = get_league(year)
    board = load_draft_board(league, year, force_refresh=force_refresh_draft)
    war_by_id, weeks_used, position_averages = calculate_war_for_year(league, year, board)
    write_war_output(year, board, war_by_id)


def main():
    parser = argparse.ArgumentParser(description="Backfill historical WAR for past seasons.")
    parser.add_argument("--years", type=int, nargs="+", default=DEFAULT_YEARS,
                         help=f"Seasons to process (default: {DEFAULT_YEARS})")
    parser.add_argument("--force-refresh-draft", action="store_true",
                         help="Re-pull draft results/enrichment from Yahoo even if a "
                              "draft_{YEAR}.json cache already exists.")
    args = parser.parse_args()

    for year in args.years:
        run_year(year, force_refresh_draft=args.force_refresh_draft)


if __name__ == "__main__":
    main()
