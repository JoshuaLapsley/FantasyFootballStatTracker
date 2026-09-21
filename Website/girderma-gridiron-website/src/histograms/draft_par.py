"""
Calculates each drafted player's Points Above Replacement (PAR) for the
2026 Girderma Gridiron season, then prints a draft board (in real draft
order) showing name, position, and PAR for every pick.

--------------------------------------------------------------------------
WHAT "PAR" MEANS HERE
--------------------------------------------------------------------------
Replacement level (per position, season-long flat baseline):
    QB = 15, RB = 5, WR = 7, TE = 6, K = 7, DEF = 5

For every week a drafted player could have played:
  * If Yahoo's PRE-GAME projection for that player/week was ABOVE their
    position's replacement level, the player is credited with their
    ACTUAL points scored that week (even if the actual came in under
    replacement -- the projection is what gates it, not the outcome).
  * If the projection was AT/BELOW replacement level, OR the player did
    not play at all that week (bye/inactive/not on an NFL roster yet),
    the player is credited with replacement level for that week instead.
  * A player's PAR for the season is the sum of (points credited that
    week - replacement level) across all processed weeks.

--------------------------------------------------------------------------
WEEK 1 SPECIAL CASE
--------------------------------------------------------------------------
Yahoo's API only exposes a player's pregame projection for weeks that
haven't finished yet -- once a week is final, Yahoo overwrites that
value with the actual box score and the original projection is gone for
good (confirmed live against this league: querying player_stats for an
already-completed week returns actuals, not the pregame number).

Since week 1 of 2026 was already final by the time this script was
written, there is no way to recover what Yahoo projected for it. Week 1
is therefore handled with a fallback rule instead of the normal
projection-gated rule:
  * If a player played in week 1 at all, they're credited their ACTUAL
    week 1 points (no replacement-level gating, since we have nothing to
    gate against).
  * If a player did NOT play at all in week 1 (bye/inactive), they're
    credited replacement level for that week, same as normal weeks.

--------------------------------------------------------------------------
THE PROJECTION CACHE (why it exists / how it works)
--------------------------------------------------------------------------
Because pregame projections disappear once a week finalizes, this script
snapshots them into a small JSON cache file (PROJECTION_CACHE_PATH) the
first time it sees a not-yet-final week. Every subsequent run reuses the
cached number for that week instead of re-querying Yahoo (which would
just return the now-final actual score).

This means: run the script once per week *before* that week's games
start (or anytime before Yahoo marks it final) to capture the real
projection. If a week is skipped entirely -- final before ever being
cached -- PAR simply can't be computed properly for it, and it will be
reported as skipped rather than silently guessed at.

--------------------------------------------------------------------------
0.0 SCORES ARE FLAGGED FOR MANUAL REVIEW, NOT AUTO-GUESSED
--------------------------------------------------------------------------
Yahoo's player_stats response has no explicit "played" flag, so there's
no clean automatic way to tell "played and scored a genuine zero" apart
from "was inactive/didn't play." Bye weeks are unambiguous (Yahoo tells
us those directly) and are always treated as DNP automatically.

For every OTHER 0.0 score, this script does NOT guess. Instead it
records the player/week in ZERO_SCORE_REVIEW_PATH with "played": null and
prints a NEEDS REVIEW list at the end of the run. Until you edit that
file and set "played" to true or false for an entry, that player/week is
treated as a DNP (replacement level) by default -- edit the file and
re-run to correct it once you know the real answer.

--------------------------------------------------------------------------
USAGE
--------------------------------------------------------------------------
    python3 draft_par.py

Requires PythonData/oauth2.json (Yahoo OAuth credentials) to already
exist and be valid -- this script does not set up OAuth itself.

Files it reads/writes (all under PythonData/draftData/):
  draft_{YEAR}.json                  cached draft board (delete to refresh)
  par_projection_cache_{YEAR}.json   cached pregame projections per week
  par_zero_score_review_{YEAR}.json  manual "did they actually play?" log

It also writes two images into this same src/histograms/ folder:
  draft_board_by_position_{YEAR}.png   grid colored by player position
  draft_board_by_par_{YEAR}.png        grid colored by PAR: red gradient
                                        for positive PAR (darker = higher),
                                        blue gradient for negative PAR
                                        (darker = more negative)
"""

