"""
Pull Yahoo's own weekly player projections for every team in the league.

Yahoo's public Fantasy Sports REST API does *not* expose per-player
projected points (confirmed: player stats requests for a future/unplayed
week come back all zero -- Yahoo only computes per-player projections for
display on the website, not through the API). The only place these
numbers exist is the Yahoo Fantasy website itself, on each team's roster
page with the "Projected Stats" view.

This script drives a real, logged-in Chrome session (via Selenium) to
pull that data directly:

    https://football.fantasysports.yahoo.com/f1/{league_id}/{team_id}/team
        ?week={week}&stat1=P&stat2=PW

For each team in the league, for each regular-season week, this loads
that URL and scrapes the roster table (id="statTable0"): roster slot
(QB/RB/WR/TE/W-R-T/BN/IR), player name, NFL team, position, and Yahoo's
projected fantasy points for that week.

Login / session handling
-------------------------
Yahoo's login page actively fingerprints for Selenium/automation markers
and refuses to let a login proceed through a Selenium-driven browser at
all -- even a real person typing into a real, visible window gets
rejected with "This browser or app may not be secure." So this script
never drives the Yahoo login form itself.

Instead:
  1. You log into Yahoo normally, in your own everyday Chrome (not
     launched by this script).
  2. This script reads the resulting Yahoo session cookies directly out
     of that real Chrome profile's cookie store (via `browser_cookie3`,
     which decrypts Chrome's cookie DB through the macOS Keychain -- you
     may see a one-time Keychain permission prompt).
  3. Those cookies are injected into the Selenium-controlled browser,
     which only ever loads already-authenticated pages. Selenium never
     touches the login form, so there's nothing for Yahoo to flag.

When your Yahoo session eventually expires, just log in again in your
normal Chrome and re-run this script -- no code changes needed.

Team/league metadata (team ids, names, current week, season length) comes
from the existing Yahoo OAuth API setup (oauth2.json) already used
elsewhere in this project -- that part is unaffected by the API's lack of
player-level projections, since it's only used for league bookkeeping.

Output
------
Since projections change throughout the week as Yahoo updates them, this
is meant to be re-run weekly (or more often). Each run overwrites:

    simulate_season/projections/week_<N>.json

with the full "team -> [players...]" projection data for that week, for
every team in the league. Re-running does not require re-scraping every
past week -- use --weeks to control the range (defaults to just the
current week through end of the regular season).
"""

import argparse
import json
import os
import time

from yahoo_oauth import OAuth2
import yahoo_fantasy_api as yfa

import browser_cookie3

from selenium import webdriver
from selenium.webdriver.chrome.options import Options
from selenium.webdriver.common.by import By
from selenium.webdriver.support.ui import WebDriverWait
from selenium.common.exceptions import (
    NoSuchElementException,
    WebDriverException,
    TimeoutException,
    InvalidSessionIdException,
)


# --------------------------------------------------------------------------
# CONFIG
# --------------------------------------------------------------------------

LEAGUE_ID = "470.l.205662"  # Girderma Gridiron, 2026 season -- update yearly
OAUTH_FILE = os.path.join(os.path.dirname(__file__), "..", "oauth2.json")

SCRIPT_DIR = os.path.dirname(os.path.abspath(__file__))
OUTPUT_DIR = os.path.join(SCRIPT_DIR, "projections")

# Persistent Chrome profile so login cookies survive across runs. This is
# NOT the same as your everyday Chrome profile -- it's a dedicated,
# separate profile just for this scraper.
CHROME_PROFILE_DIR = os.path.join(SCRIPT_DIR, ".chrome_profile")

LOGIN_HOST = "login.yahoo.com"
BASE_URL = "https://football.fantasysports.yahoo.com"

REQUEST_DELAY_SECONDS = 4  # be polite between page loads -- Yahoo starts
                            # returning a bare "Request denied" page after
                            # roughly 50-70 rapid roster-page loads in a
                            # short window (observed after ~5 min at 1.5s
                            # spacing). A larger gap avoids tripping that.

RATE_LIMIT_BACKOFF_SECONDS = 45  # cooldown observed to clear the block
RATE_LIMIT_MAX_RETRIES = 3

