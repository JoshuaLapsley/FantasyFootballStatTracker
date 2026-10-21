"""
Evaluate every completed trade made this season: for each trade, freeze
both sides' rosters at the point the trade actually took effect, then
measure the net point swing each week going forward if each team had
instead kept the player(s) they gave up, instead of the player(s) they
received.

--------------------------------------------------------------------------
WHAT THIS MEASURES
--------------------------------------------------------------------------
For a trade where team A sends {p_out_A...} to team B in exchange for
{p_out_B...} (so A receives p_out_B's players, B receives p_out_A's
players):

  For every week from the trade's "freeze week" (the first week the
  trade could actually have been in effect for -- see find_freeze_week:
  the trade must have cleared on or before that week's FRIDAY
  (week_start + 3 days), AND Yahoo's own roster snapshot for that week
  must confirm both sides already have what they received) through the
  most recently completed week:

    team A's real lineup      = team A's actual roster that week
                                 (includes the player(s) received)
    team A's counterfactual   = team A's roster that week with the
    lineup                      received player(s) swapped back out
                                 for the player(s) they originally gave
                                 up (as if the trade never happened)

    net_gain_A[week] = actual_points(real lineup)
                      - actual_points(counterfactual lineup)

  and the mirror image for team B. The 7 skill-position slots (QB, 2x
  RB, 2x WR, TE, FLEX) are chosen using each team's HIGHEST-PROJECTED
  legal lineup for that week (same rules as
  simulate_season/calculate_lineups.py), but ultimately SCORED using
  actual points, not projections -- a team only benefits/suffers from a
  traded skill-position player if that player would have actually been
  in the optimal (by projection) lineup that week.

  K and DEF are handled differently, per explicit instruction: whichever
  K and DEF a team actually rosters that week is ALWAYS started (no
  projection/"best available" comparison needed -- this league's
  rosters only ever carry exactly one of each, and a manager always
  starts them), scored with their real actual points for any week
  they're active. No projection data is needed or used for K/DEF at
  all.

  If a skill-position slot has no eligible player available (bye week
  or on IR) in either the real or counterfactual roster, or the best
  available player projects below that slot's replacement level, that
  slot falls back to replacement level -- identical rule, same
  constants, applied symmetrically to both the real and counterfactual
  roster. K/DEF fall back to replacement level only if that team has no
  K/DEF rostered that week, or their K/DEF is on a bye that week.

Trades with more than one player per side (e.g. a 2-for-2) are handled
the same way: ALL of a team's received players stay in that team's real
roster, and ALL of them are swapped back out for ALL of the players that
team gave up in the counterfactual roster -- net_gain is still a single
per-team, per-week point swing, just reflecting the whole trade instead
of a single player pair.

--------------------------------------------------------------------------
DATA SOURCES (all read-only, no live scraping performed by this script)
--------------------------------------------------------------------------
  * league.transactions("trade", "") -- which players moved, between
    which teams, and whether the trade actually went through
    (status == "successful"; "vetoed"/"pending" trades are excluded).
  * draftData/full_rosters_by_week_{YEAR}.json (built/refreshed via the
    same loader CalculateWaiverWAR.py uses) -- every team's full roster
    (every slot) for every week. Used to find each trade's actual
    "freeze week" (the first week both sides' received players show up
    on their new team), AND as the only source of which K and which DEF
    each team actually rostered that week (the scraped projections data
    never includes K/DEF at all in this league).
  * league.player_details(ids) -- bye_week lookup for K/DEF player_ids
    only (cached process-wide, since a bye week never changes once the
    schedule is set), used to decide whether a team's rostered K/DEF
    was actually active a given week.
  * simulate_season/projections/week_N.json and
    simulate_season/projections_historical/week_N.json -- Yahoo's own
    scraped per-player PREGAME projection for that team-week (used only
    to decide each week's optimal lineup, exactly like
    calculate_lineups.py). projections/ is checked first (the live,
    regularly-rescraped folder) and projections_historical/ second (the
    permanent once-scraped cache for already-finished weeks -- see
    pull_historical_projections.py); a week missing from both means that
    week can't be evaluated and is skipped with a warning, not silently
    guessed at.
  * league.player_stats(ids, "week", week=N) -- real ACTUAL points for
    the specific players being swapped in/out, used to score both the
    real and counterfactual lineups once their lineups are chosen.

--------------------------------------------------------------------------
OUTPUT
--------------------------------------------------------------------------
draftData/trade_evaluator_{YEAR}.json -- a list of trade records:
    {
      "transaction_id": "...",
      "timestamp": 1790757488,
      "traded_at": "2026-09-29T...",
      "freeze_week": 5,
      "last_week_evaluated": 6,
      "sides": {
        "<team_key>": {
          "team_name": "...",
          "received": [{"player_id", "player_name", "position"}, ...],
          "gave_up": [{"player_id", "player_name", "position"}, ...],
          "weekly_net_gain": {"5": +4.3, "6": -1.1, ...},
          "total_net_gain": 3.2
        },
        "<other_team_key>": { ... mirror image ... }
      },
      "weeks_skipped_no_projection_data": [...]
    }

Usage:
    python3 trade_evaluator.py                 # current (2026) season
    python3 trade_evaluator.py --force-refresh-rosters
"""

import argparse
import json
import os
import sys
from datetime import datetime, timedelta, timezone
from pathlib import Path

from yahoo_oauth import OAuth2
import yahoo_fantasy_api as yfa

