"""
Calculate WAR for every team's waiver-wire / free-agent pickups, for
one or more seasons -- i.e. every player a team rostered who was NOT
drafted by that team and NOT acquired via trade, with WAR summed only
over the specific weeks that player was actually on that team's
roster (not the player's whole season).

Uses the exact same WAR formula/constants as CalculateWAR.py /
CalculateHistoricalWAR.py (Phi((P-D_relative)/MARGIN_SIGMA) win-
probability-added, see CalculateWAR.py's module docstring for the full
derivation) -- this script only changes WHICH weeks get summed per
player, and adds a layer to identify which players/weeks even count as
a "pickup" in the first place.

--------------------------------------------------------------------------
WHAT COUNTS AS A "WAIVER PICKUP" HERE (per user's explicit answers)
--------------------------------------------------------------------------
- A (team, player) pair counts if that player appears on that team's
  roster in some week, AND that player was NOT drafted by that same
  team (checked against draftData/draft_{YEAR}.json).
- Trade acquisitions are explicitly EXCLUDED (per user instruction):
  any week where a player's presence on a team's roster was the direct
  result of a trade (per the `trade-transactions.json` feed) does not
  count toward that team's pickup WAR for that player. In practice this
  means: if a player was ever traded TO a team, the weeks starting from
  that trade (until the next drop/trade-away) are excluded for that
  team, even if the player was also later re-added via waivers by the
  same team (which WOULD count).
- If a player bounces between teams during a season (dropped, picked
  up by someone else, re-added by the original team, etc.), each
  team's stint is scored independently using only that team's own
  rostered weeks (user's choice 2a) -- a player can appear under
  multiple teams' columns in the same season if this happens.
- Short-lived stashes that are added and dropped quickly, or that never
  score real points, are still included (user's choice 3) -- no
  minimum-weeks-rostered filter.

--------------------------------------------------------------------------
HOW TEAM-BY-WEEK ROSTER OWNERSHIP IS DETERMINED
--------------------------------------------------------------------------
Rather than parsing the transactions feed's add/drop timestamps (fragile:
inconsistent dict/list shapes, no week numbers, multiple re-adds), this
script directly reconstructs "who had player X in week N" by pulling
every team's FULL roster (every slot, including bench/IR -- NOT just
starters) for every week via team.roster(week=N), the same call
CalculateWAR.py's fetch_starters_for_week already makes but without
filtering out BN/IR. This naturally handles multi-stint players
correctly with no timestamp bucketing needed. The transactions feed is
still used, but only for its trade records (to know which team-player-
week combinations were trade-driven rather than waiver-driven).

Results are cached per year to draftData/full_rosters_by_week_{YEAR}.json
so repeat runs don't re-pull from Yahoo.

--------------------------------------------------------------------------
OUTPUTS
--------------------------------------------------------------------------
Data:
  draftData/full_rosters_by_week_{YEAR}.json
      {week: {team_key: [player_id, ...]}} -- full roster (every slot)
      snapshot per team per week, cached so Yahoo isn't re-queried on
      every run.
  draftData/waiver_war_{YEAR}.json
      one row per (team, pickup player) pair: {team_key, drafted_by
      (manager/team display name), player_id, player_name, position,
      weeks_rostered, war} sorted by team then WAR descending.

Images (into Website/girderma-gridiron-website/src/histograms/):
  waiver_war_board_{YEAR}.png (+ _colorbar)
      one column per team (same team order as that year's draft board),
      one cell per waiver pickup that team made that season, sorted
      top-to-bottom by WAR descending, colored by WAR (same diverging
      red/blue scheme as every other board in this codebase).

Usage:
    python3 CalculateWaiverWAR.py                   # runs 2023-2026
    python3 CalculateWaiverWAR.py --years 2025
    python3 CalculateWaiverWAR.py --years 2025 --force-refresh-rosters
"""

import argparse
import json
import os
from pathlib import Path

import numpy as np

from yahoo_oauth import OAuth2
import yahoo_fantasy_api as yfa

import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt

# Reuse the exact same formula constants/helpers as the live + historical
# WAR scripts, so waiver WAR stays on an identical scale.
from CalculateWAR import (
    REPLACEMENT_LEVEL,
    POSITION_ALIASES,
    NON_STARTER_SLOTS,
    player_did_not_play,
    calculate_position_averages,
    win_probability_added,
)


