"""
Calculate PABB (Points Above Best Bench) for every team's current
starting lineup and write it to JSON + a PNG roster board.

--------------------------------------------------------------------------
WHAT "PABB" MEANS HERE
--------------------------------------------------------------------------
PABB measures how many points a team has lost, in total this season, by
rostering a given player instead of a typical replacement-level option
at that position, given this league's format (14 teams; 1 QB, 2 RB,
2 WR, 1 TE, 1 FLEX that can be RB/WR/TE).

Replacement level is recomputed SEPARATELY FOR EVERY COMPLETED WEEK,
using that week's own roster situation and that week's own projections
(not today's roster projected backward) -- an RB who was a clear
must-start in week 2 might have been much deeper on the depth chart by
week 7, and replacement level should reflect what was actually true
each week:

  For each completed week w:
    1. Pull every team's full roster AS OF week w (starters + bench +
       IR, via Yahoo) and that week's saved Sleeper projections
       (../APICallsAndStats/Projections/SleeperProjections/{year}/
       projections/week_{w:02d}.json).
    2. Drop any rostered player not projected for more than 0 points
       that week (covers byes, injuries, and non-factors in one rule --
       no separate Yahoo injury-status check) from every ranking group
       below.
    3. Rank the remaining rostered players at each position by that
       week's projected points and fill the league-wide starting slots
       (14 QB, 28 RB, 28 WR, 14 TE), then the 14 FLEX slots from
       whichever leftover RB/WR/TE players projected best that week --
       however many of each position land in FLEX is that week's
       empirical flex share, p_w.
    4. The next `num_teams` (14) leftover rostered players at each
       position become that week's "replacement bench player band",
       filled with rostered players first and topped off with the
       highest-projected WAIVER players that week (anyone in that
       week's Sleeper projections not on any of the 14 rosters) if the
       rostered bench wasn't deep enough.
    5. A second "flex band" pools the best 14 players, by that week's
       projection, out of the three position bands combined.
    6. That week's band baseline for a position = the average of its
       band members' REAL Yahoo actual points IN THAT WEEK. Waiver
       (non-rostered) members have no Yahoo player_id from a roster
       pull, so each one is resolved to its real Yahoo player_id first
       (for free, if they were ever rostered by anyone in another week;
       otherwise via a Yahoo player-name search) so they're scored
       exactly like a rostered player. Any band member who didn't play
       that week (no data, or an exact 0.0) is excluded from the
       average rather than dragging it to 0.
    7. That week's replacement level for RB/WR/TE blends the two bands:
           replacement_w = p_w * flex_band_baseline_w
                          + (1 - p_w) * position_band_baseline_w
       QB has no flex eligibility in this league, so QB replacement_w
       is just that week's position-only band baseline.

  Each currently-rostered player's season PABB is then the SUM, across
  every completed week, of (that week's own actual points -
  that week's replacement level for their position) -- 0 for any week
  they didn't play (bye/DNP), so a bye week neither helps nor hurts.
  This mirrors the same "0 for a non-playing week" convention already
  used by CalculatePAR.py / CalculateWar.py elsewhere in this codebase,
  just applied to a data-driven, week-specific replacement level
  instead of one flat constant.

Name matching: Yahoo and Sleeper use different player IDs, so rostered
players are matched to Sleeper projections each week by normalized
name (position as a tiebreaker for collisions). Any rostered player
this script can't confidently match to that week's projection is
treated the same as a bye for that week (excluded from ranking groups).

--------------------------------------------------------------------------
OUTPUT
--------------------------------------------------------------------------
    ../APICallsAndStats/Data/{year}/PABB.json
        - weekly_replacement_level / weekly_band_baseline / weekly_p /
          weekly_flex_band_baseline: one entry per completed week
        - most_recent_week_detail: full band membership for the last
          completed week only (for sanity-checking)
        - teams: each team's CURRENT lineup (QB, RB, RB, WR, WR, TE,
          FLEX), each slot's season-summed PABB plus a week-by-week
          margin breakdown
    ../APICallsAndStats/Data/{year}/PABB/pabb_board_{year}_week{week}.png
        (+ _colorbar.png)

Usage:
    python3 CalculatePABB.py          # current season
"""

import json
import re
from pathlib import Path

import matplotlib
matplotlib.use("Agg")
import matplotlib.cm
import matplotlib.colors
import matplotlib.pyplot as plt

