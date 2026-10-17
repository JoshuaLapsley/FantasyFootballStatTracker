"""
Draft value analysis: fit a non-increasing (isotonic) "expected WAR by
overall pick" curve from past seasons, then compare each season's
actual picks against that curve to see which picks outperformed/
underperformed history.

--------------------------------------------------------------------------
METHOD
--------------------------------------------------------------------------
1. Pool every drafted player's (pick, WAR) pair from every COMPLETED
   historical season (2023/2024/2025 -- see ALL_HISTORICAL_YEARS
   below). "Pick" here is overall pick number (1, 2, 3, ... across all
   rounds), not round number -- pooling raw overall pick number across
   seasons is an approximation since league size changed between
   2023/2024 (12 teams) and 2025 (14 teams), but overall pick number
   still meaningfully captures "how early was this player taken"
   regardless of team count.

2. Fit `IsotonicRegression(increasing=False)` on those pooled (pick,
   WAR) pairs. This solves exactly the "non-increasing least squares
   fit" the user described -- it's the standard pool-adjacent-violators
   solution, so no hand-rolled optimizer is needed. The result is a
   step function: expected_war(pick) for any pick from 1 up to the
   largest pick seen in training data.

3. For picks beyond the training data's max pick, the fitted curve is
   extended flat at its last fitted value (isotonic regression's own
   out_of_bounds="clip" behavior), since a non-increasing curve's most
   defensible extrapolation past the last observed pick is "no higher
   than the last observed step."

4. Every COMPLETED historical season (2023/2024/2025) is scored against
   the SAME single curve -- fit once, pooling all three historical
   seasons together -- rather than a separate fit per year. Each
   season's surplus is therefore partly self-referential (e.g. 2024's
   own data did influence the curve it's compared against), which is
   a deliberate choice: this keeps "expected WAR at pick N" consistent
   and comparable across every rendered image (2023, 2024, 2025, and
   2026 all read off the exact same curve).

5. The CURRENT, in-progress season (2026) is scored against the same fit
   trained on all three historical seasons, but with the expected-WAR
   curve PRORATED by (weeks completed so far / full regular season
   length) before subtracting from actual WAR. This matters because
   WAR is a season-SUM stat: comparing a handful of completed weeks'
   actual WAR against a full-season expectation would make every pick
   look artificially bad early in the season, since actual hasn't had
   time to accumulate yet. Prorating assumes WAR accrues roughly evenly
   week to week (the same assumption implicit in every other week-by-
   week stat this codebase tracks -- no stronger assumption than that
   is being introduced here).

--------------------------------------------------------------------------
OUTPUTS
--------------------------------------------------------------------------
Data (all under draftData/):
  isotonic_expected_war_by_pick.json
      {pick: expected_war} from the ALL-historical-years fit (used for
      2026's comparison), plus fit metadata.
  draft_value_2026.json
      one row per 2026 drafted player: {pick, round, player_name,
      position, actual_war, expected_war_full_season,
      expected_war_prorated, weeks_completed, full_season_weeks,
      surplus_war (actual - prorated expected)}, sorted by pick.
  draft_value_{year}.json  (for each of 2023/2024/2025)
      one row per drafted player: {pick, round, player_name, position,
      actual_war, expected_war, surplus_war}, sorted by pick --
      expected_war here comes from the single all-historical-years fit
      (same curve used for every year, including 2026).

Images (default folder: Website/girderma-gridiron-website/src/
league_stats_output/CurrentSeason/DraftBoards/SurplusWar/ -- override
with run_draft_value(output_directory=...) or --output-dir):
  draft_board_regressed_expected_war.png (+ _colorbar)
      2026-shaped draft board grid, each cell colored/labeled by the
      ALL-historical-years fitted curve's expected WAR for that pick
      slot (full season basis, i.e. "what a full season at this pick
      slot is historically worth").
  draft_board_2026_surplus_war.png (+ _colorbar)
      2026's real draft board, colored/labeled by actual WAR minus
      PRORATED expected WAR (fair mid-season comparison).
  draft_board_by_war_{year}.png (+ _colorbar)  for year in 2023,2024,2025
      that season's real draft board, colored/labeled by actual
      season-sum WAR (same visual convention as CalculateWAR.py's live
      board).
  draft_board_surplus_war_{year}.png (+ _colorbar)  for year in 2023,2024,2025
      that season's real draft board, colored/labeled by actual WAR
      minus expected WAR from the single all-historical-years isotonic
      fit (same curve as everywhere else in this script).

Usage:
    python3 CalculateDraftValue.py
    python3 CalculateDraftValue.py --output-dir /some/other/folder

From another file (e.g. RunWeekly.py), reusing an already-authenticated league:
    from CalculateDraftValue import run_draft_value
    run_draft_value(league=lg)                          # default image folder
    run_draft_value(league=lg, output_directory="...")  # custom image folder
"""

