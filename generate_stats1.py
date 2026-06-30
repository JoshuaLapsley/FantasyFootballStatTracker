from yahoo_oauth import OAuth2
import yahoo_fantasy_api as yfa
import json
import os

sc = OAuth2(None, None, from_file='oauth2.json')
gm = yfa.Game(sc, 'nfl')

# --------------------------------------------------------------------------
# Hardcode league IDs per season. Add or remove seasons here as needed.
# --------------------------------------------------------------------------
SEASONS = {
    2023: "423.l.902802",   
    2024: "449.l.106896",   
    2025: "461.l.111150",
}

BASE_OUTPUT_DIR = "league_stats_output"
os.makedirs(BASE_OUTPUT_DIR, exist_ok=True)


# --------------------------------------------------------------------------
# Helpers (all accept lg as an explicit argument instead of a global)
# --------------------------------------------------------------------------
def get_teams_dict(lg):
    teams = lg.teams()
    return {team_key: team_data["name"] for team_key, team_data in teams.items()}


def get_league_end_week(lg):
    try:
        settings = lg.settings()
        return int(settings.get("end_week", lg.current_week() ))
    except Exception:
        return lg.current_week()


# --------------------------------------------------------------------------
# A) Points for / points against per team per week
# --------------------------------------------------------------------------
def save_weekly_points_for_against(lg, output_dir, start_week=1, end_week=None):
    """
    For each team, records points scored for and against for every week.
    Output: <output_dir>/weekly_points.json

    Structure:
    {
        "<team_name>": {
            "week_1": {"points_for": X, "points_against": Y, "opponent": "<team_name>"},
            ...
        },
        ...
    }
    """
    teams_dict = get_teams_dict(lg)

    if end_week is None:
        end_week = lg.current_week()

    results = {team_name: {} for team_name in teams_dict.values()}

    for week in range(start_week, end_week + 1):
        print(f"  Fetching matchups for week {week}...")
        try:
            matchups = lg.matchups(week=week)
        except Exception as e:
            print(f"    Failed to fetch matchups for week {week}: {e}")
            continue

        try:
            matchup_data = matchups["fantasy_content"]["league"][1]["scoreboard"]["0"]["matchups"]
        except (KeyError, IndexError, TypeError) as e:
            print(f"    Unexpected matchup structure for week {week}: {e}")
            with open(os.path.join(output_dir, f"_raw_matchup_week_{week}.json"), "w") as f:
                json.dump(matchups, f, indent=2)
            continue

        for key, matchup in matchup_data.items():
            if key == "count":
                continue
            try:
                matchup_block = matchup["matchup"]
                teams_block = matchup_block["0"]["teams"]
            except (KeyError, TypeError):
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
                except (KeyError, TypeError, ValueError, IndexError):
                    continue

            if len(team_entries) != 2:
                continue

            (name_a, pts_a), (name_b, pts_b) = team_entries

            for name, pts, opp_name, opp_pts in [
                (name_a, pts_a, name_b, pts_b),
                (name_b, pts_b, name_a, pts_a),
            ]:
                if name not in results:
                    results[name] = {}
                results[name][f"week_{week}"] = {
                    "points_for": pts,
                    "points_against": opp_pts,
                    "opponent": opp_name,
                }

    output_path = os.path.join(output_dir, "weekly_points.json")
    with open(output_path, "w") as f:
        json.dump(results, f, indent=2)
    print(f"  Saved weekly points → {output_path}")


# --------------------------------------------------------------------------
# B) Roster on week 1 and final week of the season for each team
# --------------------------------------------------------------------------
def save_first_and_last_week_rosters(lg, output_dir, first_week=1, last_week=None):
    """
    For each team, stores roster on the first and last week of the season.
    Output: <output_dir>/rosters_first_last_week.json

    Structure:
    {
        "<team_name>": {
            "week_1_roster": [...],
            "week_<last>_roster": [...]
        },
        ...
    }
    """
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
            print(f"  Fetching {team_name} roster for week {wk}...")
            try:
                roster = team.roster(week=wk)
            except Exception as e:
                print(f"    Failed: {e}")
                roster = []
            results[team_name][label] = roster

    output_path = os.path.join(output_dir, "rosters_first_last_week.json")
    with open(output_path, "w") as f:
        json.dump(results, f, indent=2)
    print(f"  Saved rosters → {output_path}")


# --------------------------------------------------------------------------
# C) Total wins/losses, final regular season standings, playoff standings
# --------------------------------------------------------------------------
def save_standings_and_records(lg, output_dir):
    """
    Stores total wins/losses per team, final regular season standings,
    and playoff standings/results.
    Output: <output_dir>/standings.json
    """
    results = {
        "regular_season_standings": [],
        "playoff_results_raw": None,
    }

    print("  Fetching league standings...")
    try:
        results["regular_season_standings"] = lg.standings()
    except Exception as e:
        print(f"    Failed to fetch standings: {e}")

    print("  Fetching playoff bracket data...")
    try:
        raw = lg.yhandler.get_standings_raw(lg.league_id)
        results["playoff_results_raw"] = raw
    except AttributeError:
        print("    yhandler.get_standings_raw not available in this yahoo_fantasy_api version.")
    except Exception as e:
        print(f"    Failed to fetch playoff bracket: {e}")

    output_path = os.path.join(output_dir, "standings.json")
    with open(output_path, "w") as f:
        json.dump(results, f, indent=2)
    print(f"  Saved standings → {output_path}")


# --------------------------------------------------------------------------
# Main — iterate over all seasons
# --------------------------------------------------------------------------
if __name__ == "__main__":
    for season, league_id in SEASONS.items():
        print(f"\n{'='*60}")
        print(f"  Processing season {season}  (league: {league_id})")
        print(f"{'='*60}")

        # Each season gets its own subfolder: league_stats_output/2023/, etc.
        output_dir = os.path.join(BASE_OUTPUT_DIR, str(season))
        os.makedirs(output_dir, exist_ok=True)

        try:
            lg = gm.to_league(league_id)
        except Exception as e:
            print(f"  Failed to connect to league {league_id}: {e}")
            continue

        # A) Weekly points for/against
        save_weekly_points_for_against(lg, output_dir, start_week=1)

        # B) First and last week rosters
        save_first_and_last_week_rosters(lg, output_dir, first_week=1)

        # C) Standings and records
        save_standings_and_records(lg, output_dir)

    print(f"\nAll done. Files are in: {BASE_OUTPUT_DIR}/")