from yahoo_oauth import OAuth2
import yahoo_fantasy_api as yfa

SCRIPT_DIR = Path(__file__).resolve().parent
PYTHON_DATA_DIR = SCRIPT_DIR / ".."

OAUTH_FILE = SCRIPT_DIR / "oauth2.json"
LEAGUE_NAME_HINT = "Girderma Gridiron"  # used to disambiguate if the Yahoo
                                        # account belongs to multiple leagues

PROJECTIONS_ROOT = (PYTHON_DATA_DIR / "APICallsAndStats" / "Projections"
                     / "SleeperProjections").resolve()
DATA_ROOT = (PYTHON_DATA_DIR / "APICallsAndStats" / "Data").resolve()

YEAR = 2026

DEDICATED_PER_TEAM = {"QB": 1, "RB": 2, "WR": 2, "TE": 1}
FLEX_ELIGIBLE = ("RB", "WR", "TE")
FLEX_PER_TEAM = 1
SKILL_POSITIONS = ("QB", "RB", "WR", "TE")

# Statuses that mean "can't be counted on this week" -- excluded from
# every ranking group for that week (but still shown on a team's actual
# current lineup if a manager started them anyway).
INJURED_STATUSES = {"IR", "IR-R", "IR+", "O", "PUP", "NFI", "SUSP", "COVID-19"}

# Yahoo roster slot name -> output board row, in the order the user wants.
SLOT_ORDER = ["QB", "RB1", "RB2", "WR1", "WR2", "TE", "FLEX"]

SUFFIX_WORDS = {"jr", "sr", "ii", "iii", "iv", "v"}


# --------------------------------------------------------------------------
# AUTH
# --------------------------------------------------------------------------
def get_league(year: int = YEAR):
    sc = OAuth2(None, None, from_file=str(OAUTH_FILE))
    gm = yfa.Game(sc, "nfl")
    league_ids = gm.league_ids(year=year)
    if len(league_ids) == 1:
        return gm.to_league(league_ids[0])

    for league_id in league_ids:
        candidate = gm.to_league(league_id)
        if candidate.settings().get("name") == LEAGUE_NAME_HINT:
            return candidate

    print(f"Warning: couldn't find a league named {LEAGUE_NAME_HINT!r} among "
          f"{league_ids}; defaulting to the first one.")
    return gm.to_league(league_ids[0])


# --------------------------------------------------------------------------
# NAME NORMALIZATION / MATCHING
# --------------------------------------------------------------------------
def normalize_name(name: str) -> str:
    if not name:
        return ""
    name = name.lower()
    name = name.replace("'", "").replace(".", "").replace("-", " ")
    words = [w for w in re.sub(r"[^a-z0-9 ]", "", name).split() if w not in SUFFIX_WORDS]
    return " ".join(words)


def primary_position(eligible_positions) -> str | None:
    """First skill position (QB/RB/WR/TE) in a Yahoo roster entry's
    eligible_positions list -- a player's natural position, independent
    of whatever slot (BN/IR/W-R-T/etc.) they currently occupy."""
    for pos in eligible_positions or []:
        if pos in SKILL_POSITIONS:
            return pos
    return None


# --------------------------------------------------------------------------
# ROSTERS (live; works for the current week or any past week)
# --------------------------------------------------------------------------
def fetch_rosters_for_week(lg, team_names: dict, week: int) -> list:
    """Returns a list of rostered skill-position players AS OF `week`:
        {team_key, team_name, player_id (str), name, position,
         selected_position, status, injured (bool)}
    `week` can be the current week or any already-played week -- Yahoo
    returns that week's actual roster snapshot either way.
    """
    rostered_players = []
    for team_key, team_name in team_names.items():
        roster = lg.to_team(team_key).roster(week=week)
        for p in roster:
            pos = primary_position(p.get("eligible_positions"))
            if pos is None:
                continue  # K / DEF / anything outside this league's skill positions
            rostered_players.append({
                "team_key": team_key,
                "team_name": team_name,
                "player_id": str(p["player_id"]),
                "name": p["name"],
                "position": pos,
                "selected_position": p.get("selected_position"),
                "status": p.get("status") or "",
                "injured": (p.get("status") or "") in INJURED_STATUSES,
            })
    return rostered_players


