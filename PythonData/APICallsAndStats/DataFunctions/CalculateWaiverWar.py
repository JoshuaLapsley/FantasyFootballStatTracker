"""
Waiver-wire / free-agent pickup WAR for every team in a league, built
from locally saved Yahoo API data. No API calls for the calculation, no images.

Usage
-----
    from CalculateWaiverWAR import calculate_waiver_war

    calculate_waiver_war(league, 2026)

Inputs (all under ../APIData/{year}/, relative to this script)
--------------------------------------------------------------
    TransactionData.json   add / drop / add/drop / trade transactions
    DraftData.json         draft picks
    RosterPoints.json      {week: {team_key: [{player_id, selected_position, points}]}}
    Sleeper projection files (read through ProjectionTranslation.py, via
    CalculateWar.py) decide whether a pickup actually played.

Output
------
    ../Data/{year}/WaiverWar.json
    One row per (team, pickup player), sorted by WAR descending.

How it matches CalculateWar.py
------------------------------
- D (position averages) comes from calculate_war(year), so waiver WAR is on
  exactly the same scale as WAR.json.
- Weeks used are the same completed weeks calculate_war used.
- Did-not-play rule, replacement levels and the WAR formula are imported from
  CalculateWar.py. A player did not play if their Sleeper projection
  (projection_ppr) is 0, null, or missing.

Pickup rules
------------
- A (team, player) pair counts if the player was on that team's roster in some
  week and was NOT drafted by that team.
- Pairs where that team acquired the player by a successful trade are excluded
  (vetoed trades are ignored).
- If the picking team trades the player away, the pickup keeps scoring for the
  picking team each week the player is on the roster of a team that got him
  by trade. It stops once he is dropped or appears on a team that did not get
  him by trade (that team's own waiver pickup is scored separately).
"""

import json
import os
from pathlib import Path

try:
    from .CalculateWar import (
        REPLACEMENT_LEVEL,
        POSITION_ALIASES,
        player_did_not_play,
        win_probability_added,
        calculate_war,
    )
except ImportError:
    from PythonData.APICallsAndStats.DataFunctions.CalculateWar import (
        REPLACEMENT_LEVEL,
        POSITION_ALIASES,
        player_did_not_play,
        win_probability_added,
        calculate_war,
    )

SCRIPT_DIR = os.path.dirname(os.path.abspath(__file__))
API_DATA_DIR = (Path(SCRIPT_DIR) / ".." / "APIData").resolve()   # inputs
DATA_DIR = (Path(SCRIPT_DIR) / ".." / "Data").resolve()          # output


# --------------------------------------------------------------------------
# LOADING
# --------------------------------------------------------------------------
def _load_json(path: Path):
    if not path.exists():
        raise FileNotFoundError(f"{path} not found.")
    with open(path, "r", encoding="utf-8") as f:
        return json.load(f)


def load_year_data(year) -> tuple:
    year_dir = API_DATA_DIR / str(year)
    transactions = _load_json(year_dir / "TransactionData.json")
    draft = _load_json(year_dir / "DraftData.json")
    rosters_raw = _load_json(year_dir / "RosterPoints.json")
    rosters_by_week = {int(week): teams for week, teams in rosters_raw.items()}
    return transactions, draft, rosters_by_week


# --------------------------------------------------------------------------
# PLAYER + TEAM INFO from the saved files
# --------------------------------------------------------------------------
def build_player_info(draft: list, transactions: list) -> dict:
    """{player_id: {"player_name", "position"}}"""
    info = {}
    for p in draft:
        pid = str(p["player_id"])
        pos = p.get("position")
        info[pid] = {
            "player_name": p.get("player_name"),
            "position": POSITION_ALIASES.get(pos, pos),
        }
    for tx in transactions:
        for p in tx.get("players", []):
            pid = str(p["player_id"])
            pos = p.get("position")
            entry = info.setdefault(pid, {"player_name": None, "position": None})
            if not entry["player_name"]:
                entry["player_name"] = p.get("player_name")
            if not entry["position"]:
                entry["position"] = POSITION_ALIASES.get(pos, pos)
    return info


