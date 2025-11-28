#the replacement-level points for each position for each week

#RLP means replacement-level points
#here is a sample RLP
RLP = {
    4: {   # week number
        "QB": 14.0,
        "RB": 9.0,
        "WR": 8.0,
        "TE": 6.0,
        "W/R/T": 9.0, #flex is the max{wr,rb,te}
        "K": 7.0,
        "DEF": 6.0
    }
}

def determine_comparison_position(player):
    pos = player["selected_position"]
    
    if pos == "W/R/T":
        for p in player["eligible_positions"]:
            if p in {"RB", "WR", "TE"}:
                return p
    return pos

def get_player_points(player):
    pts = player["weekly_stats"].get("total_points", 0)
    return float(pts) if pts not in ("", None) else 0.0

def compute_PAR_for_team(roster, week, replacement_levels):
    results = []

    for player in roster:
        natural_pos = determine_comparison_position(player)
        player_points = get_player_points(player)

        # if the player is in the flex spot compare vs FLEX RLP
        if player["selected_position"] == "W/R/T":
            comp_pos = "W/R/T"
        else:
            comp_pos = natural_pos

        # look up replacement-level value
        try:
            rl_points = replacement_levels[week][comp_pos]
        except KeyError:
            raise ValueError(f"Missing replacement level for pos={comp_pos} week={week}")

        par = player_points - rl_points

        results.append({
            "player_id": player["player_id"],
            "name": player["name"],
            "natural_position": natural_pos,
            "team_position": player["selected_position"],
            "comparison_position": comp_pos,
            "points": player_points,
            "replacement_level": rl_points,
            "PAR": par
        })

    return results