import argparse
import json
import os
from pathlib import Path

import numpy as np
from sklearn.isotonic import IsotonicRegression

from yahoo_oauth import OAuth2
import yahoo_fantasy_api as yfa

import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt

import shutil


# --------------------------------------------------------------------------
# CONFIG
# --------------------------------------------------------------------------
ALL_HISTORICAL_YEARS = [2023, 2024, 2025]   # completed seasons, used (pooled) to fit curves
EVAL_YEAR = 2026                             # in-progress season, excluded from every fit

# Same year -> league_id map as CalculateHistoricalWAR.py / CalculateWAR.py.
LEAGUE_IDS = {
    2023: "423.l.902802",
    2024: "449.l.106896",
    2025: "461.l.111150",
    2026: "470.l.205662",
}

SCRIPT_DIR = os.path.dirname(os.path.abspath(__file__))
PYTHON_DATA_DIR = Path(SCRIPT_DIR) / ".."
DRAFT_DATA_DIR = PYTHON_DATA_DIR / "draftData"
OAUTH_FILE = str(PYTHON_DATA_DIR / "oauth2.json")

# Default destination for every image this script writes. Callers can
# override it per run via run_draft_value(output_directory=...) or the
# --output-dir command-line flag.
DEFAULT_IMAGE_DIR = (
    Path(SCRIPT_DIR) / ".." / ".." / "Website" / "girderma-gridiron-website"
    / "src" / "league_stats_output" / "CurrentSeason" / "DraftBoards" / "SurplusWar"
).resolve()

EXPECTED_WAR_JSON_PATH = DRAFT_DATA_DIR / "isotonic_expected_war_by_pick.json"
DRAFT_VALUE_2026_PATH = DRAFT_DATA_DIR / "draft_value_2026.json"

DEFAULT_TEXT_COLOR = "#374151"


# --------------------------------------------------------------------------
# LOAD POOLED TRAINING DATA
# --------------------------------------------------------------------------
def load_war_rows(year: int) -> list:
    path = DRAFT_DATA_DIR / f"war_{year}.json"
    with open(path, "r") as f:
        return json.load(f)


def load_training_pairs(years: list) -> tuple:
    """Returns (picks, wars) arrays pooled across every year in `years`."""
    picks, wars = [], []
    for year in years:
        rows = load_war_rows(year)
        for r in rows:
            picks.append(r["pick"])
            wars.append(r["war"])
        print(f"[train] {year}: {len(rows)} picks loaded")
    return np.array(picks, dtype=float), np.array(wars, dtype=float)


# --------------------------------------------------------------------------
# FIT ISOTONIC REGRESSION
# --------------------------------------------------------------------------
def fit_isotonic(picks: np.ndarray, wars: np.ndarray) -> IsotonicRegression:
    """
    Non-increasing least-squares fit of WAR as a function of overall
    pick number -- i.e. the earlier the pick, the higher (or equal)
    its expected WAR must be. out_of_bounds="clip" means picks beyond
    the training range reuse the nearest-boundary fitted value rather
    than extrapolating/erroring.
    """
    model = IsotonicRegression(increasing=False, out_of_bounds="clip")
    model.fit(picks, wars)
    return model


def expected_war_by_pick(model: IsotonicRegression, max_pick: int) -> dict:
    all_picks = np.arange(1, max_pick + 1, dtype=float)
    predicted = model.predict(all_picks)
    return {int(p): float(w) for p, w in zip(all_picks, predicted)}