def build_team_info(draft: list, transactions: list) -> dict:
    """{team_key: {"team_name", "manager_nickname"}}"""
    teams = {}
    for p in draft:
        teams[p["team_key"]] = {
            "team_name": p.get("team_name"),
            "manager_nickname": p.get("manager_nickname"),
        }
    for tx in transactions:
        for p in tx.get("players", []):
            for key_field, name_field in (("destination_team_key", "destination_team_name"),
                                          ("source_team_key", "source_team_name")):
                key = p.get(key_field)
                if key and key not in teams:
                    teams[key] = {"team_name": p.get(name_field), "manager_nickname": None}
    return teams


def build_trade_pairs(transactions: list, team_info: dict) -> tuple:
    """
    Returns (pairs, edges) for every successful trade.

      pairs : {(destination_team_key, player_id)}
      edges : {(source_team_key or None, destination_team_key, player_id)}

    Team keys are resolved in this order, because trade players don't
    always carry a team key of their own:
      1. the player's own destination/source_team_key
      2. the transaction's trader/tradee keys, matched by team name
      3. any team name -> key seen in the draft / transaction data
    A trade player whose destination can't be resolved is reported, since it
    would otherwise slip through as a waiver pickup.
    """
    name_to_key = {
        info["team_name"]: key
        for key, info in team_info.items()
        if info.get("team_name")
    }

    pairs = set()
    edges = set()
    unresolved = []
    for tx in transactions:
        if tx.get("type") != "trade" or tx.get("status") != "successful":
            continue

        tx_name_to_key = {}
        for side in ("trader", "tradee"):
            name = tx.get(f"{side}_team_name")
            key = tx.get(f"{side}_team_key")
            if name and key:
                tx_name_to_key[name] = key

        for p in tx.get("players", []):
            dest_name = p.get("destination_team_name")
            dest = (
                p.get("destination_team_key")
                or tx_name_to_key.get(dest_name)
                or name_to_key.get(dest_name)
            )
            src_name = p.get("source_team_name")
            src = (
                p.get("source_team_key")
                or tx_name_to_key.get(src_name)
                or name_to_key.get(src_name)
            )
            if dest:
                pid = str(p["player_id"])
                pairs.add((dest, pid))
                edges.add((src, dest, pid))   # src may be None if unresolved
            else:
                unresolved.append(
                    f"{p.get('player_name')} -> {dest_name} "
                    f"(transaction {tx.get('transaction_id')})"
                )

    if unresolved:
        print(f"  WARNING: couldn't resolve the destination team for "
              f"{len(unresolved)} traded player(s); they may appear as pickups:")
        for line in unresolved:
            print(f"    {line}")

    return pairs, edges


def _trade_reachable(edges_from: dict, start: str, target: str) -> bool:
    """True if `target` can be reached from `start` through trade edges
    (handles A -> B -> C chains between weekly snapshots). An edge whose
    source couldn't be resolved (stored under None) counts as from anyone."""
    seen = {start}
    stack = [start]
    while stack:
        cur = stack.pop()
        for nxt in edges_from.get(cur, set()) | edges_from.get(None, set()):
            if nxt == target:
                return True
            if nxt not in seen:
                seen.add(nxt)
                stack.append(nxt)
    return False


def identify_pickups(draft: list, rosters_by_week: dict, weeks: list,
                     trade_pairs: set, trade_edges: set) -> dict:
    """
    {(team_key, player_id): [weeks credited to that team's pickup]}

    A pickup is credited for every week the picking team held the player,
    plus every week afterwards that the player sits on the roster of a team
    that got him (directly or via a chain) by trade from that team. The
    credit ends the first week the player is dropped (on no roster) or is on
    a team that didn't get him by trade, and doesn't restart unless the
    picking team holds him again.
    """
    drafted_pairs = {(p["team_key"], str(p["player_id"])) for p in draft}

    # who holds each player each week
    owner_by_week = {}
    held_pairs = set()
    for week in weeks:
        owners = {}
        for team_key, players in rosters_by_week.get(week, {}).items():
            for player in players:
                pid = str(player["player_id"])
                owners[pid] = team_key
                held_pairs.add((team_key, pid))
        owner_by_week[week] = owners

    # {pid: {source_team: {destination_teams}}}
    edges_by_pid = {}
    for src, dest, pid in trade_edges:
        edges_by_pid.setdefault(pid, {}).setdefault(src, set()).add(dest)

    pickups = {}
    for team_key, pid in held_pairs:
        pair = (team_key, pid)
        if pair in drafted_pairs or pair in trade_pairs:
            continue

        edges_from = edges_by_pid.get(pid, {})
        credited = []
        chain_active = False
        holder = None
        for week in weeks:
            owner = owner_by_week[week].get(pid)
            if owner == team_key:
                credited.append(week)
                chain_active, holder = True, team_key
            elif (chain_active and owner is not None
                  and _trade_reachable(edges_from, holder, owner)):
                credited.append(week)      # traded away, still on someone's roster
                holder = owner
            else:
                chain_active, holder = False, None   # dropped / picked up elsewhere
        pickups[pair] = credited

    return pickups