# Reuse the exact same roster-snapshot fetcher/cache file
# CalculateWaiverWAR.py already built for this purpose, instead of
# re-implementing team.roster(week=N) pagination/caching a second time.
# NOTE: CalculateWaiverWAR.load_full_rosters_by_week() itself is
# all-or-nothing -- if the cache file exists at all, it's returned as-is
# even if it doesn't cover every week requested (the only other caller,
# CalculateWaiverWAR.py's own run_year(), always calls it with exactly
# the weeks already determined to need (re-)fetching, so this has never
# been an issue there). trade_evaluator.py needs an incrementally-
# extended version instead: it runs independently and the most recently
# finished week is almost always the one week this cache DOESN'T have
# yet, so load_full_rosters_by_week_extended() (below) fetches only
# whatever's missing and merges it into the same on-disk cache.
from CalculateWaiverWAR import fetch_full_roster_for_week, full_rosters_cache_path

# Reuse the exact lineup-optimization + replacement-value rules used
# for the season simulation, so trade evaluation stays consistent with
# every other "optimal legal lineup" calculation in this codebase.
SCRIPT_DIR = os.path.dirname(os.path.abspath(__file__))
SIMULATE_SEASON_DIR = os.path.join(SCRIPT_DIR, "..", "simulate_season")
sys.path.insert(0, SIMULATE_SEASON_DIR)
from calculate_lineups import (  # noqa: E402
    REPLACEMENT_POINTS,
    DEDICATED_SLOTS,
    FLEX_ELIGIBLE_POSITIONS,
)


# --------------------------------------------------------------------------
# CONFIG
# --------------------------------------------------------------------------
YEAR = 2026
LEAGUE_ID = "470.l.205662"  # Girderma Gridiron, 2026 season -- update yearly

PYTHON_DATA_DIR = Path(SCRIPT_DIR) / ".."

WEBSITE_DIR = (
    Path(SCRIPT_DIR) / ".." / ".." / "Website" / "girderma-gridiron-website"
    / "src" / "league_stats_output" / "CurrentSeason"
).resolve()


DRAFT_DATA_DIR = PYTHON_DATA_DIR / "draftData"
OAUTH_FILE = str(PYTHON_DATA_DIR / "oauth2.json")

PROJECTIONS_DIR = Path(SIMULATE_SEASON_DIR) / "projections"
PROJECTIONS_HISTORICAL_DIR = Path(SIMULATE_SEASON_DIR) / "projections_historical"

OUTPUT_PATH = WEBSITE_DIR / f"trade_evaluator_{YEAR}.json"


# --------------------------------------------------------------------------
# AUTH
# --------------------------------------------------------------------------
def get_league(oauth_file: str = OAUTH_FILE, league_id: str = LEAGUE_ID):
    sc = OAuth2(None, None, from_file=oauth_file)
    gm = yfa.Game(sc, "nfl")
    return gm.to_league(league_id)


# --------------------------------------------------------------------------
# FULL ROSTER SNAPSHOTS: incrementally-extended version of
# CalculateWaiverWAR.load_full_rosters_by_week() -- see import comment
# above for why this wrapper exists instead of calling that directly.
# --------------------------------------------------------------------------
def load_full_rosters_by_week_extended(league, year: int, weeks: list,
                                        force_refresh: bool = False) -> dict:
    """Returns {week: {team_key: [{"player_id", "selected_position"}, ...]}}
    for every week in `weeks`, fetching only whichever of those weeks
    aren't already in the on-disk cache (or re-fetching all of them if
    force_refresh=True), then merging the result back into that same
    cache file so other scripts/future runs benefit too."""
    cache_path = full_rosters_cache_path(year)

    cached = {}
    if cache_path.exists() and not force_refresh:
        with open(cache_path, "r") as f:
            raw = json.load(f)
        cached = {int(week): teams for week, teams in raw.items()}

    missing_weeks = [w for w in weeks if w not in cached]
    if missing_weeks:
        print(f"[{year}] Full roster cache missing week(s) {missing_weeks} -- fetching from Yahoo...")
    for week in missing_weeks:
        print(f"[{year}] Fetching full rosters (all slots) for week {week}...")
        cached[week] = fetch_full_roster_for_week(league, week)

    if missing_weeks:
        DRAFT_DATA_DIR.mkdir(parents=True, exist_ok=True)
        with open(cache_path, "w") as f:
            json.dump({str(w): teams for w, teams in sorted(cached.items())}, f, indent=2)
        print(f"[{year}] Saved -> {cache_path}")

    return cached


# --------------------------------------------------------------------------
# TRADES: fetch + parse into per-trade, per-team, per-player moves
# --------------------------------------------------------------------------
def fetch_successful_trades(league) -> list:
    """Returns the raw trade transactions, excluding anything that
    didn't actually go through (vetoed/pending)."""
    try:
        trades = league.transactions("trade", "")
    except Exception as e:
        print(f"  \u26a0 could not fetch trade transactions: {e}")
        return []
    successful = [tx for tx in trades if tx.get("status") == "successful"]
    skipped = [tx for tx in trades if tx.get("status") != "successful"]
    if skipped:
        print(f"Skipping {len(skipped)} non-successful trade(s): "
              f"{[(tx.get('transaction_id'), tx.get('status')) for tx in skipped]}")
    return successful


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


def parse_trade(tx: dict) -> dict:
    """
    Returns {
      "transaction_id": str, "timestamp": int,
      "moves": [{"player_id", "player_name", "position",
                 "from_team_key", "from_team_name",
                 "to_team_key", "to_team_name"}, ...]
    }
    """
    moves = []
    players = tx.get("players", {})
    for key, entry in players.items():
        if key == "count":
            continue
        player_blob = entry.get("player", [])
        if len(player_blob) < 2:
            continue
        meta_list, tx_data_holder = player_blob[0], player_blob[1]

        pid, name, position = None, None, None
        for meta in meta_list:
            if "player_id" in meta:
                pid = str(meta["player_id"])
            if "name" in meta:
                name = meta["name"].get("full")
            if "display_position" in meta:
                position = meta["display_position"]
        if pid is None:
            continue

        tx_data_list = _normalize_transaction_data(tx_data_holder.get("transaction_data"))
        for tx_data in tx_data_list:
            moves.append({
                "player_id": pid,
                "player_name": name,
                "position": position,
                "from_team_key": tx_data.get("source_team_key"),
                "from_team_name": tx_data.get("source_team_name"),
                "to_team_key": tx_data.get("destination_team_key"),
                "to_team_name": tx_data.get("destination_team_name"),
            })

    return {
        "transaction_id": tx.get("transaction_id"),
        "timestamp": int(tx.get("timestamp")) if tx.get("timestamp") else None,
        "moves": moves,
    }


