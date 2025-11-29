import os
import json
import math

from yahoo_oauth import OAuth2
import yahoo_fantasy_api as yfa

# Authenticate
sc = OAuth2(None, None, from_file='oauth2Josh.json')
gm = yfa.Game(sc, 'nfl')

# Get league object
GirdermaGridironnLeague2025Id = '461.l.111150'
lg = gm.to_league(GirdermaGridironnLeague2025Id)


#the replacement-level points for each position for each week

#RLP means replacement-level points
#here is a sample RLP
RLP = {
    13: {   # week number
        "QB": 16.49,
        "RB": 6.96,
        "WR": 8.31,
        "TE": 9.20,
        "W/R/T": 9.20, #flex is the max{wr,rb,te}
        "K": 8.91,
        "DEF": 6.80
    }
}
standardRLP = {
    
    "QB": 15.00,
    "RB": 8,
    "WR": 8,
    "TE": 7,
    "W/R/T": 8, #flex is the max{wr,rb,te}
    "K": 8,
    "DEF": 6.50
    
}

def determine_comparison_position(player):
    pos = player["selected_position"]
    
    if pos == "W/R/T":
        for p in player["eligible_positions"]:
            if p in {"RB", "WR", "TE"}:
                return p
    return pos



def compute_PAR_for_each_player_on_team(roster, week, replacement_levels):
    results = []

    for player in roster:
        natural_pos = determine_comparison_position(player)
        player_points = get_player_points(player)

        comp_pos = natural_pos
        '''# if the player is in the flex spot compare vs FLEX RLP
        if player["selected_position"] == "W/R/T":
            comp_pos = "W/R/T"
        else:
            comp_pos = natural_pos'''

        # look up replacement-level value
        try:
            rl_points = replacement_levels[week][comp_pos]
        except KeyError:
            raise ValueError(f"Missing replacement level for pos={comp_pos} week={week}")

        par = player_points - rl_points

        results.append({
            "player_id": player["player_id"],
            "name": player["name"],
            #"natural_position": natural_pos,
            #"team_position": player["selected_position"],
            "comparison_position": comp_pos,
            "points": player_points,
            "replacement_level": rl_points,
            "PAR": par
        })

    return results






import os
import json

def load_roster(manager_name, week):
    """
    Finds and loads the JSON roster file for the given manager and week.
    Returns the roster (list of players) or None if not found.
    """
    safe_name = manager_name.replace(" ", "_").replace("/", "_")

    for root, dirs, files in os.walk("."):
        for file in files:
            if file.startswith(safe_name) and f"week_{int(week)}" in file and file.endswith(".json"):
                file_path = os.path.join(root, file)
                try:
                    with open(file_path, "r") as f:
                        data = json.load(f)
                    roster_key = list(data.keys())[0]
                    return data[roster_key]
                except Exception as e:
                    print(f"Error loading {file_path}: {e}")
                    return None

    print(f"Roster file not found for {manager_name}, week {week}")
    return None


def sum_optimal_lineup_points(roster):
    """
    Given a roster with weekly stats, selects the optimal lineup for each position
    (QB, RB, WR, TE, K, DEF, flex) and sums total points.
    """
    if not roster:
        return 0.0

    position_slots = {
        "QB": 1,
        "RB": 2,
        "WR": 2,
        "TE": 1,
        "K": 1,
        "DEF": 1,
        "W/R/T": 1  # flex
    }

    # Build a dict of eligible players by position
    players_by_pos = {pos: [] for pos in position_slots}
    for player in roster:
        try:
            total_points = float(player.get("weekly_stats", {}).get("total_points", 0.0))
        except ValueError:
            total_points = 0.0
        for pos in player.get("eligible_positions", []):
            if pos in players_by_pos:
                players_by_pos[pos].append((total_points, player))

    used_players = set()
    total_score = 0.0

    # Select players for each slot, taking highest points first
    for pos, count in position_slots.items():
        eligible = sorted(players_by_pos.get(pos, []), key=lambda x: x[0], reverse=True)
        for points, player in eligible:
            if player["player_id"] not in used_players and count > 0:
                total_score += points
                used_players.add(player["player_id"])
                count -= 1

    return total_score

  


import json
import os

# Load projections once
with open("fantasypros_projFinal.json") as f:
    projected_points = json.load(f)

# Standard fallback points if no player is available for a slot
standardRLP = {
    "QB": 15.0,
    "RB": 8.0,
    "WR": 8.0,
    "TE": 7.0,
    "FLEX": 8.0,
    "K": 8.0,
    "DEF": 6.5
}

