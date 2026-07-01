"""
compile_stats.py

Reads the per-season output files produced by generate_league_stats.py and
aggregates points for/against, wins/losses, and standings for each manager
across all 3 seasons.

Since Yahoo redacts other users' guids from the API, we match managers across
seasons by nickname. For duplicate nicknames (e.g. two managers both called
"Josh" or "Sam"), NICKNAME_ALIASES maps (nickname, team_name) → a unique key
for any season where that person appeared.

Output: league_stats_output/compiled_stats.json
"""

from yahoo_oauth import OAuth2
import yahoo_fantasy_api as yfa
import json
import os

sc = OAuth2(None, None, from_file='oauth2.json')
gm = yfa.Game(sc, 'nfl')

# Must match generate_league_stats.py
SEASONS = {
    2023: "423.l.902802",
    2024: "449.l.106896",
    2025: "461.l.111150",
}

BASE_DIR = "league_stats_output"

REGULAR_SEASON_WEEKS = range(1, 15)   # weeks 1-14
PLAYOFF_WEEKS        = range(15, 18)  # weeks 15-17



# --------------------------------------------------------------------------
# Disambiguation config for duplicate nicknames.
# Format: (nickname, team_name) -> unique stable key
# Add one row per (nickname, team_name) pair that would otherwise collide.
# --------------------------------------------------------------------------
NICKNAME_ALIASES = {
    ("Josh", "No Punts Intented"):      "Josh_Rubik",
    ("Josh", "The Sage's Playmakers"):  "Josh_Sage",
    ("Josh", "Room 40"):                "Josh_Rubik",
    ("Josh", "Mahomes Alone"):          "Josh_Rubik",
    ("Sam",  "Pad D's"):                "Sam_Paddy",
    ("Sam",  "Girder\u2019s Grippers"): "Sam_Girder",
}


# --------------------------------------------------------------------------
# Helpers
# --------------------------------------------------------------------------

def resolve_manager_key(nickname, team_name):
    if (nickname, team_name) in NICKNAME_ALIASES:
        return NICKNAME_ALIASES[(nickname, team_name)]
    known_duplicate_nicknames = {n for (n, _) in NICKNAME_ALIASES}
    if nickname in known_duplicate_nicknames:
        raise ValueError(
            f"Duplicate nickname '{nickname}' found for team '{team_name}' "
            f"but no alias is configured for this (nickname, team_name) pair. "
            f"Add an entry to NICKNAME_ALIASES at the top of compile_stats.py."
        )
    return nickname


def get_manager_to_team_map(lg):
    teams = lg.teams()
    mapping = {}
    for team_key, team_data in teams.items():
        team_name = team_data.get("name", "Unknown")
        managers = team_data.get("managers", [])
        for mgr_entry in managers:
            mgr = mgr_entry.get("manager", {})
            nickname = mgr.get("nickname", "Unknown")
            manager_key = resolve_manager_key(nickname, team_name)
            mapping[manager_key] = {
                "nickname": nickname,
                "team_name": team_name,
                "team_key": team_key,
            }
    return mapping


def get_standings_by_team_name(lg):
    standings = lg.standings()
    return {entry["name"]: entry for entry in standings if "name" in entry}


def load_weekly_points(season):
    path = os.path.join(BASE_DIR, str(season), "weekly_points.json")
    with open(path, "r") as f:
        return json.load(f)


def compute_season_totals_from_weekly(weekly_points, team_name):
    """
    Returns separate totals for the regular season (weeks 1-14) and playoffs
    (weeks 15-17). Playoff fields are None when the team had no data in those
    weeks (i.e. they didn't make the playoffs, or the data wasn't fetched).

    Returns: (regular_season_totals, playoff_totals | None)
    """
    weeks = weekly_points.get(team_name, {})

    reg  = {"points_for": 0.0, "points_against": 0.0, "wins": 0, "losses": 0, "ties": 0}
    play = {"points_for": 0.0, "points_against": 0.0}
    play_weeks_found = 0

    for week_key, week_data in weeks.items():
        if week_key.startswith("_"):
            continue

        try:
            week_num = int(week_key.split("_")[1])
        except (IndexError, ValueError):
            continue



        pf = week_data.get("points_for")
        pa = week_data.get("points_against")
        if pf is None or pa is None:
            continue

        if week_num in REGULAR_SEASON_WEEKS:
            reg["points_for"]     += pf
            reg["points_against"] += pa
            if pf > pa:
                reg["wins"] += 1
            elif pf < pa:
                reg["losses"] += 1
            else:
                reg["ties"] += 1

        elif week_num in PLAYOFF_WEEKS:
            play["points_for"]     += pf
            play["points_against"] += pa
            play_weeks_found += 1

    
    reg["points_for"]     = round(reg["points_for"],     2)
    reg["points_against"] = round(reg["points_against"], 2)

    if play_weeks_found > 0:
        playoff_totals = {
            "points_for":     round(play["points_for"],     2),
            "points_against": round(play["points_against"], 2),
        }
    else:
        playoff_totals = None  # team had no data in weeks 15-17

    return reg, playoff_totals


