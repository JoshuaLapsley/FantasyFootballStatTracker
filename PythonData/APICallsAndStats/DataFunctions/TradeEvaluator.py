"""
Evaluate every completed trade for a given season: for each trade, freeze
both sides' rosters at the point the trade actually took effect, then
measure the net point swing each week going forward if each team had
instead kept the player(s) they gave up, instead of the player(s) they
received.

Usage:
    python3 trade_evaluator.py 2026
    python3 trade_evaluator.py 2025 --last-week 17
    python3 trade_evaluator.py 2024 --season-start 2024-09-05

--------------------------------------------------------------------------
WHAT THIS MEASURES
--------------------------------------------------------------------------
For a trade where team A sends {p_out_A...} to team B in exchange for
{p_out_B...} (so A receives p_out_B's players, B receives p_out_A's
players):

  For every week from the trade's "freeze week" (the first week the
  trade could actually have been in effect for -- see find_freeze_week:
  the trade must have cleared on or before that week's SUNDAY cutoff,
  AND the roster snapshot for that week must confirm both sides already
  have what they received) through the most recently completed week:

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
  actual points, not projections.

  K and DEF: whichever K and DEF a team actually has in its K / DEF
  roster slot that week is ALWAYS started, scored with real actual
  points. They only fall back to replacement level if the team has no
  K/DEF in that slot, or the K/DEF is on a bye.

  If a skill-position slot has no eligible player available (bye week
  / no projection) in either the real or counterfactual roster, or the
  best available player projects below that slot's replacement level,
  that slot falls back to replacement level -- identical rule, same
  constants, applied symmetrically to both the real and counterfactual
  roster. A player's roster slot (including IR) is NOT considered: any
  player with a projection is eligible to be started.

Trades with more than one player per side are handled the same way: ALL
of a team's received players stay in that team's real roster, and ALL of
them are swapped back out for ALL of the players that team gave up in
the counterfactual roster.

--------------------------------------------------------------------------
INPUTS (paths are relative to this script's folder)
--------------------------------------------------------------------------
  ../APIData/{year}/TransactionData.json
      All league transactions. Only type == "trade" with
      status == "successful" are evaluated (vetoed/pending excluded).
  ../APIData/{year}/RosterPoints.json
      {week: {team_key: [{player_id, name, selected_position, points}]}}
      Every team's full roster and every player's actual points, per
      week. Used for the real rosters, the freeze-week confirmation,
      actual points, and K/DEF.
  ../Projections/SleeperProjections/{year}/projections/week_{##}.json
      Sleeper projections (pts_ppr is used) -- only used to decide each
      week's optimal skill-position lineup, and to detect K/DEF byes.
      Sleeper player_ids differ from Yahoo's, so players are matched to
      Yahoo roster entries by normalized name.

OUTPUT
  ../Data/{year}/trade_evaluator_{year}.json -- a list of trade records
  (same schema as before).
"""

import argparse
import json
import os
import re
import sys
from datetime import date, datetime, timedelta, timezone
from pathlib import Path

# Reuse the exact lineup-optimization + replacement-value rules used
# for the season simulation, so trade evaluation stays consistent with
# every other "optimal legal lineup" calculation in this codebase.
SCRIPT_DIR = os.path.dirname(os.path.abspath(__file__))
SIMULATE_SEASON_DIR = os.path.join(SCRIPT_DIR, "..", "simulate_season")
sys.path.insert(0, SIMULATE_SEASON_DIR)


REPLACEMENT_POINTS = {
    "QB": 15,
    "RB": 5,
    "WR": 7,
    "TE": 6,
    "FLEX": 7,
    "K": 7,
    "DEF": 5,
}

DEDICATED_SLOTS = {
    "QB": ("QB", 1),
    "RB1": ("RB", 1),
    "RB2": ("RB", 1),
    "WR1": ("WR", 1),
    "WR2": ("WR", 1),
    "TE": ("TE", 1),
}
FLEX_ELIGIBLE_POSITIONS = {"RB", "WR", "TE"}