# --------------------------------------------------------------------------
# CONFIG
# --------------------------------------------------------------------------
LEAGUE_IDS = {
    2023: "423.l.902802",
    2024: "449.l.106896",
    2025: "461.l.111150",
    2026: "470.l.205662",
}
DEFAULT_YEARS = [2023, 2024, 2025, 2026]

SCRIPT_DIR = os.path.dirname(os.path.abspath(__file__))
PYTHON_DATA_DIR = Path(SCRIPT_DIR) / ".."
DRAFT_DATA_DIR = PYTHON_DATA_DIR / "draftData"
OAUTH_FILE = str(PYTHON_DATA_DIR / "oauth2.json")

HISTOGRAMS_DIR = (
    Path(SCRIPT_DIR) / ".." / ".." / "Website" / "girderma-gridiron-website"
    / "src" / "histograms"
).resolve()

DEFAULT_TEXT_COLOR = "#374151"


def full_rosters_cache_path(year: int) -> Path:
    return DRAFT_DATA_DIR / f"full_rosters_by_week_{year}.json"


def waiver_war_output_path(year: int) -> Path:
    return DRAFT_DATA_DIR / f"waiver_war_{year}.json"


def draft_cache_path(year: int) -> Path:
    return DRAFT_DATA_DIR / f"draft_{year}.json"


# --------------------------------------------------------------------------
# AUTH
# --------------------------------------------------------------------------
def get_league(year: int):
    league_id = LEAGUE_IDS.get(year)
    if not league_id:
        raise ValueError(f"No Yahoo league id configured for {year}.")
    sc = OAuth2(None, None, from_file=OAUTH_FILE)
    gm = yfa.Game(sc, "nfl")
    return gm.to_league(league_id)


# --------------------------------------------------------------------------
# WEEK RANGE (completed-season-safe for 2023-2025, current-week-safe for 2026)
# --------------------------------------------------------------------------
def determine_weeks_to_process(league, year: int) -> list:
    if year == 2026:
        return list(range(1, league.current_week()))
    settings = league.settings()
    playoff_start = int(settings.get("playoff_start_week", 15))
    return list(range(1, playoff_start))


# --------------------------------------------------------------------------
# DRAFT BOARD (reused as-is if cached -- see CalculateWAR.py/
# CalculateHistoricalWAR.py's load_draft_board for the enrichment logic
# this cache was originally built with)
# --------------------------------------------------------------------------
def load_draft_board(league, year: int) -> list:
    cache_path = draft_cache_path(year)
    if cache_path.exists():
        with open(cache_path, "r") as f:
            return json.load(f)
    raise FileNotFoundError(
        f"{cache_path} not found. Run CalculateWAR.py (2026) or "
        f"CalculateHistoricalWAR.py --years {year} first to build the draft board cache."
    )


# --------------------------------------------------------------------------
# FULL ROSTER SNAPSHOTS (every slot, including bench/IR -- unlike
# CalculateWAR.py's fetch_starters_for_week which excludes BN/IR/IR+/NA)
# --------------------------------------------------------------------------
def fetch_full_roster_for_week(league, week: int) -> dict:
    """
    Returns {team_key: [{"player_id": str, "selected_position": str}, ...]}
    -- every player on each team's roster this week, regardless of
    selected_position, WITH selected_position included so callers can
    derive starters (selected_position not in NON_STARTER_SLOTS)
    without a second round-trip to Yahoo (see compute_league_position_
    averages, which used to re-fetch this same data separately -- that
    doubled call volume per week and contributed to tripping Yahoo's
    rate limiting).
    """
    rosters = {}
    teams_info = league.teams()
    for team_key in teams_info:
        team = yfa.Team(league.sc, team_key)
        try:
            roster = team.roster(week=week)
        except Exception as e:
            print(f"  \u26a0 could not fetch roster for {team_key} (week {week}): {e}")
            continue
        rosters[team_key] = [
            {"player_id": str(p.get("player_id")), "selected_position": p.get("selected_position")}
            for p in roster
        ]
    return rosters


