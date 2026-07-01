import json
import os

BASE_DIR = "league_stats_output"

# Must match the seasons defined in generate_league_stats.py
SEASONS = [2023, 2024, 2025]

START_WEEK = 1
END_WEEK = 14


def load_weekly_points(season):
    path = os.path.join(BASE_DIR, str(season), "weekly_points.json")
    with open(path, "r") as f:
        return json.load(f)


def generate_bump_chart_data(weekly_points, season, start_week=START_WEEK, end_week=END_WEEK):
    """
    Builds long-format bump chart data: one row per team per week, with that
    team's rank in the league standings AFTER that week's games are included.

    Ranking rule:
      1. Higher cumulative wins ranks better.
      2. Ties in wins are broken by higher cumulative points_for (up to and
         including that week).

    Output rows:
      {
        "season": <int>,
        "week": <int>,
        "team": <str>,
        "rank": <int>,           # 1 = best record in the league that week
        "cumulative_wins": <int>,
        "cumulative_losses": <int>,
        "cumulative_ties": <int>,
        "cumulative_points_for": <float>,
        "points_for_this_week": <float>,
        "points_against_this_week": <float>,
        "result_this_week": "W" | "L" | "T" | None  # None if no data for that week
      }
    """
    teams = list(weekly_points.keys())

    # Running totals per team
    cum_wins = {t: 0 for t in teams}
    cum_losses = {t: 0 for t in teams}
    cum_ties = {t: 0 for t in teams}
    cum_points_for = {t: 0.0 for t in teams}

    rows = []

    for week in range(start_week, end_week + 1):
        week_key = f"week_{week}"

        # First pass: update cumulative stats for every team based on this week's result
        for team in teams:
            week_data = weekly_points.get(team, {}).get(week_key)

            if week_data is None:
                # No game data for this team/week (bye, missing data, etc.)
                continue

            pf = week_data.get("points_for")
            pa = week_data.get("points_against")

            if pf is None or pa is None:
                continue

            cum_points_for[team] += pf

            if pf > pa:
                cum_wins[team] += 1
                result = "W"
            elif pf < pa:
                cum_losses[team] += 1
                result = "L"
            else:
                cum_ties[team] += 1
                result = "T"

            # Stash this week's result temporarily; recovered below for the row
            weekly_points[team][week_key]["_result_computed"] = result

        # Second pass: rank teams after this week using (wins desc, points_for desc)
        ranking_order = sorted(
            teams,
            key=lambda t: (-cum_wins[t], -cum_points_for[t])
        )

        for rank, team in enumerate(ranking_order, start=1):
            week_data = weekly_points.get(team, {}).get(week_key, {})
            pf_week = week_data.get("points_for")
            pa_week = week_data.get("points_against")
            result_week = week_data.get("_result_computed")

            rows.append({
                "season": season,
                "week": week,
                "team": team,
                "rank": rank,
                "cumulative_wins": cum_wins[team],
                "cumulative_losses": cum_losses[team],
                "cumulative_ties": cum_ties[team],
                "cumulative_points_for": round(cum_points_for[team], 2),
                "points_for_this_week": pf_week,
                "points_against_this_week": pa_week,
                "result_this_week": result_week,
            })

    return rows


def main():
    all_rows = []

    for season in SEASONS:
        print(f"Processing season {season}...")
        try:
            weekly_points = load_weekly_points(season)
        except FileNotFoundError:
            print(f"  weekly_points.json not found for {season}, skipping.")
            continue

        rows = generate_bump_chart_data(weekly_points, season, START_WEEK, END_WEEK)
        all_rows.extend(rows)
        print(f"  {len(rows)} rows generated "
              f"({len(rows) // (END_WEEK - START_WEEK + 1)} teams x {END_WEEK - START_WEEK + 1} weeks)")

    output_path = os.path.join(BASE_DIR, "bump_chart_long.json")
    with open(output_path, "w") as f:
        json.dump(all_rows, f, indent=2)

    print(f"\nSaved {len(all_rows)} total rows → {output_path}")


if __name__ == "__main__":
    main()