SLOT_ORDER = ["QB", "RB1", "RB2", "WR1", "WR2", "TE", "FLEX", "K", "DEF"]
SHOW_LINEUPS = True

def print_week_lineups(week: int, team_name: str, real_lineup: dict, cf_lineup: dict,
                       received_names: set, gave_up_names: set) -> None:
    """Side-by-side real vs counterfactual lineup for one team-week.
    '*' = a traded player, '(R)' = replacement-level fallback."""
    def cell(slot: dict, traded_names: set) -> tuple[str, str]:
        name = slot["player"] or "(none)"
        if slot["player"] in traded_names:
            name += " *"
        if slot["used_replacement"]:
            name += " (R)"
        return name, f"{slot['actual_points']:.2f}"

    print(f"\n    Week {week} - {team_name}")
    print(f"    {'Slot':<5} {'REAL (with trade)':<28}{'Pts':>7}   "
          f"{'COUNTERFACTUAL (no trade)':<28}{'Pts':>7}")
    print("    " + "-" * 82)
    for slot_name in SLOT_ORDER:
        r_name, r_pts = cell(real_lineup["slots"][slot_name], received_names)
        c_name, c_pts = cell(cf_lineup["slots"][slot_name], gave_up_names)
        print(f"    {slot_name:<5} {r_name:<28}{r_pts:>7}   {c_name:<28}{c_pts:>7}")
    print("    " + "-" * 82)
    print(f"    {'TOTAL':<5} {'':<28}{real_lineup['total_actual_points']:>7.2f}   "
          f"{'':<28}{cf_lineup['total_actual_points']:>7.2f}")


# --------------------------------------------------------------------------
# PATHS
# --------------------------------------------------------------------------
def get_year_paths(year: int) -> dict:
    base = Path(SCRIPT_DIR)
    return {
        "transactions": (base / ".." / "APIData" / str(year) / "TransactionData.json").resolve(),
        "rosters": (base / ".." / "APIData" / str(year) / "RosterPoints.json").resolve(),
        "projections_dir": (base / ".." / "Projections" / "SleeperProjections" / str(year) / "projections").resolve(),
        "output_dir": (base / ".." / "Data" / str(year)).resolve(),
    }


def load_json(path):
    with open(path, "r", encoding="utf-8") as f:
        return json.load(f)


# --------------------------------------------------------------------------
# NAME MATCHING (Sleeper ids differ from Yahoo ids, so match on name)
# --------------------------------------------------------------------------
_NAME_SUFFIXES = {"jr", "sr", "ii", "iii", "iv", "v"}


def normalize_name(name) -> str:
    if not name:
        return ""
    cleaned = re.sub(r"[.'\u2019`]", "", name.lower()).replace("-", " ")
    tokens = cleaned.split()
    while len(tokens) > 1 and tokens[-1] in _NAME_SUFFIXES:
        tokens.pop()
    return " ".join(tokens)


# --------------------------------------------------------------------------
# ROSTERS
# --------------------------------------------------------------------------
def load_rosters_by_week(path: Path) -> dict:
    """Returns {week(int): {team_key: [{"player_id", "name",
    "selected_position", "points"}, ...]}}"""
    raw = load_json(path)
    return {int(week): teams for week, teams in raw.items()}


def build_week_index(week_rosters: dict) -> dict:
    """{player_id: {"entry": roster_entry, "team_key": team_key}} across
    every team for one week -- used to find a given-up player wherever
    they ended up (almost always the other side of the trade)."""
    index = {}
    for team_key, entries in week_rosters.items():
        for entry in entries:
            index[str(entry["player_id"])] = {"entry": entry, "team_key": team_key}
    return index


