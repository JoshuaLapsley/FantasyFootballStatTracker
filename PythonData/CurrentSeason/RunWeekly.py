"""
Weekly pipeline for the current (2026) Girderma Gridiron season.

Runs four steps against the live Yahoo league:
  1. write_week_files          -- pulls each finished week's matchup data
  2. calculate_earned_wins      -- derives earned-wins stats from that data
  3. run_draft_par              -- calculates each drafted player's Points
                                    Above Replacement (PAR) and renders the
                                    draft board images (by position, and by
                                    PAR on a red/blue diverging gradient)
  4. run_simulate_matchups      -- Monte Carlo simulates the remaining
                                    regular season (record distribution,
                                    weekly points, playoff/punishment odds)

Steps 3 and 4 were originally their own standalone scripts
(Website/girderma-gridiron-website/src/histograms/draft_par.py and
PythonData/simulate_season/simulate_matchups.py) and have been folded
into this file so a single `python3 RunWeekly.py` run keeps everything --
matchups, earned wins, draft board, and season simulation -- up to date
together. Their logic/behavior is unchanged from the standalone
versions; only the OAuth/league setup was de-duplicated to reuse this
file's existing `lg` instead of each creating its own.

run_simulate_matchups() requires PythonData/simulate_season/lineups/
(from calculate_lineups.py) and PythonData/simulate_season/schedule.json
(from pull_schedule.py) to already be up to date for the weeks being
simulated -- it does not pull or refresh either itself, same as the
original standalone script.

--------------------------------------------------------------------------
WHAT "PAR" MEANS (run_draft_par and helpers, below)
--------------------------------------------------------------------------
Replacement level (per position, season-long flat baseline):
    QB = 15, RB = 5, WR = 7, TE = 6, K = 7, DEF = 5

For every week a drafted skill-position player (QB/RB/WR/TE) could have
played, from week 3 onward:
  * If the scraped Yahoo-website pregame projection for that player/week
    was ABOVE their position's replacement level, the player is credited
    with their ACTUAL points scored that week (even if the actual came
    in under replacement -- the projection is what gates it, not the
    outcome).
  * If the projection was AT/BELOW replacement level, OR the player did
    not play at all that week (bye/inactive/not on an NFL roster yet),
    the player is credited with replacement level for that week instead.
  * A player's PAR for the season is the sum of (points credited that
    week - replacement level) across all processed weeks.

K and DEF are never gated by a projection at all (see "K / DEF" below) --
they always use the same ungated rule as weeks 1-2.

WEEKS 1-2: NO PROJECTION GATING (ungated rule)
Yahoo's official API (league.player_stats()) cannot return a real
pregame projection for any week -- querying it for a week that hasn't
happened yet returns an all-zero placeholder, and once the week is final
it just returns the actual box score. Weeks 1 and 2 were never captured
by the website scraper (simulate_season/pull_projections.py) before
their games started, so there is no way to recover a real pregame
projection for either of them. Both weeks use the same ungated fallback
rule:
  * If a player played in the week at all, they're credited their ACTUAL
    points for that week -- no replacement-level gating, even if that
    actual score is very low.
  * If a player did NOT play at all that week (bye/inactive), they're
    credited replacement level for that week instead.

WEEK 3+: PROJECTION-GATED RULE, SOURCED FROM THE WEBSITE SCRAPE
From week 3 onward, the pregame projection used for gating comes from
simulate_season/pull_projections.py's scraped output
(simulate_season/projections/week_{N}.json), NOT the Yahoo API -- that
scraper reads the actual "Projected Stats" view on the Yahoo website,
which is the only place a real per-player pregame projection exists.
This only works if pull_projections.py was run for that week BEFORE the
week's games started. If no scrape file exists for a given final week,
that week is skipped for PAR entirely (see weeks_skipped) rather than
guessed at.

K and DEF are excluded from this rule since this league's rosters never
actually carry either position, so there's never a scraped projection to
gate against -- they always use the ungated rule, every week.

Players are matched between the draft board and the scraped projections
by full name (the scraper doesn't carry Yahoo's numeric player_id).

0.0 SCORES DEFAULT TO DNP AUTOMATICALLY
Bye weeks are unambiguous and always treated as DNP automatically. Any
OTHER exact 0.0 score is now ALSO auto-treated as DNP by default -- no
manual review needed for the common case. The zero-score review log
(ZERO_SCORE_REVIEW_PATH) is only for the opposite, rarer case: a player
who genuinely played and scored a real 0. If you know that happened for
a given player/week, manually add an entry to that file:
    {"<week>": {"<player_id>": {"name": "...", "position": "...", "played": true}}}
and re-run -- that flips just that one player/week from DNP (replacement
level) to counted-as-played (actual points, which will be 0).

Files PAR reads (all under PythonData/):
  draftData/draft_{YEAR}.json                cached draft board (delete to refresh)
  simulate_season/projections/week_{N}.json  scraped pregame projections (week 3+)

Files PAR reads/writes:
  draftData/par_zero_score_review_{YEAR}.json  manual "did they actually play?" log

Images PAR writes (into Website/girderma-gridiron-website/src/histograms/):
  draft_board_by_position_{YEAR}.png   grid colored by player position
  draft_board_by_par_{YEAR}.png        grid colored by PAR: red gradient
                                        for positive PAR (darker = higher),
                                        blue gradient for negative PAR
                                        (darker = more negative)
"""

from yahoo_oauth import OAuth2
from WriteWeeklyMatchupData import write_week_files
from WriteEarnedWinsData import calculate_earned_wins
import yahoo_fantasy_api as yfa
import glob
import json
import os
from pathlib import Path