# After repeated "Request denied" rate-limit responses, the Chrome
# instance itself has been observed to become unstable and eventually
# crash outright ("session deleted") rather than just keep failing
# gracefully -- seen twice in testing, always after ~100-150 page loads
# in one continuous session. Restarting the browser (fresh process, new
# connections) periodically avoids both problems: it naturally paces
# requests and sidesteps whatever degrades in a single long-lived session.
TEAMS_PER_BROWSER_SESSION = 20

# Suffixes Yahoo glues directly onto player names with no separator on
# the roster page (injury designations + the "Video Forecast" link text).
# Longer/more specific strings must come before shorter ones they contain
# (e.g. "PUP-R" before "PUP", "IR-R"/"IR+" before "IR") since we only
# strip the first matching suffix.
NAME_NOISE_SUFFIXES = [
    "Video Forecast",
    "CEL",
    "PUP-R", "PUP",
    "IR-R", "IR+", "IR",
    "NFI-R", "NFI",
    "O", "D", "Q",
]


# --------------------------------------------------------------------------
# YAHOO OAUTH -- league/team metadata only (no per-player projections here)
# --------------------------------------------------------------------------

def get_league(oauth_file: str = OAUTH_FILE, league_id: str = LEAGUE_ID):
    sc = OAuth2(None, None, from_file=oauth_file)
    gm = yfa.Game(sc, "nfl")
    return gm.to_league(league_id)


def get_teams(league) -> dict:
    """Return {team_id (str): team_name} for every team in the league."""
    teams_info = league.teams()
    teams = {}
    for team_key, info in teams_info.items():
        team_id = team_key.split(".t.")[-1]
        teams[team_id] = info["name"]
    return teams


def get_regular_season_weeks(league) -> list:
    """Regular season is weeks 1..(playoff_start_week - 1)."""
    settings = league.settings()
    playoff_start = int(settings.get("playoff_start_week", 15))
    return list(range(1, playoff_start))


# --------------------------------------------------------------------------
# SELENIUM SESSION / LOGIN (via cookies lifted from your real Chrome)
# --------------------------------------------------------------------------

def load_cookies_from_real_chrome(chrome_profile: str = None) -> list:
    """
    Read Yahoo-related cookies out of the user's actual, everyday Chrome
    profile via browser_cookie3 (decrypts Chrome's cookie DB through the
    macOS Keychain -- you may see a one-time Keychain permission prompt).

    :param chrome_profile: optional path to a specific Chrome profile
        directory (e.g. ".../Chrome/Profile 2") if you don't want the
        default profile. If None, browser_cookie3 uses Chrome's default.
    :return: list of http.cookiejar.Cookie objects for yahoo.com domains.
    """
    try:
        cj = browser_cookie3.chrome(domain_name="yahoo.com", cookie_file=chrome_profile)
    except Exception as e:
        raise RuntimeError(
            "Could not read cookies from your everyday Chrome. Make sure "
            "Chrome is closed (Chrome sometimes locks its cookie DB while "
            "running) and that you've logged into Yahoo in it at least "
            f"once. Underlying error: {e}"
        )

    cookies = [c for c in cj if "yahoo.com" in c.domain]
    if not cookies:
        raise RuntimeError(
            "No yahoo.com cookies found in your everyday Chrome profile. "
            "Log into https://football.fantasysports.yahoo.com in your "
            "normal Chrome first, then re-run this script."
        )
    return cookies


def build_driver(headless: bool = False) -> webdriver.Chrome:
    """
    Launch Chrome against a persistent local profile dedicated to this
    scraper (separate from your everyday Chrome). Cookies get injected
    into this profile after launch -- see inject_cookies().
    """
    os.makedirs(CHROME_PROFILE_DIR, exist_ok=True)

    options = Options()
    options.add_argument(f"--user-data-dir={CHROME_PROFILE_DIR}")
    options.add_argument("--start-maximized")
    options.add_argument("--no-first-run")
    options.add_argument("--no-default-browser-check")
    if headless:
        options.add_argument("--headless=new")

    # The Yahoo roster page pulls in 30+ ad/tracking iframes. With the
    # default "normal" strategy, Selenium's get() blocks until the whole
    # page (including every one of those third-party scripts) fires
    # "load" -- which can hang well past any reasonable timeout if one of
    # them stalls. "eager" only waits for DOMContentLoaded, which is all
    # we need since we're scraping server-rendered table markup, not
    # waiting on ad content.
    options.page_load_strategy = "eager"

    driver = webdriver.Chrome(options=options)
    driver.set_page_load_timeout(45)
    return driver


