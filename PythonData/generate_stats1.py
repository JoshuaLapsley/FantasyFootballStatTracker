from yahoo_oauth import OAuth2
import yahoo_fantasy_api as yfa
import json
from pathlib import Path

sc = OAuth2(None, None, from_file='oauth2.json')
gm = yfa.Game(sc, 'nfl')

# --------------------------------------------------------------------------
# Hardcode league IDs per season
# --------------------------------------------------------------------------
SEASONS = {
    2023: "423.l.902802",
    2024: "449.l.106896",
    2025: "461.l.111150",
}

# --------------------------------------------------------------------------
# Output directories (OLD + NEW)
# --------------------------------------------------------------------------
BASE_DIR = Path(__file__).resolve().parent

OLD_OUTPUT_ROOT = BASE_DIR / "league_stats_output"
NEW_OUTPUT_ROOT = (BASE_DIR / ".." / "Website" / "girderma-gridiron-website" / "src").resolve()

OLD_OUTPUT_ROOT.mkdir(parents=True, exist_ok=True)
NEW_OUTPUT_ROOT.mkdir(parents=True, exist_ok=True)

# --------------------------------------------------------------------------
# Helpers
# --------------------------------------------------------------------------
def get_teams_dict(lg):
    teams = lg.teams()
    return {team_key: team_data["name"] for team_key, team_data in teams.items()}


def get_league_end_week(lg):
    try:
        settings = lg.settings()
        return int(settings.get("end_week", lg.current_week()))
    except Exception:
        return lg.current_week()


def write_to_both_dirs(output_dirs, filename, data):
    old_dir, new_dir = output_dirs

    for d in [old_dir, new_dir]:
        with open(d / filename, "w") as f:
            json.dump(data, f, indent=2)


# --------------------------------------------------------------------------
# A) Points for / against
# --------------------------------------------------------------------------
def save_weekly_points_for_against(lg, output_dirs, start_week=1, end_week=None):
    teams_dict = get_teams_dict(lg)

    if end_week is None:
        end_week = lg.current_week()

    results = {team_name: {} for team_name in teams_dict.values()}

    for week in range(start_week, end_week + 1):
        print(f"  Fetching matchups for week {week}...")

        try:
            matchups = lg.matchups(week=week)
        except Exception as e:
            print(f"    Failed week {week}: {e}")
            continue

        try:
            matchup_data = matchups["fantasy_content"]["league"][1]["scoreboard"]["0"]["matchups"]
        except Exception as e:
            print(f"    Bad structure week {week}: {e}")
            continue

        for key, matchup in matchup_data.items():
            if key == "count":
                continue

            try:
                matchup_block = matchup["matchup"]
                teams_block = matchup_block["0"]["teams"]
            except Exception:
                continue

            team_entries = []

            for tkey, tval in teams_block.items():
                if tkey == "count":
                    continue

                try:
                    team_info_list = tval["team"][0]
                    team_points = float(tval["team"][1]["team_points"]["total"])

                    team_name = None
                    for item in team_info_list:
                        if isinstance(item, dict) and "name" in item:
                            team_name = item["name"]
                            break

                    team_entries.append((team_name, team_points))
                except Exception:
                    continue

            if len(team_entries) != 2:
                continue

            (name_a, pts_a), (name_b, pts_b) = team_entries

            for name, pts, opp_name, opp_pts in [
                (name_a, pts_a, name_b, pts_b),
                (name_b, pts_b, name_a, pts_a),
            ]:
                results.setdefault(name, {})
                results[name][f"week_{week}"] = {
                    "points_for": pts,
                    "points_against": opp_pts,
                    "opponent": opp_name,
                }

    write_to_both_dirs(output_dirs, "weekly_points.json", results)
    print("  Saved weekly points")


# --------------------------------------------------------------------------
# B) Rosters
# --------------------------------------------------------------------------
def save_first_and_last_week_rosters(lg, output_dirs, first_week=1, last_week=None):
    teams_dict = get_teams_dict(lg)

    if last_week is None:
        last_week = get_league_end_week(lg)

    results = {}

    for team_key, team_name in teams_dict.items():
        team = lg.to_team(team_key)
        results[team_name] = {}

        for label, wk in [
            (f"week_{first_week}_roster", first_week),
            (f"week_{last_week}_roster", last_week),
        ]:
            try:
                roster = team.roster(week=wk)
            except Exception:
                roster = []

            results[team_name][label] = roster

    write_to_both_dirs(output_dirs, "rosters_first_last_week.json", results)
    print("  Saved rosters")


# --------------------------------------------------------------------------
# C) Standings
# --------------------------------------------------------------------------
def save_standings_and_records(lg, output_dirs):
    results = {
        "regular_season_standings": [],
        "playoff_results_raw": None,
    }

    try:
        results["regular_season_standings"] = lg.standings()
    except Exception:
        pass

    try:
        results["playoff_results_raw"] = lg.yhandler.get_standings_raw(lg.league_id)
    except Exception:
        pass

    write_to_both_dirs(output_dirs, "standings.json", results)
    print("  Saved standings")


# --------------------------------------------------------------------------
# Main
# --------------------------------------------------------------------------
if __name__ == "__main__":
    for season, league_id in SEASONS.items():

        print("\n" + "=" * 60)
        print(f"Processing season {season}")
        print("=" * 60)

        old_dir = OLD_OUTPUT_ROOT / str(season)
        new_dir = NEW_OUTPUT_ROOT / str(season)

        old_dir.mkdir(parents=True, exist_ok=True)
        new_dir.mkdir(parents=True, exist_ok=True)

        output_dirs = (old_dir, new_dir)

        try:
            lg = gm.to_league(league_id)
        except Exception as e:
            print(f"Failed league {league_id}: {e}")
            continue

        save_weekly_points_for_against(lg, output_dirs, start_week=1)
        save_first_and_last_week_rosters(lg, output_dirs, first_week=1)
        save_standings_and_records(lg, output_dirs)

    print("\nDone.")