def load_full_rosters_by_week(league, year: int, weeks: list, force_refresh: bool = False) -> dict:
    """Returns {week: {team_key: [{"player_id", "selected_position"}, ...]}}, cached to disk."""
    cache_path = full_rosters_cache_path(year)
    if cache_path.exists() and not force_refresh:
        with open(cache_path, "r") as f:
            raw = json.load(f)
        return {int(week): teams for week, teams in raw.items()}

    rosters_by_week = {}
    for week in weeks:
        print(f"[{year}] Fetching full rosters (all slots) for week {week}...")
        rosters_by_week[week] = fetch_full_roster_for_week(league, week)

    DRAFT_DATA_DIR.mkdir(parents=True, exist_ok=True)
    with open(cache_path, "w") as f:
        json.dump(rosters_by_week, f, indent=2)
    print(f"[{year}] Saved -> {cache_path}")

    return rosters_by_week


# --------------------------------------------------------------------------
# TRADES (to exclude trade-acquired team-player-weeks from "pickups")
# --------------------------------------------------------------------------
def fetch_trade_transactions(league) -> list:
    try:
        return league.transactions("trade", "")
    except Exception as e:
        print(f"  \u26a0 could not fetch trade transactions: {e}")
        return []


def _normalize_transaction_data(raw) -> list:
    """transaction_data is sometimes a dict, sometimes a one-element
    list, in this feed -- normalize to a list of dicts."""
    if raw is None:
        return []
    if isinstance(raw, dict):
        return [raw]
    if isinstance(raw, list):
        return raw
    return []


def build_trade_acquired_team_player_pairs(league, year: int) -> set:
    """
    Returns a set of (destination_team_key, player_id) pairs that were
    ever acquired via trade at some point this season. Used as a coarse
    exclusion filter: ANY week that player was on that team's roster
    gets excluded from that team's pickup WAR, even weeks before/after
    the trade, since this script has no reliable way to timestamp-map
    trades to exact weeks (see module docstring) and erring toward
    excluding too much here is safer than crediting a trade as a
    "waiver pickup".
    """
    trades = fetch_trade_transactions(league)
    pairs = set()
    for tx in trades:
        if tx.get("type") != "trade":
            continue
        players = tx.get("players", {})
        for key, entry in players.items():
            if key == "count":
                continue
            player_blob = entry.get("player", [])
            if len(player_blob) < 2:
                continue
            meta_list, tx_data_holder = player_blob[0], player_blob[1]
            pid = None
            for meta in meta_list:
                if "player_id" in meta:
                    pid = str(meta["player_id"])
                    break
            if pid is None:
                continue
            tx_data_list = _normalize_transaction_data(tx_data_holder.get("transaction_data"))
            for tx_data in tx_data_list:
                dest_team_key = tx_data.get("destination_team_key")
                if dest_team_key:
                    pairs.add((dest_team_key, pid))

    print(f"[{year}] {len(pairs)} (team, player) pairs excluded as trade-acquired.")
    return pairs


# --------------------------------------------------------------------------
# IDENTIFY PICKUPS: (team_key, player_id) -> list of weeks rostered,
# excluding drafted-by-that-team and trade-acquired-by-that-team
# --------------------------------------------------------------------------
def identify_pickups(board: list, rosters_by_week: dict, trade_pairs: set) -> dict:
    """
    Returns {(team_key, player_id): [weeks rostered by that team]}.
    """
    drafted_pairs = {(p["team_key"], p["player_id"]) for p in board}

    weeks_by_team_player = {}
    for week, teams in rosters_by_week.items():
        for team_key, players in teams.items():
            for player in players:
                pid = player["player_id"]
                weeks_by_team_player.setdefault((team_key, pid), []).append(week)

    pickups = {}
    for (team_key, pid), weeks in weeks_by_team_player.items():
        if (team_key, pid) in drafted_pairs:
            continue
        if (team_key, pid) in trade_pairs:
            continue
        pickups[(team_key, pid)] = sorted(weeks)

    return pickups