# --------------------------------------------------------------------------
# Main compilation
# --------------------------------------------------------------------------

def compile_stats():
    """
    Output structure per manager:
    {
        "Zach": {
            "nickname": "Zach",
            "seasons": {
                2025: {
                    "team_name": "Go With The Flow",
                    "regular_season": {
                        "points_for": 1482.3,
                        "points_against": 1401.7,
                        "wins": 9,
                        "losses": 5,
                        "ties": 0
                    },
                    "playoffs": {                    # null if team missed playoffs
                        "points_for": 312.5,
                        "points_against": 287.1
                    },
                    "final_rank": 2,
                    "playoff_seed": "2"
                },
                ...
            },
            "career_totals": {
                "regular_season": { "points_for": ..., "points_against": ..., "wins": ..., ... },
                "playoffs":       { "points_for": ..., "points_against": ... },
                "seasons_played": 3,
                "playoff_appearances": 2
            }
        }
    }
    """
    compiled = {}

    for season, league_id in SEASONS.items():
        print(f"\n{'='*55}")
        print(f"  Season {season}  ({league_id})")
        print(f"{'='*55}")

        try:
            lg = gm.to_league(league_id)
        except Exception as e:
            print(f"  Could not connect to league: {e}")
            continue

        try:
            manager_map = get_manager_to_team_map(lg)
            for key, info in manager_map.items():
                print(f"  {key:25s} (nickname: {info['nickname']:15s}) → {info['team_name']}")
        except ValueError as e:
            print(f"\n  CONFIG ERROR: {e}\n")
            return
        except Exception as e:
            print(f"  Failed to get team/manager map: {e}")
            continue

        try:
            standings_by_name = get_standings_by_team_name(lg)
        except Exception as e:
            print(f"  Failed to fetch standings: {e}")
            standings_by_name = {}

        try:
            weekly_points = load_weekly_points(season)
        except FileNotFoundError:
            print(f"  weekly_points.json not found for {season} — run generate_league_stats.py first.")
            weekly_points = {}

        for manager_key, team_info in manager_map.items():
            team_name = team_info["team_name"]
            nickname  = team_info["nickname"]

            reg_totals, playoff_totals = compute_season_totals_from_weekly(weekly_points, team_name)

            standing = standings_by_name.get(team_name, {})
            outcome  = standing.get("outcome_totals", {})

            # Prefer Yahoo's official standings W/L; fall back to computed
            wins   = int(outcome.get("wins",   reg_totals["wins"]))
            losses = int(outcome.get("losses", reg_totals["losses"]))
            ties   = int(outcome.get("ties",   reg_totals["ties"]))

            season_entry = {
                "team_name": team_name,
                "regular_season": {
                    "points_for":     reg_totals["points_for"],
                    "points_against": reg_totals["points_against"],
                    "wins":   wins,
                    "losses": losses,
                    "ties":   ties,
                },
                "playoffs": playoff_totals,   # None if no playoff data
                "final_rank": standing.get("rank"),
                "playoff_seed":        standing.get("playoff_seed"),
            }

            if manager_key not in compiled:
                compiled[manager_key] = {"nickname": nickname, "seasons": {}}

            compiled[manager_key]["nickname"] = nickname
            compiled[manager_key]["seasons"][season] = season_entry

    # --------------------------------------------------------------------------
    # Career totals
    # --------------------------------------------------------------------------
    for manager_key, data in compiled.items():
        career_reg = {"points_for": 0.0, "points_against": 0.0, "wins": 0, "losses": 0, "ties": 0}
        career_play = {"points_for": 0.0, "points_against": 0.0}
        seasons_played      = 0
        playoff_appearances = 0

        for season_entry in data["seasons"].values():
            reg  = season_entry["regular_season"]
            play = season_entry["playoffs"]

            career_reg["points_for"]     += reg["points_for"]
            career_reg["points_against"] += reg["points_against"]
            career_reg["wins"]           += reg["wins"]
            career_reg["losses"]         += reg["losses"]
            career_reg["ties"]           += reg["ties"]
            seasons_played += 1

            if play is not None:
                career_play["points_for"]     += play["points_for"]
                career_play["points_against"] += play["points_against"]
                playoff_appearances += 1

        career_reg["points_for"]      = round(career_reg["points_for"],      2)
        career_reg["points_against"]  = round(career_reg["points_against"],  2)
        career_play["points_for"]     = round(career_play["points_for"],     2)
        career_play["points_against"] = round(career_play["points_against"], 2)

        data["career_totals"] = {
            "regular_season":     career_reg,
            "playoffs":           career_play,
            "seasons_played":     seasons_played,
            "playoff_appearances": playoff_appearances,
        }

    output_path = os.path.join(BASE_DIR, "compiled_stats.json")
    with open(output_path, "w") as f:
        json.dump(compiled, f, indent=2)

    print(f"\nSaved compiled stats for {len(compiled)} managers → {output_path}")
    return compiled


if __name__ == "__main__":
    compile_stats()