def group_trade_by_side(parsed_trade: dict) -> dict:
    """
    Returns {team_key: {"team_name": str, "received": [move...],
    "gave_up": [move...]}} for the two (or more) teams in this trade.
    "received" = moves where to_team_key == this team. "gave_up" = moves
    where from_team_key == this team (i.e. the players this team sent
    away, which are exactly the OTHER side(s)' "received" list).
    """
    sides = {}

    def ensure_side(team_key, team_name):
        if team_key not in sides:
            sides[team_key] = {"team_name": team_name, "received": [], "gave_up": []}

    for move in parsed_trade["moves"]:
        ensure_side(move["to_team_key"], move["to_team_name"])
        ensure_side(move["from_team_key"], move["from_team_name"])
        sides[move["to_team_key"]]["received"].append(move)
        sides[move["from_team_key"]]["gave_up"].append(move)

    return sides


# --------------------------------------------------------------------------
# WEEK TRADE CUTOFF DATES (for timestamp-based freeze-week detection)
# --------------------------------------------------------------------------
_week_cutoff_date_cache = {}

# Yahoo's own week_start/week_end (from league.matchups()) is just the
# calendar date range (Tuesday-to-Monday) a fantasy week spans. A trade
# that clears on or before the FRIDAY of that week (week_start + 3 days)
# is treated as in effect for that week; a trade clearing Saturday or
# later rolls to the following week. (This is a league-defined cutoff,
# deliberately later than the Thursday-night kickoff -- trades through
# Friday count for that week.)
# Week 1 is the one known exception most seasons (a Wednesday
# week_start, not Tuesday, e.g. due to an international opener) --
# not relevant here since no trade in this league has ever happened in
# week 1, but flagged in case that changes.
TRADE_CUTOFF_OFFSET_DAYS = 3


def get_week_trade_cutoff_date(league, week: int):
    """Returns the LAST date a trade can clear and still count for
    `week` (its Friday: week_start + 3 days). A trade clearing ON this
    date or any earlier day is evaluated starting that week; any later
    date rolls to the following week. Cached process-wide since the
    schedule never changes once set."""
    if week in _week_cutoff_date_cache:
        return _week_cutoff_date_cache[week]
    raw = league.matchups(week=week)
    scoreboard = raw["fantasy_content"]["league"][1]["scoreboard"]
    sb_key = next(k for k in scoreboard.keys() if k.isdigit())
    matchup = scoreboard[sb_key]["matchups"]["0"]["matchup"]
    week_start = datetime.strptime(matchup["week_start"], "%Y-%m-%d").date()
    cutoff = week_start + timedelta(days=TRADE_CUTOFF_OFFSET_DAYS)
    _week_cutoff_date_cache[week] = cutoff
    return cutoff


# --------------------------------------------------------------------------
# FREEZE WEEK: first week a trade could actually have been in effect
# for a manager setting that week's lineup
# --------------------------------------------------------------------------
def find_freeze_week(league, parsed_trade: dict, sides: dict, rosters_by_week: dict, weeks: list) -> int | None:
    """
    Returns the first week in `weeks` (sorted ascending) that the trade
    could actually have been in effect for, combining two checks:

      1. TIMING: the trade must have cleared ON OR BEFORE that week's
         Friday (see get_week_trade_cutoff_date -- week_start + 3 days,
         where Yahoo's week_start is a Tuesday). A trade clearing any
         day from Tuesday through Friday of week N counts for week N;
         one clearing Saturday or later that week rolls to N+1
         instead.

      2. CONFIRMATION: Yahoo's own roster snapshot for that week must
         also show every side already in possession of what they
         received (a floor/sanity check -- if Yahoo's own roster data
         hasn't caught up yet for some reason, don't freeze earlier
         than that).

    The freeze week is the later of whichever week each check settles
    on. Returns None if the TIMING check can't be satisfied within
    `weeks` at all (the trade cleared too late even for the last
    available week -- e.g. it happened after that week's Friday cutoff,
    and the following week isn't complete/available yet), or if the
    trade happened after the last week with roster-snapshot data
    available.
    """
    timestamp = parsed_trade.get("timestamp")
    timing_week = None
    if timestamp is not None:
        trade_date = datetime.fromtimestamp(timestamp, tz=timezone.utc).date()
        for week in sorted(weeks):
            if trade_date <= get_week_trade_cutoff_date(league, week):
                timing_week = week
                break

    confirmation_week = None
    for week in sorted(weeks):
        week_rosters = rosters_by_week.get(week, {})
        all_sides_have_their_players = True
        for team_key, side in sides.items():
            roster_player_ids = {p["player_id"] for p in week_rosters.get(team_key, [])}
            received_ids = {m["player_id"] for m in side["received"]}
            if not received_ids:
                continue  # this "side" gave players away but received none back (shouldn't happen in a trade, but guard anyway)
            if not received_ids.issubset(roster_player_ids):
                all_sides_have_their_players = False
                break
        if all_sides_have_their_players:
            confirmation_week = week
            break

    # timing_week being None means no week in `weeks` has a cutoff date
    # on or after the trade -- i.e. the trade cleared too late even for
    # the LAST available week (e.g. a trade that cleared after this
    # week's Friday cutoff, where "this week" is still in progress and
    # hasn't been added to `weeks` yet). That's not the same as "no
    # timing constraint" -- it means the correct freeze week is beyond
    # what's evaluable right now, so this trade isn't evaluable yet,
    # regardless of what the roster snapshot already shows. Falling
    # back to confirmation_week here would silently treat an
    # in-progress week's trade as already frozen a week early.
    if timing_week is None:
        return None
    if confirmation_week is None:
        return timing_week
    return max(timing_week, confirmation_week)