def safe_get(driver: webdriver.Chrome, url: str, retries: int = 1) -> None:
    """
    driver.get() with the page-load timeout treated as non-fatal: with
    page_load_strategy="eager" the DOM is almost always ready well before
    the timeout even fires, so a timeout here usually just means Chrome
    is still waiting on a slow ad iframe -- stopping the load and moving
    on is fine since the roster table itself has long since rendered.
    """
    for attempt in range(retries + 1):
        try:
            driver.get(url)
            return
        except TimeoutException:
            try:
                driver.execute_script("window.stop();")
            except Exception:
                pass
            if attempt == retries:
                return
            time.sleep(1)


def inject_cookies(driver: webdriver.Chrome, cookies: list) -> None:
    """
    Load each cookie into the Selenium-controlled browser. Selenium's
    add_cookie() requires being on a page whose domain matches the
    cookie, so we first navigate to a lightweight Yahoo page, then add
    cookies one by one (skipping any that Chrome rejects, e.g. host-only
    mismatches).
    """
    # A plain load of the apex domain is enough to establish the
    # yahoo.com origin for add_cookie() -- much lighter than loading the
    # actual (ad-heavy) fantasy roster page just to set cookies.
    safe_get(driver, "https://www.yahoo.com/")

    added, skipped = 0, 0
    for c in cookies:
        cookie_dict = {
            "name": c.name,
            "value": c.value,
            "domain": c.domain.lstrip("."),  # selenium wants no leading dot
            "path": c.path or "/",
            "secure": bool(c.secure),
        }
        if c.expires:
            cookie_dict["expiry"] = int(c.expires)
        try:
            driver.add_cookie(cookie_dict)
            added += 1
        except Exception:
            skipped += 1

    print(f"Injected {added} Yahoo cookies into the scraping session "
          f"({skipped} skipped).")


def ensure_logged_in(driver: webdriver.Chrome, chrome_profile: str = None) -> None:
    """
    Pull Yahoo cookies from the user's real Chrome and load them into the
    Selenium-controlled browser. Verifies the result actually lands on a
    logged-in fantasysports.yahoo.com page (not bounced to login).
    """
    cookies = load_cookies_from_real_chrome(chrome_profile)
    inject_cookies(driver, cookies)

    safe_get(driver, f"{BASE_URL}/f1/{LEAGUE_ID.split('.l.')[-1]}")
    if LOGIN_HOST in driver.current_url:
        raise RuntimeError(
            "Still bounced to the Yahoo login page after injecting cookies. "
            "Your Yahoo session in your everyday Chrome may have expired -- "
            "log in there again (https://football.fantasysports.yahoo.com) "
            "and re-run this script."
        )
    print("Logged in successfully using cookies from your everyday Chrome.\n")


# --------------------------------------------------------------------------
# SCRAPING
# --------------------------------------------------------------------------

def _clean_player_name(raw_name: str) -> str:
    """
    Strip known noise Yahoo appends directly onto the player name with no
    separating space/character, e.g. "James Cook IIIVideo Forecast" or
    "Rico DowdleQ".
    """
    name = raw_name
    for suffix in NAME_NOISE_SUFFIXES:
        if name.endswith(suffix):
            name = name[: -len(suffix)]
    return name.strip()


