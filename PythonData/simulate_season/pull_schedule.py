"""
Pull the head-to-head schedule (which team plays which, each week) for
the whole league directly from Yahoo's OAuth API -- no scraping needed
for this one. Yahoo's league.matchups(week) call returns each week's
pairings directly, for past, current, and future weeks alike.

Output
------
simulate_season/schedule.json:
    {
      "2": [["Flow Brrr", "You gotta be Falcon kiddin me"], ...],
      "3": [...],
      ...
    }
keyed by week number (as a string, for plain-JSON compatibility),
each a list of [team_a, team_b] pairs for that week's matchups.
"""

import argparse
import json
import os

from yahoo_oauth import OAuth2
import yahoo_fantasy_api as yfa

LEAGUE_ID = "470.l.205662"  # Girderma Gridiron, 2026 season -- update yearly
SCRIPT_DIR = os.path.dirname(os.path.abspath(__file__))
OAUTH_FILE = os.path.join(SCRIPT_DIR, "..", "oauth2.json")
OUTPUT_PATH = os.path.join(SCRIPT_DIR, "schedule.json")


def get_league(oauth_file: str = OAUTH_FILE, league_id: str = LEAGUE_ID):
    sc = OAuth2(None, None, from_file=oauth_file)
    gm = yfa.Game(sc, "nfl")
    return gm.to_league(league_id)


def get_regular_season_weeks(league) -> list:
    settings = league.settings()
    playoff_start = int(settings.get("playoff_start_week", 15))
    return list(range(1, playoff_start))


def _team_meta_field(meta_list, field):
    for item in meta_list:
        if isinstance(item, dict) and field in item:
            return item[field]
    return None


def _extract_team_name(team_raw) -> str:
    meta = team_raw[0]
    return _team_meta_field(meta, "name")


def get_week_matchups(league, week: int) -> list:
    """Return [[team_a, team_b], ...] for the given week."""
    raw = league.matchups(week=week)
    try:
        scoreboard = raw["fantasy_content"]["league"][1]["scoreboard"]
        sb_key = next(k for k in scoreboard.keys() if k.isdigit())
        matchups_raw = scoreboard[sb_key]["matchups"]
        count = int(matchups_raw["count"])
    except (KeyError, IndexError, StopIteration, TypeError) as e:
        raise RuntimeError(f"Unexpected Yahoo scoreboard JSON shape for week {week}: {e}")

    pairs = []
    for i in range(count):
        matchup = matchups_raw[str(i)]["matchup"]
        teams_raw = matchup["0"]["teams"]
        team_count = int(teams_raw["count"])
        names = [_extract_team_name(teams_raw[str(j)]["team"]) for j in range(team_count)]
        if len(names) == 2:
            pairs.append(names)
        else:
            print(f"  \u26a0 week {week}: matchup with {len(names)} teams "
                  f"(expected 2), skipping: {names}")

    return pairs


def pull_schedule(league, weeks: list) -> dict:
    schedule = {}
    for week in weeks:
        pairs = get_week_matchups(league, week)
        schedule[str(week)] = pairs
        print(f"  Week {week}: {len(pairs)} matchups")
    return schedule


def main():
    parser = argparse.ArgumentParser(
        description="Pull the head-to-head schedule for every week of the regular season."
    )
    parser.add_argument("--oauth-file", default=OAUTH_FILE, help="Path to yahoo_oauth credentials json")
    parser.add_argument("--league-id", default=LEAGUE_ID, help="Yahoo league id, e.g. 470.l.205662")
    parser.add_argument(
        "--weeks", default="all",
        help="Weeks to pull: 'all' (full regular season, default), a range like '3-6', "
             "or a comma list like '3,5,7'."
    )
    parser.add_argument("--output", default=OUTPUT_PATH, help="Path to write schedule.json")
    args = parser.parse_args()

    league = get_league(oauth_file=args.oauth_file, league_id=args.league_id)
    regular_season_weeks = get_regular_season_weeks(league)

    if args.weeks == "all":
        weeks = regular_season_weeks
    elif "-" in args.weeks:
        start, end = args.weeks.split("-", 1)
        weeks = list(range(int(start), int(end) + 1))
    else:
        weeks = [int(w) for w in args.weeks.split(",")]

    print(f"Pulling schedule for weeks: {weeks}\n")
    schedule = pull_schedule(league, weeks)

    with open(args.output, "w") as f:
        json.dump(schedule, f, indent=2)
    print(f"\nSaved -> {args.output}")


if __name__ == "__main__":
    main()