def build_actuals_by_week(rosters_by_week: dict, weeks: list) -> dict:
    """{week: {player_id: points}} for everyone on any roster that week."""
    actuals_by_week = {}
    for week in weeks:
        actuals = {}
        for players in rosters_by_week.get(week, {}).values():
            for player in players:
                try:
                    actuals[str(player["player_id"])] = float(player.get("points", 0.0))
                except (TypeError, ValueError):
                    actuals[str(player["player_id"])] = 0.0
        actuals_by_week[week] = actuals
    return actuals_by_week


# --------------------------------------------------------------------------
# MAIN FUNCTION
# --------------------------------------------------------------------------
def calculate_waiver_war(league, year) -> list:
    """
    Calculate waiver/FA pickup WAR for every team and write it to
    ../Data/{year}/WaiverWar.json. Returns the rows written.

    league : the authenticated Yahoo league object. The calculation reads
             only locally saved files, so the league is not queried; it is
             accepted so this matches how the other steps are called.
    year   : season year.
    """
    year = int(year)

    transactions, draft, rosters_by_week = load_year_data(year)

    # D and the completed-week list come straight from the drafted-player WAR.
    _results, weeks_used, position_averages = calculate_war(year)
    weeks = [w for w in weeks_used if w in rosters_by_week]
    d_relative_by_pos = {
        pos: d - REPLACEMENT_LEVEL[pos]
        for pos, d in position_averages.items()
        if pos in REPLACEMENT_LEVEL
    }
    print(f"[{year}] Weeks processed: {weeks}")

    player_info = build_player_info(draft, transactions)
    team_info = build_team_info(draft, transactions)
    trade_pairs, trade_edges = build_trade_pairs(transactions, team_info)
    pickups = identify_pickups(draft, rosters_by_week, weeks, trade_pairs, trade_edges)
    print(f"[{year}] {len(pickups)} pickup (team, player) pairs; "
          f"{len(trade_pairs)} trade-acquired pairs excluded.")

    actuals_by_week = build_actuals_by_week(rosters_by_week, weeks)

    rows = []
    for (team_key, pid), weeks_rostered in pickups.items():
        info = player_info.get(pid)
        if not info:
            continue
        position = info.get("position")
        if position not in REPLACEMENT_LEVEL:
            continue
        d_relative = d_relative_by_pos.get(position)
        if d_relative is None:
            continue

        player_name = info.get("player_name") or pid
        replacement = REPLACEMENT_LEVEL[position]
        war_total = 0.0
        for week in weeks_rostered:
            actual = actuals_by_week.get(week, {}).get(pid)
            dnp = player_did_not_play(player_name, actual, None, week, year)
            credited = replacement if dnp else actual
            war_total += win_probability_added(credited - replacement, d_relative)

        team = team_info.get(team_key, {})
        rows.append({
            "Player": player_name,
            "Player ID": pid,
            "Position": position,
            "Team": team.get("team_name") or team_key,
            "Team Key": team_key,
            "Manager": team.get("manager_nickname"),
            "Weeks Rostered": weeks_rostered,
            "WAR": round(war_total, 4) + 0.0,  # + 0.0 turns -0.0 into 0.0
        })

    rows.sort(key=lambda r: r["WAR"], reverse=True)
    for rank, row in enumerate(rows, start=1):
        row["WAR Rank"] = rank

    out_dir = DATA_DIR / str(year)
    out_dir.mkdir(parents=True, exist_ok=True)
    out_path = out_dir / "WaiverWar.json"
    with open(out_path, "w", encoding="utf-8") as f:
        json.dump(rows, f, indent=4)
    print(f"[{year}] Saved -> {out_path} ({len(rows)} rows)")

    return rows