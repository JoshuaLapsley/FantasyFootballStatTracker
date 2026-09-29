"""
Calculate each drafted player's standardized WAR (Wins Above
Replacement) stat for the current (2026) season, and render a draft
board colored by season-sum WAR (same visual style as RunWeekly.py's
PAR draft board).

Standalone script -- takes a live `league` object (see main() at the
bottom for how it authenticates on its own), so it can be run directly:
    python3 CalculateWAR.py

--------------------------------------------------------------------------
WHAT "WAR" MEANS HERE
--------------------------------------------------------------------------
For a given player in a given week:

    P = that player's PAR contribution for the week, i.e. their
        credited points that week minus their position's replacement
        level. "Credited points" uses the same ungated rule as
        RunWeekly.py's PAR calculation, every week, no exceptions:
        credit actual points if they played, replacement level if they
        didn't (bye/inactive). No week is ever skipped.

        This used to be gated (week 3+) by comparing a scraped Yahoo-
        website pregame projection against replacement level, but that
        rule was removed after finding real cases where the scraped
        projection was erroneously 0.0 for a player who was clearly a
        legitimate starter and had a great week -- e.g. Brock Bowers
        scored 27.6 in week 3 but had a scraped projection of 0.0,
        which silently zeroed his entire week's PAR/WAR contribution
        under the old rule. The scraped projection data isn't reliable
        enough to safely gate a real outcome on.

    D = the season-long average points scored by STARTERS at that
        player's position, across every real Yahoo starting lineup so
        far this season (pulled live from each team's roster(week=N),
        using Yahoo's own `selected_position` to know who actually
        started). A player counts toward a position's D for a given
        week if their selected_position that week was anything other
        than BN/IR/IR+/NA -- this includes the FLEX slot ("W/R/T"),
        which counts toward whichever of RB/WR/TE that player actually
        plays, per the user's instruction.

        D is a single value per position, computed ONCE per run using
        every completed week's starters, and then applied uniformly
        to every week's WAR calculation -- including weeks that
        happened before D reached its current value. It is NOT
        recomputed week-by-week.

        IMPORTANT: D as described above is a RAW points-scored average,
        but P is already points-ABOVE-REPLACEMENT (credited -
        replacement). Since Phi((P-D)/sigma) subtracts them directly,
        D has to be put on the same points-above-replacement basis
        first: D_relative = D - REPLACEMENT_LEVEL[pos]. All uses of "D"
        inside the actual Phi formula below refer to this
        replacement-adjusted D_relative, not the raw D reported in
        print_draft_board()'s "D (season-long starter average)" line
        (which intentionally stays in raw points, since that's the more
        readable number to show).

WAR for a single week is:

    WAR_week = Phi((P - D_relative) / MARGIN_SIGMA) - Phi((-D_relative) / MARGIN_SIGMA)

where Phi is the standard normal CDF, D_relative = D - replacement (see
above), and MARGIN_SIGMA (~33) is this league's own empirical standard
deviation of the MARGIN between two teams' scores -- fit directly from
544 pooled real team-weeks across the 2023-2026 seasons (regular season
only, K/DEF included): each season's own single-team score sigma was
~23.3 (24.3/23.5/22.0/21.0 individually), and margin sigma =
single-team sigma * sqrt(2) ~= 33, matching almost exactly (empirical
pooled margin sigma = 32.98). See RunWeekly.py's SIM_VARIANCE (its
Monte Carlo season simulator), which uses the single-team version of
this same empirical fit (sigma=23.3, i.e. Normal(mu, sigma=23.3) per
team, so the DIFFERENCE of two such simulated scores also has a margin
sigma of ~33).

Phi((P-D_relative)/MARGIN_SIGMA) is the probability a game whose mean
margin is (P-D_relative) is won, and Phi(-D_relative/MARGIN_SIGMA) is
that same win probability if the player were replaced by a perfectly
average starter at their position (mean margin -D_relative, i.e. an
average starter's own points-above-replacement). WAR_week is therefore
the win probability ADDED by this player's actual week versus an
average starter.

A player's season WAR is the sum of WAR_week across every week
processed (every week strictly before the league's current week --
no weeks or players are ever skipped).

--------------------------------------------------------------------------
Files this script reads (all under PythonData/):
  draftData/draft_{YEAR}.json                cached draft board (delete to refresh)
  simulate_season/projections/week_{N}.json  scraped pregame projections (week 3+, optional)

Files this script reads:
  draftData/par_zero_score_review_{YEAR}.json  manual "did they actually play?" log
  (shared with RunWeekly.py's PAR calculation -- same DNP semantics)

Images this script writes (into Website/girderma-gridiron-website/src/histograms/):
  draft_board_by_war_{YEAR}.png            grid colored by season WAR: red
                                            gradient for positive WAR
                                            (darker = higher), blue
                                            gradient for negative WAR
                                            (darker = more negative)
  draft_board_by_war_{YEAR}_colorbar.png   legend strip for the gradient above
"""

