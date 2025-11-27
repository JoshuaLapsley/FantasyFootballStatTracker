from yahoo_oauth import OAuth2
import yahoo_fantasy_api as yfa
import json
import os

#Takes in the league
def getCurrentWeek(lg):
    return lg.current_week()
    
def save_team_rosters_with_weekly_stats(league, week):
    """
    Loops through all teams and saves each team's roster for every week in the given range,
    including each player's actual weekly stats (no projected points).
    """
    teams = league.teams()  # dict of all teams

    # Base folder
    base_folder = f"team_rosters_weekly_stats_week_{week}"
    os.makedirs(base_folder, exist_ok=True)

    for team_key, team_data in teams.items():
        team_name = team_data["name"]
        safe_team_name = team_name.replace(" ", "_").replace("/", "_")

        # Convert team_key → team object
        team = league.to_team(team_key)

        
        try:
            # Get roster for the week
            roster = team.roster(week=week)  # list of players
        except Exception as e:
            print(f"Failed to get roster for {team_name}, week {week}: {e}")
            roster = []

        # Add stats for each player
        for player in roster:
            pid = player["player_id"]
            try:
                week_stats_list = league.player_stats([pid], "week", week=week)
                if week_stats_list:
                    player["weekly_stats"] = week_stats_list[0]
                else:
                    player["weekly_stats"] = {}
            except Exception:
                player["weekly_stats"] = {}

        # Build JSON
        data = { f"{team_name}_week_{week}_roster": roster }

        # Save file
        file_path = os.path.join(base_folder, f"{safe_team_name}_week_{week}.json")
        with open(file_path, "w") as f:
            json.dump(data, f, indent=4)

        print(f"Saved {team_name} roster with weekly stats for week {week} → {file_path}")


def save_all_waiver_wire_players_weekly_stats(league, week):
    """
    Saves all waiver wire players for every position including weekly stats.
    Each player is saved as a JSON file in a folder for their position.
    Retrieves the list of free agents as of the given week.
    """
    positions = ["QB", "RB", "WR", "TE", "K", "DEF"]  # all positions

    for position in positions:
        folder = f"free_agents_in_week_{week}/{position}"
        os.makedirs(folder, exist_ok=True)

        # Get free agents for this position for the specific week
        free_agents = league.free_agents(position, week=week)  # <--- specify week here
        players = list(free_agents.values()) if isinstance(free_agents, dict) else free_agents

        print(f"Saving {len(players)} free-agent {position}s with weekly stats for week {week}...")

        for player in players:
            pid = player["player_id"]
            safe_name = player["name"].replace(" ", "_").replace("/", "_")
            file_name = f"{pid}_{safe_name}.json"
            file_path = os.path.join(folder, file_name)

            # Get the player's stats for that week
            try:
                week_stats_list = league.player_stats([pid], "week", week=week)
                weekly_stats = week_stats_list if week_stats_list else [{}]
            except Exception:
                weekly_stats = [{}]

            player["weekly_stats"] = weekly_stats

            # Save JSON
            with open(file_path, "w") as f:
                json.dump(player, f, indent=4)

            print(f"Saved {player['name']} ({position}) → {file_path}")




    
sc = OAuth2(None, None, from_file='oauth2Josh.json')

#get nfl leagues (connected to player)
gm = yfa.Game(sc, 'nfl')
#leagues = gm.league_ids()

#print(leagues)
#Get League for this year
GirdermaGridironnLeague2025Id = '461.l.111150'
lg = gm.to_league(GirdermaGridironnLeague2025Id)


#print(getCurrentWeek(lg))

#authroize("Josh")

#save_team_rosters_with_weekly_stats(lg, 12)

save_all_waiver_wire_players_weekly_stats(lg, 1)
save_all_waiver_wire_players_weekly_stats(lg, 2)
save_all_waiver_wire_players_weekly_stats(lg, 3)
save_all_waiver_wire_players_weekly_stats(lg, 4)
save_all_waiver_wire_players_weekly_stats(lg, 5)
save_all_waiver_wire_players_weekly_stats(lg, 6)
save_all_waiver_wire_players_weekly_stats(lg, 7)
save_all_waiver_wire_players_weekly_stats(lg, 8)
save_all_waiver_wire_players_weekly_stats(lg, 9)
save_all_waiver_wire_players_weekly_stats(lg, 10)
save_all_waiver_wire_players_weekly_stats(lg, 11)
save_all_waiver_wire_players_weekly_stats(lg, 12)