# --------------------------------------------------------------------------
# PROJECTIONS (Sleeper, pts_ppr)
# --------------------------------------------------------------------------
def load_week_projections(projections_dir: Path, week: int) -> dict | None:
    """Returns {"skill": {normalized_name: {"position", "projected_points"}},
    "kickers": {normalized_name}, "defenses": [lowercase team names]} or
    None if that week's file doesn't exist (caller must treat that week
    as unevaluable, not guess)."""
    raw = None
    for fname in (f"week_{week:02d}.json", f"week_{week}.json"):
        path = projections_dir / fname
        if path.exists():
            raw = load_json(path)
            break
    if raw is None:
        return None

    skill, kickers, defenses = {}, set(), []
    for p in raw.get("players", []):
        pts = p.get("pts_ppr")
        if pts is None:
            continue
        pos = p.get("position")
        if pos == "K":
            kickers.add(normalize_name(p["name"]))
        elif pos == "DEF":
            defenses.append(p["name"].strip().lower())
        else:
            key = normalize_name(p["name"])
            if key not in skill:  # file is sorted by projection; keep the highest on a name collision
                skill[key] = {"position": pos, "projected_points": float(pts)}
    return {"skill": skill, "kickers": kickers, "defenses": defenses}


def is_kdef_active(name: str, position: str, week_projs: dict) -> bool:
    """A K/DEF with no entry in that week's projections is treated as on
    a bye (Sleeper omits bye-week teams)."""
    if position == "K":
        return normalize_name(name) in week_projs["kickers"]
    nick = name.strip().lower()  # Yahoo "Texans" vs Sleeper "Houston Texans"
    return any(d == nick or d.endswith(" " + nick) for d in week_projs["defenses"])


# --------------------------------------------------------------------------
# TRADES: fetch + parse into per-trade, per-team, per-player moves
# --------------------------------------------------------------------------
def fetch_successful_trades(transactions: list) -> list:
    trades = [tx for tx in transactions if tx.get("type") == "trade"]
    successful = [tx for tx in trades if tx.get("status") == "successful"]
    skipped = [tx for tx in trades if tx.get("status") != "successful"]
    if skipped:
        print(f"Skipping {len(skipped)} non-successful trade(s): "
              f"{[(tx.get('transaction_id'), tx.get('status')) for tx in skipped]}")
    return successful


def parse_trade(tx: dict) -> dict:
    moves = []
    for p in tx.get("players", []):
        if not p.get("source_team_key") or not p.get("destination_team_key"):
            continue
        moves.append({
            "player_id": str(p["player_id"]),
            "player_name": p.get("player_name"),
            "position": p.get("position"),
            "from_team_key": p.get("source_team_key"),
            "from_team_name": p.get("source_team_name"),
            "to_team_key": p.get("destination_team_key"),
            "to_team_name": p.get("destination_team_name"),
        })
    return {
        "transaction_id": tx.get("transaction_id"),
        "timestamp": int(tx["timestamp"]) if tx.get("timestamp") else None,
        "moves": moves,
    }


def group_trade_by_side(parsed_trade: dict) -> dict:
    """{team_key: {"team_name", "received": [move...], "gave_up": [move...]}}"""
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
# WEEK TRADE CUTOFF DATES
# --------------------------------------------------------------------------
# A trade that clears on or before the SUNDAY of a fantasy week is treated
# as in effect for that week; a trade clearing Monday or later rolls to the
# following week (league-defined cutoff, deliberately later than the
# Thursday-night kickoff).
#
# The old script read each week's week_start from Yahoo and took the first
# Sunday on or after it. That is always the Sunday of that NFL week, so it
# is computed here from the season kickoff instead: the Thursday after
# Labor Day (override with --season-start for years where that isn't true).
def default_season_start(year: int) -> date:
    labor_day = date(year, 9, 1)
    labor_day += timedelta(days=(0 - labor_day.weekday()) % 7)  # first Monday of September
    return labor_day + timedelta(days=3)


def get_week_trade_cutoff_date(season_start: date, week: int) -> date:
    """The LAST date a trade can clear and still count for `week`."""
    first_sunday = season_start + timedelta(days=(6 - season_start.weekday()) % 7)
    return first_sunday + timedelta(days=7 * (week - 1))