# --------------------------------------------------------------------------
# PROJECTIONS: per-week, per-team-name player lists (for lineup choice)
# --------------------------------------------------------------------------
def load_week_projections(week: int) -> dict | None:
    """Returns {team_name: [player_dict, ...]} for a week, preferring
    the live projections/ folder and falling back to the permanent
    projections_historical/ cache. Returns None if neither has this
    week (caller must treat that week as unevaluable, not guess)."""
    for directory in (PROJECTIONS_DIR, PROJECTIONS_HISTORICAL_DIR):
        path = directory / f"week_{week}.json"
        if path.exists():
            with open(path) as f:
                return json.load(f)
    return None


def build_name_index(week_projections: dict) -> dict:
    """Returns {player_name: player_dict} across every team, for a
    single week's projections -- used to look up a traded player's
    projection/position/bye-or-IR status for that week regardless of
    which team's roster they actually appear under in the scrape."""
    index = {}
    for _team_name, players in week_projections.items():
        for p in players:
            index[p["name"]] = p
    return index


# --------------------------------------------------------------------------
# ACTUAL POINTS (for scoring the chosen lineup slots)
# --------------------------------------------------------------------------
def fetch_actuals_for_week(league, player_ids: list, week: int) -> dict:
    """Returns {player_id: actual_total_points} for a single week."""
    actuals = {}
    batch_size = 25
    unique_ids = sorted({str(pid) for pid in player_ids})
    for i in range(0, len(unique_ids), batch_size):
        batch = [int(pid) for pid in unique_ids[i:i + batch_size]]
        try:
            stats = league.player_stats(batch, "week", week=week)
        except Exception as e:
            print(f"  \u26a0 could not fetch player_stats for week {week}, batch starting {batch[0]}: {e}")
            continue
        for row in stats:
            pid = str(row.get("player_id"))
            try:
                pts = float(row.get("total_points", 0.0))
            except (TypeError, ValueError):
                pts = 0.0
            actuals[pid] = pts
    return actuals


# --------------------------------------------------------------------------
# K / DEF: this league's rosters always carry exactly one of each and
# a manager always starts them -- no projection comparison needed, just
# whether they're active (not on bye) that week.
# --------------------------------------------------------------------------
_bye_week_cache = {}


def get_kdef_from_roster(week_roster: list, position: str) -> str | None:
    """Returns the player_id of the K or DEF (position="K"/"DEF") on a
    single team's full roster for a week, or None if that team has
    none rostered (shouldn't normally happen in this league, but
    handled as a replacement-level fallback same as everywhere else)."""
    for p in week_roster:
        if p.get("selected_position") == position:
            return p["player_id"]
    return None


def fetch_bye_weeks(league, player_ids: list) -> dict:
    """Returns {player_id: bye_week (int or None)} via batched
    league.player_details(), cached process-wide since bye weeks never
    change once the season's schedule is set."""
    to_fetch = [pid for pid in set(player_ids) if pid not in _bye_week_cache]
    batch_size = 25
    for i in range(0, len(to_fetch), batch_size):
        batch = [int(pid) for pid in to_fetch[i:i + batch_size]]
        try:
            details_list = league.player_details(batch)
        except Exception as e:
            print(f"  \u26a0 could not fetch player_details (bye weeks) for batch starting {batch[0]}: {e}")
            continue
        for d in details_list:
            pid = str(d.get("player_id"))
            bye_week = None
            bye_info = d.get("bye_weeks")
            if isinstance(bye_info, dict) and bye_info.get("week"):
                try:
                    bye_week = int(bye_info["week"])
                except (TypeError, ValueError):
                    bye_week = None
            _bye_week_cache[pid] = bye_week
    return {pid: _bye_week_cache.get(pid) for pid in player_ids}


def score_kdef_slot(player_id: str | None, position: str, week: int,
                     bye_weeks: dict, actuals_by_id: dict) -> dict:
    """Returns the slot dict for a K or DEF slot: always-start rule --
    if a player is rostered and not on a bye this week, use their real
    actual points; otherwise replacement level."""
    replacement = REPLACEMENT_POINTS[position]
    if player_id is None:
        return {"player": None, "position": position, "projected_points": replacement,
                "actual_points": replacement, "used_replacement": True}

    bye_week = bye_weeks.get(player_id)
    if bye_week is not None and bye_week == week:
        return {"player": player_id, "position": position, "projected_points": replacement,
                "actual_points": replacement, "used_replacement": True}

    actual = actuals_by_id.get(player_id)
    if actual is None:
        # No actual-points entry means we don't yet know if they played
        # (e.g. stats not fetched for this id) -- treat as replacement
        # rather than silently scoring 0, consistent with "no data"
        # elsewhere in this script always falling back to replacement.
        return {"player": player_id, "position": position, "projected_points": replacement,
                "actual_points": replacement, "used_replacement": True}

    return {"player": player_id, "position": position, "projected_points": actual,
            "actual_points": actual, "used_replacement": False}


# --------------------------------------------------------------------------
# LINEUP OPTIMIZATION (mirrors calculate_lineups.py's rules exactly, but
# additionally carries each chosen slot's ACTUAL points for scoring)
# --------------------------------------------------------------------------
def _eligible_players(players: list) -> list:
    """Same eligibility rule as calculate_lineups.py: not on a bye
    (projected_points is not null) and not stashed on IR."""
    return [
        p for p in players
        if p.get("projected_points") is not None
        and p.get("selected_position") != "IR"
    ]


