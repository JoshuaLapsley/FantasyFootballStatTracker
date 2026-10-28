"""
Pull the head-to-head schedule (which team plays which, each week) for
a league directly from Yahoo's OAuth API -- no scraping needed.
Yahoo's league.matchups(week) call returns each week's pairings directly,
for past, current, and future weeks alike.

Usage as a function
-------------------
    from pull_schedule import pull_league_schedule

    pull_league_schedule("470.l.205662", 2026)
    # or pass an already-built yahoo_fantasy_api League object:
    pull_league_schedule(league, 2026)

Output
------
../APIData/{year}/schedule.json (relative to this script):
    {
      "1": [["Flow Brrr", "You gotta be Falcon kiddin me"], ...],
      "2": [...],
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

SCRIPT_DIR = os.path.dirname(os.path.abspath(__file__))
OAUTH_FILE = os.path.join(SCRIPT_DIR, "..", "oauth2.json")
API_DATA_DIR = os.path.join(SCRIPT_DIR, "..", "APIData")


def get_league(league_id: str, oauth_file: str = OAUTH_FILE):
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


def parse_weeks(spec, regular_season_weeks: list) -> list:
    """'all', a range like '3-6', or a comma list like '3,5,7'."""
    if spec == "all":
        return regular_season_weeks
    if "-" in spec:
        start, end = spec.split("-", 1)
        return list(range(int(start), int(end) + 1))
    return [int(w) for w in spec.split(",")]


def pull_league_schedule(league, year, weeks="all", oauth_file: str = OAUTH_FILE) -> dict:
    """
    Pull a league's head-to-head schedule and save it to
    ../APIData/{year}/schedule.json.

    Parameters
    ----------
    league : str or yahoo_fantasy_api League
        A Yahoo league id (e.g. "470.l.205662") or an existing League object.
    year : int or str
        Season year; determines the output folder.
    weeks : str
        'all' (full regular season, default), a range like '3-6',
        or a comma list like '3,5,7'.
    oauth_file : str
        Path to yahoo_oauth credentials json (only used if `league` is an id).

    Returns
    -------
    dict : the schedule that was written.
    """
    if isinstance(league, str):
        league = get_league(league, oauth_file=oauth_file)

    week_list = parse_weeks(weeks, get_regular_season_weeks(league))

    print(f"Pulling {year} schedule for weeks: {week_list}\n")
    schedule = pull_schedule(league, week_list)

    out_dir = os.path.join(API_DATA_DIR, str(year))
    os.makedirs(out_dir, exist_ok=True)
    output_path = os.path.join(out_dir, "schedule.json")
    with open(output_path, "w") as f:
        json.dump(schedule, f, indent=2)
    print(f"\nSaved -> {os.path.normpath(output_path)}")

    return schedule


def main():
    parser = argparse.ArgumentParser(
        description="Pull the head-to-head schedule for every week of the regular season."
    )
    parser.add_argument("league_id", help="Yahoo league id, e.g. 470.l.205662")
    parser.add_argument("year", help="Season year, e.g. 2026 (used for the output folder)")
    parser.add_argument("--oauth-file", default=OAUTH_FILE, help="Path to yahoo_oauth credentials json")
    parser.add_argument(
        "--weeks", default="all",
        help="Weeks to pull: 'all' (default), a range like '3-6', or a comma list like '3,5,7'."
    )
    args = parser.parse_args()

    pull_league_schedule(args.league_id, args.year, weeks=args.weeks, oauth_file=args.oauth_file)


if __name__ == "__main__":
    main()