# --------------------------------------------------------------------------
# FREEZE WEEK: first week a trade could actually have been in effect
# for a manager setting that week's lineup
# --------------------------------------------------------------------------
def find_freeze_week(parsed_trade: dict, sides: dict, rosters_by_week: dict,
                     weeks: list, season_start: date) -> int | None:
    """
    Returns the first week in `weeks` (sorted ascending) that the trade
    could actually have been in effect for, combining two checks:

      1. TIMING: the trade must have cleared ON OR BEFORE that week's
         Sunday cutoff (see get_week_trade_cutoff_date).

      2. CONFIRMATION: the roster snapshot for that week must also show
         every side already in possession of what they received.

    The freeze week is the later of whichever week each check settles
    on. Returns None if the TIMING check can't be satisfied within
    `weeks` (the trade cleared too late for the last available week, so
    it first takes effect in a week that hasn't finished yet).
    """
    timestamp = parsed_trade.get("timestamp")
    timing_week = None
    if timestamp is not None:
        trade_date = datetime.fromtimestamp(timestamp, tz=timezone.utc).date()
        for week in sorted(weeks):
            if trade_date <= get_week_trade_cutoff_date(season_start, week):
                timing_week = week
                break

    confirmation_week = None
    for week in sorted(weeks):
        week_rosters = rosters_by_week.get(week, {})
        all_sides_have_their_players = True
        for team_key, side in sides.items():
            roster_player_ids = {str(p["player_id"]) for p in week_rosters.get(team_key, [])}
            received_ids = {m["player_id"] for m in side["received"]}
            if not received_ids:
                continue
            if not received_ids.issubset(roster_player_ids):
                all_sides_have_their_players = False
                break
        if all_sides_have_their_players:
            confirmation_week = week
            break

    # timing_week None means the trade is too late for every available
    # week -- not evaluable yet, regardless of what the roster snapshot
    # shows.
    if timing_week is None:
        return None
    if confirmation_week is None:
        return timing_week
    return max(timing_week, confirmation_week)


# --------------------------------------------------------------------------
# K / DEF: always-start, resolved from the K / DEF roster slot
# --------------------------------------------------------------------------
def get_kdef_from_roster(week_roster: list, position: str) -> dict | None:
    """The roster entry sitting in the K or DEF slot, or None."""
    for p in week_roster:
        if p.get("selected_position") == position:
            return {"player_id": str(p["player_id"]), "name": p["name"],
                    "points": float(p.get("points") or 0.0)}
    return None


def kdef_candidate_from_move(move: dict, week_index: dict) -> dict:
    """A traded K/DEF as a candidate; points are None if they aren't on
    any roster this week (scores as replacement level, same as before)."""
    hit = week_index.get(move["player_id"])
    return {"player_id": move["player_id"], "name": move["player_name"],
            "points": float(hit["entry"].get("points") or 0.0) if hit else None}


def score_kdef_slot(candidate: dict | None, position: str, week_projs: dict) -> dict:
    """Always-start rule -- if a K/DEF is rostered and not on a bye this
    week, use their real actual points; otherwise replacement level."""
    replacement = REPLACEMENT_POINTS[position]
    if candidate is None:
        return {"player": None, "position": position, "projected_points": replacement,
                "actual_points": replacement, "used_replacement": True}

    if not is_kdef_active(candidate["name"], position, week_projs) or candidate["points"] is None:
        return {"player": candidate["name"], "position": position, "projected_points": replacement,
                "actual_points": replacement, "used_replacement": True}

    actual = candidate["points"]
    return {"player": candidate["name"], "position": position, "projected_points": actual,
            "actual_points": actual, "used_replacement": False}