# --------------------------------------------------------------------------
# SLEEPER PROJECTIONS
# --------------------------------------------------------------------------
def load_week_projections(year: int, week: int) -> list:
    path = PROJECTIONS_ROOT / str(year) / "projections" / f"week_{week:02d}.json"
    if not path.exists():
        raise FileNotFoundError(
            f"No Sleeper projections file for {year} week {week}: {path}"
        )
    with open(path, encoding="utf-8") as f:
        data = json.load(f)
    return [p for p in data.get("players", []) if p.get("position") in SKILL_POSITIONS]


def build_projection_index(players: list) -> dict:
    """{normalized_name: [player_dict, ...]}"""
    index = {}
    for p in players:
        key = normalize_name(p.get("name"))
        if not key:
            continue
        index.setdefault(key, []).append(p)
    return index


def match_rostered_players(rostered_players: list, proj_index: dict) -> list:
    """Returns list of normalized names matched to a rostered player,
    and annotates each rostered player in-place with
    'projected_points' (float or None) and 'matched' (bool)."""
    used_norm_names = []

    for rp in rostered_players:
        key = normalize_name(rp["name"])
        candidates = proj_index.get(key, [])
        chosen = None
        if len(candidates) == 1:
            chosen = candidates[0]
        elif len(candidates) > 1:
            same_pos = [c for c in candidates if c.get("position") == rp["position"]]
            if same_pos:
                chosen = same_pos[0]
            else:
                chosen = candidates[0]

        if chosen is not None:
            rp["projected_points"] = chosen.get("pts_ppr")
            rp["matched"] = True
            used_norm_names.append(key)
        else:
            rp["projected_points"] = None
            rp["matched"] = False

    return used_norm_names


def build_waiver_pool(proj_index: dict, used_norm_names: list) -> dict:
    """Returns {position: [player_dict, ...]} sorted by projected points
    desc, for every Sleeper-projected player not matched to one of the
    14 rosters that week AND projected for more than 0 points that week
    (i.e. actually expected to play). Each entry gets a
    'projected_points' key (mirroring rostered_players' field name) so
    downstream ranking code can treat rostered and waiver candidates
    identically."""
    used = set(used_norm_names)
    pool = {pos: [] for pos in SKILL_POSITIONS}
    for key, candidates in proj_index.items():
        if key in used:
            continue
        for c in candidates:
            pos = c.get("position")
            pts = c.get("pts_ppr")
            if pos in pool and pts:
                entry = dict(c)
                entry["projected_points"] = pts
                pool[pos].append(entry)
    for pos in pool:
        pool[pos].sort(key=lambda p: p["projected_points"] or 0, reverse=True)
    return pool


# --------------------------------------------------------------------------
# WEEKLY ACTUAL POINTS (Yahoo), for one set of player ids, many weeks
# --------------------------------------------------------------------------
BATCH_SIZE = 25
POINT_KEYS = ("total_points", "points", "fantasy_points")


def _extract_points(stat_row):
    for key in POINT_KEYS:
        if key in stat_row:
            try:
                return float(stat_row[key])
            except (TypeError, ValueError):
                return None
    return None


def fetch_weekly_actual_points(lg, player_ids: list, weeks: list) -> dict:
    """Returns {week (int): {player_id (str): points}}. A player with
    no entry for a given week (bye, no data) is simply absent from that
    week's dict -- callers treat a missing id the same as DNP."""
    ids = sorted({int(pid) for pid in player_ids})
    by_week = {}
    for week in weeks:
        points = {}
        for i in range(0, len(ids), BATCH_SIZE):
            batch = ids[i:i + BATCH_SIZE]
            try:
                stats = lg.player_stats(batch, "week", week=week)
            except Exception as e:
                print(f"  \u26a0 week {week} actuals batch starting {batch[0]} failed: {e}")
                continue
            for row in stats:
                pid = str(row.get("player_id"))
                pts = _extract_points(row)
                if pts is not None:
                    points[pid] = pts
        by_week[week] = points
        print(f"  fetched actuals for week {week} ({len(points)} players)")
    return by_week


# --------------------------------------------------------------------------
# RANKING: starters, flex, bands, p -- for a single week's roster
# --------------------------------------------------------------------------
def eligible_candidates(rostered_players: list, position: str) -> list:
    """Rostered players at `position` who are projected for more than 0
    points that week -- i.e. actually expected to play (this excludes
    byes, injuries, and anyone this script couldn't match to a
    projection at all, with no separate injury-status check needed)."""
    return [
        p for p in rostered_players
        if p["position"] == position and (p["projected_points"] or 0) > 0
    ]


