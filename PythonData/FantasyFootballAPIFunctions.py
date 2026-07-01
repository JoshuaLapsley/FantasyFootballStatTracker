from yahoo_oauth import OAuth2
import yahoo_fantasy_api as yfa
import json
import os

sc = OAuth2(None, None, from_file='oauth2.json')

#get nfl leagues (connected to player)
gm = yfa.Game(sc, 'nfl')
#leagues = gm.league_ids()

#print(leagues)
#Get League for this year
GirdermaGridironnLeague2025Id = '461.l.111150'
lg = gm.to_league(GirdermaGridironnLeague2025Id)


#Takes in the league
def getCurrentWeek():
    return lg.current_week()
    
def save_team_rosters_with_weekly_stats(week):
    """
    Saves every team's roster for the given week, including each player's real weekly stats.
    Output: team_rosters_weekly_stats_week_<week>/<team_name>_week_<week>_roster.json
    """

    teams = lg.teams()              # dict of all teams
    base_folder = f"team_rosters_weekly_stats_week_{week}"
    os.makedirs(base_folder, exist_ok=True)

    for team_key, team_data in teams.items():
        team_name = team_data["name"]
        safe_team_name = team_name.replace(" ", "_").replace("/", "_")

        # Convert team key → team object
        team = lg.to_team(team_key)

        # Get roster for that week
        try:
            roster = team.roster(week=week)
        except Exception as e:
            print(f"Failed to fetch roster for {team_name} (week {week}): {e}")
            roster = []

        # Add weekly stats to every player
        for player in roster:
            pid = player.get("player_id")

            if not pid:
                player["weekly_stats"] = {}
                continue

            try:
                stats_list = lg.player_stats([pid], "week", week=week)

                if stats_list:
                    player["weekly_stats"] = stats_list[0]
                else:
                    player["weekly_stats"] = {}
            except Exception:
                player["weekly_stats"] = {}

        # Build output JSON document
        data = {
            f"{team_name}_week_{week}": roster
        }

        # File path
        output_path = os.path.join(
            base_folder,
            f"{safe_team_name}_week_{week}.json"
        )

        # Save the JSON file
        try:
            with open(output_path, "w") as f:
                json.dump(data, f, indent=4)
            print(f"Saved {team_name} week {week} roster → {output_path}")
        except Exception as ex:
            print(f"Error saving {team_name} roster: {ex}")

def getTransactionData(tran_type):

    folder = "transactions"
    os.makedirs(folder, exist_ok=True)

    print(f"\n=== Fetching transactions ===")
    try:
        transactions = lg.transactions(tran_type, "")

    except Exception:
        print(f"\n=== Something Went Wrong ===")

    filename = f"transactions/{tran_type}-transactions.json"
    with open(filename, "w") as f:
        json.dump(transactions, f, indent=2)
        
def getDraftData():

    folder = "draftData"
    os.makedirs(folder, exist_ok=True)

    print(f"\n=== Fetching draftData ===")
    try:
        draftResults = lg.draft_results()

    except Exception:
        print(f"\n=== Something Went Wrong ===")

    filename = f"draftData/draftData.json"
    with open(filename, "w") as f:
        json.dump(draftResults, f, indent=2)

def getMatchupData(week):

    folder = "all_matchup_data"
    os.makedirs(folder, exist_ok=True)

    print(f"\n=== Fetching matchpuData ===")
    try:
        matchups = lg.matchups(week=week)

    except Exception:
        print(f"\n=== Something Went Wrong ===")

    filename = f"all_matchup_data/all_matchup_data_week{week}.json"
    with open(filename, "w") as f:
        json.dump(matchups, f, indent=2)

def GetPlayerDataByWeek(week):
    folder = "AllPlayerStats"
    os.makedirs(folder, exist_ok=True)

    with open("allPlayerIds.json", "r") as f:
        player_ids = json.load(f)


    # # --------------------------
    # # STEP 3 — LOOP THROUGH EVERY WEEK
    # # --------------------------
    os.makedirs("AllPlayerStats", exist_ok=True)

    print(f"\n=== Fetching stats for WEEK {week} ===")

    weekly_stats = {}


    try:
        stats = lg.player_stats(
            player_ids=player_ids,   # MUST be a list
            req_type="week",
            week=week
        )

    except Exception:
        print("Error")
    # Save to file
    filename = f"AllPlayerStats/week_{week}.json"
    with open(filename, "w") as f:
        json.dump(stats, f, indent=2)

    print(f"Saved: {filename}")
    print("\n✓ DONE — weekly stat files saved in AllPlayerStats/")
    



#RUN THIS CODE AFTER WEEK 14
# GetPlayerDataByWeek(14)
#save_team_rosters_with_weekly_stats(14)
# getTransactionData("add")
# getTransactionData("drop")
# getMatchupData(14)

save_team_rosters_with_weekly_stats(12)