def _parse_roster_table(driver, week: int) -> list:
    """
    Parse the "statTable0" roster table on a team's roster page (already
    loaded with stat1=P&stat2=PW) into a list of player dicts.

    Column layout is NOT fixed: on your own team's roster (where Yahoo
    gives you inline lineup-editing controls), there's an extra leading
    "edit" cell (a <select> position dropdown) that other teams' rosters
    don't have, which shifts every subsequent cell index by one. Rather
    than hardcode positions, find the player-name cell and the points
    cell by their stable CSS classes ("player" and "pts") instead.
    """
    try:
        table = driver.find_element(By.ID, "statTable0")
    except NoSuchElementException:
        return []

    players = []
    rows = table.find_elements(By.CSS_SELECTOR, "tbody tr")
    for row in rows:
        cells = row.find_elements(By.TAG_NAME, "td")
        if len(cells) < 6:
            # Section/divider rows (e.g. a bare "BN" header) have no stats.
            continue

        name_cell = next((c for c in cells if "player" in (c.get_attribute("class") or "").split()), None)
        pts_cell = next((c for c in cells if "pts" in (c.get_attribute("class") or "").split()), None)
        if name_cell is None or pts_cell is None:
            continue

        selected_position = cells[0].text.strip()
        name_block_lines = name_cell.text.splitlines()
        if not name_block_lines:
            continue

        raw_name = name_block_lines[0]
        name = _clean_player_name(raw_name)

        nfl_team, nfl_position = None, None
        if len(name_block_lines) > 1:
            team_pos = name_block_lines[1]
            if " - " in team_pos:
                nfl_team, nfl_position = [p.strip() for p in team_pos.split(" - ", 1)]

        game_info = " ".join(name_block_lines[2:]).strip() if len(name_block_lines) > 2 else ""

        pts_text = pts_cell.text.strip()
        try:
            projected_points = float(pts_text)
        except ValueError:
            projected_points = None

        players.append({
            "name": name,
            "nfl_team": nfl_team,
            "position": nfl_position,
            "selected_position": selected_position,
            "game_info": game_info,
            "projected_points": projected_points,
            "week": week,
        })

    return players


def _is_rate_limited(driver) -> bool:
    """
    Detect Yahoo's bare "Request denied" block page, returned after too
    many rapid roster-page loads in a short window. It has no <title>
    and a body consisting of just that phrase -- nothing else on the
    real site looks like this.
    """
    try:
        body_text = driver.find_element(By.TAG_NAME, "body").text.strip()
    except NoSuchElementException:
        return False
    return body_text == "Request denied"


def scrape_team_week(driver, team_id: str, week: int) -> list:
    league_short_id = LEAGUE_ID.split(".l.")[-1]
    url = f"{BASE_URL}/f1/{league_short_id}/{team_id}/team?week={week}&stat1=P&stat2=PW"

    for attempt in range(RATE_LIMIT_MAX_RETRIES + 1):
        safe_get(driver, url)

        if LOGIN_HOST in driver.current_url:
            raise RuntimeError(
                "Got bounced to the Yahoo login page mid-scrape -- the "
                "session expired. Re-run the script and log in again when "
                "prompted."
            )

        if _is_rate_limited(driver):
            if attempt == RATE_LIMIT_MAX_RETRIES:
                raise RuntimeError(
                    f"Still rate-limited by Yahoo (\"Request denied\") after "
                    f"{RATE_LIMIT_MAX_RETRIES} retries. Stop and let it cool "
                    f"down longer, then re-run -- past runs have recovered "
                    f"after roughly {RATE_LIMIT_BACKOFF_SECONDS}-90s idle."
                )
            print(f"    \u26a0 rate-limited by Yahoo, backing off "
                  f"{RATE_LIMIT_BACKOFF_SECONDS}s (attempt {attempt + 1}/{RATE_LIMIT_MAX_RETRIES})...")
            time.sleep(RATE_LIMIT_BACKOFF_SECONDS)
            continue

        break

    # With page_load_strategy="eager", get() can return before the roster
    # table has actually rendered its rows: the <table id="statTable0">
    # element itself is present in the DOM almost immediately, but its
    # <tbody> rows get populated a beat later. Waiting for mere presence
    # of the table is not enough -- it was seen to return successfully
    # with an empty tbody, causing a team to come back with 0 players.
    # Wait for an actual populated row instead.
    try:
        WebDriverWait(driver, 15).until(
            lambda d: len(d.find_elements(By.CSS_SELECTOR, "#statTable0 tbody tr td")) > 0
        )
    except TimeoutException:
        pass  # _parse_roster_table will just return [] if it's truly empty

    time.sleep(REQUEST_DELAY_SECONDS)
    return _parse_roster_table(driver, week)