import numpy as np
import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt

sc = OAuth2(None, None, from_file='../oauth2.json')
gm = yfa.Game(sc, 'nfl')



YEAR_ID = '470.l.205662'#Change this every year
lg = gm.to_league(YEAR_ID)

SCRIPT_DIR = os.path.dirname(os.path.abspath(__file__))

CURRENT_SEASON_DATA_DIR = os.path.normpath(os.path.join(
    SCRIPT_DIR, "..", "..", "Website", "girderma-gridiron-website",
    "src", "league_stats_output", "CurrentSeason"
))

MATCHUP_DATA_DIR = os.path.normpath(os.path.join(
    SCRIPT_DIR, "..", "..", "Website", "girderma-gridiron-website",
    "src", "league_stats_output", "CurrentSeason", "MatchupData"
))


# ==========================================================================
# DRAFT PAR (formerly draft_par.py)
# ==========================================================================
PAR_YEAR = 2026

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

# This league's rosters never actually carry a kicker or defense (every
# team's real roster is QB/RB/WR/TE only), so there's never a scraped
# pregame projection to gate these positions against. They always use
# the same ungated "actual if played, replacement if DNP" rule as weeks
# 1-2, regardless of week.
UNGATED_POSITIONS = {"K", "DEF"}

# Weeks 1-2 are already-played and were never scraped before their games
# started, so there's no real pregame projection recoverable for either
# -- both use the ungated rule. Week 3 onward uses the scraped-projection
# gated rule.
UNGATED_WEEKS = {1, 2}

# Same palette used by the website's own draft board component
# (src/pages/LeagueHistory/Draft/Draft.tsx POSITION_COLORS) so the
# generated images match the site's look.
POSITION_COLORS = {
    "QB": "#E0E7FF",
    "RB": "#D1FAE5",
    "WR": "#DBEAFE",
    "TE": "#FFEDD5",
    "K": "#EDE9FE",
    "DEF": "#F3F4F6",
}
POSITION_TEXT_COLORS = {
    "QB": "#3730A3",
    "RB": "#065F46",
    "WR": "#1E40AF",
    "TE": "#9A3412",
    "K": "#5B21B6",
    "DEF": "#374151",
}
DEFAULT_CELL_COLOR = "#F3F4F6"
DEFAULT_TEXT_COLOR = "#374151"

# PythonData/ root (this file lives at PythonData/CurrentSeason/).
PYTHON_DATA_DIR = Path(SCRIPT_DIR) / ".."

DRAFT_CACHE_PATH = PYTHON_DATA_DIR / "draftData" / f"draft_{PAR_YEAR}.json"
ZERO_SCORE_REVIEW_PATH = PYTHON_DATA_DIR / "draftData" / f"par_zero_score_review_{PAR_YEAR}.json"
SCRAPED_PROJECTIONS_DIR = PYTHON_DATA_DIR / "simulate_season" / "projections"

# Draft board images live in the website's histograms folder (same place
# create_histograms.py writes to), NOT in this CurrentSeason folder.
HISTOGRAMS_DIR = (
    Path(SCRIPT_DIR) / ".." / ".." / "Website" / "girderma-gridiron-website"
    / "src" / "histograms"
).resolve()
POSITION_BOARD_IMAGE_PATH = HISTOGRAMS_DIR / f"draft_board_by_position_{PAR_YEAR}.png"
PAR_BOARD_IMAGE_PATH = HISTOGRAMS_DIR / f"draft_board_by_par_{PAR_YEAR}.png"


# --------------------------------------------------------------------------
# DRAFT DATA
# --------------------------------------------------------------------------
def load_draft_board(league) -> list[dict]:
    """
    Returns the season's draft in real pick order, each entry enriched
    with player name/position. Cached to disk since player_details() for
    ~210 picks is a non-trivial batch of API calls we don't want to redo
    every run.
    """
    if DRAFT_CACHE_PATH.exists():
        with open(DRAFT_CACHE_PATH, "r") as f:
            return json.load(f)

    print(f"Pulling {PAR_YEAR} draft results from Yahoo...")
    draft_results = league.draft_results()  # [{pick, round, team_key, player_id}, ...]

    teams = league.teams()  # team_key -> team info (name, managers, ...)

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
# SCRAPED PREGAME PROJECTIONS (week 3+)
# --------------------------------------------------------------------------
def load_scraped_projections(week: int):
    """
    Returns {player_name: projected_points} from
    simulate_season/projections/week_{week}.json (produced by
    pull_projections.py), or None if that file doesn't exist -- meaning
    the week wasn't scraped before it started and can't be gated.

    Players on a bye that week have projected_points == null in the
    scraped file; they're omitted here (treated as "no projection", same
    as any other player absent from the file -- player_did_not_play()
    catches the bye case separately via the draft board's own bye_week
    field).
    """
    path = SCRAPED_PROJECTIONS_DIR / f"week_{week}.json"
    if not path.exists():
        return None

    with open(path, "r") as f:
        rosters = json.load(f)

    projections = {}
    for team_players in rosters.values():
        for p in team_players:
            if p.get("projected_points") is not None:
                projections[p["name"]] = p["projected_points"]
    return projections


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
# ZERO-SCORE MANUAL REVIEW LOG
# --------------------------------------------------------------------------
def load_zero_score_review() -> dict:
    if ZERO_SCORE_REVIEW_PATH.exists():
        with open(ZERO_SCORE_REVIEW_PATH, "r") as f:
            return json.load(f)
    return {}