import json
import os
from pathlib import Path

import numpy as np
from scipy.stats import norm

import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt

import yahoo_fantasy_api as yfa


# --------------------------------------------------------------------------
# CONSTANTS (mirrors RunWeekly.py's PAR section so the two stay consistent)
# --------------------------------------------------------------------------
WAR_YEAR = 2026

REPLACEMENT_LEVEL = {
    "QB": 15,
    "WR": 7,
    "RB": 5,
    "TE": 6,
    "K": 7,
    "DEF": 5,
}

# Yahoo labels the defense/special-teams slot "DEF" in this league's
# draft results, but player_details() sometimes reports display_position
# as "DEF" already -- this alias map is here in case that ever drifts.
POSITION_ALIASES = {"DST": "DEF"}

# Positions that can occupy the FLEX slot; a FLEX starter counts toward
# their own actual position's starter pool (for D), not a separate
# "FLEX" bucket.
FLEX_ELIGIBLE_POSITIONS = {"RB", "WR", "TE"}

# Yahoo's selected_position values that mean "did not start" this week.
NON_STARTER_SLOTS = {"BN", "IR", "IR+", "NA"}

# This league's own empirical single-team weekly-score standard
# deviation (see RunWeekly.py's SIM_VARIANCE = 23.3 ** 2, same fit).
# WAR uses sigma * sqrt(2), the standard deviation of the margin between
# two independent such scores (~33, matching this league's real margin
# variance almost exactly -- see module docstring for the fit details).
GAME_SIGMA = 23.3
MARGIN_SIGMA = GAME_SIGMA * np.sqrt(2)

# Same palette used by the website's own draft board / RunWeekly.py's PAR
# board, kept identical here for visual consistency.
DEFAULT_TEXT_COLOR = "#374151"

SCRIPT_DIR = os.path.dirname(os.path.abspath(__file__))
PYTHON_DATA_DIR = Path(SCRIPT_DIR) / ".."

DRAFT_CACHE_PATH = PYTHON_DATA_DIR / "draftData" / f"draft_{WAR_YEAR}.json"
ZERO_SCORE_REVIEW_PATH = PYTHON_DATA_DIR / "draftData" / f"par_zero_score_review_{WAR_YEAR}.json"

HISTOGRAMS_DIR = (
    Path(SCRIPT_DIR) / ".." / ".." / "Website" / "girderma-gridiron-website"
    / "src" / "histograms"
).resolve()
WAR_BOARD_IMAGE_PATH = HISTOGRAMS_DIR / f"draft_board_by_war_{WAR_YEAR}.png"