def build_bands_and_replacement(rostered_players: list, waiver_pool: dict, num_teams: int) -> dict:
    """
    Returns a dict with starters/flex/band membership and the p values
    for ONE week, built entirely from that week's rostered_players +
    waiver_pool.
    """
    band_size = num_teams
    result = {"dedicated_starters": {}, "flex_starters": [], "p": {},
              "position_bands": {}, "flex_band": []}

    leftover_by_pos = {}
    for pos in SKILL_POSITIONS:
        pool = sorted(eligible_candidates(rostered_players, pos),
                       key=lambda p: p["projected_points"], reverse=True)
        n_dedicated = DEDICATED_PER_TEAM[pos] * num_teams
        result["dedicated_starters"][pos] = pool[:n_dedicated]
        leftover_by_pos[pos] = pool[n_dedicated:]

    # FLEX: best remaining RB/WR/TE by projection.
    flex_candidates = sorted(
        (p for pos in FLEX_ELIGIBLE for p in leftover_by_pos[pos]),
        key=lambda p: p["projected_points"], reverse=True,
    )
    n_flex = FLEX_PER_TEAM * num_teams
    flex_starters = flex_candidates[:n_flex]
    result["flex_starters"] = flex_starters
    flex_ids = {p["player_id"] for p in flex_starters}

    flex_count_by_pos = {pos: 0 for pos in FLEX_ELIGIBLE}
    for p in flex_starters:
        flex_count_by_pos[p["position"]] += 1
    for pos in FLEX_ELIGIBLE:
        result["p"][pos] = flex_count_by_pos[pos] / n_flex if n_flex else 0.0

    for pos in FLEX_ELIGIBLE:
        leftover_by_pos[pos] = [p for p in leftover_by_pos[pos] if p["player_id"] not in flex_ids]

    # Position-only bands: next `band_size` leftover rostered players per
    # position, topped off with the best available waiver players.
    for pos in SKILL_POSITIONS:
        rostered_band = leftover_by_pos[pos][:band_size]
        need = band_size - len(rostered_band)
        waiver_band = waiver_pool.get(pos, [])[:need] if need > 0 else []
        result["position_bands"][pos] = {"rostered": rostered_band, "waiver": waiver_band}
        leftover_by_pos[pos] = leftover_by_pos[pos][band_size:]

    # Flex band: best 14 (band_size), pooled across the three position
    # bands just built (rostered + waiver members alike).
    flex_band_candidates = []
    for pos in FLEX_ELIGIBLE:
        flex_band_candidates.extend(result["position_bands"][pos]["rostered"])
        flex_band_candidates.extend(result["position_bands"][pos]["waiver"])
    flex_band_candidates.sort(key=lambda p: p["projected_points"] or 0, reverse=True)
    result["flex_band"] = flex_band_candidates[:band_size]

    return result


# --------------------------------------------------------------------------
# YAHOO ID RESOLUTION FOR WAIVER BAND MEMBERS
# --------------------------------------------------------------------------
# A waiver-pool band member only exists in our data via their Sleeper
# record (no Yahoo player_id, since they were never on any of the 14
# rosters). To score them with REAL actual points (not a projection
# proxy) we need their Yahoo player_id too. Most of the time they turn
# out to already be known -- rostered by someone in some OTHER week of
# the season -- so the cheap path is a name lookup against everyone
# who was ever rostered; only a true, never-rostered free agent needs
# an actual Yahoo player search (league.player_details(name)).
def build_known_name_to_yahoo_id(all_weekly_rosters: list) -> dict:
    known = {}
    for roster in all_weekly_rosters:
        for p in roster:
            known.setdefault(normalize_name(p["name"]), p["player_id"])
    return known


def resolve_waiver_yahoo_ids(lg, waiver_members: list, known_name_to_id: dict) -> dict:
    """Mutates each member dict in `waiver_members` in place, adding
    'resolved_player_id' (str or None). Returns {name: player_id or None}
    for logging/debugging. Caches player_details() lookups so the same
    never-rostered free agent is only searched once even if they appear
    in multiple weeks' bands."""
    search_cache = {}
    resolved_log = {}

    for member in waiver_members:
        norm = normalize_name(member.get("name"))
        pid = known_name_to_id.get(norm)
        if pid is None:
            if norm not in search_cache:
                try:
                    results = lg.player_details(member["name"])
                except Exception as e:
                    print(f"  \u26a0 player_details lookup failed for {member['name']!r}: {e}")
                    results = []
                match = next(
                    (r for r in results if normalize_name(r.get("name", {}).get("full")) == norm),
                    results[0] if results else None,
                )
                search_cache[norm] = str(match["player_id"]) if match else None
            pid = search_cache[norm]
        member["resolved_player_id"] = pid
        resolved_log[member.get("name")] = pid

    return resolved_log