def player_did_not_play(
    actual_points,
    bye_week,
    week: int,
    player: dict,
    review: dict,
) -> bool:
    """
    Determines whether a player should be treated as DNP (credited
    replacement level) for a given week.

    Bye weeks are unambiguous and handled automatically. Any OTHER exact
    0.0 score is now ALSO auto-treated as DNP by default -- that's the
    common case (inactive/didn't play) and needs no manual input.

    The zero-score review log (ZERO_SCORE_REVIEW_PATH) only matters for
    the rarer opposite case: a player who genuinely played and scored a
    real 0. If review[week][player_id]["played"] is explicitly set to
    true, that overrides the default and the player is NOT treated as
    DNP (their real, played 0 counts as-is). Anything else (no entry,
    or "played": false) stays DNP.
    """
    if bye_week is not None and bye_week == week:
        return True
    if actual_points is None:
        return True
    if actual_points != 0.0:
        return False

    # Actual score is exactly 0.0 and it's not a bye -- defaults to DNP
    # unless a manual override says they actually played.
    week_review = review.get(str(week), {})
    entry = week_review.get(player["player_id"])
    if entry and entry.get("played") is True:
        return False  # confirmed: they played and genuinely scored 0.
    return True


# --------------------------------------------------------------------------
# PAR CALCULATION
# --------------------------------------------------------------------------
def determine_weeks_to_process(league) -> tuple:
    """
    Returns (weeks_with_final_actuals, current_week). Only weeks strictly
    before the league's current week are treated as final/played.
    """
    current_week = league.current_week()
    final_weeks = list(range(1, current_week))
    return final_weeks, current_week


def _apply_ungated_week(week: int, board, position_by_id, actuals,
                         zero_score_review, par_by_id) -> None:
    """
    Ungated rule: credit actual points if played, replacement level only
    if the player didn't play at all (bye/inactive). No comparison
    against replacement level -- a real, played performance always
    counts as-is, however low.
    """
    for p in board:
        pid = p["player_id"]
        pos = position_by_id[pid]
        replacement = REPLACEMENT_LEVEL.get(pos)
        if replacement is None:
            continue
        actual = actuals.get(pid)
        dnp = player_did_not_play(actual, p["bye_week"], week, p, zero_score_review)
        credited = replacement if dnp else actual
        par_by_id[pid] += credited - replacement


def _apply_gated_week(week: int, board, position_by_id, actuals, projections_by_name,
                       zero_score_review, par_by_id) -> None:
    """
    Projection-gated rule (skill positions, week 3+): if the scraped
    pregame projection was above replacement level, credit actual points
    (even if actual came in lower); otherwise credit replacement level.
    K/DEF (UNGATED_POSITIONS) are routed through the ungated rule instead,
    since there's never a scraped projection for them.
    """
    for p in board:
        pid = p["player_id"]
        pos = position_by_id[pid]
        replacement = REPLACEMENT_LEVEL.get(pos)
        if replacement is None:
            continue

        actual = actuals.get(pid)
        dnp = player_did_not_play(actual, p["bye_week"], week, p, zero_score_review)

        if pos in UNGATED_POSITIONS:
            credited = replacement if dnp else actual
            par_by_id[pid] += credited - replacement
            continue

        if dnp:
            continue  # credited == replacement -> contributes 0 to PAR

        projection = projections_by_name.get(p["player_name"])
        if projection is None:
            # Not found on any scraped roster for this week (e.g. a free
            # agent that week) -- nothing to gate against, treat as if
            # projected at/below replacement.
            projection = 0.0

        credited = actual if projection > replacement else replacement
        par_by_id[pid] += credited - replacement


def calculate_par(league, board: list) -> tuple:
    """
    Returns (par_by_player_id, weeks_used, weeks_skipped).

    weeks_used: weeks that actually contributed to PAR this run.
    weeks_skipped: weeks that were final (week 3+) but had no scraped
    projections file -- pull_projections.py wasn't run for that week
    before its games started, so it can't be gated and is excluded
    rather than guessed at.
    """
    player_ids = [p["player_id"] for p in board]
    position_by_id = {p["player_id"]: p["position"] for p in board}

    final_weeks, current_week = determine_weeks_to_process(league)
    print(f"Current week per Yahoo: {current_week}. Final/played weeks: {final_weeks or 'none yet'}")

    zero_score_review = load_zero_score_review()

    par_by_id = {pid: 0.0 for pid in player_ids}
    weeks_used = []
    weeks_skipped = []

    for week in final_weeks:
        actuals = fetch_actuals_for_week(league, player_ids, week)

        if week in UNGATED_WEEKS:
            print(f"Processing week {week} (ungated rule: weeks 1-2 have no "
                  f"recoverable pregame projection)...")
            _apply_ungated_week(week, board, position_by_id, actuals,
                                 zero_score_review, par_by_id)
            weeks_used.append(week)
            continue

        projections_by_name = load_scraped_projections(week)
        if projections_by_name is None:
            print(f"  No scraped projections file for week {week} "
                  f"(pull_projections.py wasn't run for it before it started) "
                  f"-- skipping this week for PAR.")
            weeks_skipped.append(week)
            continue

        print(f"Processing week {week} (projection-gated rule, scraped projections)...")
        _apply_gated_week(week, board, position_by_id, actuals, projections_by_name,
                           zero_score_review, par_by_id)
        weeks_used.append(week)

    return par_by_id, weeks_used, weeks_skipped