def scrape_week(driver, teams: dict, week: int) -> dict:
    """Return {team_name: [player_dict, ...]} for every team, for one week."""
    week_data = {}
    for team_id, team_name in teams.items():
        try:
            players = scrape_team_week(driver, team_id, week)
        except InvalidSessionIdException:
            # Chrome itself crashed/closed -- every remaining team in this
            # run would fail with the same low-level error, so stop here
            # with one clear message instead of repeating a stack trace
            # per team. Whatever's already in week_data is still valid and
            # gets saved by the caller.
            print(f"  \u26a0 Chrome session died while scraping {team_name} "
                  f"(week {week}) -- stopping this week early. Re-run the "
                  f"script to pick up where it left off.")
            break
        except (WebDriverException, RuntimeError) as e:
            print(f"  \u26a0 failed to scrape {team_name} (week {week}): {e}")
            players = []
            week_data[team_name] = players
            print(f"  Week {week}: {team_name:<30} {len(players)} players")
            continue

        week_data[team_name] = players
        print(f"  Week {week}: {team_name:<30} {len(players)} players")

    return week_data


# --------------------------------------------------------------------------
# MAIN
# --------------------------------------------------------------------------

def parse_week_range(weeks_arg: str, current_week: int, regular_season_weeks: list) -> list:
    if weeks_arg == "all":
        return regular_season_weeks
    if weeks_arg == "remaining":
        return [w for w in regular_season_weeks if w >= current_week]
    if "-" in weeks_arg:
        start, end = weeks_arg.split("-", 1)
        return list(range(int(start), int(end) + 1))
    return [int(w) for w in weeks_arg.split(",")]


def main():
    parser = argparse.ArgumentParser(
        description="Scrape Yahoo's per-player weekly projected points for every team in the league."
    )
    parser.add_argument(
        "--weeks", default="remaining",
        help="Weeks to scrape: 'remaining' (default, current week through end of regular season), "
             "'all' (full regular season), a range like '3-6', or a comma list like '3,5,7'."
    )
    parser.add_argument("--oauth-file", default=OAUTH_FILE, help="Path to yahoo_oauth credentials json")
    parser.add_argument("--league-id", default=LEAGUE_ID, help="Yahoo league id, e.g. 470.l.205662")
    parser.add_argument("--headless", action="store_true",
                         help="Run the scraping browser headless (safe here since it never touches the login form).")
    parser.add_argument("--chrome-profile", default=None,
                         help="Path to a specific Chrome cookie DB / profile to read your Yahoo login "
                              "from, if not Chrome's default profile.")
    parser.add_argument("--skip-existing", action="store_true",
                         help="Skip weeks that already have a saved projections file, instead of "
                              "re-scraping (and overwriting) them. Useful for resuming an "
                              "interrupted multi-week backfill without re-doing finished weeks. "
                              "By default every requested week is re-scraped, since projections "
                              "change throughout the week as Yahoo updates them.")
    args = parser.parse_args()

    league = get_league(oauth_file=args.oauth_file, league_id=args.league_id)
    teams = get_teams(league)
    current_week = league.current_week()
    regular_season_weeks = get_regular_season_weeks(league)

    weeks_to_scrape = parse_week_range(args.weeks, current_week, regular_season_weeks)
    print(f"Teams: {len(teams)}. Current week: {current_week}. "
          f"Scraping weeks: {weeks_to_scrape}\n")

    os.makedirs(OUTPUT_DIR, exist_ok=True)

    driver = build_driver(headless=args.headless)
    ensure_logged_in(driver, chrome_profile=args.chrome_profile)
    teams_scraped_this_session = 0

    try:
        for i, week in enumerate(weeks_to_scrape):
            out_path = os.path.join(OUTPUT_DIR, f"week_{week}.json")
            if args.skip_existing and os.path.exists(out_path):
                print(f"=== Week {week} already has a saved file, skipping "
                      f"(--skip-existing) ===\n")
                continue

            print(f"=== Scraping week {week} ===")

            if teams_scraped_this_session + len(teams) > TEAMS_PER_BROWSER_SESSION:
                print("  -- restarting browser session to avoid rate-limit "
                      "buildup / long-session instability --")
                driver.quit()
                driver = build_driver(headless=args.headless)
                ensure_logged_in(driver, chrome_profile=args.chrome_profile)
                teams_scraped_this_session = 0

            week_data = scrape_week(driver, teams, week)
            teams_scraped_this_session += len(teams)

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