# --------------------------------------------------------------------------
# PER-WEEK VALUE LOOKUP (real actual points for everyone, rostered or
# waiver) + baseline averaging
# --------------------------------------------------------------------------
def _member_yahoo_id(member: dict):
    if "team_key" in member:  # rostered that week -- real Yahoo player_id
        return member["player_id"]
    return member.get("resolved_player_id")  # waiver -- resolved separately


def band_member_week_value(member: dict, week_actuals: dict):
    """Returns the value of one band member FOR THIS WEEK (their real
    Yahoo actual points), or None if they didn't play that week (no
    Yahoo id resolved, no data for that week, or an exact 0.0) --
    excluded from the average instead of dragging it to 0."""
    pid = _member_yahoo_id(member)
    if pid is None:
        return None
    raw = week_actuals.get(pid)
    if raw is None or raw == 0.0:
        return None
    return raw


def weekly_band_baseline(members: list, week_actuals: dict) -> float:
    values = [v for v in (band_member_week_value(m, week_actuals) for m in members) if v is not None]
    return sum(values) / len(values) if values else 0.0


def band_member_detail(member: dict, week_actuals: dict) -> dict:
    value = band_member_week_value(member, week_actuals)
    return {
        "player_name": member.get("name"),
        "position": member.get("position"),
        "source": "rostered" if "team_key" in member else "waiver",
        "week_actual_points": round(value, 2) if value is not None else None,
    }


# --------------------------------------------------------------------------
# TEAM BOARDS (current roster, actual manager lineup)
# --------------------------------------------------------------------------
def build_team_lineup(roster_players: list) -> dict:
    """Returns {slot_name: player_dict or None} for one team's players,
    using their CURRENT selected_position (actual manager lineup)."""
    lineup = {slot: None for slot in SLOT_ORDER}
    rb_i = wr_i = 0
    for p in roster_players:
        sel = p["selected_position"]
        if sel == "QB":
            lineup["QB"] = p
        elif sel == "RB":
            rb_i += 1
            if rb_i <= 2:
                lineup[f"RB{rb_i}"] = p
        elif sel == "WR":
            wr_i += 1
            if wr_i <= 2:
                lineup[f"WR{wr_i}"] = p
        elif sel == "TE":
            lineup["TE"] = p
        elif sel == "W/R/T":
            lineup["FLEX"] = p
    return lineup