# --------------------------------------------------------------------------
# DRAFT BOARD DISPLAY
# --------------------------------------------------------------------------
def print_draft_board(board: list, par_by_id: dict, weeks_used: list, weeks_skipped: list) -> None:
    print()
    print("=" * 72)
    print(f"{PAR_YEAR} DRAFT BOARD -- Points Above Replacement (PAR)")
    if weeks_used:
        print(f"Weeks included: {weeks_used}")
    if weeks_skipped:
        print(f"Weeks skipped (no usable projection): {weeks_skipped}")
    print("=" * 72)

    picks_by_round = {}
    for p in board:
        picks_by_round.setdefault(p["round"], []).append(p)

    for round_num in sorted(picks_by_round):
        print(f"\n--- Round {round_num} ---")
        for p in sorted(picks_by_round[round_num], key=lambda x: x["pick"]):
            pid = p["player_id"]
            par = par_by_id.get(pid, 0.0)
            drafted_by = p.get("manager_nickname") or p.get("team_name") or p["team_key"]
            print(
                f"  Pick {p['pick']:>3}  "
                f"{p['player_name']:<26} "
                f"{(p['position'] or '?'):<4} "
                f"PAR: {par:+7.2f}   "
                f"(drafted by {drafted_by})"
            )


# --------------------------------------------------------------------------
# BOARD GRID (rows = round, columns = teams in round-1 draft order)
# --------------------------------------------------------------------------
def build_board_grid(board: list) -> tuple:
    """
    Returns (rounds, columns, cell_by_round_and_team).

    Columns are ordered by each team's round-1 pick (left to right in
    draft order), same convention the website's own Draft.tsx board uses.
    Since this is a snake draft, later rounds naturally alternate
    direction within each row, but the column a team sits in stays fixed
    -- matching how the site already displays it.
    """
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


def _draw_board(
    rounds,
    columns,
    cell_by_round_and_team,
    cell_color_fn,
    text_color_fn,
    cell_label_fn,
    title: str,
    output_path,
    legend_handles=None,
) -> None:
    """
    Shared grid-drawing routine. cell_color_fn/text_color_fn/cell_label_fn
    each take a single pick dict and return what to draw for that cell.
    """
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

    # Column headers (team/manager names).
    for col_idx, col in enumerate(columns):
        ax.text(
            col_idx + 0.5, -0.55, col["label"],
            ha="center", va="center", fontsize=10, fontweight="bold", color="#111827",
        )

    # Row headers (round numbers).
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


def render_position_board(rounds, columns, cell_by_round_and_team) -> None:
    def cell_color(pick):
        if pick is None:
            return "#FFFFFF"
        return POSITION_COLORS.get(pick["position"], DEFAULT_CELL_COLOR)

    def text_color(pick):
        return POSITION_TEXT_COLORS.get(pick["position"], DEFAULT_TEXT_COLOR)

    def label(pick):
        return f"#{pick['pick']}  {pick['position'] or '?'}\n{pick['player_name']}"

    legend_handles = [
        plt.Rectangle((0, 0), 1, 1, facecolor=color, edgecolor="white", label=pos)
        for pos, color in POSITION_COLORS.items()
    ]

    HISTOGRAMS_DIR.mkdir(parents=True, exist_ok=True)
    _draw_board(
        rounds, columns, cell_by_round_and_team,
        cell_color_fn=cell_color,
        text_color_fn=text_color,
        cell_label_fn=label,
        title=f"{PAR_YEAR} Draft Board -- by Position",
        output_path=POSITION_BOARD_IMAGE_PATH,
        legend_handles=legend_handles,
    )