# --------------------------------------------------------------------------
# LINEUP OPTIMIZATION (mirrors calculate_lineups.py's rules, except that
# IR slot status is ignored, and additionally carries each chosen slot's
# ACTUAL points for scoring)
# --------------------------------------------------------------------------
def build_player(entry: dict, week_projs: dict) -> dict:
    proj = week_projs["skill"].get(normalize_name(entry["name"]))
    return {
        "player_id": str(entry["player_id"]),
        "name": entry["name"],
        "position": proj["position"] if proj else None,
        "projected_points": proj["projected_points"] if proj else None,
        "actual_points": float(entry.get("points") or 0.0),
        "selected_position": entry.get("selected_position"),
    }


def _eligible_players(players: list) -> list:
    """Eligible if not on a bye (has a projection). Roster slot is
    ignored, so a player sitting on IR can still be started."""
    return [p for p in players if p.get("projected_points") is not None]


def _best_lineup(players: list, k_slot: dict, def_slot: dict) -> dict:
    """
    Chooses the highest-PROJECTED legal lineup for the 7 skill-position
    slots from `players` (same slot structure/replacement rules as
    calculate_lineups.py's _best_lineup_for_team), but reports each
    slot's ACTUAL points.

    K and DEF are NOT chosen here -- the caller passes their already
    resolved slot dicts in directly.
    """
    eligible = _eligible_players(players)

    by_position = {}
    for p in eligible:
        by_position.setdefault(p["position"], []).append(p)
    for pos in by_position:
        by_position[pos].sort(key=lambda p: p["projected_points"], reverse=True)

    used_ids = set()
    slots = {}

    def take_best(position: str):
        for p in by_position.get(position, []):
            if p["player_id"] not in used_ids:
                used_ids.add(p["player_id"])
                return p
        return None

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
                "actual_points": player["actual_points"],
                "used_replacement": False,
            }

    for slot_name, (position, _count) in DEDICATED_SLOTS.items():
        fill_slot(slot_name, position, position)

    flex_candidates = [
        p for pos in FLEX_ELIGIBLE_POSITIONS
        for p in by_position.get(pos, [])
        if p["player_id"] not in used_ids
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
        used_ids.add(flex_player["player_id"])
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
                "actual_points": flex_player["actual_points"],
                "used_replacement": False,
            }

    slots["K"] = k_slot
    slots["DEF"] = def_slot

    total_actual = round(sum(s["actual_points"] for s in slots.values()), 2)
    total_projected = round(sum(s["projected_points"] for s in slots.values()), 2)
    return {"total_actual_points": total_actual, "total_projected_points": total_projected, "slots": slots}