# --------------------------------------------------------------------------
# MAIN CALCULATION
# --------------------------------------------------------------------------
def calculate_pabb(year: int = YEAR):
    lg = get_league(year)
    current_week = lg.current_week()
    completed_weeks = list(range(1, current_week))  # weeks with real results
    num_teams = int(lg.settings().get("num_teams", 14))

    print(f"League: {lg.settings().get('name')}  Current week: {current_week}  "
          f"Completed weeks: {completed_weeks}  Teams: {num_teams}")

    team_names = {k: v["name"] for k, v in lg.teams().items()}

    current_roster = fetch_rosters_for_week(lg, team_names, current_week)
    print(f"Fetched {len(current_roster)} currently-rostered skill players.")

    # ---- per-week roster snapshot + band/replacement computation ----
    weekly_rosters = {}
    weekly_bands = {}
    not_playing_by_week = {}
    for w in completed_weeks:
        roster_w = fetch_rosters_for_week(lg, team_names, w)
        proj_w = load_week_projections(year, w)
        index_w = build_projection_index(proj_w)
        match_rostered_players(roster_w, index_w)
        used_w = [normalize_name(p["name"]) for p in roster_w if (p["projected_points"] or 0) > 0]
        waiver_w = build_waiver_pool(index_w, used_w)
        bands_w = build_bands_and_replacement(roster_w, waiver_w, num_teams)

        weekly_rosters[w] = roster_w
        weekly_bands[w] = bands_w
        not_playing_by_week[w] = [p for p in roster_w if (p["projected_points"] or 0) <= 0]
        print(f"  week {w}: {len(roster_w)} rostered players, "
              f"{len(not_playing_by_week[w])} not projected to play "
              f"(0 projection, bye, or unmatched)")

    # ---- resolve a real Yahoo player_id for every waiver-pool band
    #      member, so their baseline contribution uses real actual
    #      points instead of a projection proxy ----
    all_known_rosters = list(weekly_rosters.values()) + [current_roster]
    known_name_to_id = build_known_name_to_yahoo_id(all_known_rosters)

    waiver_members_all = [
        m
        for w in completed_weeks
        for pos in SKILL_POSITIONS
        for m in weekly_bands[w]["position_bands"][pos]["waiver"]
    ]
    print(f"Resolving Yahoo player ids for {len(waiver_members_all)} waiver-band "
          f"member appearance(s) across all weeks...")
    resolved_log = resolve_waiver_yahoo_ids(lg, waiver_members_all, known_name_to_id)
    unresolved_waiver_players = sorted({name for name, pid in resolved_log.items() if pid is None})
    if unresolved_waiver_players:
        print(f"  \u26a0 could not resolve a Yahoo id for: {unresolved_waiver_players}")

    # ---- actual points for every player who appears in any week's
    #      roster, on today's roster, or as a resolved waiver band
    #      member, for every completed week ----
    id_universe = {p["player_id"] for p in current_roster}
    for w in completed_weeks:
        id_universe.update(p["player_id"] for p in weekly_rosters[w])
    id_universe.update(pid for pid in resolved_log.values() if pid is not None)

    print(f"Fetching weekly actual points for {len(id_universe)} players "
          f"across {len(completed_weeks)} completed week(s)...")
    weekly_actuals = fetch_weekly_actual_points(lg, list(id_universe), completed_weeks)

    # ---- weekly baselines / replacement levels ----
    weekly_band_baseline_out = {}
    weekly_flex_band_baseline_out = {}
    weekly_p_out = {}
    weekly_replacement_level = {}

    for w in completed_weeks:
        bands_w = weekly_bands[w]
        actuals_w = weekly_actuals.get(w, {})

        pos_baseline_w = {}
        for pos in SKILL_POSITIONS:
            members = bands_w["position_bands"][pos]["rostered"] + bands_w["position_bands"][pos]["waiver"]
            pos_baseline_w[pos] = weekly_band_baseline(members, actuals_w)

        flex_baseline_w = weekly_band_baseline(bands_w["flex_band"], actuals_w)

        replacement_w = {}
        for pos in SKILL_POSITIONS:
            if pos in FLEX_ELIGIBLE:
                p_val = bands_w["p"][pos]
                replacement_w[pos] = p_val * flex_baseline_w + (1 - p_val) * pos_baseline_w[pos]
            else:
                replacement_w[pos] = pos_baseline_w[pos]

        weekly_band_baseline_out[w] = {pos: round(v, 2) for pos, v in pos_baseline_w.items()}
        weekly_flex_band_baseline_out[w] = round(flex_baseline_w, 2)
        weekly_p_out[w] = {pos: round(bands_w["p"][pos], 4) for pos in FLEX_ELIGIBLE}
        weekly_replacement_level[w] = {pos: round(v, 2) for pos, v in replacement_w.items()}

    # ---- season PABB per currently-rostered player: sum of weekly
    #      margins (0 for any week they didn't play) ----
    def season_margin(pid: str, position: str) -> dict:
        weekly_margins = {}
        season_actual = 0.0
        weeks_counted = 0
        for w in completed_weeks:
            raw = weekly_actuals.get(w, {}).get(pid)
            dnp = raw is None or raw == 0.0
            if dnp:
                weekly_margins[str(w)] = 0.0
                continue
            rep = weekly_replacement_level[w][position]
            weekly_margins[str(w)] = round(raw - rep, 2)
            season_actual += raw
            weeks_counted += 1
        return {
            "weekly_margins": weekly_margins,
            "pabb": round(sum(weekly_margins.values()), 2),
            "season_actual_points": round(season_actual, 2),
            "weeks_counted": weeks_counted,
        }

    # ---- per-team current lineup + PABB ----
    by_team = {}
    for p in current_roster:
        by_team.setdefault(p["team_key"], []).append(p)

    teams_output = {}
    for team_key, team_name in team_names.items():
        lineup = build_team_lineup(by_team.get(team_key, []))
        slots_out = []
        for slot in SLOT_ORDER:
            player = lineup[slot]
            if player is None:
                slots_out.append({"slot": slot, "player": None})
                continue
            margin_info = season_margin(player["player_id"], player["position"])
            slots_out.append({
                "slot": slot,
                "player_id": player["player_id"],
                "player_name": player["name"],
                "position": player["position"],
                "status": player["status"],
                **margin_info,
            })
        teams_output[team_name] = {"team_key": team_key, "slots": slots_out}

    # ---- full band detail for the most recently completed week only
    #      (so the output isn't 7x the band-membership payload) ----
    most_recent_detail = None
    if completed_weeks:
        last_w = completed_weeks[-1]
        bands_w = weekly_bands[last_w]
        actuals_w = weekly_actuals.get(last_w, {})
        detail = {}
        for pos in SKILL_POSITIONS:
            band = bands_w["position_bands"][pos]
            detail[pos] = {
                "dedicated_starters_count": len(bands_w["dedicated_starters"][pos]),
                "flex_starters_count": sum(1 for f in bands_w["flex_starters"] if f["position"] == pos) if pos in FLEX_ELIGIBLE else 0,
                "p": weekly_p_out[last_w].get(pos) if pos in FLEX_ELIGIBLE else None,
                "band_members": [band_member_detail(m, actuals_w) for m in band["rostered"] + band["waiver"]],
                "band_rostered_count": len(band["rostered"]),
                "band_waiver_count": len(band["waiver"]),
                "band_baseline": weekly_band_baseline_out[last_w][pos],
                "replacement_level": weekly_replacement_level[last_w][pos],
            }
        most_recent_detail = {
            "week": last_w,
            "position_bands": detail,
            "flex_band": {
                "members": [band_member_detail(m, actuals_w) for m in bands_w["flex_band"]],
                "baseline": weekly_flex_band_baseline_out[last_w],
            },
        }

    output = {
        "year": year,
        "current_week": current_week,
        "completed_weeks": completed_weeks,
        "num_teams": num_teams,
        "weekly_band_baseline": weekly_band_baseline_out,
        "weekly_flex_band_baseline": weekly_flex_band_baseline_out,
        "weekly_p": weekly_p_out,
        "weekly_replacement_level": weekly_replacement_level,
        "most_recent_week_detail": most_recent_detail,
        "teams": teams_output,
        "not_playing_by_week": {
            str(w): [{"team_name": p["team_name"], "player_name": p["name"], "position": p["position"]}
                     for p in not_playing_by_week[w]]
            for w in completed_weeks
        },
        "unresolved_waiver_players": unresolved_waiver_players,
        "assumptions": [
            "Replacement level is recomputed separately for EVERY completed week, "
            "using that week's own historical roster snapshot and that week's own "
            "Sleeper projections -- not today's roster applied retroactively.",
            "A player (rostered or waiver) only counts for a given week's ranking if "
            "they were projected for more than 0 points that week -- this is the sole "
            "filter (covers byes, injuries, and non-factors in one rule); see "
            "not_playing_by_week.",
            "Waiver pool for a week = that week's Sleeper-projected players (also "
            "projected > 0) not matched to any of the 14 rosters that week.",
            "A band's baseline for a week = average of its members' REAL actual Yahoo "
            "points that week (not a projection). Waiver members are resolved to a "
            "real Yahoo player_id first (via another week's roster if they were ever "
            "rostered, else a Yahoo player search) so they're scored the same way as "
            "rostered members; any name that couldn't be resolved at all is excluded "
            "from the average and listed in unresolved_waiver_players.",
            "A band member who didn't play a given week (no actual data, or an exact "
            "0.0) is excluded from that week's average rather than dragging it to 0.",
            "Each currently-rostered player's PABB = sum, over every completed week, "
            "of (that week's actual points - that week's replacement level for their "
            "position); a week they didn't play contributes exactly 0.",
            "p (flex share) is computed fresh for each week from that week's own "
            "flex-slot outcome, not a fixed constant.",
        ],
    }
    return output


