import json
import os

BASE_DIR = os.path.dirname(os.path.abspath(__file__))


def calculate_earned_wins(year):
    data_directory = os.path.join(BASE_DIR, "..", "APIData", str(year), "MatchupData")
    output_directory = os.path.join(BASE_DIR, "..", "Data", str(year))

    if not os.path.isdir(data_directory):
        raise FileNotFoundError(f"Matchup data not found: {data_directory}")

    teams = {}

    # ----------------------------------------
    # Get every JSON file from data directory
    # ----------------------------------------

    json_files = [
        filename
        for filename in os.listdir(data_directory)
        if filename.lower().endswith(".json")
        and filename.lower() != "earnedwins.json"  # don't read the output file
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

        # Computed per week so it stays correct if league size changes
        # or a playoff week only involves a subset of teams.
        total_teams = len(weekly_teams)

        for rank, team in enumerate(weekly_teams, start=1):

            # Earned Wins = fraction of the OTHER teams this week that
            # this team's score beat (1st = 1.0, last = 0.0).
            earned_win = (
                (total_teams - rank)
                / (total_teams - 1)
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
    # Write output JSON
    # ----------------------------------------

    os.makedirs(output_directory, exist_ok=True)

    output_path = os.path.join(output_directory, "EarnedWins.json")

    with open(output_path, "w", encoding="utf-8") as file:
        json.dump(results, file, indent=4)

    print(f"Created: {output_path}")