# --------------------------------------------------------------------------
# SEASON PROGRESS (for prorating 2026's comparison -- see module
# docstring point 5)
# --------------------------------------------------------------------------
def get_season_progress(year: int, league=None) -> tuple:
    """
    Returns (weeks_completed, full_season_weeks) for the given year's
    Yahoo league. If `league` is passed in, it's reused as-is (no new
    OAuth session); otherwise this authenticates fresh (same OAuth
    pattern as CalculateHistoricalWAR.py). weeks_completed matches
    CalculateWAR.py's determine_weeks_to_process (every week strictly
    before league.current_week()); full_season_weeks is
    playoff_start_week - 1 (the regular season's last week).
    """
    if league is None:
        sc = OAuth2(None, None, from_file=OAUTH_FILE)
        gm = yfa.Game(sc, "nfl")
        league = gm.to_league(LEAGUE_IDS[year])

    weeks_completed = league.current_week() - 1
    settings = league.settings()
    full_season_weeks = int(settings.get("playoff_start_week", 15)) - 1

    return weeks_completed, full_season_weeks


# --------------------------------------------------------------------------
# BOARD GRID (same convention as CalculateWAR.py's build_board_grid)
# --------------------------------------------------------------------------
def build_board_grid(board: list) -> tuple:
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
                 cell_label_fn, title: str, output_path) -> None:
    """Identical grid-drawing routine to CalculateWAR.py's _draw_board."""
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

    fig.tight_layout()
    Path(output_path).parent.mkdir(parents=True, exist_ok=True)
    fig.savefig(output_path, dpi=200, bbox_inches="tight")
    plt.close(fig)
    print(f"Saved -> {output_path}")