def load_frozen_roster(manager_name, roster_week):
    """
    Load the frozen roster for the manager from a given week
    """
    path = f"team_rosters_weekly_stats_week_{roster_week}/{manager_name.replace(' ', '_')}_week_{roster_week}.json"
    with open(path) as f:
        data = json.load(f)
    key = f"{manager_name}_week_{roster_week}_roster"
    return data[key]

def get_actual_points(player_name, week):
    """
    Search all weekly roster files for the player's actual points in a given week
    """
    week_path = f"team_rosters_weekly_stats_week_{week}"
    for file in os.listdir(week_path):
        if file.endswith(".json"):
            with open(os.path.join(week_path, file)) as f:
                data = json.load(f)
            for roster_key in data:
                for p in data[roster_key]:
                    if p["name"] == player_name:
                        return float(p["weekly_stats"].get("total_points", 0.0))
    # If not found
    #print(f"WARNING: {player_name} not found in week {week}")
    return 0.0

def get_projected_points(player_name, week):
    """
    Get projected points from fantasypros_projFinal.json by player name + team
    """
    week_str = str(week)
    for key in projected_points:
        if key.startswith(player_name):
            return float(projected_points[key].get(week_str, 0.0))
    # Not found
    #print(f"WARNING: No projection found for {player_name} in week {week}")
    return 0.0

def future_points_with_frozen_roster_actual(manager_name, roster_week, start_week, end_week):
    frozen_roster = load_frozen_roster(manager_name, roster_week)
    #print(f"week:", roster_week)
    '''for player in frozen_roster:
    
        print(f"player:", player["name"], player["eligible_positions"])'''
    total_points = 0.0

    for w in range(start_week, end_week + 1):
        #print(f"\nWeek {w}:")
        # Build weekly roster with projected and actual points
        weekly_roster = []
        for player in frozen_roster:
            name = player["name"]
            proj_pts = get_projected_points(name, w)
            actual_pts = get_actual_points(name, w)
            weekly_roster.append({
                "name": name,
                "position": player.get("eligible_positions", ""),
                "projected_points": proj_pts,
                "actual_points": actual_pts
            })

        # Build optimal lineup
        week_total = sum_actual_points_of_optimal_lineup(weekly_roster)
        total_points += week_total
        #print(f"Total points for week {w}: {week_total:.2f}")

    return total_points

def sum_actual_points_of_optimal_lineup(weekly_roster):
    """
    Build the optimal lineup by projected points (considering all eligible positions, including bench).
    Only players with projected_points >= RLP for that slot can start; else use fallback.
    weekly_roster: list of dicts with keys: name, position (list), projected_points, actual_points
    """
    slots = {
        "QB": 1,
        "RB": 2,
        "WR": 2,
        "TE": 1,
        "FLEX": 1,  # W/R/T
        "K": 1,
        "DEF": 1
    }

    total = 0.0
    used_players = set()

    for pos, count in slots.items():
        # Determine RLP for this slot
        rlp = standardRLP.get(pos, 0.0) if pos != "FLEX" else standardRLP["FLEX"]

        # Determine eligible players
        if pos == "FLEX":
            eligible_positions = ("RB", "WR", "TE")
        else:
            eligible_positions = (pos,)

        # Candidates: players not already used and whose position list contains at least one eligible slot
        candidates = [p for p in weekly_roster if p["name"] not in used_players and any(ep in eligible_positions for ep in p["position"])]

        # Sort candidates by projected points descending
        candidates.sort(key=lambda x: x["projected_points"], reverse=True)

        # Only allow starters with projected_points >= RLP
        starters_allowed = [p for p in candidates if p["projected_points"] >= rlp]

        for i in range(count):
            if i < len(starters_allowed):
                player = starters_allowed[i]
                total += player["actual_points"]
                used_players.add(player["name"])
                #print(f"{player['name']} ({pos}): projected {player['projected_points']:.2f} pts, actual {player['actual_points']:.2f} pts")
            else:
                # fallback
                total += rlp
                #print(f"Fallback for {pos}: {rlp:.2f} pts")

    return total







# Example usage:
if __name__ == "__main__":
    total_before = future_points_with_frozen_roster_actual(
        manager_name="Deej-lanta Falcons",
        roster_week=4,
        start_week=5,
        end_week=12
    )
    #print("\nTotal points over weeks 5-12:", total_before)



if __name__ == "__main__":
    total_after = future_points_with_frozen_roster_actual(
        manager_name="Deej-lanta Falcons",
        roster_week=5,
        start_week=5,
        end_week=12
    )
    #print("Total points over weeks 5-12:", total_after)