def _best_lineup(players: list, actuals_by_name: dict, k_slot: dict, def_slot: dict) -> dict:
    """
    Chooses the highest-PROJECTED legal lineup for the 7 skill-position
    slots from `players` (same slot structure/eligibility/replacement
    rules as calculate_lineups.py's _best_lineup_for_team), but reports
    each slot's ACTUAL points (via actuals_by_name, falling back to
    that slot's replacement level for any slot that used replacement,
    or 0.0 if a real player was chosen but has no actual-points entry --
    which would indicate a data gap, logged by the caller).

    K and DEF are NOT chosen here -- they're always-start slots decided
    entirely by roster + bye week (see score_kdef_slot), so the
    caller passes their already-resolved slot dicts in directly.

    Returns {"total_actual_points": float, "total_projected_points":
    float, "slots": {slot_name: {...}}}.
    """
    eligible = _eligible_players(players)

    by_position = {}
    for p in eligible:
        by_position.setdefault(p["position"], []).append(p)
    for pos in by_position:
        by_position[pos].sort(key=lambda p: p["projected_points"], reverse=True)

    used_names = set()
    slots = {}

    def take_best(position: str):
        for p in by_position.get(position, []):
            if p["name"] not in used_names:
                used_names.add(p["name"])
                return p
        return None

    def actual_for(player_name: str) -> float:
        actual = actuals_by_name.get(player_name)
        return actual if actual is not None else 0.0

    def fill_slot(slot_name: str, position: str, replacement_key: str):
        player = take_best(position)
        if player is None:
            slots[slot_name] = {
                "player": None, "position": position,
                "projected_points": REPLACEMENT_POINTS[replacement_key],
                "actual_points": REPLACEMENT_POINTS[replacement_key],
                "used_replacement": True,
            }
            return
        pts = player["projected_points"]
        replacement = REPLACEMENT_POINTS[replacement_key]
        if pts < replacement:
            slots[slot_name] = {
                "player": player["name"], "position": position,
                "projected_points": replacement,
                "actual_points": replacement,
                "used_replacement": True,
            }
        else:
            slots[slot_name] = {
                "player": player["name"], "position": position,
                "projected_points": pts,
                "actual_points": actual_for(player["name"]),
                "used_replacement": False,
            }

    for slot_name, (position, _count) in DEDICATED_SLOTS.items():
        fill_slot(slot_name, position, position)

    flex_candidates = [
        p for pos in FLEX_ELIGIBLE_POSITIONS
        for p in by_position.get(pos, [])
        if p["name"] not in used_names
    ]
    flex_candidates.sort(key=lambda p: p["projected_points"], reverse=True)
    flex_player = flex_candidates[0] if flex_candidates else None
    if flex_player is None:
        slots["FLEX"] = {
            "player": None, "position": None,
            "projected_points": REPLACEMENT_POINTS["FLEX"],
            "actual_points": REPLACEMENT_POINTS["FLEX"],
            "used_replacement": True,
        }
    else:
        used_names.add(flex_player["name"])
        pts = flex_player["projected_points"]
        replacement = REPLACEMENT_POINTS["FLEX"]
        if pts < replacement:
            slots["FLEX"] = {
                "player": flex_player["name"], "position": flex_player["position"],
                "projected_points": replacement,
                "actual_points": replacement,
                "used_replacement": True,
            }
        else:
            slots["FLEX"] = {
                "player": flex_player["name"], "position": flex_player["position"],
                "projected_points": pts,
                "actual_points": actual_for(flex_player["name"]),
                "used_replacement": False,
            }

    # K / DEF: always-start, resolved by the caller (see score_kdef_slot)
    # rather than chosen here -- this league's rosters only ever carry
    # one of each and a manager always starts them, no projection
    # comparison needed.
    slots["K"] = k_slot
    slots["DEF"] = def_slot

    total_actual = round(sum(s["actual_points"] for s in slots.values()), 2)
    total_projected = round(sum(s["projected_points"] for s in slots.values()), 2)
    return {"total_actual_points": total_actual, "total_projected_points": total_projected, "slots": slots}


def build_counterfactual_roster(real_roster: list, received_player_names: set,
                                 gave_up_player_rows: list) -> list:
    """
    Returns a new player list: `real_roster` with every received player
    removed, and every given-up player's row (as they actually appear
    in this week's projections data, wherever that is -- see
    build_name_index) added in their place. If a given-up player can't
    be found anywhere in this week's projections (e.g. they were cut
    /dropped from every roster entirely before this week), they're
    simply omitted from the counterfactual roster -- equivalent to that
    slot having nobody available, which naturally falls back to
    replacement level in _best_lineup.
    """
    counterfactual = [p for p in real_roster if p["name"] not in received_player_names]
    counterfactual.extend(gave_up_player_rows)
    return counterfactual


def build_real_roster(week_projections: dict, name_index: dict, team_name: str,
                       side: dict) -> list:
    """
    Returns the ACTUAL roster to use for `team_name` this week, patched
    against the scraped projections data's own team grouping using the
    trade's ground-truth direction (received/gave_up) for just the
    traded players.

    Why patching is needed: the live roster scrape (pull_projections.py)
    captures each team's roster AT THE TIME IT WAS SCRAPED, so for a
    week whose scrape happened before a trade executed that same week,
    the scraped "team -> players" grouping can still show a just-traded
    player under their OLD team, even though full_rosters_by_week (the
    ground truth used to pick this trade's freeze week) confirms they
    were truly on the NEW team by this week. Rather than reconstruct
    every team's whole roster from id-keyed sources (which would need a
    slow per-player name lookup for every non-traded player too), this
    only patches the specific traded players: any "received" player
    missing from this team's scraped roster is added (pulled from
    wherever they appear in the week's data via name_index -- almost
    always the OTHER team's scraped roster, i.e. exactly the bug case
    above), and any "gave_up" player still incorrectly present on this
    team's scraped roster is removed.
    """
    roster = list(week_projections.get(team_name, []))
    roster_names = {p["name"] for p in roster}

    gave_up_names = set()
    for m in side["gave_up"]:
        row = name_index.get(m["player_name"])
        gave_up_names.add(row["name"] if row is not None else m["player_name"])
    roster = [p for p in roster if p["name"] not in gave_up_names]

    for m in side["received"]:
        row = name_index.get(m["player_name"])
        name = row["name"] if row is not None else m["player_name"]
        if name not in roster_names and row is not None:
            roster.append(row)

    return roster