# --------------------------------------------------------------------------
# PNG BOARD
# --------------------------------------------------------------------------
def render_pabb_board(output: dict, out_dir: Path) -> None:
    year, week = output["year"], output["current_week"]
    teams = output["teams"]

    columns = sorted(teams.items(), key=lambda kv: int(kv[1]["team_key"].rsplit(".t.", 1)[-1]))
    rows = SLOT_ORDER

    pabb_values = [
        slot["pabb"] for _, team in columns for slot in team["slots"] if slot.get("pabb") is not None
    ]
    pabb_max = max((v for v in pabb_values if v > 0), default=1.0) or 1.0
    pabb_min = min((v for v in pabb_values if v < 0), default=-1.0) or -1.0

    reds = matplotlib.colormaps["Reds"]
    blues = matplotlib.colormaps["Blues"]

    def intensity(value):
        return value / pabb_max if value >= 0 else value / pabb_min

    def cell_color(slot):
        if slot is None or slot.get("pabb") is None:
            return "#FFFFFF"
        v = slot["pabb"]
        t = intensity(v)
        return reds(t) if v >= 0 else blues(t)

    def text_color(slot):
        if slot is None or slot.get("pabb") is None:
            return "#374151"
        return "#FFFFFF" if intensity(slot["pabb"]) > 0.6 else "#111827"

    def label(slot):
        if slot is None or slot.get("player_name") is None:
            return "(empty)"
        return f"{slot['player_name']}\n{slot['position']}  {slot['pabb']:+.1f}"

    n_rows, n_cols = len(rows), len(columns)
    cell_w, cell_h = 2.0, 1.1
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

    for col_idx, (team_name, _) in enumerate(columns):
        ax.text(col_idx + 0.5, -0.55, team_name, ha="center", va="center",
                fontsize=9, fontweight="bold", color="#111827", wrap=True)

    for row_idx, slot_name in enumerate(rows):
        ax.text(-0.3, row_idx + 0.5, slot_name, ha="center", va="center",
                fontsize=9, fontweight="bold", color="#6B7280")

    for row_idx, slot_name in enumerate(rows):
        for col_idx, (_, team) in enumerate(columns):
            slot = team["slots"][row_idx]
            ax.add_patch(plt.Rectangle(
                (col_idx, row_idx), 1, 1,
                facecolor=cell_color(slot), edgecolor="white", linewidth=1.5,
            ))
            ax.text(col_idx + 0.5, row_idx + 0.5, label(slot),
                    ha="center", va="center", fontsize=7.2,
                    color=text_color(slot), linespacing=1.3)

    ax.set_title(f"{year} (through week {week - 1}) -- season PABB "
                 f"(Points Above Best Bench)",
                 fontsize=14, fontweight="bold", color="#111827", pad=36)

    out_dir.mkdir(parents=True, exist_ok=True)
    board_path = out_dir / f"pabb_board_{year}_week{week}.png"
    fig.tight_layout()
    fig.savefig(board_path, dpi=200, bbox_inches="tight")
    plt.close(fig)
    print(f"Saved -> {board_path}")

    n_stops = 256
    half = n_stops // 2
    blue_half = [blues(1.0 - i / (half - 1)) for i in range(half)]
    red_half = [reds(i / (half - 1)) for i in range(half)]
    diverging_cmap = matplotlib.colors.ListedColormap(blue_half + red_half)

    fig2, ax2 = plt.subplots(figsize=(6, 0.6))
    fig2.subplots_adjust(bottom=0.5)
    mappable = matplotlib.cm.ScalarMappable(
        norm=matplotlib.colors.Normalize(vmin=pabb_min, vmax=pabb_max),
        cmap=diverging_cmap,
    )
    cb = fig2.colorbar(mappable, cax=ax2, orientation="horizontal")
    cb.set_label("Season PABB (negative -> positive)", fontsize=9)
    colorbar_path = board_path.with_name(board_path.stem + "_colorbar.png")
    fig2.savefig(colorbar_path, dpi=200, bbox_inches="tight")
    plt.close(fig2)
    print(f"Saved -> {colorbar_path}")


# --------------------------------------------------------------------------
# WRITE + ENTRY POINT
# --------------------------------------------------------------------------
def write_pabb(year: int = YEAR):
    output = calculate_pabb(year)

    output_dir = DATA_ROOT / str(year)
    output_dir.mkdir(parents=True, exist_ok=True)
    json_path = output_dir / "PABB.json"
    with open(json_path, "w", encoding="utf-8") as f:
        json.dump(output, f, indent=2, ensure_ascii=False)
    print(f"Saved -> {json_path}")

    render_pabb_board(output, output_dir / "PABB")


if __name__ == "__main__":
    write_pabb(YEAR)