print("Net points from trade for DJ: ", total_after-total_before)
total_before1 = future_points_with_frozen_roster_actual(manager_name="No Punts Intented",
                                                        roster_week=4,
                                                        start_week=5,
                                                        end_week=12)
total_after1 = future_points_with_frozen_roster_actual(manager_name="No Punts Intented",
                                                        roster_week=5,
                                                        start_week=5,
                                                        end_week=12)
print("Net points from trade for Rubik: ", total_after1-total_before1)
print("\n")

total_before2 = future_points_with_frozen_roster_actual(manager_name="Supernova’s Studs",
                                                        roster_week=4,
                                                        start_week=5,
                                                        end_week=12)
total_after2 = future_points_with_frozen_roster_actual(manager_name="Supernova’s Studs",
                                                        roster_week=5,
                                                        start_week=5,
                                                        end_week=12)
print("Net points from trade for Gav: ", total_after2-total_before2)
total_before3 = future_points_with_frozen_roster_actual(manager_name="Hungry Hungry Hokk",
                                                        roster_week=4,
                                                        start_week=5,
                                                        end_week=12)
total_after3 = future_points_with_frozen_roster_actual(manager_name="Hungry Hungry Hokk",
                                                        roster_week=5,
                                                        start_week=5,
                                                        end_week=12)
print("Net points from trade for Hokk: ", total_after3-total_before3)
print("\n")

total_before4 = future_points_with_frozen_roster_actual(manager_name="Hungry Hungry Hokk",
                                                        roster_week=5,
                                                        start_week=6,
                                                        end_week=12)
total_after4 = future_points_with_frozen_roster_actual(manager_name="Hungry Hungry Hokk",
                                                        roster_week=6,
                                                        start_week=6,
                                                        end_week=12)
print("Net points from trade for hokk: ", total_after4-total_before4)
total_before5 = future_points_with_frozen_roster_actual(manager_name="The Sage's Playmakers",
                                                        roster_week=5,
                                                        start_week=6,
                                                        end_week=12)
total_after5 = future_points_with_frozen_roster_actual(manager_name="The Sage's Playmakers",
                                                        roster_week=6,
                                                        start_week=6,
                                                        end_week=12)
print("Net points from trade for lapsley: ", total_after5-total_before5)
print("\n")

total_before6 = future_points_with_frozen_roster_actual(manager_name="Supernova’s Studs",
                                                        roster_week=6,
                                                        start_week=7,
                                                        end_week=12)
total_after6 = future_points_with_frozen_roster_actual(manager_name="Supernova’s Studs",
                                                        roster_week=7,
                                                        start_week=7,
                                                        end_week=12)
print("Net points from trade for gav: ", total_after6-total_before6)
total_before7 = future_points_with_frozen_roster_actual(manager_name="The Sage's Playmakers",
                                                        roster_week=6,
                                                        start_week=7,
                                                        end_week=12)
total_after7 = future_points_with_frozen_roster_actual(manager_name="The Sage's Playmakers",
                                                        roster_week=7,
                                                        start_week=7,
                                                        end_week=12)
print("Net points from trade for lapsley: ", total_after7-total_before7)
print("\n")

total_before8 = future_points_with_frozen_roster_actual(manager_name="Supernova’s Studs",
                                                        roster_week=11,
                                                        start_week=12,
                                                        end_week=12)
total_after8 = future_points_with_frozen_roster_actual(manager_name="Supernova’s Studs",
                                                        roster_week=12,
                                                        start_week=12,
                                                        end_week=12)
print("Net points from trade for gav: ", total_after8-total_before8)
total_before9 = future_points_with_frozen_roster_actual(manager_name="Ozzy Stick",
                                                        roster_week=11,
                                                        start_week=12,
                                                        end_week=12)
total_after9 = future_points_with_frozen_roster_actual(manager_name="Ozzy Stick",
                                                        roster_week=12,
                                                        start_week=12,
                                                        end_week=12)
print("Net points from trade for bullman: ", total_after9-total_before9)
print("\n")




#points_frozen = future_points_with_frozen_roster(manager_name, week)
#print(f"Points with frozen roster from week {int(week)} onwards: {points_frozen}")

# Points using actual roster week-by-week
##points_actual = get_points_after_week(manager_name, week)
#print(f"Points with actual roster each week after week {int(week)}: {points_actual}")
# print("Points (actual weekly rosters):", points_actual)
# print("Points (frozen roster):", points_frozen)