# --------------------------------------------------------------------------
# PER-TRADE, PER-WEEK EVALUATION
# --------------------------------------------------------------------------
def evaluate_trade_week(sides: dict, week: int, rosters_by_week: dict,
                        projections_by_week: dict) -> tuple[dict, list, bool]:
    """
    Returns ({team_key: {...net gain detail...}}, warnings, no_projection_data)
    for one week of one trade. `no_projection_data` is True iff this week
    had to be skipped entirely because there is no projections file for it.
    """
    warnings = []
    week_projs = projections_by_week.get(week)
    if week_projs is None:
        warnings.append(f"week {week}: no projections data available -- skipped")
        return {}, warnings, True

    week_rosters = rosters_by_week.get(week, {})
    week_index = build_week_index(week_rosters)

    net_gain_by_team = {}

    for team_key, side in sides.items():
        team_name = side["team_name"]
        if team_key not in week_rosters:
            warnings.append(f"week {week}: no roster data for team '{team_name}' -- skipped for this side")
            continue

        roster_entries = week_rosters[team_key]
        real_roster = [build_player(e, week_projs) for e in roster_entries]

        # Counterfactual: real roster with every received player removed
        # and every given-up player (wherever they appear on a roster
        # this week) added in their place. A given-up player on nobody's
        # roster is omitted (nobody available -> replacement fallback).
        received_ids = {m["player_id"] for m in side["received"]}
        counterfactual_roster = [p for p in real_roster if p["player_id"] not in received_ids]
        counterfactual_ids = {p["player_id"] for p in counterfactual_roster}

        gave_up_missing = []
        for m in side["gave_up"]:
            hit = week_index.get(m["player_id"])
            if hit is None:
                gave_up_missing.append(m["player_name"])
                continue
            if m["player_id"] not in counterfactual_ids:
                counterfactual_roster.append(build_player(hit["entry"], week_projs))
                counterfactual_ids.add(m["player_id"])

        if gave_up_missing:
            warnings.append(
                f"week {week}, team '{team_name}': given-up player(s) {gave_up_missing} are on no "
                f"roster this week -- treated as unavailable (replacement-level fallback for that slot)"
            )

        # Traded players who scored but have no projection are almost
        # certainly a name mismatch between Yahoo and Sleeper.
        for p in real_roster:
            if (p["player_id"] in received_ids and p["projected_points"] is None
                    and p["actual_points"] > 0 and p["selected_position"] not in ("K", "DEF")):
                warnings.append(f"week {week}, team '{team_name}': received player {p['name']} scored "
                                f"{p['actual_points']} but has no projection (name mismatch?)")

        # K / DEF: always-start, resolved from the K / DEF slot. The
        # counterfactual swaps a K/DEF out only if THIS trade actually
        # moved the team's real K/DEF.
        real_k = get_kdef_from_roster(roster_entries, "K")
        real_def = get_kdef_from_roster(roster_entries, "DEF")

        received_kdef = {m["position"]: m for m in side["received"] if m["position"] in ("K", "DEF")}
        gave_up_kdef = {m["position"]: m for m in side["gave_up"] if m["position"] in ("K", "DEF")}

        counterfactual_k = real_k
        if (real_k is not None and "K" in received_kdef
                and received_kdef["K"]["player_id"] == real_k["player_id"] and "K" in gave_up_kdef):
            counterfactual_k = kdef_candidate_from_move(gave_up_kdef["K"], week_index)
        counterfactual_def = real_def
        if (real_def is not None and "DEF" in received_kdef
                and received_kdef["DEF"]["player_id"] == real_def["player_id"] and "DEF" in gave_up_kdef):
            counterfactual_def = kdef_candidate_from_move(gave_up_kdef["DEF"], week_index)

        real_k_slot = score_kdef_slot(real_k, "K", week_projs)
        real_def_slot = score_kdef_slot(real_def, "DEF", week_projs)
        counterfactual_k_slot = score_kdef_slot(counterfactual_k, "K", week_projs)
        counterfactual_def_slot = score_kdef_slot(counterfactual_def, "DEF", week_projs)

        real_lineup = _best_lineup(real_roster, real_k_slot, real_def_slot)
        counterfactual_lineup = _best_lineup(counterfactual_roster, counterfactual_k_slot,
                                             counterfactual_def_slot)

        net_gain = round(real_lineup["total_actual_points"] - counterfactual_lineup["total_actual_points"], 2)
        if SHOW_LINEUPS:
            print_week_lineups(
                week, team_name, real_lineup, counterfactual_lineup,
                {m["player_name"] for m in side["received"]},
                {m["player_name"] for m in side["gave_up"]},
            )
            print(f"    Net gain: {net_gain:+.2f}")
        net_gain_by_team[team_key] = {
            "net_gain": net_gain,
            "real_lineup_points": real_lineup["total_actual_points"],
            "counterfactual_lineup_points": counterfactual_lineup["total_actual_points"],
        }

    return net_gain_by_team, warnings, False


def audit_unmatched_players(rosters_by_week: dict, projections_by_week: dict, weeks: list) -> None:
    """Rostered skill players who scored but have no Sleeper projection
    are most likely name mismatches -- they would silently be treated as
    ineligible for lineups, so surface them once per week."""
    for week in weeks:
        projs = projections_by_week.get(week)
        if projs is None:
            continue
        unmatched = set()
        for entries in rosters_by_week.get(week, {}).values():
            for e in entries:
                if e.get("selected_position") in ("K", "DEF"):
                    continue
                pid = str(e["player_id"])
                if pid.isdigit() and int(pid) >= 100000:  # team defense
                    continue
                key = normalize_name(e["name"])
                if key in projs["kickers"]:
                    continue
                if (e.get("points") or 0) > 0 and key not in projs["skill"]:
                    unmatched.add(e["name"])
        if unmatched:
            print(f"  \u26a0 week {week}: scored but not in projections (name mismatch or unprojected): "
                  f"{sorted(unmatched)}")