# --------------------------------------------------------------------------
# DRAFT DATA (same cache/shape as RunWeekly.py's load_draft_board)
# --------------------------------------------------------------------------
def load_draft_board(league) -> list:
    """
    Returns the season's draft in real pick order, each entry enriched
    with player name/position. Shares the same on-disk cache as
    RunWeekly.py's PAR step (draftData/draft_{YEAR}.json) -- if that
    cache already exists (which it will, once RunWeekly.py has been run
    at least once this season), it's reused as-is rather than re-pulled.
    """
    if DRAFT_CACHE_PATH.exists():
        with open(DRAFT_CACHE_PATH, "r") as f:
            return json.load(f)

    print(f"Pulling {WAR_YEAR} draft results from Yahoo...")
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

    DRAFT_CACHE_PATH.parent.mkdir(parents=True, exist_ok=True)
    with open(DRAFT_CACHE_PATH, "w") as f:
        json.dump(board, f, indent=2)

    return board


# --------------------------------------------------------------------------
# ACTUAL STATS
# --------------------------------------------------------------------------
def fetch_actuals_for_week(league, player_ids, week: int) -> dict:
    """Returns {player_id: actual_total_points} for a single week."""
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


# --------------------------------------------------------------------------
# ACTUAL STARTING LINEUPS (for D -- the season-long starter average)
# --------------------------------------------------------------------------
def fetch_starters_for_week(league, week: int) -> set:
    """
    Returns the set of player_ids that actually STARTED (any slot other
    than BN/IR/IR+/NA, including FLEX/"W/R/T") for some team, this week.

    Pulled live from each team's real roster via Yahoo's own
    selected_position -- this is deliberately the actual lineup a
    manager set, not an optimal/re-solved one (unlike
    simulate_season/calculate_lineups.py).
    """
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
# ZERO-SCORE MANUAL REVIEW LOG (shared with PAR)
# --------------------------------------------------------------------------
def load_zero_score_review() -> dict:
    if ZERO_SCORE_REVIEW_PATH.exists():
        with open(ZERO_SCORE_REVIEW_PATH, "r") as f:
            return json.load(f)
    return {}


def save_zero_score_review(review: dict) -> None:
    ZERO_SCORE_REVIEW_PATH.parent.mkdir(parents=True, exist_ok=True)
    with open(ZERO_SCORE_REVIEW_PATH, "w") as f:
        json.dump(review, f, indent=2)


def auto_flag_zero_scores(week: int, board: list, actuals: dict, review: dict) -> dict:
    """
    Same auto-flagging behavior as RunWeekly.py's version (shares the
    same review file) -- adds a default `"played": false` entry for
    every drafted, non-bye player who scored exactly 0.0 this week and
    isn't already in the log, without touching any existing entry.
    """
    week_key = str(week)
    week_review = review.setdefault(week_key, {})
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

        week_review[pid] = {
            "name": p["player_name"],
            "position": p["position"],
            "played": False,
        }
        added.append(p["player_name"])

    if added:
        save_zero_score_review(review)
        print(f"  Auto-flagged {len(added)} zero-score player(s) for week {week} "
              f"review (default played=false): {added}")

    return review


def player_did_not_play(actual_points, bye_week, week: int, player: dict, review: dict) -> bool:
    """Same DNP semantics as RunWeekly.py's PAR calculation (see that
    file for the full rationale) -- bye weeks and missing actuals are
    always DNP; any other exact 0.0 defaults to DNP unless the manual
    zero-score review log confirms the player genuinely played."""
    if bye_week is not None and bye_week == week:
        return True
    if actual_points is None:
        return True
    if actual_points != 0.0:
        return False

    week_review = review.get(str(week), {})
    entry = week_review.get(player["player_id"])
    if entry and entry.get("played") is True:
        return False
    return True