# --------------------------------------------------------------------------
# PLAYER METADATA for non-drafted players (position, bye_week) --
# needed because credited_points_for_week-style logic requires this,
# and waiver pickups aren't on the draft board.
# --------------------------------------------------------------------------
def enrich_player_metadata(league, player_ids: list) -> dict:
    """Returns {player_id: {"position": str|None, "bye_week": int|None,
    "player_name": str|None}}, via league.player_details() batched."""
    metadata = {}
    batch_size = 25
    unique_ids = sorted(set(player_ids))
    for i in range(0, len(unique_ids), batch_size):
        batch = unique_ids[i:i + batch_size]
        try:
            details_list = league.player_details([int(pid) for pid in batch])
        except Exception as e:
            print(f"  \u26a0 could not fetch player_details for batch starting {batch[0]}: {e}")
            continue
        for d in details_list:
            pid = str(d.get("player_id"))
            position = d.get("display_position") or d.get("primary_position")
            position = POSITION_ALIASES.get(position, position)

            name = d.get("name", {})
            player_name = name.get("full") if isinstance(name, dict) else name

            bye_week = None
            bye_info = d.get("bye_weeks")
            if isinstance(bye_info, dict) and bye_info.get("week"):
                try:
                    bye_week = int(bye_info["week"])
                except (TypeError, ValueError):
                    bye_week = None

            metadata[pid] = {"position": position, "bye_week": bye_week, "player_name": player_name}
    return metadata


# --------------------------------------------------------------------------
# ACTUALS (same batched call as CalculateWAR.py's fetch_actuals_for_week)
# --------------------------------------------------------------------------
def fetch_actuals_for_week(league, player_ids: list, week: int) -> dict:
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
# D (POSITION AVERAGES) -- league-wide baseline, computed the same way
# as CalculateWAR.py (every real starter, every week), NOT scoped to
# pickups -- this is deliberately a whole-league constant. Derives
# starters directly from the already-fetched full-roster snapshots
# (rosters_by_week) instead of re-querying Yahoo's team.roster()
# endpoint a second time per team per week, which doubled this script's
# call volume and contributed to tripping Yahoo's rate limiting.
# --------------------------------------------------------------------------
def compute_league_position_averages(league, year: int, weeks: list, rosters_by_week: dict) -> tuple:
    starters_by_week = {}
    all_player_ids_seen = set()

    for week in weeks:
        starters = set()
        for team_key, players in rosters_by_week.get(week, {}).items():
            for player in players:
                pid = player["player_id"]
                all_player_ids_seen.add(pid)
                if player.get("selected_position") in NON_STARTER_SLOTS:
                    continue
                starters.add(pid)
        starters_by_week[week] = starters

    position_metadata = enrich_player_metadata(league, list(all_player_ids_seen))
    pseudo_board = [{"player_id": pid, "position": meta["position"]}
                     for pid, meta in position_metadata.items()]

    actuals_by_week = {}
    for week in weeks:
        print(f"[{year}] Fetching actuals for league-wide D (week {week})...")
        actuals_by_week[week] = fetch_actuals_for_week(league, list(all_player_ids_seen), week)

    return calculate_position_averages(pseudo_board, weeks, starters_by_week, actuals_by_week), \
        position_metadata, actuals_by_week


