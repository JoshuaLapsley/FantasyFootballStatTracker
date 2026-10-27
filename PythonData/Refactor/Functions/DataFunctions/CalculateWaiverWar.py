"""
Waiver-wire / free-agent pickup WAR for every team in a league, built
from locally saved Yahoo API data. No API calls for the calculation, no images.

Usage
-----
    from CalculateWaiverWAR import calculate_waiver_war

    calculate_waiver_war(league_obj)          # year read from the league's settings
    calculate_waiver_war(league_obj, 2025)    # or give the year explicitly
    calculate_waiver_war("470.l.205662")      # league id string also works
    calculate_waiver_war(year=2026)           # no league needed if the year is given

Inputs (all under ../APIData/{year}/, relative to this script)
--------------------------------------------------------------
    TransactionData.json   add / drop / add/drop / trade transactions
    DraftData.json         draft picks
    RosterPoints.json      {week: {team_key: [{player_id, selected_position, points}]}}
    ZeroScoreReview.json   shared with CalculateWar.py (read, and appended to)

Output
------
    ../APIData/{year}/WaiverWar.json
    One row per (team, pickup player), sorted by WAR descending.

How it matches CalculateWar.py
------------------------------
- D (position averages) comes from calculate_war(year), so waiver WAR is on
  exactly the same scale as WAR.json.
- Weeks used are the same completed weeks calculate_war used.
- Did-not-play rule, replacement levels and the WAR formula are imported from
  CalculateWar.py. Zero-score pickups are auto-logged to ZeroScoreReview.json
  as played=false (flip to true for a real zero), same as drafted players.

Pickup rules
------------
- A (team, player) pair counts if the player was on that team's roster in some
  week and was NOT drafted by that team.
- Pairs where that team acquired the player by a successful trade are excluded
  (vetoed trades are ignored).
- Each team's stint is scored independently, over only the weeks that team had
  the player on its roster (bench/IR included). No minimum-weeks filter.
"""

import argparse
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
        load_zero_score_review,
        auto_flag_zero_scores,
    )
except ImportError:
    from CalculateWar import (
        REPLACEMENT_LEVEL,
        POSITION_ALIASES,
        player_did_not_play,
        win_probability_added,
        calculate_war,
        load_zero_score_review,
        auto_flag_zero_scores,
    )

SCRIPT_DIR = os.path.dirname(os.path.abspath(__file__))
API_DATA_DIR = Path(SCRIPT_DIR) / ".." / "APIData"
OAUTH_FILE = str(Path(SCRIPT_DIR) / ".." / "oauth2.json")


# --------------------------------------------------------------------------
# LOADING
# --------------------------------------------------------------------------
def get_league(league_id: str, oauth_file: str = OAUTH_FILE):
    from yahoo_oauth import OAuth2
    import yahoo_fantasy_api as yfa

    sc = OAuth2(None, None, from_file=oauth_file)
    gm = yfa.Game(sc, "nfl")
    return gm.to_league(league_id)


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


def build_trade_pairs(transactions: list) -> set:
    """(destination_team_key, player_id) for every successful trade."""
    pairs = set()
    for tx in transactions:
        if tx.get("type") != "trade" or tx.get("status") != "successful":
            continue
        for p in tx.get("players", []):
            dest = p.get("destination_team_key")
            if dest:
                pairs.add((dest, str(p["player_id"])))
    return pairs


def identify_pickups(draft: list, rosters_by_week: dict, weeks: list, trade_pairs: set) -> dict:
    """{(team_key, player_id): [weeks rostered by that team]}"""
    drafted_pairs = {(p["team_key"], str(p["player_id"])) for p in draft}

    weeks_by_pair = {}
    for week in weeks:
        for team_key, players in rosters_by_week.get(week, {}).items():
            for player in players:
                weeks_by_pair.setdefault((team_key, str(player["player_id"])), []).append(week)

    return {
        pair: sorted(w)
        for pair, w in weeks_by_pair.items()
        if pair not in drafted_pairs and pair not in trade_pairs
    }


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
def calculate_waiver_war(league=None, year=None, oauth_file: str = OAUTH_FILE) -> list:
    """
    Calculate waiver/FA pickup WAR for every team and write it to
    ../APIData/{year}/WaiverWar.json. Returns the rows written.

    league : yahoo_fantasy_api League or Yahoo league id string. Only used to
             read the season year, so it can be None if `year` is given.
    year   : season year; read from the league's settings if omitted.
    """
    if year is None:
        if league is None:
            raise ValueError("Pass a league or a year.")
        if isinstance(league, str):
            league = get_league(league, oauth_file=oauth_file)
        year = league.settings().get("season")
        if year is None:
            raise ValueError("Could not read the season year from the league; pass year explicitly.")
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
    trade_pairs = build_trade_pairs(transactions)
    pickups = identify_pickups(draft, rosters_by_week, weeks, trade_pairs)
    print(f"[{year}] {len(pickups)} pickup (team, player) pairs; "
          f"{len(trade_pairs)} trade-acquired pairs excluded.")

    actuals_by_week = build_actuals_by_week(rosters_by_week, weeks)

    # Log this week's zero-scoring pickups to the shared review file first.
    review = load_zero_score_review(year)
    for week in weeks:
        pids = {pid for (_team, pid), ws in pickups.items() if week in ws}
        week_board = [
            {
                "player_id": pid,
                "player_name": player_info.get(pid, {}).get("player_name") or pid,
                "position": player_info.get(pid, {}).get("position"),
                "bye_week": None,
            }
            for pid in pids
            if player_info.get(pid, {}).get("position") in REPLACEMENT_LEVEL
        ]
        review = auto_flag_zero_scores(year, week, week_board, actuals_by_week[week], review)

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

        replacement = REPLACEMENT_LEVEL[position]
        war_total = 0.0
        for week in weeks_rostered:
            actual = actuals_by_week.get(week, {}).get(pid)
            dnp = player_did_not_play(actual, None, week, pid, review)
            credited = replacement if dnp else actual
            war_total += win_probability_added(credited - replacement, d_relative)

        team = team_info.get(team_key, {})
        rows.append({
            "Player": info.get("player_name") or pid,
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

    out_dir = API_DATA_DIR / str(year)
    out_dir.mkdir(parents=True, exist_ok=True)
    out_path = out_dir / "WaiverWar.json"
    with open(out_path, "w", encoding="utf-8") as f:
        json.dump(rows, f, indent=4)
    print(f"[{year}] Saved -> {out_path.resolve()} ({len(rows)} rows)")

    return rows


def main():
    parser = argparse.ArgumentParser(description="Calculate waiver-wire/FA pickup WAR for a league.")
    parser.add_argument("--league-id", default=None, help="Yahoo league id, e.g. 470.l.205662")
    parser.add_argument("--year", type=int, default=None,
                        help="Season year (default: read from the league).")
    parser.add_argument("--oauth-file", default=OAUTH_FILE, help="Path to yahoo_oauth credentials json")
    args = parser.parse_args()
    calculate_waiver_war(args.league_id, args.year, oauth_file=args.oauth_file)


if __name__ == "__main__":
    main()