from __future__ import annotations

import json
import os
from pathlib import Path

import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt
import numpy as np

from yahoo_oauth import OAuth2
import yahoo_fantasy_api as yfa

# --------------------------------------------------------------------------
# CONFIG
# --------------------------------------------------------------------------
YEAR = 2026
LEAGUE_ID = "470.l.205662"  # Girderma Gridiron, confirmed live against gm.league_ids()

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

# --------------------------------------------------------------------------
# PATHS
# --------------------------------------------------------------------------
SCRIPT_DIR = Path(__file__).resolve().parent

PYTHON_DATA_DIR = (
    SCRIPT_DIR / ".." / ".." / ".." / ".." / "PythonData"
).resolve()

OAUTH_FILE = PYTHON_DATA_DIR / "oauth2.json"
DRAFT_CACHE_PATH = PYTHON_DATA_DIR / "draftData" / f"draft_{YEAR}.json"
PROJECTION_CACHE_PATH = PYTHON_DATA_DIR / "draftData" / f"par_projection_cache_{YEAR}.json"
ZERO_SCORE_REVIEW_PATH = PYTHON_DATA_DIR / "draftData" / f"par_zero_score_review_{YEAR}.json"

POSITION_BOARD_IMAGE_PATH = SCRIPT_DIR / f"draft_board_by_position_{YEAR}.png"
PAR_BOARD_IMAGE_PATH = SCRIPT_DIR / f"draft_board_by_par_{YEAR}.png"


# --------------------------------------------------------------------------
# YAHOO CONNECTION
# --------------------------------------------------------------------------
def get_league():
    if not OAUTH_FILE.exists():
        raise FileNotFoundError(
            f"Could not find Yahoo OAuth credentials at {OAUTH_FILE}. "
            "This script expects the same oauth2.json already used by the "
            "other PythonData scripts."
        )
    sc = OAuth2(None, None, from_file=str(OAUTH_FILE))
    gm = yfa.Game(sc, "nfl")
    return gm.to_league(LEAGUE_ID)


# --------------------------------------------------------------------------
# DRAFT DATA
# --------------------------------------------------------------------------
def load_draft_board(league) -> list[dict]:
    """
    Returns the 2026 draft in real pick order, each entry enriched with
    player name/position. Cached to disk since player_details() for 210
    picks is a non-trivial batch of API calls we don't want to redo every
    run.
    """
    if DRAFT_CACHE_PATH.exists():
        with open(DRAFT_CACHE_PATH, "r") as f:
            return json.load(f)

    print(f"Pulling {YEAR} draft results from Yahoo...")
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
# PROJECTION CACHE
# --------------------------------------------------------------------------
def load_projection_cache() -> dict:
    if PROJECTION_CACHE_PATH.exists():
        with open(PROJECTION_CACHE_PATH, "r") as f:
            return json.load(f)
    return {}


def save_projection_cache(cache: dict) -> None:
    PROJECTION_CACHE_PATH.parent.mkdir(parents=True, exist_ok=True)
    with open(PROJECTION_CACHE_PATH, "w") as f:
        json.dump(cache, f, indent=2)


def snapshot_projections_if_needed(league, week: int, player_ids: list[str], cache: dict) -> None:
    """
    If we don't already have cached projections for this week, pull them
    now via player_stats(). This only produces a real PREGAME projection
    if `week` hasn't finished yet -- once Yahoo marks a week final, this
    same call just returns actuals, so callers should only invoke this
    for weeks they know (or suspect) are still upcoming.
    """
    week_key = str(week)
    if week_key in cache:
        return

    print(f"  Snapshotting week {week} pregame projections ({len(player_ids)} players)...")
    week_cache = {}
    batch_size = 25  # matches league.player_stats()'s internal batching
    for i in range(0, len(player_ids), batch_size):
        batch = [int(pid) for pid in player_ids[i:i + batch_size]]
        stats = league.player_stats(batch, "week", week=week)
        for row in stats:
            pid = str(row.get("player_id"))
            try:
                pts = float(row.get("total_points", 0.0))
            except (TypeError, ValueError):
                pts = 0.0
            week_cache[pid] = pts

    cache[week_key] = week_cache
    save_projection_cache(cache)