# --------------------------------------------------------------------------
# PER-WEEK CREDITED POINTS (P = credited - replacement), never skipped
# --------------------------------------------------------------------------
def credited_points_for_week(week: int, board: list, position_by_id: dict, actuals: dict,
                              zero_score_review: dict) -> dict:
    """
    Returns {player_id: credited_points} for one week, for every drafted
    player with a recognized position. Ungated rule only (see module
    docstring): credit actual points if the player played, replacement
    level if they didn't. The projection-gated rule that used to apply
    here (week 3+) was removed after finding real cases where a scraped
    pregame projection was erroneously 0.0 for a player who was clearly
    a legitimate starter and had a great week -- see module docstring
    for the Brock Bowers example that surfaced this.
    """
    credited_by_id = {}

    for p in board:
        pid = p["player_id"]
        pos = position_by_id.get(pid)
        replacement = REPLACEMENT_LEVEL.get(pos)
        if replacement is None:
            continue

        actual = actuals.get(pid)
        dnp = player_did_not_play(actual, p["bye_week"], week, p, zero_score_review)
        credited_by_id[pid] = replacement if dnp else actual

    return credited_by_id


# --------------------------------------------------------------------------
# ORCHESTRATION: compute P for every player/week, and D per position
# --------------------------------------------------------------------------
def determine_weeks_to_process(league) -> list:
    """Every week strictly before the league's current week -- same
    convention as RunWeekly.py. No weeks are ever skipped for WAR."""
    return list(range(1, league.current_week()))


def calculate_weekly_par_and_starters(league, board: list) -> tuple:
    """
    Returns (par_by_id_by_week, starters_by_week):
      par_by_id_by_week: {week: {player_id: P}}  (P = credited - replacement)
      starters_by_week:  {week: set(player_id)}  (actually-started player_ids that week)
    """
    player_ids = [p["player_id"] for p in board]
    position_by_id = {p["player_id"]: p["position"] for p in board}
    zero_score_review = load_zero_score_review()

    weeks = determine_weeks_to_process(league)
    print(f"Current week per Yahoo: {league.current_week()}. Weeks to process: {weeks or 'none yet'}")

    par_by_id_by_week = {}
    starters_by_week = {}

    for week in weeks:
        print(f"Processing week {week}...")
        actuals = fetch_actuals_for_week(league, player_ids, week)
        credited = credited_points_for_week(week, board, position_by_id, actuals, zero_score_review)

        par_this_week = {}
        for pid, credited_pts in credited.items():
            replacement = REPLACEMENT_LEVEL.get(position_by_id.get(pid))
            if replacement is None:
                continue
            par_this_week[pid] = credited_pts - replacement
        par_by_id_by_week[week] = par_this_week

        starters_by_week[week] = fetch_starters_for_week(league, week)

    return par_by_id_by_week, starters_by_week


def calculate_position_averages(board: list, weeks: list, starters_by_week: dict,
                                 actuals_by_week: dict) -> dict:
    """
    Returns {position: D} -- the season-long average ACTUAL points scored
    by starters at that position, across every started player-week so
    far. A FLEX starter (selected_position "W/R/T") counts toward
    whichever of RB/WR/TE they actually play, per the draft board.

    This is a single value per position for the whole run (not
    recomputed week by week) and gets applied uniformly to every week's
    WAR calculation, including weeks before this value was reached.
    """
    position_by_id = {p["player_id"]: p["position"] for p in board}

    totals = {}
    counts = {}
    for week in weeks:
        starters = starters_by_week.get(week, set())
        actuals = actuals_by_week.get(week, {})
        for pid in starters:
            pos = position_by_id.get(pid)
            if pos is None or pos not in REPLACEMENT_LEVEL:
                continue
            actual = actuals.get(pid)
            if actual is None:
                continue
            totals[pos] = totals.get(pos, 0.0) + actual
            counts[pos] = counts.get(pos, 0) + 1

    return {pos: (totals[pos] / counts[pos]) for pos in totals if counts.get(pos)}