# --------------------------------------------------------------------------
# PER-TRADE, PER-WEEK EVALUATION
# --------------------------------------------------------------------------
def evaluate_trade_week(league, sides: dict, week: int, rosters_by_week: dict,
                         actuals_cache: dict) -> tuple[dict, list, bool]:
    """
    Returns ({team_key: net_gain_this_week}, warnings, no_projection_data)
    for one week of one trade. `actuals_cache` is
    {week: {player_id: actual_points}}, mutated in place to avoid
    re-fetching the same week's actuals once for every trade that needs
    it. `no_projection_data` is True iff this week had to be skipped
    entirely because neither the live nor historical projections cache
    has that week. `rosters_by_week` is the full-roster snapshot cache
    (see load_full_rosters_by_week_extended) -- used here to find each
    team's actual K and DEF for the week (skill positions come from the
    scraped projections data instead; K/DEF never appear there).
    """
    warnings = []
    week_projections = load_week_projections(week)
    if week_projections is None:
        warnings.append(f"week {week}: no projections data available (live or historical) -- skipped")
        return {}, warnings, True

    name_index = build_name_index(week_projections)
    week_rosters = rosters_by_week.get(week, {})

    # Make sure we have actual points for every player involved this
    # week (received + given-up, across every side, PLUS every team's
    # actual K/DEF this week since those are always-started and need
    # real points directly -- no lineup-selection step to defer to),
    # fetched once per week and cached across trades/sides.
    if week not in actuals_cache:
        all_player_ids = set()
        for side in sides.values():
            all_player_ids.update(m["player_id"] for m in side["received"])
            all_player_ids.update(m["player_id"] for m in side["gave_up"])
        for team_key in sides:
            for pos in ("K", "DEF"):
                pid = get_kdef_from_roster(week_rosters.get(team_key, []), pos)
                if pid:
                    all_player_ids.add(pid)
        actuals_cache[week] = fetch_actuals_for_week(league, list(all_player_ids), week)
    actuals_by_id = actuals_cache[week]

    # actuals_by_name needs the NAME each player appears under in this
    # week's scrape (could differ slightly trade to trade, but names are
    # stable within one week's single scrape), bridged via player_id.
    def actuals_by_name_for(player_ids_to_names: dict) -> dict:
        return {
            name: actuals_by_id.get(pid)
            for pid, name in player_ids_to_names.items()
            if pid in actuals_by_id
        }

    net_gain_by_team = {}

    for team_key, side in sides.items():
        team_name = side["team_name"]
        if team_name not in week_projections:
            warnings.append(f"week {week}: no projections row for team '{team_name}' -- skipped for this side")
            continue

        real_roster = build_real_roster(week_projections, name_index, team_name, side)

        received_names = set()
        gave_up_rows = []
        gave_up_missing = []
        id_to_name = {}

        for m in side["received"]:
            row = name_index.get(m["player_name"])
            if row is not None:
                received_names.add(row["name"])
                id_to_name[m["player_id"]] = row["name"]
            else:
                received_names.add(m["player_name"])  # best-effort fallback

        for m in side["gave_up"]:
            row = name_index.get(m["player_name"])
            if row is not None:
                gave_up_rows.append(row)
                id_to_name[m["player_id"]] = row["name"]
            else:
                gave_up_missing.append(m["player_name"])

        if gave_up_missing:
            warnings.append(
                f"week {week}, team '{team_name}': could not find projection data for "
                f"given-up player(s) {gave_up_missing} in anyone's roster this week -- "
                f"treated as unavailable (replacement-level fallback for that slot)"
            )

        # Actual points for the traded players (the only ones we can
        # cheaply get by player_id so far).
        actuals_by_name = actuals_by_name_for(id_to_name)

        counterfactual_roster = build_counterfactual_roster(real_roster, received_names, gave_up_rows)

        # K / DEF: always-start, resolved from the real roster snapshot
        # directly (never from the scraped projections data, which
        # doesn't cover K/DEF at all). The counterfactual swaps a K/DEF
        # out only if THIS trade actually moved the team's real K/DEF
        # -- e.g. a WR-for-RB trade leaves a team's own K/DEF completely
        # unaffected in both the real and counterfactual roster.
        real_k_id = get_kdef_from_roster(week_rosters.get(team_key, []), "K")
        real_def_id = get_kdef_from_roster(week_rosters.get(team_key, []), "DEF")

        received_kdef_by_position = {m["position"]: m["player_id"] for m in side["received"] if m["position"] in ("K", "DEF")}
        gave_up_kdef_by_position = {m["position"]: m["player_id"] for m in side["gave_up"] if m["position"] in ("K", "DEF")}

        counterfactual_k_id = real_k_id
        if received_kdef_by_position.get("K") == real_k_id and "K" in gave_up_kdef_by_position:
            counterfactual_k_id = gave_up_kdef_by_position["K"]
        counterfactual_def_id = real_def_id
        if received_kdef_by_position.get("DEF") == real_def_id and "DEF" in gave_up_kdef_by_position:
            counterfactual_def_id = gave_up_kdef_by_position["DEF"]

        kdef_ids = {pid for pid in (real_k_id, real_def_id, counterfactual_k_id, counterfactual_def_id) if pid}
        bye_weeks = fetch_bye_weeks(league, list(kdef_ids)) if kdef_ids else {}
        missing_kdef_actuals = kdef_ids - set(actuals_by_id.keys())
        if missing_kdef_actuals:
            actuals_by_id.update(fetch_actuals_for_week(league, list(missing_kdef_actuals), week))

        real_k_slot = score_kdef_slot(real_k_id, "K", week, bye_weeks, actuals_by_id)
        real_def_slot = score_kdef_slot(real_def_id, "DEF", week, bye_weeks, actuals_by_id)
        counterfactual_k_slot = score_kdef_slot(counterfactual_k_id, "K", week, bye_weeks, actuals_by_id)
        counterfactual_def_slot = score_kdef_slot(counterfactual_def_id, "DEF", week, bye_weeks, actuals_by_id)

        # Scraped roster rows are name-keyed with no player_id, so any
        # NON-traded player who ends up chosen into either lineup has
        # no actual-points entry yet. Do a cheap first pass to see who
        # gets chosen, resolve actuals for just those names via a
        # direct Yahoo lookup (cached process-wide by name), then
        # re-score both lineups with the complete actuals map. This
        # avoids resolving actuals for the whole roster when only ~9
        # players per side ever actually get chosen.
        real_lineup = _best_lineup(real_roster, actuals_by_name, real_k_slot, real_def_slot)
        counterfactual_lineup = _best_lineup(counterfactual_roster, actuals_by_name,
                                              counterfactual_k_slot, counterfactual_def_slot)

        chosen_names = {
            slot["player"] for slot in list(real_lineup["slots"].values()) + list(counterfactual_lineup["slots"].values())
            if slot["player"]
        }
        # K/DEF slots store a player_id in "player", not a name -- drop
        # those since they're never looked up through actuals_by_name.
        chosen_names -= kdef_ids
        missing_names = chosen_names - set(actuals_by_name.keys())
        if missing_names:
            resolved = _resolve_actuals_by_name(league, missing_names, week)
            actuals_by_name.update(resolved)
            real_lineup = _best_lineup(real_roster, actuals_by_name, real_k_slot, real_def_slot)
            counterfactual_lineup = _best_lineup(counterfactual_roster, actuals_by_name,
                                                  counterfactual_k_slot, counterfactual_def_slot)

        net_gain = round(real_lineup["total_actual_points"] - counterfactual_lineup["total_actual_points"], 2)
        net_gain_by_team[team_key] = {
            "net_gain": net_gain,
            "real_lineup_points": real_lineup["total_actual_points"],
            "counterfactual_lineup_points": counterfactual_lineup["total_actual_points"],
        }

    return net_gain_by_team, warnings, False