# --------------------------------------------------------------------------
# ACTUAL STATS
# --------------------------------------------------------------------------
def fetch_actuals_for_week(league, player_ids: list[str], week: int) -> dict:
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


def save_zero_score_review(review: dict) -> None:
    ZERO_SCORE_REVIEW_PATH.parent.mkdir(parents=True, exist_ok=True)
    with open(ZERO_SCORE_REVIEW_PATH, "w") as f:
        json.dump(review, f, indent=2)


def player_did_not_play(
    actual_points: float | None,
    bye_week: int | None,
    week: int,
    player: dict,
    review: dict,
    needs_review: list,
) -> bool:
    """
    Determines whether a player should be treated as DNP (credited
    replacement level) for a given week.

    Bye weeks are unambiguous and handled automatically. Any other 0.0
    score is NOT auto-guessed -- it's looked up in the zero-score review
    log (ZERO_SCORE_REVIEW_PATH). If it's not in there yet, an entry is
    added with "played": null, it's added to needs_review for this run's
    printout, and it defaults to DNP (replacement level) until you edit
    the log and set "played" to true/false yourself.
    """
    if bye_week is not None and bye_week == week:
        return True
    if actual_points is None:
        return True
    if actual_points != 0.0:
        return False

    # Actual score is exactly 0.0 and it's not a bye -- needs a human call.
    week_key = str(week)
    pid = player["player_id"]
    week_review = review.setdefault(week_key, {})

    if pid not in week_review:
        week_review[pid] = {
            "name": player["player_name"],
            "position": player["position"],
            "played": None,
        }

    entry = week_review[pid]
    if entry.get("played") is None:
        needs_review.append((week, player["player_name"], player["position"], pid))
        return True  # default to DNP until manually resolved

    # "played": true  -> they played and genuinely scored 0 -> NOT a DNP.
    # "played": false -> confirmed DNP.
    return not entry["played"]


# --------------------------------------------------------------------------
# PAR CALCULATION
# --------------------------------------------------------------------------
def determine_weeks_to_process(league) -> tuple[list[int], int]:
    """
    Returns (weeks_with_final_actuals, current_week). Only weeks strictly
    before the league's current week are treated as final/played.
    """
    current_week = league.current_week()
    final_weeks = list(range(1, current_week))
    return final_weeks, current_week


def calculate_par(league, board: list[dict]) -> tuple[dict, list[int], list[int], list]:
    """
    Returns (par_by_player_id, weeks_used, weeks_skipped, needs_review).

    weeks_used: weeks that actually contributed to PAR this run.
    weeks_skipped: weeks that were final but had no cached projection
    (and aren't week 1, which has its own fallback) -- these can't be
    scored under the normal rule and are excluded rather than guessed at.
    needs_review: (week, player_name, position, player_id) tuples for
    every 0.0-score/non-bye case that hasn't been manually resolved yet
    in the zero-score review log.
    """
    player_ids = [p["player_id"] for p in board]
    board_by_id = {p["player_id"]: p for p in board}
    position_by_id = {p["player_id"]: p["position"] for p in board}

    final_weeks, current_week = determine_weeks_to_process(league)
    print(f"Current week per Yahoo: {current_week}. Final/played weeks: {final_weeks or 'none yet'}")

    # Snapshot the projection for the *upcoming* week too (if there is
    # one), so it's captured before those games happen and is ready for
    # next run once that week finalizes.
    upcoming_week = current_week
    print(f"Caching pregame projections for upcoming week {upcoming_week} (for future runs)...")
    projection_cache = load_projection_cache()
    snapshot_projections_if_needed(league, upcoming_week, player_ids, projection_cache)

    zero_score_review = load_zero_score_review()
    needs_review = []

    par_by_id = {pid: 0.0 for pid in player_ids}
    weeks_used = []
    weeks_skipped = []

    for week in final_weeks:
        if week == 1:
            # No recoverable pregame projection for week 1 -- fallback
            # rule: actual points if played, replacement level if DNP.
            print(f"Processing week {week} (fallback rule: no projection available)...")
            actuals = fetch_actuals_for_week(league, player_ids, week)
            for p in board:
                pid = p["player_id"]
                pos = position_by_id[pid]
                replacement = REPLACEMENT_LEVEL.get(pos)
                if replacement is None:
                    continue
                actual = actuals.get(pid)
                dnp = player_did_not_play(
                    actual, p["bye_week"], week, p, zero_score_review, needs_review
                )
                credited = replacement if dnp else actual
                par_by_id[pid] += credited - replacement
            weeks_used.append(week)
            continue

        week_key = str(week)
        if week_key not in projection_cache:
            print(f"  No cached projection for week {week} (it finalized before ever being "
                  f"snapshotted) -- skipping this week for PAR.")
            weeks_skipped.append(week)
            continue

        print(f"Processing week {week} (projection-gated rule)...")
        projections = projection_cache[week_key]
        actuals = fetch_actuals_for_week(league, player_ids, week)

        for p in board:
            pid = p["player_id"]
            pos = position_by_id[pid]
            replacement = REPLACEMENT_LEVEL.get(pos)
            if replacement is None:
                continue

            actual = actuals.get(pid)
            dnp = player_did_not_play(
                actual, p["bye_week"], week, p, zero_score_review, needs_review
            )
            if dnp:
                continue  # credited == replacement -> contributes 0 to PAR

            projection = projections.get(pid, 0.0)
            credited = actual if projection > replacement else replacement
            par_by_id[pid] += credited - replacement

        weeks_used.append(week)

    save_zero_score_review(zero_score_review)

    return par_by_id, weeks_used, weeks_skipped, needs_review