# --------------------------------------------------------------------------
# WAR CALCULATION
# --------------------------------------------------------------------------
def win_probability_added(p: float, d_relative: float) -> float:
    """
    WAR for a single week:
        Phi((P - D_relative) / MARGIN_SIGMA) - Phi((-D_relative) / MARGIN_SIGMA)

    IMPORTANT: d_relative must already be D's raw points-scored value
    MINUS that position's replacement level, NOT the raw D itself. P
    (credited_points - replacement) is a points-ABOVE-REPLACEMENT
    quantity, so D has to be put on that same basis before subtracting
    -- otherwise P-D mixes a replacement-relative number with a raw
    one. The caller (calculate_war) is responsible for converting D to
    D_relative = D - REPLACEMENT_LEVEL[pos] before calling this.
    """
    return norm.cdf((p - d_relative) / MARGIN_SIGMA) - norm.cdf((-d_relative) / MARGIN_SIGMA)


def calculate_war(league, board: list) -> tuple:
    """
    Returns (war_by_id, weeks_used, position_averages).

    war_by_id: {player_id: season_sum_WAR}
    weeks_used: every week processed (never skipped, per instruction)
    position_averages: {position: D} used for this run
    """
    player_ids = [p["player_id"] for p in board]
    position_by_id = {p["player_id"]: p["position"] for p in board}
    zero_score_review = load_zero_score_review()

    weeks = determine_weeks_to_process(league)
    print(f"Current week per Yahoo: {league.current_week()}. Weeks to process: {weeks or 'none yet'}")

    par_by_id_by_week = {}
    starters_by_week = {}
    actuals_by_week = {}

    for week in weeks:
        print(f"Fetching actuals + starters for week {week}...")
        actuals = fetch_actuals_for_week(league, player_ids, week)
        actuals_by_week[week] = actuals
        zero_score_review = auto_flag_zero_scores(week, board, actuals, zero_score_review)

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
    print(f"\nSeason-long starter averages (D, raw points) by position: "
          f"{ {pos: round(d, 2) for pos, d in position_averages.items()} }")

    # D (position_averages) is a RAW points-scored average, but P
    # (par_this_week, from credited_points_for_week) is already
    # points-ABOVE-REPLACEMENT. Phi((P-D)/sigma) requires both sides of
    # the subtraction to be on the same basis, so D has to be converted
    # to points-above-replacement here too: D_relative = D - replacement.
    # Without this, P-D mixes a replacement-relative number with a raw
    # one, which understates every player's WAR by treating "replacement
    # level" and "0" as the same point on two different scales.
    position_averages_relative = {
        pos: d - REPLACEMENT_LEVEL[pos]
        for pos, d in position_averages.items()
        if pos in REPLACEMENT_LEVEL
    }
    print(f"Season-long starter averages (D, relative to replacement) by position: "
          f"{ {pos: round(d, 2) for pos, d in position_averages_relative.items()} }")

    war_by_id = {pid: 0.0 for pid in player_ids}
    for week in weeks:
        par_this_week = par_by_id_by_week.get(week, {})
        for pid in player_ids:
            pos = position_by_id.get(pid)
            if pos not in REPLACEMENT_LEVEL:
                continue
            d_relative = position_averages_relative.get(pos)
            if d_relative is None:
                continue  # no starters observed yet at this position this run
            p = par_this_week.get(pid)
            if p is None:
                continue
            war_by_id[pid] += win_probability_added(p, d_relative)

    return war_by_id, weeks, position_averages


# --------------------------------------------------------------------------
# DRAFT BOARD DISPLAY (console)
# --------------------------------------------------------------------------
def print_draft_board(board: list, war_by_id: dict, weeks_used: list, position_averages: dict) -> None:
    print()
    print("=" * 72)
    print(f"{WAR_YEAR} DRAFT BOARD -- Wins Above Replacement (WAR)")
    if weeks_used:
        print(f"Weeks included: {weeks_used}")
    print(f"D (season-long starter average) by position: "
          f"{ {pos: round(d, 2) for pos, d in position_averages.items()} }")
    print("=" * 72)

    picks_by_round = {}
    for p in board:
        picks_by_round.setdefault(p["round"], []).append(p)

    for round_num in sorted(picks_by_round):
        print(f"\n--- Round {round_num} ---")
        for p in sorted(picks_by_round[round_num], key=lambda x: x["pick"]):
            pid = p["player_id"]
            war = war_by_id.get(pid, 0.0)
            drafted_by = p.get("manager_nickname") or p.get("team_name") or p["team_key"]
            print(
                f"  Pick {p['pick']:>3}  "
                f"{p['player_name']:<26} "
                f"{(p['position'] or '?'):<4} "
                f"WAR: {war:+7.3f}   "
                f"(drafted by {drafted_by})"
            )