def render_par_board(rounds, columns, cell_by_round_and_team, par_by_id: dict) -> None:
    """
    Diverging gradient split at zero: positive PAR uses the 'Reds'
    colormap (darker red = higher PAR), negative PAR uses the 'Blues'
    colormap (darker blue = more negative PAR). Each half is normalized
    independently against the actual positive/negative extremes seen this
    run, so both directions get full contrast regardless of scale.
    """
    par_values = [par_by_id.get(p["player_id"], 0.0) for p in cell_by_round_and_team.values()]
    par_max = max((v for v in par_values if v > 0), default=1.0) or 1.0
    par_min = min((v for v in par_values if v < 0), default=-1.0) or -1.0

    reds = matplotlib.colormaps["Reds"]
    blues = matplotlib.colormaps["Blues"]

    def intensity(value: float) -> float:
        """0..1 how far value is toward its side's extreme (0 at zero)."""
        if value >= 0:
            return value / par_max if par_max else 0.0
        return value / par_min if par_min else 0.0  # both negative -> positive ratio

    def cell_color(pick):
        if pick is None:
            return "#FFFFFF"
        par = par_by_id.get(pick["player_id"], 0.0)
        t = intensity(par)
        return reds(t) if par >= 0 else blues(t)

    def text_color(pick):
        if pick is None:
            return DEFAULT_TEXT_COLOR
        par = par_by_id.get(pick["player_id"], 0.0)
        # Flip to white text once the gradient gets dark enough to need it.
        return "#FFFFFF" if intensity(par) > 0.6 else "#111827"

    def label(pick):
        par = par_by_id.get(pick["player_id"], 0.0)
        return f"#{pick['pick']}  {par:+.1f}\n{pick['player_name']}"

    HISTOGRAMS_DIR.mkdir(parents=True, exist_ok=True)
    _draw_board(
        rounds, columns, cell_by_round_and_team,
        cell_color_fn=cell_color,
        text_color_fn=text_color,
        cell_label_fn=label,
        title=f"{PAR_YEAR} Draft Board -- Points Above Replacement (PAR)",
        output_path=PAR_BOARD_IMAGE_PATH,
        legend_handles=None,
    )

    # Colorbar as a separate small legend strip: blue (very negative) on
    # the left, through white at zero, to red (very positive) on the
    # right. Built by stitching the two halves into one diverging map
    # since 'Reds'/'Blues' individually only run light-to-dark, not
    # negative-to-positive.
    n_stops = 256
    blue_half = [blues(1.0 - i / (n_stops // 2 - 1)) for i in range(n_stops // 2)]
    red_half = [reds(i / (n_stops // 2 - 1)) for i in range(n_stops // 2)]
    diverging_cmap = matplotlib.colors.ListedColormap(blue_half + red_half)

    fig, ax = plt.subplots(figsize=(6, 0.6))
    fig.subplots_adjust(bottom=0.5)
    norm = matplotlib.colors.Normalize(vmin=par_min, vmax=par_max)
    cb = matplotlib.colorbar.ColorbarBase(ax, cmap=diverging_cmap, norm=norm, orientation="horizontal")
    cb.set_label("PAR (negative -> positive)", fontsize=9)
    colorbar_path = PAR_BOARD_IMAGE_PATH.with_name(PAR_BOARD_IMAGE_PATH.stem + "_colorbar.png")
    fig.savefig(colorbar_path, dpi=200, bbox_inches="tight")
    plt.close(fig)
    print(f"Saved -> {colorbar_path}")


def run_draft_par(league) -> None:
    """Entry point for the draft-PAR step (formerly draft_par.py's main())."""
    board = load_draft_board(league)
    par_by_id, weeks_used, weeks_skipped = calculate_par(league, board)
    print_draft_board(board, par_by_id, weeks_used, weeks_skipped)

    rounds, columns, cell_by_round_and_team = build_board_grid(board)
    render_position_board(rounds, columns, cell_by_round_and_team)
    render_par_board(rounds, columns, cell_by_round_and_team, par_by_id)


# ==========================================================================
# SIMULATE MATCHUPS (formerly simulate_season/simulate_matchups.py)
# ==========================================================================
"""
Monte Carlo simulate the remaining regular season (from Yahoo's current
week onward) using each team's optimal projected lineup score (from
calculate_lineups.py) as the mean of a normal distribution with a fixed
standard deviation, and the real schedule (from pull_schedule.py) to
know who plays whom.

Each simulated game:
    score ~ Normal(mu=team's lineup total that week, sigma=33)
    higher score wins (a tie has probability 0 under a continuous draw)

Each simulated season starts from each team's REAL record and
points-for so far (pulled live from Yahoo standings/matchups -- whichever
weeks are already final), then simulates the remaining weeks using the
schedule + per-week lineup means. Which weeks count as "already
happened" is determined automatically from Yahoo's own current_week()
each time this runs.

Playoff seeding, for both the simulation and the odds chart, ranks teams
by (wins, total points scored) descending. Seeds 1-2 get a first-round
bye; seeds 3-6 make the playoffs without a bye; the bottom 4 (seeds
11-14) land in the punishment bracket; seeds 7-10 make neither.

Output (into PythonData/simulate_season/):
  record_distribution.jpg    heatmap of each team's final-record odds
  average_weekly_points.jpg  heatmap of actual + projected points per week
  playoff_odds.jpg           bar chart of bye/playoff/punishment odds
  record_distribution.json   raw record-count distribution

Requires simulate_season/lineups/week_{N}.json (calculate_lineups.py)
and simulate_season/schedule.json (pull_schedule.py) to already cover
every week being simulated -- this step does not generate either itself.
"""

SIMULATE_SEASON_DIR = (Path(SCRIPT_DIR) / ".." / "simulate_season").resolve()
LINEUPS_DIR = SIMULATE_SEASON_DIR / "lineups"
SCHEDULE_PATH = SIMULATE_SEASON_DIR / "schedule.json"

SIM_VARIANCE = 33 ** 2
SIM_N_SIMULATIONS = 10_000
SIM_END_WEEK = 14
SIM_BYE_SPOTS = 2
SIM_PLAYOFF_SPOTS = 4
SIM_PUNISHMENT_SPOTS = 4

RECORD_DISTRIBUTION_IMAGE = SIMULATE_SEASON_DIR / "record_distribution.jpg"
RECORD_DISTRIBUTION_JSON = SIMULATE_SEASON_DIR / "record_distribution.json"
WEEKLY_POINTS_IMAGE = SIMULATE_SEASON_DIR / "average_weekly_points.jpg"
PLAYOFF_ODDS_IMAGE = SIMULATE_SEASON_DIR / "playoff_odds.jpg"


def get_completed_weeks(league) -> list:
    """
    Weeks that have actually finished, per Yahoo's own current_week().
    Same convention as determine_weeks_to_process() above.
    """
    return list(range(1, league.current_week()))


def get_real_records(league) -> dict:
    """Return {team_name: (wins, losses)} from Yahoo's live standings,
    reflecting every game actually played so far."""
    standings = league.standings()
    records = {}
    for team in standings:
        name = team["name"]
        totals = team["outcome_totals"]
        wins = int(totals["wins"])
        losses = int(totals["losses"])
        records[name] = (wins, losses)
    return records


def get_actual_points_for_week(league, week: int) -> dict:
    """Return {team_name: actual_points_scored} for one already-played
    week, via the same matchups parsing convention used elsewhere in this
    project (WriteWeeklyMatchupData.py)."""
    raw = league.matchups(week=week)
    scoreboard = raw["fantasy_content"]["league"][1]["scoreboard"]
    sb_key = next(k for k in scoreboard.keys() if k.isdigit())
    matchups_raw = scoreboard[sb_key]["matchups"]
    count = int(matchups_raw["count"])

    points = {}
    for i in range(count):
        matchup = matchups_raw[str(i)]["matchup"]
        teams_raw = matchup["0"]["teams"]
        team_count = int(teams_raw["count"])
        for j in range(team_count):
            team_raw = teams_raw[str(j)]["team"]
            meta = team_raw[0]
            name = next((it["name"] for it in meta if isinstance(it, dict) and "name" in it), None)
            for chunk in team_raw[1:]:
                if isinstance(chunk, dict) and "team_points" in chunk:
                    points[name] = float(chunk["team_points"]["total"])
    return points


def get_real_points_by_week(league, completed_weeks: list) -> dict:
    """Return {week: {team_name: actual_points}} for every completed week."""
    return {week: get_actual_points_for_week(league, week) for week in completed_weeks}


def get_total_points_so_far(points_by_week: dict, teams: list) -> dict:
    """Return {team_name: total actual points across all completed weeks}."""
    totals = {t: 0.0 for t in teams}
    for week_points in points_by_week.values():
        for t, pts in week_points.items():
            totals[t] = totals.get(t, 0.0) + pts
    return totals


def load_lineup_means(weeks: list) -> dict:
    """Return {week: {team_name: projected_total_points}}."""
    means = {}
    for week in weeks:
        path = LINEUPS_DIR / f"week_{week}.json"
        if not path.exists():
            raise FileNotFoundError(
                f"No lineup file for week {week} ({path}). Run "
                f"simulate_season/calculate_lineups.py first."
            )
        with open(path) as f:
            lineups = json.load(f)
        means[week] = {team: data["total_points"] for team, data in lineups.items()}
    return means


def load_schedule(weeks: list) -> dict:
    """Return {week: [(team_a, team_b), ...]} for the requested weeks."""
    with open(SCHEDULE_PATH) as f:
        full_schedule = json.load(f)

    schedule = {}
    for week in weeks:
        key = str(week)
        if key not in full_schedule:
            raise KeyError(f"No schedule entry for week {week} in {SCHEDULE_PATH}")
        schedule[week] = [tuple(pair) for pair in full_schedule[key]]
    return schedule


def simulate_season(teams: list, real_records: dict, points_so_far: dict,
                     lineup_means: dict, schedule: dict, weeks: list,
                     n_simulations: int, variance: float, bye_spots: int = 2,
                     playoff_spots: int = 4, punishment_spots: int = 4,
                     seed: int = None) -> dict:
    """
    Run the Monte Carlo simulation.

    Seeds 1..bye_spots get a first-round bye. Seeds
    (bye_spots+1)..(bye_spots+playoff_spots) make the playoffs without a
    bye. The bottom `punishment_spots` seeds land in the punishment
    bracket. Whatever's left in the middle makes neither.

    Returns a dict with:
      "record_counts": {team_name: {(wins, losses): count}}
      "bye_counts": {team_name: count}          -- trials finishing in the bye seeds
      "playoff_counts": {team_name: count}      -- trials finishing in the non-bye playoff seeds
      "punishment_counts": {team_name: count}   -- trials finishing bottom `punishment_spots`

    Seeding within each trial ranks teams by (wins, total points scored)
    descending.
    """
    if seed is not None:
        np.random.seed(seed)

    sigma = np.sqrt(variance)
    base_wins = {t: real_records.get(t, (0, 0))[0] for t in teams}
    base_losses = {t: real_records.get(t, (0, 0))[1] for t in teams}
    base_points = {t: points_so_far.get(t, 0.0) for t in teams}

    record_counts = {t: {} for t in teams}
    bye_counts = {t: 0 for t in teams}
    playoff_counts = {t: 0 for t in teams}
    punishment_counts = {t: 0 for t in teams}

    for _ in range(n_simulations):
        wins = dict(base_wins)
        losses = dict(base_losses)
        points_for = dict(base_points)

        for week in weeks:
            means = lineup_means[week]
            for team_a, team_b in schedule[week]:
                mu_a = means[team_a]
                mu_b = means[team_b]
                score_a = np.random.normal(mu_a, sigma)
                score_b = np.random.normal(mu_b, sigma)
                points_for[team_a] += score_a
                points_for[team_b] += score_b
                if score_a > score_b:
                    wins[team_a] += 1
                    losses[team_b] += 1
                else:
                    wins[team_b] += 1
                    losses[team_a] += 1

        for t in teams:
            record = (wins[t], losses[t])
            record_counts[t][record] = record_counts[t].get(record, 0) + 1

        ranked = sorted(teams, key=lambda t: (wins[t], points_for[t]), reverse=True)
        for t in ranked[:bye_spots]:
            bye_counts[t] += 1
        for t in ranked[bye_spots:bye_spots + playoff_spots]:
            playoff_counts[t] += 1
        for t in ranked[-punishment_spots:]:
            punishment_counts[t] += 1

    return {
        "record_counts": record_counts,
        "bye_counts": bye_counts,
        "playoff_counts": playoff_counts,
        "punishment_counts": punishment_counts,
    }


def _week_range_label(weeks: list) -> str:
    if not weeks:
        return "none"
    if len(weeks) == 1:
        return str(weeks[0])
    return f"{weeks[0]}-{weeks[-1]}"


def plot_record_distribution(record_counts: dict, n_simulations: int,
                              total_games: int, completed_weeks: list,
                              simulated_weeks: list, out_file) -> None:
    """
    Heatmap: one row per team (sorted by average wins, best first), one
    column per possible final win count (0..total_games), cell = % of
    simulations in which that team finished with that many wins (summed
    across whatever the loss count works out to, since wins+losses is
    always total_games with no ties possible under a continuous draw).
    """
    teams = list(record_counts.keys())

    win_counts = {t: np.zeros(total_games + 1) for t in teams}
    for t, records in record_counts.items():
        for (w, l), count in records.items():
            win_counts[t][w] += count

    avg_wins = {t: sum(w * c for w, c in enumerate(win_counts[t])) / n_simulations for t in teams}
    teams_sorted = sorted(teams, key=lambda t: -avg_wins[t])

    n = len(teams_sorted)
    data = np.zeros((n, total_games + 1))
    for i, t in enumerate(teams_sorted):
        data[i] = win_counts[t] / n_simulations * 100

    fig, ax = plt.subplots(figsize=(16, 0.55 * n + 2))
    im = ax.imshow(data, aspect="auto", cmap="viridis")

    ax.set_xticks(range(total_games + 1))
    ax.set_xticklabels([f"{w}-{total_games - w}" for w in range(total_games + 1)], rotation=45, ha="right")
    ax.set_yticks(range(n))
    ax.set_yticklabels([f"{t} (avg {avg_wins[t]:.1f}-{total_games - avg_wins[t]:.1f})" for t in teams_sorted])

    for i in range(n):
        for j in range(total_games + 1):
            val = data[i, j]
            if val >= 0.5:
                ax.text(j, i, f"{val:.0f}", ha="center", va="center", fontsize=7,
                         color="white" if val < 40 else "black")

    cbar = plt.colorbar(im, ax=ax)
    cbar.set_label("% of simulations")

    completed_label = _week_range_label(completed_weeks)
    simulated_label = _week_range_label(simulated_weeks)

    ax.set_xlabel("Final record (wins-losses)")
    ax.set_title(f"Final Record Distribution -- {n_simulations:,} simulated seasons "
                 f"(weeks {completed_label} actual + weeks {simulated_label} simulated)")

    plt.tight_layout()
    plt.savefig(out_file, dpi=220, bbox_inches="tight")
    plt.close()


def plot_average_weekly_points(real_points_by_week: dict, lineup_means: dict,
                                completed_weeks: list, simulated_weeks: list,
                                teams: list, out_file) -> None:
    """
    Heatmap: one row per team, one column per week of the season (actual
    score for already-played weeks, projected optimal lineup total for
    the rest), cell value = that team's points that week. Deterministic
    -- no Monte Carlo needed, since these are just real scores plus the
    lineup totals.

    Teams are sorted by season-long average points, best first.
    """
    all_weeks = completed_weeks + simulated_weeks

    def points_for_week(team, week):
        if week in real_points_by_week:
            return real_points_by_week[week].get(team, 0.0)
        return lineup_means[week][team]

    points = {t: [points_for_week(t, w) for w in all_weeks] for t in teams}
    avg_points = {t: float(np.mean(points[t])) for t in teams}
    teams_sorted = sorted(teams, key=lambda t: -avg_points[t])

    n = len(teams_sorted)
    data = np.array([points[t] for t in teams_sorted])

    fig, ax = plt.subplots(figsize=(1.1 * len(all_weeks) + 3, 0.5 * n + 2))
    im = ax.imshow(data, aspect="auto", cmap="YlGn")

    ax.set_xticks(range(len(all_weeks)))
    ax.set_xticklabels([f"Wk {w}" for w in all_weeks])
    ax.set_yticks(range(n))
    ax.set_yticklabels([f"{t} (avg {avg_points[t]:.1f})" for t in teams_sorted])

    vmax = data.max()
    for i in range(n):
        for j in range(len(all_weeks)):
            val = data[i, j]
            ax.text(j, i, f"{val:.1f}", ha="center", va="center", fontsize=7,
                     color="white" if val > 0.6 * vmax else "black")

    cbar = plt.colorbar(im, ax=ax)
    cbar.set_label("Points")

    completed_label = _week_range_label(completed_weeks)
    simulated_label = _week_range_label(simulated_weeks)

    ax.set_xlabel("Week")
    ax.set_title(f"Average Points Per Week (weeks {completed_label} actual, "
                 f"weeks {simulated_label} projected optimal lineup)")

    plt.tight_layout()
    plt.savefig(out_file, dpi=220, bbox_inches="tight")
    plt.close()


def plot_playoff_odds(bye_counts: dict, playoff_counts: dict, punishment_counts: dict,
                       n_simulations: int, bye_spots: int, playoff_spots: int,
                       punishment_spots: int, out_file) -> None:
    """
    Horizontal bar chart: for each team, % of simulations it landed in
    each of three tiers -- first-round bye (top `bye_spots` seeds),
    playoffs without a bye (next `playoff_spots` seeds), and the
    punishment bracket (bottom `punishment_spots` seeds). Teams sorted by
    combined bye+playoff odds, best first.
    """
    teams = list(playoff_counts.keys())
    bye_pct = {t: bye_counts[t] / n_simulations * 100 for t in teams}
    playoff_pct = {t: playoff_counts[t] / n_simulations * 100 for t in teams}
    punishment_pct = {t: punishment_counts[t] / n_simulations * 100 for t in teams}

    teams_sorted = sorted(teams, key=lambda t: -(bye_pct[t] + playoff_pct[t]))
    n = len(teams_sorted)
    y = np.arange(n)

    fig, ax = plt.subplots(figsize=(10, 0.5 * n + 2))

    bar_height = 0.26
    ax.barh(y + bar_height, [bye_pct[t] for t in teams_sorted],
            height=bar_height, color="#1b4332", label=f"First-round bye (top {bye_spots})")
    ax.barh(y, [playoff_pct[t] for t in teams_sorted],
            height=bar_height, color="#2b8a3e",
            label=f"Playoffs, no bye (seeds {bye_spots + 1}-{bye_spots + playoff_spots})")
    ax.barh(y - bar_height, [punishment_pct[t] for t in teams_sorted],
            height=bar_height, color="#c92a2a", label=f"Punishment bracket (bottom {punishment_spots})")

    for i, t in enumerate(teams_sorted):
        ax.text(bye_pct[t] + 1, i + bar_height, f"{bye_pct[t]:.0f}%", va="center", fontsize=8)
        ax.text(playoff_pct[t] + 1, i, f"{playoff_pct[t]:.0f}%", va="center", fontsize=8)
        ax.text(punishment_pct[t] + 1, i - bar_height, f"{punishment_pct[t]:.0f}%", va="center", fontsize=8)

    ax.set_yticks(y)
    ax.set_yticklabels(teams_sorted)
    ax.invert_yaxis()
    ax.set_xlim(0, 105)
    ax.set_xlabel("% of simulations")
    ax.set_title(f"Playoff / Punishment Bracket Odds -- {n_simulations:,} simulated seasons")
    ax.legend(loc="lower right")
    ax.grid(axis="x", alpha=0.3)

    plt.tight_layout()
    plt.savefig(out_file, dpi=220, bbox_inches="tight")
    plt.close()


def run_simulate_matchups(league, start_week: int = None, end_week: int = SIM_END_WEEK,
                           n_simulations: int = SIM_N_SIMULATIONS, variance: float = SIM_VARIANCE,
                           bye_spots: int = SIM_BYE_SPOTS, playoff_spots: int = SIM_PLAYOFF_SPOTS,
                           punishment_spots: int = SIM_PUNISHMENT_SPOTS, seed: int = None) -> None:
    """Entry point for the season-simulation step (formerly simulate_matchups.py's main())."""
    completed_weeks = get_completed_weeks(league)
    start_week = start_week if start_week is not None else league.current_week()
    weeks = list(range(start_week, end_week + 1))

    print(f"\nYahoo current week: {league.current_week()}. "
          f"Treating weeks {completed_weeks or 'none'} as already played.")

    print("Fetching real results so far from Yahoo...")
    real_records = get_real_records(league)
    real_points_by_week = get_real_points_by_week(league, completed_weeks)
    teams = list(real_records.keys())
    points_so_far = get_total_points_so_far(real_points_by_week, teams)
    for t, (w, l) in real_records.items():
        print(f"  {t:<32} {w}-{l}  ({points_so_far.get(t, 0):.2f} pts so far)")

    print(f"\nLoading lineup projections for weeks {weeks}...")
    lineup_means = load_lineup_means(weeks)

    print(f"Loading schedule for weeks {weeks}...")
    schedule = load_schedule(weeks)

    total_games = len(completed_weeks) + len(weeks)
    print(f"\nRunning {n_simulations:,} simulations of weeks {weeks[0]}-{weeks[-1]} "
          f"(final records will be out of {total_games} games)...")

    results = simulate_season(
        teams, real_records, points_so_far, lineup_means, schedule, weeks,
        n_simulations=n_simulations, variance=variance,
        bye_spots=bye_spots, playoff_spots=playoff_spots,
        punishment_spots=punishment_spots, seed=seed,
    )
    record_counts = results["record_counts"]
    bye_counts = results["bye_counts"]
    playoff_counts = results["playoff_counts"]
    punishment_counts = results["punishment_counts"]

    serializable = {
        team: {f"{w}-{l}": count for (w, l), count in records.items()}
        for team, records in record_counts.items()
    }
    with open(RECORD_DISTRIBUTION_JSON, "w") as f:
        json.dump(serializable, f, indent=2)
    print(f"\nSaved raw distribution -> {RECORD_DISTRIBUTION_JSON}")

    plot_record_distribution(record_counts, n_simulations, total_games,
                              completed_weeks, weeks, RECORD_DISTRIBUTION_IMAGE)
    print(f"Saved chart -> {RECORD_DISTRIBUTION_IMAGE}")

    plot_average_weekly_points(real_points_by_week, lineup_means, completed_weeks,
                                weeks, teams, WEEKLY_POINTS_IMAGE)
    print(f"Saved chart -> {WEEKLY_POINTS_IMAGE}")

    plot_playoff_odds(bye_counts, playoff_counts, punishment_counts, n_simulations,
                       bye_spots, playoff_spots, punishment_spots, PLAYOFF_ODDS_IMAGE)
    print(f"Saved chart -> {PLAYOFF_ODDS_IMAGE}")

    avg_summary = []
    for t, records in record_counts.items():
        avg_w = sum(w * c for (w, l), c in records.items()) / n_simulations
        avg_l = total_games - avg_w
        avg_summary.append((t, avg_w, avg_l))
    avg_summary.sort(key=lambda x: -x[1])

    print("\n=== Average final record (sorted) ===")
    for t, avg_w, avg_l in avg_summary:
        pct_bye = bye_counts[t] / n_simulations * 100
        pct_playoff = playoff_counts[t] / n_simulations * 100
        pct_punish = punishment_counts[t] / n_simulations * 100
        print(f"  {t:<32} {avg_w:5.2f}-{avg_l:5.2f}   "
              f"bye {pct_bye:5.1f}%   playoffs(no bye) {pct_playoff:5.1f}%   punishment {pct_punish:5.1f}%")


def main():
    write_week_files(lg, OUTPUT_DIR=MATCHUP_DATA_DIR)
    calculate_earned_wins(data_directory=MATCHUP_DATA_DIR, output_directory=CURRENT_SEASON_DATA_DIR)
    run_draft_par(lg)
    run_simulate_matchups(lg)

main()