# --------------------------------------------------------------------------
# ORCHESTRATION
# --------------------------------------------------------------------------
def evaluate_all_trades(year: int, paths: dict, last_week: int | None = None,
                        season_start: date | None = None) -> list:
    season_start = season_start or default_season_start(year)

    transactions = load_json(paths["transactions"])
    trades_raw = fetch_successful_trades(transactions)
    if not trades_raw:
        print("No successful trades found this season.")
        return []

    rosters_by_week = load_rosters_by_week(paths["rosters"])
    last_completed_week = last_week if last_week is not None else max(rosters_by_week)
    all_weeks = [w for w in range(1, last_completed_week + 1) if w in rosters_by_week]
    print(f"[{year}] Season kickoff {season_start}. Last completed week: {last_completed_week}. "
          f"Weeks with roster data: {all_weeks}")

    projections_by_week = {w: load_week_projections(paths["projections_dir"], w) for w in all_weeks}
    audit_unmatched_players(rosters_by_week, projections_by_week, all_weeks)

    results = []

    for tx in trades_raw:
        parsed = parse_trade(tx)
        sides = group_trade_by_side(parsed)

        if len(sides) != 2:
            print(f"  \u26a0 trade {parsed['transaction_id']}: expected exactly 2 teams, "
                  f"found {len(sides)} -- skipping (multi-team trades not supported).")
            continue

        freeze_week = find_freeze_week(parsed, sides, rosters_by_week, all_weeks, season_start)
        if freeze_week is None:
            print(f"  \u26a0 trade {parsed['transaction_id']}: could not determine a freeze week "
                  f"within weeks {all_weeks} (the trade cleared after the last completed "
                  f"week's cutoff, so it first takes effect in a week that hasn't "
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
                sides, week, rosters_by_week, projections_by_week
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


def print_summary(year: int, results: list) -> None:
    print("\n" + "=" * 72)
    print(f"{year} TRADE EVALUATOR SUMMARY")
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


def run_trade_evaluator(year: int, last_week: int | None = None,
                        season_start: date | None = None) -> list:
    paths = get_year_paths(year)
    results = evaluate_all_trades(year, paths, last_week=last_week, season_start=season_start)

    paths["output_dir"].mkdir(parents=True, exist_ok=True)
    output_path = paths["output_dir"] / f"trade_evaluator_{year}.json"
    with open(output_path, "w", encoding="utf-8") as f:
        json.dump(results, f, indent=2, ensure_ascii=False)
    print(f"\nSaved -> {output_path} ({len(results)} trade(s) evaluated)")

    print_summary(year, results)
    return results


def main():
    global SHOW_LINEUPS
    SHOW_LINEUPS = not args.no_lineups
    
    parser = argparse.ArgumentParser(
        description="Evaluate the net point impact of every completed trade for a season."
    )
    parser.add_argument("year", type=int, help="Season year, e.g. 2026")
    parser.add_argument("--last-week", type=int, default=None,
                        help="Last completed week to evaluate (default: the latest week in RosterPoints.json)")
    parser.add_argument("--season-start", type=date.fromisoformat, default=None,
                        help="NFL kickoff date YYYY-MM-DD (default: the Thursday after Labor Day)")
    parser.add_argument("--no-lineups", action="store_true",
                        help="Suppress the per-week lineup printout")
    args = parser.parse_args()

    

    run_trade_evaluator(args.year, last_week=args.last_week, season_start=args.season_start)


if __name__ == "__main__":
    main()