# --------------------------------------------------------------------------
# WAIVER WAR CALCULATION -- scoped to only the weeks each team actually
# rostered each pickup
# --------------------------------------------------------------------------
def calculate_waiver_war(league, year: int, board: list, pickups: dict, rosters_by_week: dict) -> list:
    weeks = determine_weeks_to_process(league, year)

    position_averages, player_metadata_cache, actuals_by_week = compute_league_position_averages(
        league, year, weeks, rosters_by_week
    )
    print(f"[{year}] D (raw points) by position: "
          f"{ {pos: round(d, 2) for pos, d in position_averages.items()} }")

    position_averages_relative = {
        pos: d - REPLACEMENT_LEVEL[pos]
        for pos, d in position_averages.items()
        if pos in REPLACEMENT_LEVEL
    }

    team_name_by_key = {}
    for p in board:
        team_name_by_key[p["team_key"]] = p.get("manager_nickname") or p.get("team_name") or p["team_key"]
    # Pickups may belong to teams with zero draft picks represented in
    # `board` only if the whole league drafted (shouldn't happen), but
    # guard anyway by falling back to league.teams() if needed.
    missing_team_keys = {team_key for (team_key, _pid) in pickups if team_key not in team_name_by_key}
    if missing_team_keys:
        teams_info = league.teams()
        for team_key in missing_team_keys:
            team_name_by_key[team_key] = teams_info.get(team_key, {}).get("name", team_key)

    rows = []
    zero_score_review = {}  # no manual review log for pickups; same safe DNP default as historical WAR

    for (team_key, pid), weeks_rostered in pickups.items():
        meta = player_metadata_cache.get(pid)
        if meta is None:
            meta = enrich_player_metadata(league, [pid]).get(pid)
        if meta is None:
            continue
        position = meta.get("position")
        if position not in REPLACEMENT_LEVEL:
            continue
        replacement = REPLACEMENT_LEVEL[position]
        bye_week = meta.get("bye_week")
        d_relative = position_averages_relative.get(position)
        if d_relative is None:
            continue

        pseudo_player = {
            "player_id": pid,
            "player_name": meta.get("player_name") or pid,
            "bye_week": bye_week,
        }

        war_total = 0.0
        for week in weeks_rostered:
            actual = actuals_by_week.get(week, {}).get(pid)
            dnp = player_did_not_play(actual, bye_week, week, pseudo_player, zero_score_review)
            credited = replacement if dnp else actual
            p_above_replacement = credited - replacement
            war_total += win_probability_added(p_above_replacement, d_relative)

        rows.append({
            "team_key": team_key,
            "drafted_by": team_name_by_key.get(team_key, team_key),
            "player_id": pid,
            "player_name": meta.get("player_name") or pid,
            "position": position,
            "weeks_rostered": weeks_rostered,
            "war": war_total,
        })

    rows.sort(key=lambda r: (r["drafted_by"], -r["war"]))
    return rows


