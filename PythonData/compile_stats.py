from yahoo_oauth import OAuth2
import yahoo_fantasy_api as yfa
import json
from pathlib import Path

sc = OAuth2(None, None, from_file='oauth2.json')
gm = yfa.Game(sc, 'nfl')

# Must match generate_league_stats.py
SEASONS = {
    2023: "423.l.902802",
    2024: "449.l.106896",
    2025: "461.l.111150",
}

REGULAR_SEASON_WEEKS = range(1, 15)
PLAYOFF_WEEKS = range(15, 18)

# --------------------------------------------------------------------------
# Output directories (OLD + NEW)
# --------------------------------------------------------------------------
BASE_DIR = Path(__file__).resolve().parent

OLD_OUTPUT_DIR = BASE_DIR / "league_stats_output"
NEW_OUTPUT_DIR = (BASE_DIR / ".." / "Website" / "girderma-gridiron-website" / "src").resolve()

OLD_OUTPUT_DIR.mkdir(parents=True, exist_ok=True)
NEW_OUTPUT_DIR.mkdir(parents=True, exist_ok=True)

# --------------------------------------------------------------------------
# Disambiguation config
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
            f"Duplicate nickname '{nickname}' for '{team_name}' missing alias."
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
    path = OLD_OUTPUT_DIR / str(season) / "weekly_points.json"
    with open(path, "r") as f:
        return json.load(f)


def compute_season_totals_from_weekly(weekly_points, team_name):
    weeks = weekly_points.get(team_name, {})

    reg = {"points_for": 0.0, "points_against": 0.0, "wins": 0, "losses": 0, "ties": 0}
    play = {"points_for": 0.0, "points_against": 0.0}
    play_weeks_found = 0

    for week_key, week_data in weeks.items():
        if week_key.startswith("_"):
            continue

        try:
            week_num = int(week_key.split("_")[1])
        except Exception:
            continue

        pf = week_data.get("points_for")
        pa = week_data.get("points_against")
        if pf is None or pa is None:
            continue

        if week_num in REGULAR_SEASON_WEEKS:
            reg["points_for"] += pf
            reg["points_against"] += pa
            if pf > pa:
                reg["wins"] += 1
            elif pf < pa:
                reg["losses"] += 1
            else:
                reg["ties"] += 1

        elif week_num in PLAYOFF_WEEKS:
            play["points_for"] += pf
            play["points_against"] += pa
            play_weeks_found += 1

    reg["points_for"] = round(reg["points_for"], 2)
    reg["points_against"] = round(reg["points_against"], 2)

    playoff_totals = None
    if play_weeks_found > 0:
        playoff_totals = {
            "points_for": round(play["points_for"], 2),
            "points_against": round(play["points_against"], 2),
        }

    return reg, playoff_totals


# --------------------------------------------------------------------------
# Main
# --------------------------------------------------------------------------
def compile_stats():
    compiled = {}

    for season, league_id in SEASONS.items():
        print(f"\nSeason {season}")

        try:
            lg = gm.to_league(league_id)
        except Exception as e:
            print(f"Failed league: {e}")
            continue

        manager_map = get_manager_to_team_map(lg)
        standings_by_name = get_standings_by_team_name(lg)

        weekly_points = {}
        try:
            weekly_points = load_weekly_points(season)
        except FileNotFoundError:
            print(f"Missing weekly_points for {season}")

        for manager_key, info in manager_map.items():
            team_name = info["team_name"]
            nickname = info["nickname"]

            reg, play = compute_season_totals_from_weekly(weekly_points, team_name)

            standing = standings_by_name.get(team_name, {})
            outcome = standing.get("outcome_totals", {})

            wins = int(outcome.get("wins", reg["wins"]))
            losses = int(outcome.get("losses", reg["losses"]))
            ties = int(outcome.get("ties", reg["ties"]))

            season_entry = {
                "team_name": team_name,
                "regular_season": {
                    "points_for": reg["points_for"],
                    "points_against": reg["points_against"],
                    "wins": wins,
                    "losses": losses,
                    "ties": ties,
                },
                "playoffs": play,
                "final_rank": standing.get("rank"),
                "playoff_seed": standing.get("playoff_seed"),
            }

            compiled.setdefault(manager_key, {"nickname": nickname, "seasons": {}})
            compiled[manager_key]["seasons"][season] = season_entry

    # -------------------------
    # Career totals
    # -------------------------
    for manager_key, data in compiled.items():
        career_reg = {"points_for": 0.0, "points_against": 0.0, "wins": 0, "losses": 0, "ties": 0}
        career_play = {"points_for": 0.0, "points_against": 0.0}
        seasons_played = 0
        playoff_appearances = 0

        for s in data["seasons"].values():
            reg = s["regular_season"]
            play = s["playoffs"]

            career_reg["points_for"] += reg["points_for"]
            career_reg["points_against"] += reg["points_against"]
            career_reg["wins"] += reg["wins"]
            career_reg["losses"] += reg["losses"]
            career_reg["ties"] += reg["ties"]
            seasons_played += 1

            if play is not None:
                career_play["points_for"] += play["points_for"]
                career_play["points_against"] += play["points_against"]
                playoff_appearances += 1

        data["career_totals"] = {
            "regular_season": {
                "points_for": round(career_reg["points_for"], 2),
                "points_against": round(career_reg["points_against"], 2),
                "wins": career_reg["wins"],
                "losses": career_reg["losses"],
                "ties": career_reg["ties"],
            },
            "playoffs": {
                "points_for": round(career_play["points_for"], 2),
                "points_against": round(career_play["points_against"], 2),
            },
            "seasons_played": seasons_played,
            "playoff_appearances": playoff_appearances,
        }

    # -------------------------
    # OUTPUT TO BOTH FOLDERS
    # -------------------------
    old_out = OLD_OUTPUT_DIR / "compiled_stats.json"
    new_out = NEW_OUTPUT_DIR / "compiled_stats.json"

    OLD_OUTPUT_DIR.mkdir(parents=True, exist_ok=True)
    NEW_OUTPUT_DIR.mkdir(parents=True, exist_ok=True)

    for path in [old_out, new_out]:
        with open(path, "w") as f:
            json.dump(compiled, f, indent=2)

    print(f"\nSaved compiled stats →")
    print(f"  {old_out}")
    print(f"  {new_out}")

    return compiled


if __name__ == "__main__":
    compile_stats()