# --------------------------------------------------------------------------
# BOARD GRID (rows = round, columns = teams in round-1 draft order)
# --------------------------------------------------------------------------
def build_board_grid(board: list) -> tuple:
    """Same convention as RunWeekly.py's build_board_grid -- columns
    ordered by each team's round-1 pick, rows are draft rounds."""
    round1_picks = sorted((p for p in board if p["round"] == 1), key=lambda p: p["pick"])
    columns = [
        {"team_key": p["team_key"], "label": p.get("manager_nickname") or p["team_name"]}
        for p in round1_picks
    ]

    rounds = sorted({p["round"] for p in board})

    cell_by_round_and_team = {}
    for p in board:
        cell_by_round_and_team[(p["round"], p["team_key"])] = p

    return rounds, columns, cell_by_round_and_team


def _draw_board(rounds, columns, cell_by_round_and_team, cell_color_fn, text_color_fn,
                 cell_label_fn, title: str, output_path, legend_handles=None) -> None:
    """Shared grid-drawing routine, identical to RunWeekly.py's _draw_board."""
    n_rows = len(rounds)
    n_cols = len(columns)

    cell_w, cell_h = 1.9, 1.0
    fig_w = max(10, n_cols * cell_w + 1.5)
    fig_h = n_rows * cell_h + 1.5

    fig, ax = plt.subplots(figsize=(fig_w, fig_h))
    ax.set_xlim(0, n_cols)
    ax.set_ylim(-0.9, n_rows)
    ax.invert_yaxis()
    ax.set_xticks([])
    ax.set_yticks([])
    for spine in ax.spines.values():
        spine.set_visible(False)

    for col_idx, col in enumerate(columns):
        ax.text(
            col_idx + 0.5, -0.55, col["label"],
            ha="center", va="center", fontsize=10, fontweight="bold", color="#111827",
        )

    for row_idx, round_num in enumerate(rounds):
        ax.text(
            -0.3, row_idx + 0.5, f"R{round_num}",
            ha="center", va="center", fontsize=9, fontweight="bold", color="#6B7280",
        )

    for row_idx, round_num in enumerate(rounds):
        for col_idx, col in enumerate(columns):
            pick = cell_by_round_and_team.get((round_num, col["team_key"]))

            x, y = col_idx, row_idx
            face_color = cell_color_fn(pick)
            rect = plt.Rectangle(
                (x, y), 1, 1,
                facecolor=face_color,
                edgecolor="white",
                linewidth=1.5,
            )
            ax.add_patch(rect)

            if pick is None:
                continue

            text_color = text_color_fn(pick)
            label = cell_label_fn(pick)
            ax.text(
                x + 0.5, y + 0.5, label,
                ha="center", va="center", fontsize=7.8, color=text_color, linespacing=1.4,
            )

    ax.set_title(title, fontsize=15, fontweight="bold", color="#111827", pad=36)

    if legend_handles:
        ax.legend(
            handles=legend_handles,
            loc="upper center",
            bbox_to_anchor=(0.5, -0.4 / n_rows),
            ncol=min(len(legend_handles), 6),
            frameon=False,
            fontsize=9,
        )

    fig.tight_layout()
    fig.savefig(output_path, dpi=200, bbox_inches="tight")
    plt.close(fig)
    print(f"Saved -> {output_path}")