_name_lookup_cache = {}


def _lookup_player_id_by_name(league, name: str) -> str | None:
    """
    Resolve a player's Yahoo player_id via league.player_details(name),
    tolerating Yahoo's search endpoint rejecting a literal apostrophe
    outright (e.g. "Ja'Marr Chase" raises a 400 "invalid param search"
    error; it isn't just a zero-result miss). If the raw name search
    fails or an apostrophe is present, retries with the apostrophe
    dropped -- a search like "Marr Chase" or "Andre Swift" still
    reliably finds the right player among plain-English results --
    then disambiguates among same-surname matches (e.g. "Chase" also
    matches "Chase Edmonds") by requiring an exact, case-insensitive
    full-name match against the original name before accepting a hit.
    """
    candidates = []
    try:
        candidates = league.player_details(name)
    except Exception:
        candidates = []

    if not candidates and "'" in name:
        stripped = name.replace("'", " ").split()
        # Drop the single leading token immediately before the
        # apostrophe (e.g. "Ja'Marr Chase" -> "Marr Chase"), since
        # searching on the truncated first-name fragment + last name
        # reliably matches, unlike the full un-apostrophed string.
        retry_query = " ".join(stripped[1:]) if len(stripped) > 1 else stripped[0]
        try:
            candidates = league.player_details(retry_query)
        except Exception as e:
            print(f"  \u26a0 could not resolve player_id for '{name}' (retry '{retry_query}'): {e}")
            return None

    if not candidates:
        print(f"  \u26a0 no player_details match for '{name}'")
        return None

    target = name.strip().lower()
    for d in candidates:
        full_name = (d.get("name", {}) or {}).get("full", "")
        if full_name.strip().lower() == target:
            return str(d.get("player_id"))

    print(f"  \u26a0 no exact-name match for '{name}' among player_details results "
          f"({[d.get('name', {}).get('full') for d in candidates]}) -- skipping")
    return None


def _resolve_actuals_by_name(league, player_names: set, week: int) -> dict:
    """
    Last-resort lookup: given a set of player names chosen into a
    lineup that we don't already have actual points for (every
    non-traded rostered player, since the scraped projection files are
    name-keyed with no player_id), resolve their Yahoo player_id via
    league.player_details(name) and then their actual points via
    player_stats. Cached process-wide by (name) for player_id lookups
    since a player's id never changes, and by (name, week) isn't needed
    since actuals are fetched fresh here each call.
    """
    resolved = {}
    ids_to_names = {}
    for name in player_names:
        if name in _name_lookup_cache:
            pid = _name_lookup_cache[name]
        else:
            pid = _lookup_player_id_by_name(league, name)
            if pid is None:
                continue
            _name_lookup_cache[name] = pid
        if pid:
            ids_to_names[pid] = name

    if not ids_to_names:
        return resolved

    actuals = fetch_actuals_for_week(league, list(ids_to_names.keys()), week)
    for pid, name in ids_to_names.items():
        if pid in actuals:
            resolved[name] = actuals[pid]
    return resolved