def _save_diverging_colorbar(blues, reds, value_min: float, value_max: float,
                              label: str, image_path: Path) -> None:
    """Same diverging-colorbar routine as CalculateWAR.py's render_war_board."""
    n_stops = 256
    blue_half = [blues(1.0 - i / (n_stops // 2 - 1)) for i in range(n_stops // 2)]
    red_half = [reds(i / (n_stops // 2 - 1)) for i in range(n_stops // 2)]
    diverging_cmap = matplotlib.colors.ListedColormap(blue_half + red_half)

    fig, ax = plt.subplots(figsize=(6, 0.6))
    fig.subplots_adjust(bottom=0.5)
    norm_ = matplotlib.colors.Normalize(vmin=value_min, vmax=value_max)
    cb = matplotlib.colorbar.ColorbarBase(ax, cmap=diverging_cmap, norm=norm_, orientation="horizontal")
    cb.set_label(label, fontsize=9)
    colorbar_path = Path(image_path).with_name(Path(image_path).stem + "_colorbar.png")
    colorbar_path.parent.mkdir(parents=True, exist_ok=True)
    fig.savefig(colorbar_path, dpi=200, bbox_inches="tight")
    plt.close(fig)
    print(f"Saved -> {colorbar_path}")


# --------------------------------------------------------------------------
# GENERIC DIVERGING BOARD RENDERER (shared by every board image below --
# each caller just supplies a per-pick value function + label function)
# --------------------------------------------------------------------------
def render_diverging_board(board: list, value_fn, label_fn, title: str, output_path: Path,
                            colorbar_label: str) -> None:
    rounds, columns, cell_by_round_and_team = build_board_grid(board)

    values = [value_fn(p) for p in cell_by_round_and_team.values()]
    v_max = max((v for v in values if v > 0), default=1.0) or 1.0
    v_min = min((v for v in values if v < 0), default=-1.0) or -1.0

    reds = matplotlib.colormaps["Reds"]
    blues = matplotlib.colormaps["Blues"]

    def intensity(value: float) -> float:
        if value >= 0:
            return value / v_max if v_max else 0.0
        return value / v_min if v_min else 0.0

    def cell_color(pick):
        if pick is None:
            return "#FFFFFF"
        value = value_fn(pick)
        t = intensity(value)
        return reds(t) if value >= 0 else blues(t)

    def text_color(pick):
        if pick is None:
            return DEFAULT_TEXT_COLOR
        value = value_fn(pick)
        return "#FFFFFF" if intensity(value) > 0.6 else "#111827"

    Path(output_path).parent.mkdir(parents=True, exist_ok=True)
    _draw_board(
        rounds, columns, cell_by_round_and_team,
        cell_color_fn=cell_color,
        text_color_fn=text_color,
        cell_label_fn=label_fn,
        title=title,
        output_path=output_path,
    )
    _save_diverging_colorbar(blues, reds, v_min, v_max, colorbar_label, output_path)


# --------------------------------------------------------------------------
# IMAGE: regressed/expected WAR board (2026-shaped grid, cells colored
# by the fitted curve's expected WAR for that pick slot, full-season basis)
# --------------------------------------------------------------------------
def render_regressed_board(board_2026: list, expected_by_pick: dict, output_directory) -> None:
    render_diverging_board(
        board_2026,
        value_fn=lambda pick: expected_by_pick.get(pick["pick"], 0.0),
        label_fn=lambda pick: f"#{pick['pick']}  {expected_by_pick.get(pick['pick'], 0.0):+.3f}\n(expected)",
        title=f"Expected WAR by Draft Slot (isotonic fit, {ALL_HISTORICAL_YEARS[0]}-{ALL_HISTORICAL_YEARS[-1]}, full season)",
        output_path=Path(output_directory) / "draft_board_regressed_expected_war.png",
        colorbar_label="Expected WAR, full season (negative -> positive)",
    )


# --------------------------------------------------------------------------
# IMAGE: 2026 surplus board (actual WAR - PRORATED expected WAR)
# --------------------------------------------------------------------------
def render_surplus_board_2026(board_2026: list, war_by_id_2026: dict, expected_by_pick_prorated: dict,
                               weeks_completed: int, full_season_weeks: int, output_directory) -> None:
    def surplus_for(pick):
        actual = war_by_id_2026.get(pick["player_id"], 0.0)
        expected = expected_by_pick_prorated.get(pick["pick"], 0.0)
        return actual - expected

    render_diverging_board(
        board_2026,
        value_fn=surplus_for,
        label_fn=lambda pick: f"#{pick['pick']}  {surplus_for(pick):+.3f}\n{pick['player_name']}",
        title=(f"{EVAL_YEAR} Draft Board -- Actual WAR minus Expected WAR "
               f"(vs. {ALL_HISTORICAL_YEARS[0]}-{ALL_HISTORICAL_YEARS[-1]} isotonic fit, "
               f"prorated to {weeks_completed}/{full_season_weeks} weeks)"),
        output_path=Path(output_directory) / "draft_board_2026_surplus_war.png",
        colorbar_label="Surplus WAR: actual - prorated expected (negative -> positive)",
    )


# --------------------------------------------------------------------------
# IMAGE: a completed historical season's actual WAR board (same visual
# convention as CalculateWAR.py's live render_war_board)
# --------------------------------------------------------------------------
def render_actual_war_board(board: list, war_by_id: dict, year: int, output_directory) -> None:
    output_path = Path(output_directory) / f"draft_board_by_war_{year}.png"
    render_diverging_board(
        board,
        value_fn=lambda pick: war_by_id.get(pick["player_id"], 0.0),
        label_fn=lambda pick: f"#{pick['pick']}  {war_by_id.get(pick['player_id'], 0.0):+.3f}\n{pick['player_name']}",
        title=f"{year} Draft Board -- Wins Above Replacement (WAR)",
        output_path=output_path,
        colorbar_label="WAR (negative -> positive)",
    )


# --------------------------------------------------------------------------
# IMAGE: a completed historical season's surplus board (actual WAR minus
# the single all-historical-years isotonic fit's expected WAR -- same
# curve used for every year, including 2026)
# --------------------------------------------------------------------------
def render_surplus_board_historical(board: list, war_by_id: dict, expected_by_pick: dict,
                                     year: int, output_directory) -> None:
    def surplus_for(pick):
        actual = war_by_id.get(pick["player_id"], 0.0)
        expected = expected_by_pick.get(pick["pick"], 0.0)
        return actual - expected

    output_path = Path(output_directory) / f"draft_board_surplus_war_{year}.png"
    render_diverging_board(
        board,
        value_fn=surplus_for,
        label_fn=lambda pick: f"#{pick['pick']}  {surplus_for(pick):+.3f}\n{pick['player_name']}",
        title=f"{year} Draft Board -- Actual WAR minus Expected WAR (vs. {ALL_HISTORICAL_YEARS[0]}-{ALL_HISTORICAL_YEARS[-1]} isotonic fit)",
        output_path=output_path,
        colorbar_label="Surplus WAR: actual - expected (negative -> positive)",
    )


def load_board(year: int) -> list:
    path = DRAFT_DATA_DIR / f"draft_{year}.json"
    with open(path, "r") as f:
        return json.load(f)


def print_top_bottom(draft_value_rows: list, year: int) -> None:
    print(f"\nTop 10 surplus picks ({year}, actual - expected WAR):")
    for r in sorted(draft_value_rows, key=lambda r: r["surplus_war"], reverse=True)[:10]:
        print(f"  Pick {r['pick']:>3}  {r['player_name']:<26} "
              f"actual={r['actual_war']:+.3f}  expected={r['expected_war']:+.3f}  "
              f"surplus={r['surplus_war']:+.3f}")

    print(f"\nBottom 10 surplus picks ({year}, actual - expected WAR):")
    for r in sorted(draft_value_rows, key=lambda r: r["surplus_war"])[:10]:
        print(f"  Pick {r['pick']:>3}  {r['player_name']:<26} "
              f"actual={r['actual_war']:+.3f}  expected={r['expected_war']:+.3f}  "
              f"surplus={r['surplus_war']:+.3f}")


# --------------------------------------------------------------------------
# ORCHESTRATION
# --------------------------------------------------------------------------
def run_draft_value(league=None, output_directory=DEFAULT_IMAGE_DIR) -> None:
    """
    Entry point (also callable from another file).

    league: an already-authenticated 2026 Yahoo league (e.g. RunWeekly's
        `lg`) to reuse for season-progress lookups. If omitted, this
        authenticates on its own.
    output_directory: folder every image (and its _colorbar twin) is
        written to. Defaults to DEFAULT_IMAGE_DIR (CurrentSeason/
        DraftBoards/SurplusWar). Created automatically if missing.
    """
    output_directory = Path(output_directory)
    output_directory.mkdir(parents=True, exist_ok=True)
    DRAFT_DATA_DIR.mkdir(parents=True, exist_ok=True)

    # ----------------------------------------------------------------
    # PART 1: 2026 vs. all-historical-years fit, prorated
    # ----------------------------------------------------------------
    picks_all, wars_all = load_training_pairs(ALL_HISTORICAL_YEARS)
    print(f"Pooled {len(picks_all)} (pick, WAR) pairs from {ALL_HISTORICAL_YEARS} for the isotonic fit.")
    model_all = fit_isotonic(picks_all, wars_all)

    board_2026 = load_board(EVAL_YEAR)
    max_pick_2026 = max(p["pick"] for p in board_2026)
    expected_by_pick_full = expected_war_by_pick(model_all, max_pick_2026)

    with open(EXPECTED_WAR_JSON_PATH, "w") as f:
        json.dump({
            "training_years": ALL_HISTORICAL_YEARS,
            "n_training_points": len(picks_all),
            "expected_war_by_pick": expected_by_pick_full,
        }, f, indent=2)
    print(f"Saved -> {EXPECTED_WAR_JSON_PATH}")

    weeks_completed, full_season_weeks = get_season_progress(EVAL_YEAR, league=league)
    proration = (weeks_completed / full_season_weeks) if full_season_weeks else 0.0
    print(f"[{EVAL_YEAR}] Season progress: {weeks_completed}/{full_season_weeks} weeks "
          f"(proration factor = {proration:.3f})")
    expected_by_pick_prorated = {pick: war * proration for pick, war in expected_by_pick_full.items()}

    war_rows_2026 = load_war_rows(EVAL_YEAR)
    war_by_id_2026 = {r["player_id"]: r["war"] for r in war_rows_2026}

    draft_value_rows_2026 = []
    for p in board_2026:
        actual = war_by_id_2026.get(p["player_id"], 0.0)
        expected_full = expected_by_pick_full.get(p["pick"], 0.0)
        expected_prorated = expected_by_pick_prorated.get(p["pick"], 0.0)
        draft_value_rows_2026.append({
            "pick": p["pick"],
            "round": p["round"],
            "player_id": p["player_id"],
            "player_name": p["player_name"],
            "position": p["position"],
            "drafted_by": p.get("team_name"),
            "actual_war": actual,
            "expected_war_full_season": expected_full,
            "expected_war_prorated": expected_prorated,
            "weeks_completed": weeks_completed,
            "full_season_weeks": full_season_weeks,
            # kept as "expected_war"/"surplus_war" too (prorated basis)
            # so this file's shape matches the historical draft_value_
            # {year}.json files for anyone consuming both generically.
            "expected_war": expected_prorated,
            "surplus_war": actual - expected_prorated,
        })
    draft_value_rows_2026.sort(key=lambda r: r["pick"])
    with open(DRAFT_VALUE_2026_PATH, "w") as f:
        json.dump(draft_value_rows_2026, f, indent=2)

    shutil.copy2(
        DRAFT_VALUE_2026_PATH,
        Path(SCRIPT_DIR) / ".." / ".." / "Website" / "girderma-gridiron-website"
        / "src" / "league_stats_output" / "CurrentSeason"
        / "draft_value_2026.json"
    )
    print(f"Saved -> {DRAFT_VALUE_2026_PATH}")

    render_regressed_board(board_2026, expected_by_pick_full, output_directory)
    render_surplus_board_2026(board_2026, war_by_id_2026, expected_by_pick_prorated,
                               weeks_completed, full_season_weeks, output_directory)
    print_top_bottom(draft_value_rows_2026, EVAL_YEAR)

    # ----------------------------------------------------------------
    # PART 2: each completed historical season -- actual WAR board,
    # plus a surplus board vs. the SAME all-historical-years isotonic
    # fit used for 2026 (expected_by_pick_full from Part 1 above; no
    # per-year/leave-one-out refitting).
    # ----------------------------------------------------------------
    war_rows_by_year = {year: load_war_rows(year) for year in ALL_HISTORICAL_YEARS}

    for year in ALL_HISTORICAL_YEARS:
        board = load_board(year)
        war_by_id = {r["player_id"]: r["war"] for r in war_rows_by_year[year]}

        render_actual_war_board(board, war_by_id, year, output_directory)

        draft_value_rows_year = []
        for p in board:
            actual = war_by_id.get(p["player_id"], 0.0)
            expected = expected_by_pick_full.get(p["pick"], 0.0)
            draft_value_rows_year.append({
                "pick": p["pick"],
                "round": p["round"],
                "player_id": p["player_id"],
                "player_name": p["player_name"],
                "position": p["position"],
                "drafted_by": p.get("team_name"),
                "actual_war": actual,
                "expected_war": expected,
                "surplus_war": actual - expected,
            })
        draft_value_rows_year.sort(key=lambda r: r["pick"])
        out_path = DRAFT_DATA_DIR / f"draft_value_{year}.json"
        with open(out_path, "w") as f:
            json.dump(draft_value_rows_year, f, indent=2)
        print(f"Saved -> {out_path}")

        render_surplus_board_historical(board, war_by_id, expected_by_pick_full, year, output_directory)
        print_top_bottom(draft_value_rows_year, year)


def main():
    parser = argparse.ArgumentParser(description="Fit isotonic expected-WAR-by-pick curve and render draft value boards.")
    parser.add_argument("--output-dir", default=str(DEFAULT_IMAGE_DIR),
                         help="Folder for the draft board images (default: "
                              "CurrentSeason/DraftBoards/SurplusWar).")
    args = parser.parse_args()

    run_draft_value(output_directory=args.output_dir)


if __name__ == "__main__":
    main()