# --------------------------------------------------------------------------
# IMAGE: waiver WAR board -- one column per team, pickups sorted by WAR
# descending top-to-bottom, colored by WAR
# --------------------------------------------------------------------------
def render_waiver_war_board(rows: list, board: list, year: int) -> None:
    # Column order: same convention as the draft board (each team's
    # round-1 pick order), falling back to alphabetical for any team
    # key seen only via pickups (shouldn't normally happen).
    round1_picks = sorted((p for p in board if p["round"] == 1), key=lambda p: p["pick"])
    columns = [
        {"team_key": p["team_key"], "label": p.get("manager_nickname") or p["team_name"]}
        for p in round1_picks
    ]
    known_team_keys = {c["team_key"] for c in columns}
    extra_team_keys = sorted({r["team_key"] for r in rows if r["team_key"] not in known_team_keys})
    for team_key in extra_team_keys:
        label = next((r["drafted_by"] for r in rows if r["team_key"] == team_key), team_key)
        columns.append({"team_key": team_key, "label": label})

    rows_by_team = {}
    for r in rows:
        rows_by_team.setdefault(r["team_key"], []).append(r)
    for team_key in rows_by_team:
        rows_by_team[team_key].sort(key=lambda r: r["war"], reverse=True)

    max_pickups = max((len(v) for v in rows_by_team.values()), default=0)
    if max_pickups == 0:
        print(f"[{year}] No waiver pickups found -- skipping board image.")
        return

    all_war_values = [r["war"] for r in rows]
    v_max = max((v for v in all_war_values if v > 0), default=1.0) or 1.0
    v_min = min((v for v in all_war_values if v < 0), default=-1.0) or -1.0

    reds = matplotlib.colormaps["Reds"]
    blues = matplotlib.colormaps["Blues"]

    def intensity(value: float) -> float:
        if value >= 0:
            return value / v_max if v_max else 0.0
        return value / v_min if v_min else 0.0

    n_rows = max_pickups
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

    for col_idx, col in enumerate(columns):
        team_rows = rows_by_team.get(col["team_key"], [])
        for row_idx in range(n_rows):
            x, y = col_idx, row_idx
            if row_idx < len(team_rows):
                r = team_rows[row_idx]
                war = r["war"]
                t = intensity(war)
                face_color = reds(t) if war >= 0 else blues(t)
            else:
                face_color = "#FFFFFF"

            rect = plt.Rectangle(
                (x, y), 1, 1,
                facecolor=face_color,
                edgecolor="white",
                linewidth=1.5,
            )
            ax.add_patch(rect)

            if row_idx >= len(team_rows):
                continue

            r = team_rows[row_idx]
            text_color = "#FFFFFF" if intensity(r["war"]) > 0.6 else "#111827"
            n_weeks = len(r["weeks_rostered"])
            label = f"{r['war']:+.3f}\n{r['player_name']}\n({n_weeks}wk)"
            ax.text(
                x + 0.5, y + 0.5, label,
                ha="center", va="center", fontsize=7.2, color=text_color, linespacing=1.3,
            )

    ax.set_title(f"{year} Waiver Wire / Free Agent Pickup WAR (scoped to weeks rostered)",
                 fontsize=15, fontweight="bold", color="#111827", pad=36)

    fig.tight_layout()
    HISTOGRAMS_DIR.mkdir(parents=True, exist_ok=True)
    output_path = HISTOGRAMS_DIR / f"waiver_war_board_{year}.png"
    fig.savefig(output_path, dpi=200, bbox_inches="tight")
    plt.close(fig)
    print(f"Saved -> {output_path}")

    n_stops = 256
    blue_half = [blues(1.0 - i / (n_stops // 2 - 1)) for i in range(n_stops // 2)]
    red_half = [reds(i / (n_stops // 2 - 1)) for i in range(n_stops // 2)]
    diverging_cmap = matplotlib.colors.ListedColormap(blue_half + red_half)

    fig2, ax2 = plt.subplots(figsize=(6, 0.6))
    fig2.subplots_adjust(bottom=0.5)
    norm_ = matplotlib.colors.Normalize(vmin=v_min, vmax=v_max)
    cb = matplotlib.colorbar.ColorbarBase(ax2, cmap=diverging_cmap, norm=norm_, orientation="horizontal")
    cb.set_label("WAR, scoped to weeks rostered (negative -> positive)", fontsize=9)
    colorbar_path = output_path.with_name(output_path.stem + "_colorbar.png")
    fig2.savefig(colorbar_path, dpi=200, bbox_inches="tight")
    plt.close(fig2)
    print(f"Saved -> {colorbar_path}")


# --------------------------------------------------------------------------
# ORCHESTRATION
# --------------------------------------------------------------------------
def run_year(year: int, force_refresh_rosters: bool = False) -> None:
    print(f"\n{'=' * 72}\n{year} WAIVER WAR\n{'=' * 72}")
    league = get_league(year)
    board = load_draft_board(league, year)
    weeks = determine_weeks_to_process(league, year)
    print(f"[{year}] Weeks to process: {weeks}")

    rosters_by_week = load_full_rosters_by_week(league, year, weeks, force_refresh=force_refresh_rosters)
    trade_pairs = build_trade_acquired_team_player_pairs(league, year)
    pickups = identify_pickups(board, rosters_by_week, trade_pairs)
    print(f"[{year}] {len(pickups)} (team, player) waiver/FA pickup pairs identified.")

    rows = calculate_waiver_war(league, year, board, pickups, rosters_by_week)

    out_path = waiver_war_output_path(year)
    DRAFT_DATA_DIR.mkdir(parents=True, exist_ok=True)
    with open(out_path, "w") as f:
        json.dump(rows, f, indent=2)
    print(f"[{year}] Saved -> {out_path} ({len(rows)} pickup rows)")

    render_waiver_war_board(rows, board, year)

    print(f"\nTop 10 waiver pickups ({year}, by WAR):")
    for r in sorted(rows, key=lambda r: r["war"], reverse=True)[:10]:
        print(f"  {r['drafted_by']:<22} {r['player_name']:<24} "
              f"war={r['war']:+.3f}  weeks={r['weeks_rostered']}")


def main():
    parser = argparse.ArgumentParser(description="Calculate waiver-wire/FA pickup WAR per team.")
    parser.add_argument("--years", type=int, nargs="+", default=DEFAULT_YEARS,
                         help=f"Seasons to process (default: {DEFAULT_YEARS})")
    parser.add_argument("--force-refresh-rosters", action="store_true",
                         help="Re-pull full weekly rosters from Yahoo even if a "
                              "full_rosters_by_week_{YEAR}.json cache already exists.")
    args = parser.parse_args()

    for year in args.years:
        run_year(year, force_refresh_rosters=args.force_refresh_rosters)


if __name__ == "__main__":
    main()