def render_war_board(rounds, columns, cell_by_round_and_team, war_by_id: dict) -> None:
    """
    Diverging gradient split at zero, identical scheme to RunWeekly.py's
    render_par_board: positive WAR uses 'Reds' (darker = higher), negative
    WAR uses 'Blues' (darker = more negative). Each half normalized
    independently against this run's actual max/min.
    """
    war_values = [war_by_id.get(p["player_id"], 0.0) for p in cell_by_round_and_team.values()]
    war_max = max((v for v in war_values if v > 0), default=1.0) or 1.0
    war_min = min((v for v in war_values if v < 0), default=-1.0) or -1.0

    reds = matplotlib.colormaps["Reds"]
    blues = matplotlib.colormaps["Blues"]

    def intensity(value: float) -> float:
        if value >= 0:
            return value / war_max if war_max else 0.0
        return value / war_min if war_min else 0.0

    def cell_color(pick):
        if pick is None:
            return "#FFFFFF"
        war = war_by_id.get(pick["player_id"], 0.0)
        t = intensity(war)
        return reds(t) if war >= 0 else blues(t)

    def text_color(pick):
        if pick is None:
            return DEFAULT_TEXT_COLOR
        war = war_by_id.get(pick["player_id"], 0.0)
        return "#FFFFFF" if intensity(war) > 0.6 else "#111827"

    def label(pick):
        war = war_by_id.get(pick["player_id"], 0.0)
        return f"#{pick['pick']}  {war:+.3f}\n{pick['player_name']}"

    HISTOGRAMS_DIR.mkdir(parents=True, exist_ok=True)
    _draw_board(
        rounds, columns, cell_by_round_and_team,
        cell_color_fn=cell_color,
        text_color_fn=text_color,
        cell_label_fn=label,
        title=f"{WAR_YEAR} Draft Board -- Wins Above Replacement (WAR)",
        output_path=WAR_BOARD_IMAGE_PATH,
        legend_handles=None,
    )

    n_stops = 256
    blue_half = [blues(1.0 - i / (n_stops // 2 - 1)) for i in range(n_stops // 2)]
    red_half = [reds(i / (n_stops // 2 - 1)) for i in range(n_stops // 2)]
    diverging_cmap = matplotlib.colors.ListedColormap(blue_half + red_half)

    fig, ax = plt.subplots(figsize=(6, 0.6))
    fig.subplots_adjust(bottom=0.5)
    norm_ = matplotlib.colors.Normalize(vmin=war_min, vmax=war_max)
    cb = matplotlib.colorbar.ColorbarBase(ax, cmap=diverging_cmap, norm=norm_, orientation="horizontal")
    cb.set_label("WAR (negative -> positive)", fontsize=9)
    colorbar_path = WAR_BOARD_IMAGE_PATH.with_name(WAR_BOARD_IMAGE_PATH.stem + "_colorbar.png")
    fig.savefig(colorbar_path, dpi=200, bbox_inches="tight")
    plt.close(fig)
    print(f"Saved -> {colorbar_path}")


def run_calculate_war(league) -> None:
    """Entry point for the WAR step. Can be called standalone (see
    main() below) or imported and called from RunWeekly.py."""
    board = load_draft_board(league)
    war_by_id, weeks_used, position_averages = calculate_war(league, board)
    print_draft_board(board, war_by_id, weeks_used, position_averages)

    rounds, columns, cell_by_round_and_team = build_board_grid(board)
    render_war_board(rounds, columns, cell_by_round_and_team, war_by_id)


def main():
    from yahoo_oauth import OAuth2

    sc = OAuth2(None, None, from_file='../oauth2.json')
    gm = yfa.Game(sc, 'nfl')
    YEAR_ID = '470.l.205662'  # Change this every year, matches RunWeekly.py
    league = gm.to_league(YEAR_ID)

    run_calculate_war(league)


if __name__ == "__main__":
    main()