# --------------------------------------------------------------------------
# ORCHESTRATION
# --------------------------------------------------------------------------
def determine_last_completed_week(league) -> int:
    """Last week strictly before the league's current week -- same
    'already final' convention used everywhere else in this project."""
    return league.current_week() - 1


def evaluate_all_trades(league, force_refresh_rosters: bool = False) -> list:
    trades_raw = fetch_successful_trades(league)
    if not trades_raw:
        print("No successful trades found this season.")
        return []

    last_completed_week = determine_last_completed_week(league)
    all_weeks = list(range(1, last_completed_week + 1))
    print(f"Last completed week: {last_completed_week}. Loading full roster snapshots for weeks {all_weeks}...")
    rosters_by_week = load_full_rosters_by_week_extended(league, YEAR, all_weeks, force_refresh=force_refresh_rosters)

    results = []
    actuals_cache = {}

    for tx in trades_raw:
        parsed = parse_trade(tx)
        sides = group_trade_by_side(parsed)

        if len(sides) != 2:
            print(f"  \u26a0 trade {parsed['transaction_id']}: expected exactly 2 teams, "
                  f"found {len(sides)} -- skipping (multi-team trades not supported).")
            continue

        freeze_week = find_freeze_week(league, parsed, sides, rosters_by_week, all_weeks)
        if freeze_week is None:
            print(f"  \u26a0 trade {parsed['transaction_id']}: could not determine a freeze week "
                  f"within weeks {all_weeks} (the trade cleared after the last completed "
                  f"week's Friday cutoff, so it first takes effect in a week that hasn't "
                  f"finished yet) -- skipping for now.")
            continue

        traded_at = None
        if parsed["timestamp"]:
            traded_at = datetime.fromtimestamp(parsed["timestamp"], tz=timezone.utc).isoformat()

        print(f"\nTrade {parsed['transaction_id']} ({traded_at}): freeze week {freeze_week}")
        for team_key, side in sides.items():
            received = [m["player_name"] for m in side["received"]]
            gave_up = [m["player_name"] for m in side["gave_up"]]
            print(f"  {side['team_name']:<32} received {received}, gave up {gave_up}")

        weeks_to_evaluate = [w for w in all_weeks if w >= freeze_week]
        weekly_results = {team_key: {} for team_key in sides}
        all_warnings = []
        weeks_skipped_no_projection_data = []

        for week in weeks_to_evaluate:
            net_gain_by_team, warnings, no_projection_data = evaluate_trade_week(
                league, sides, week, rosters_by_week, actuals_cache
            )
            all_warnings.extend(warnings)
            if no_projection_data:
                weeks_skipped_no_projection_data.append(week)
            for team_key, detail in net_gain_by_team.items():
                weekly_results[team_key][week] = detail

        for warning in all_warnings:
            print(f"    \u26a0 {warning}")

        record = {
            "transaction_id": parsed["transaction_id"],
            "timestamp": parsed["timestamp"],
            "traded_at": traded_at,
            "freeze_week": freeze_week,
            "last_week_evaluated": last_completed_week,
            "sides": {},
            "weeks_skipped_no_projection_data": weeks_skipped_no_projection_data,
        }

        for team_key, side in sides.items():
            weekly_net_gain = {str(week): weekly_results[team_key][week]["net_gain"]
                                for week in weekly_results[team_key]}
            total_net_gain = round(sum(weekly_net_gain.values()), 2)
            record["sides"][team_key] = {
                "team_name": side["team_name"],
                "received": [{"player_id": m["player_id"], "player_name": m["player_name"],
                               "position": m["position"]} for m in side["received"]],
                "gave_up": [{"player_id": m["player_id"], "player_name": m["player_name"],
                              "position": m["position"]} for m in side["gave_up"]],
                "weekly_net_gain": weekly_net_gain,
                "weekly_detail": {str(w): weekly_results[team_key][w] for w in weekly_results[team_key]},
                "total_net_gain": total_net_gain,
            }

        results.append(record)

    return results


def print_summary(results: list) -> None:
    print("\n" + "=" * 72)
    print(f"{YEAR} TRADE EVALUATOR SUMMARY")
    print("=" * 72)
    for record in results:
        print(f"\nTrade {record['transaction_id']} (traded {record['traded_at']}, "
              f"frozen from week {record['freeze_week']} through week {record['last_week_evaluated']}):")
        for team_key, side in record["sides"].items():
            received = ", ".join(p["player_name"] for p in side["received"])
            gave_up = ", ".join(p["player_name"] for p in side["gave_up"])
            print(f"  {side['team_name']:<32} got {received:<24} gave up {gave_up:<24} "
                  f"net: {side['total_net_gain']:+.2f} pts "
                  f"(by week: {side['weekly_net_gain']})")


def run_trade_evaluator():
    parser = argparse.ArgumentParser(
        description="Evaluate the net point impact of every completed trade this season."
    )
    parser.add_argument("--force-refresh-rosters", action="store_true",
                         help="Re-pull full weekly rosters from Yahoo even if a "
                              "full_rosters_by_week_{YEAR}.json cache already exists.")
    parser.add_argument("--oauth-file", default=OAUTH_FILE, help="Path to yahoo_oauth credentials json")
    parser.add_argument("--league-id", default=LEAGUE_ID, help="Yahoo league id, e.g. 470.l.205662")
    args = parser.parse_args()

    league = get_league(oauth_file=args.oauth_file, league_id=args.league_id)
    results = evaluate_all_trades(league, force_refresh_rosters=args.force_refresh_rosters)

    DRAFT_DATA_DIR.mkdir(parents=True, exist_ok=True)
    with open(OUTPUT_PATH, "w") as f:
        json.dump(results, f, indent=2)
    print(f"\nSaved -> {OUTPUT_PATH} ({len(results)} trade(s) evaluated)")

    print_summary(results)


if __name__ == "__main__":
    run_trade_evaluator()