# --------------------------------------------------------------------------
# DRAFT BOARD DISPLAY
# --------------------------------------------------------------------------
def print_needs_review(needs_review: list) -> None:
    if not needs_review:
        return
    print()
    print("=" * 72)
    print(f"NEEDS REVIEW -- {len(needs_review)} player/week(s) scored exactly 0.0")
    print("(not a bye week, so it's unclear if they were inactive or truly")
    print("played and scored zero). Currently defaulted to DNP (replacement")
    print(f"level). Edit {ZERO_SCORE_REVIEW_PATH.name} and set \"played\": true")
    print("or false for these entries, then re-run to apply your answer.")
    print("=" * 72)
    for week, name, pos, pid in needs_review:
        print(f"  Week {week}  {name:<26} {(pos or '?'):<4} (player_id {pid})")


def print_draft_board(board: list[dict], par_by_id: dict, weeks_used: list[int], weeks_skipped: list[int]) -> None:
    print()
    print("=" * 72)
    print(f"{YEAR} DRAFT BOARD -- Points Above Replacement (PAR)")
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
def build_board_grid(board: list[dict]) -> tuple[list[int], list[dict], dict]:
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
    rounds: list[int],
    columns: list[dict],
    cell_by_round_and_team: dict,
    cell_color_fn,
    text_color_fn,
    cell_label_fn,
    title: str,
    output_path: Path,
    legend_handles: list | None = None,
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

    _draw_board(
        rounds, columns, cell_by_round_and_team,
        cell_color_fn=cell_color,
        text_color_fn=text_color,
        cell_label_fn=label,
        title=f"{YEAR} Draft Board -- by Position",
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

    _draw_board(
        rounds, columns, cell_by_round_and_team,
        cell_color_fn=cell_color,
        text_color_fn=text_color,
        cell_label_fn=label,
        title=f"{YEAR} Draft Board -- Points Above Replacement (PAR)",
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


# --------------------------------------------------------------------------
# MAIN
# --------------------------------------------------------------------------
def main():
    league = get_league()
    board = load_draft_board(league)
    par_by_id, weeks_used, weeks_skipped, needs_review = calculate_par(league, board)
    print_draft_board(board, par_by_id, weeks_used, weeks_skipped)
    print_needs_review(needs_review)

    rounds, columns, cell_by_round_and_team = build_board_grid(board)
    render_position_board(rounds, columns, cell_by_round_and_team)
    render_par_board(rounds, columns, cell_by_round_and_team, par_by_id)


if __name__ == "__main__":
    main()
