"""
Scrape Yahoo's per-player projected points for weeks that have ALREADY
been played, and cache them separately from pull_projections.py's
regular output.

Why this exists
----------------
pull_projections.py is meant to be re-run throughout a week as Yahoo
updates its projections, right up until that week's games kick off --
so it always OVERWRITES simulate_season/projections/week_<N>.json. That
is exactly the wrong behavior for a week that's already final: once a
week is over, Yahoo stops updating that pregame number and there's no
reason to ever re-scrape it, so it should be fetched once and left
alone permanently.

This script shares all of pull_projections.py's scraping/login
machinery (login-cookie lifting, Selenium driver setup, roster-table
parsing, rate-limit backoff) via direct import -- nothing is
duplicated/reimplemented here -- but:
  * defaults to the weeks STRICTLY BEFORE the league's current week
    (i.e. weeks that have already finished), not "remaining",
  * writes to its own folder, simulate_season/projections_historical/,
    instead of simulate_season/projections/, and
  * always skips weeks that already have a saved file UNLESS
    --force-rescrape is passed, since a finished week's projection
    number never changes -- so once a week is scraped here, future
    runs only need to scrape whatever one new week just became final,
    not re-pull the whole history.

Used by trade_evaluator.py, which needs a real per-player, per-week
projection number (to pick each team's highest-projected legal lineup)
for every week a trade needs to be evaluated across -- including weeks
long before the current one, which pull_projections.py's own cache
normally won't still have around untouched.

Usage:
    python3 pull_historical_projections.py                  # all finished weeks not yet cached
    python3 pull_historical_projections.py --weeks 3-6
    python3 pull_historical_projections.py --force-rescrape --weeks 5
"""

import argparse
import os
import json
import time

from pull_projections import (
    LEAGUE_ID,
    OAUTH_FILE,
    SIMULATE_SEASON_DIR,
    REQUEST_DELAY_SECONDS,
    TEAMS_PER_BROWSER_SESSION,
    get_league,
    get_teams,
    build_driver,
    ensure_logged_in,
    scrape_week,
)

HISTORICAL_OUTPUT_DIR = os.path.join(SIMULATE_SEASON_DIR, "projections_historical")


def get_finished_weeks(league) -> list:
    """Every week strictly before the league's current week -- same
    'already final' convention used everywhere else in this project
    (CalculateWAR.py, RunWeekly.py, etc.)."""
    return list(range(1, league.current_week()))


def parse_week_arg(weeks_arg: str, finished_weeks: list) -> list:
    if weeks_arg == "all":
        return finished_weeks
    if "-" in weeks_arg:
        start, end = weeks_arg.split("-", 1)
        return list(range(int(start), int(end) + 1))
    return [int(w) for w in weeks_arg.split(",")]


def main():
    parser = argparse.ArgumentParser(
        description="Scrape Yahoo's per-player weekly projections for weeks that have "
                    "already been played, caching them permanently (separate from "
                    "pull_projections.py's always-overwritten live output)."
    )
    parser.add_argument(
        "--weeks", default="all",
        help="Weeks to scrape: 'all' (default, every finished week not yet cached here), "
             "a range like '3-6', or a comma list like '3,5,7'."
    )
    parser.add_argument("--oauth-file", default=OAUTH_FILE, help="Path to yahoo_oauth credentials json")
    parser.add_argument("--league-id", default=LEAGUE_ID, help="Yahoo league id, e.g. 470.l.205662")
    parser.add_argument("--headless", action="store_true",
                         help="Run the scraping browser headless (safe here since it never touches the login form).")
    parser.add_argument("--chrome-profile", default=None,
                         help="Path to a specific Chrome cookie DB / profile to read your Yahoo login "
                              "from, if not Chrome's default profile.")
    parser.add_argument("--force-rescrape", action="store_true",
                         help="Re-scrape (and overwrite) weeks that already have a saved file here. "
                              "Not needed in normal use -- a finished week's projection number never "
                              "changes -- but useful if a prior scrape of that week was known to be bad.")
    args = parser.parse_args()

    league = get_league(oauth_file=args.oauth_file, league_id=args.league_id)
    teams = get_teams(league)
    finished_weeks = get_finished_weeks(league)

    weeks_requested = parse_week_arg(args.weeks, finished_weeks)
    weeks_to_scrape = [w for w in weeks_requested if w in finished_weeks]
    skipped_not_finished = [w for w in weeks_requested if w not in finished_weeks]
    if skipped_not_finished:
        print(f"Skipping week(s) {skipped_not_finished} -- not finished yet per Yahoo "
              f"(current week: {league.current_week()}). Use pull_projections.py for those.")

    if not args.force_rescrape:
        already_cached = [
            w for w in weeks_to_scrape
            if os.path.exists(os.path.join(HISTORICAL_OUTPUT_DIR, f"week_{w}.json"))
        ]
        if already_cached:
            print(f"Already cached, skipping (use --force-rescrape to redo): {already_cached}")
        weeks_to_scrape = [w for w in weeks_to_scrape if w not in already_cached]

    print(f"Teams: {len(teams)}. Current week: {league.current_week()}. "
          f"Finished weeks available: {finished_weeks}. Scraping: {weeks_to_scrape or 'none'}\n")

    if not weeks_to_scrape:
        print("Nothing to do.")
        return

    os.makedirs(HISTORICAL_OUTPUT_DIR, exist_ok=True)

    driver = build_driver(headless=args.headless)
    ensure_logged_in(driver, chrome_profile=args.chrome_profile)
    teams_scraped_this_session = 0

    try:
        for i, week in enumerate(weeks_to_scrape):
            print(f"=== Scraping (historical) week {week} ===")

            if teams_scraped_this_session + len(teams) > TEAMS_PER_BROWSER_SESSION:
                print("  -- restarting browser session to avoid rate-limit "
                      "buildup / long-session instability --")
                driver.quit()
                driver = build_driver(headless=args.headless)
                ensure_logged_in(driver, chrome_profile=args.chrome_profile)
                teams_scraped_this_session = 0

            week_data = scrape_week(driver, teams, week)
            teams_scraped_this_session += len(teams)

            out_path = os.path.join(HISTORICAL_OUTPUT_DIR, f"week_{week}.json")
            with open(out_path, "w") as f:
                json.dump(week_data, f, indent=2)
            print(f"  Saved -> {out_path}\n")

            if i < len(weeks_to_scrape) - 1:
                time.sleep(REQUEST_DELAY_SECONDS * 2)
    finally:
        driver.quit()

    print("Done.")


if __name__ == "__main__":
    main()
