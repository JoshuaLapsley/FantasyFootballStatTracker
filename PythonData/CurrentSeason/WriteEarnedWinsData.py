import json
import os


def calculate_earned_wins(data_directory, output_directory):
    teams = {}

    # ----------------------------------------
    # Get every JSON file from data directory
    # ----------------------------------------

    json_files = [
        filename
        for filename in os.listdir(data_directory)
        if filename.endswith(".JSON") or filename.endswith(".json")
    ]

    # Don't accidentally read the output file
    json_files = [
        filename
        for filename in json_files
        if filename.lower() != "earnedwins.json"
    ]

    # ----------------------------------------
    # Read all files
    # ----------------------------------------

    for filename in json_files:

        file_path = os.path.join(data_directory, filename)

        with open(file_path, "r", encoding="utf-8") as file:
            matchups = json.load(file)

        # All teams' scores for this week
        weekly_teams = []

        for matchup in matchups:

            # ----------------------------------------
            # Process teams
            # ----------------------------------------

            for team in matchup["teams"]:

                team_key = team["team_key"]

                weekly_teams.append({
                    "team_key": team_key,
                    "name": team["name"],
                    "points": team["points"]
                })

                # Create team if we haven't seen it
                if team_key not in teams:
                    teams[team_key] = {
                        "name": team["name"],
                        "Earned Wins": 0,
                        "Actual Wins": 0,
                        "Points For": 0,
                        "Points Against": 0
                    }

                # Add Points For
                teams[team_key]["Points For"] += team["points"]

            # ----------------------------------------
            # Points Against
            # ----------------------------------------

            team1 = matchup["teams"][0]
            team2 = matchup["teams"][1]

            teams[team1["team_key"]]["Points Against"] += team2["points"]
            teams[team2["team_key"]]["Points Against"] += team1["points"]

            # ----------------------------------------
            # Actual Win
            # ----------------------------------------

            winner = matchup["winner_team_key"]

            teams[winner]["Actual Wins"] += 1

        # ----------------------------------------
        # Calculate Earned Wins for this week
        # ----------------------------------------

        # Sort highest points -> lowest points
        weekly_teams.sort(
            key=lambda team: team["points"],
            reverse=True
        )

        # League has 13 teams
        total_teams = 13

        for rank, team in enumerate(weekly_teams, start=1):

            # 1st  = 13/13 = 1.0000
            # 2nd  = 12/13 = 0.9231
            # 3rd  = 11/13 = 0.8462
            # ...
            # 13th = 1/13  = 0.0769

            earned_win = (
                (total_teams - rank + 1)
                / total_teams
            )

            teams[team["team_key"]]["Earned Wins"] += earned_win

    # ----------------------------------------
    # Create final results
    # ----------------------------------------

    results = []

    for team_key, team in teams.items():

        difference = (
            team["Actual Wins"]
            - team["Earned Wins"]
        )

        results.append({
            "Team": team["name"],
            "Earned Wins": round(team["Earned Wins"], 4),
            "Actual Wins": team["Actual Wins"],
            "Difference": round(difference, 4),
            "Points For": round(team["Points For"], 2),
            "Points Against": round(team["Points Against"], 2)
        })

    # ----------------------------------------
    # Sort luckiest -> unluckiest
    # ----------------------------------------

    results.sort(
        key=lambda team: team["Difference"],
        reverse=True
    )

    # Add Difference Rank
    for rank, team in enumerate(results, start=1):
        team["Difference Rank"] = rank

    # ----------------------------------------
    # Make sure output directory exists
    # ----------------------------------------

    os.makedirs(output_directory, exist_ok=True)

    # ----------------------------------------
    # Write output JSON
    # ----------------------------------------

    output_path = os.path.join(
        output_directory,
        "EarnedWins.json"
    )

    with open(output_path, "w", encoding="utf-8") as file:
        json.dump(results, file, indent=4)

    print(f"Created: {output_path}")

