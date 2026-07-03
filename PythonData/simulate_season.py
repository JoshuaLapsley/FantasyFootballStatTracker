"""
Fantasy Football Season Simulator
==================================

Pipeline:
1. Scrape FantasyPros preseason projections (PPR) for every position.
2. Convert each player's season projection into a per-game projection
   (season total / 14 weeks).
3. Pull all 14 rosters directly from Yahoo via OAuth (yahoo_oauth +
   yahoo_fantasy_api), splitting each roster into starters vs. bench
   based on `selected_position` for a given week.
4. Compute each team's projected points-per-game (mu) as the sum of its
   starters' per-game projections.
5. Build a schedule:
     - Round robin: every team plays every other team once (13 games).
     - Rivalry week: every team plays its hardcoded rival a second time
       (1 game) -> 14 total games per team, matching a 14-week season.
6. Monte Carlo simulate the season many times using:
       score ~ Normal(mu, sigma),  variance = 33**2
   and tally wins/losses/points to produce simulated standings.

Requirements: pip install yahoo_oauth yahoo_fantasy_api pandas numpy lxml
You'll also need a valid oauth2.json (Yahoo app key/secret + tokens) in
the working directory, or pass --oauth-file to point elsewhere.

Adjust the CONFIG section -- especially the RIVALS dict -- to match your
league's actual team names before running.
"""

import re
import json
import random
import argparse
from collections import defaultdict
from difflib import get_close_matches

import numpy as np
import pandas as pd

from yahoo_oauth import OAuth2
import yahoo_fantasy_api as yfa

# --------------------------------------------------------------------------
# CONFIG
# --------------------------------------------------------------------------

YEAR = 2025  # testing against the completed 2025 season; flip to 2026 once it exists
WEEKS = 14
VARIANCE = 33 ** 2
N_SIMULATIONS = 10_000

POSITIONS = ["qb", "rb", "wr", "te", "k", "dst"]

# Yahoo league IDs by season (format: "{game_id}.l.{league_id}")
LEAGUE_IDS = {
    2025: "461.l.111150",
    2026: None,  # fill in once the 2026 league is created
}

OAUTH_FILE = "oauth2.json"      # yahoo_oauth credentials file
ROSTER_WEEK = 1                 # which week's roster to pull (post-draft lineup)

# Hardcoded rivalry pairs -- every team plays its rival a 2nd time.
# Must be symmetric (if A's rival is B, B's rival must be A) and every
# team must appear exactly once as a key. Edit this to match your league.
RIVALS = {
    "Ma\u00eetre Magic": "Tsuga\u2019s Tuck Shop",
    "Tsuga\u2019s Tuck Shop": "Ma\u00eetre Magic",
    "Deej-lanta Falcons": "Girder\u2019s Grippers",
    "Girder\u2019s Grippers": "Deej-lanta Falcons",
    "Go With The Flow": "Hunter\u2019s Hunters",
    "Hunter\u2019s Hunters": "Go With The Flow",
    "No Punts Intented": "Revy\u2019s Konstruction",
    "Revy\u2019s Konstruction": "No Punts Intented",
    "Omaha Beach Real Estate": "Pad D's",
    "Pad D's": "Omaha Beach Real Estate",
    "Ozzy Stick": "Hungry Hungry Hokk",
    "Hungry Hungry Hokk": "Ozzy Stick",
    "Supernova\u2019s Studs": "The Sage's Playmakers",
    "The Sage's Playmakers": "Supernova\u2019s Studs",
}

RANDOM_SEED = None  # set an int for reproducible runs


# --------------------------------------------------------------------------
# STEP 1: SCRAPE PROJECTIONS
# --------------------------------------------------------------------------

def _flatten_columns(df: pd.DataFrame) -> pd.DataFrame:
    """FantasyPros tables sometimes have MultiIndex columns; flatten them."""
    if isinstance(df.columns, pd.MultiIndex):
        df.columns = [
            " ".join(str(level) for level in col if "Unnamed" not in str(level)).strip()
            for col in df.columns
        ]
    return df


def _clean_player_name(raw_name: str) -> str:
    """
    FantasyPros player cells look like 'Christian McCaffrey SF' or
    'Christian McCaffrey SF Q'. Strip trailing team/injury codes.
    """
    name = str(raw_name)
    # Drop anything in parentheses, e.g. "(Out)"
    name = re.sub(r"\(.*?\)", "", name)
    # Drop trailing 1-3 letter uppercase tokens (team abbreviation / status)
    tokens = name.split()
    while tokens and re.fullmatch(r"[A-Z]{1,3}", tokens[-1]):
        tokens.pop()
    return " ".join(tokens).strip()


def scrape_projections(positions=POSITIONS, year=YEAR) -> pd.DataFrame:
    """
    Scrape FantasyPros draft projections for each position and return a
    DataFrame with columns: player, position, season, season_projection,
    per_game_projection.
    """
    all_projections = []

    for pos in positions:
        url = f"https://www.fantasypros.com/nfl/projections/{pos}.php?week=draft&scoring=PPR&year={year}"
        try:
            tables = pd.read_html(url)
            df = _flatten_columns(tables[0])

            # Identify the player-name column (first column) and the FPTS column
            player_col = df.columns[0]
            fpts_candidates = [c for c in df.columns if "FPTS" in str(c).upper()]
            if not fpts_candidates:
                raise ValueError("Could not find an FPTS column")
            fpts_col = fpts_candidates[-1]  # last FPTS-like column is the total

            clean = pd.DataFrame({
                "player": df[player_col].apply(_clean_player_name),
                "season_projection": pd.to_numeric(df[fpts_col], errors="coerce"),
            })
            clean["season"] = year
            clean["position"] = pos.upper()
            clean = clean.dropna(subset=["season_projection"])

            all_projections.append(clean)
            print(f"✓ {pos.upper()} {year}")
        except Exception as e:
            print(f"✗ {pos.upper()} {year}: {e}")

    projections = pd.concat(all_projections, ignore_index=True)
    projections["per_game_projection"] = projections["season_projection"] / WEEKS
    return projections


# --------------------------------------------------------------------------
# STEP 2: LOAD ROSTERS + RIVALS
# --------------------------------------------------------------------------

def get_yahoo_league(year: int = YEAR, oauth_file: str = OAUTH_FILE):
    """
    Authenticate with Yahoo and return (sc, league) where `sc` is the
    OAuth2 session (needed to construct yfa.Team objects) and `league`
    is the yfa.League object for the configured league id.
    """
    league_id = LEAGUE_IDS.get(year)
    if not league_id:
        raise ValueError(
            f"No Yahoo league id configured for {year}. "
            f"Add it to LEAGUE_IDS at the top of this script."
        )

    sc = OAuth2(None, None, from_file=oauth_file)
    gm = yfa.Game(sc, "nfl")
    league = gm.to_league(league_id)
    return sc, league


def load_rosters_from_yahoo(year: int = YEAR, week: int = ROSTER_WEEK,
                             oauth_file: str = OAUTH_FILE) -> dict:
    """
    Pull every team's roster directly from Yahoo via OAuth.

    Starters vs. bench is determined by each player's `selected_position`
    for the given week: bench/IR slots are excluded from mu, everything
    else (QB, RB, WR, TE, W/R/T, K, DEF, etc.) counts as a starter.
    """
    sc, league = get_yahoo_league(year, oauth_file)
    teams_info = league.teams()  # dict: team_key -> team info dict

    rosters = {}
    for team_key, info in teams_info.items():
        team_name = info["name"]
        team = yfa.Team(sc, team_key)

        try:
            roster = team.roster(week=week)
        except Exception as e:
            print(f"  ⚠ could not fetch roster for {team_name} (week {week}): {e}")
            continue

        starters, bench = [], []
        for player in roster:
            name = player.get("name", "").strip()
            selected_pos = player.get("selected_position")
            if selected_pos in ("BN", "IR", "IR+", "NA"):
                bench.append(name)
            else:
                starters.append(name)

        rosters[team_name] = {"starters": starters, "bench": bench}
        print(f"  Loaded {team_name}: {len(starters)} starters, {len(bench)} bench")

    return rosters


# --------------------------------------------------------------------------
# STEP 3: MATCH ROSTER PLAYERS TO PROJECTIONS + COMPUTE TEAM MU
# --------------------------------------------------------------------------

def build_projection_lookup(projections: pd.DataFrame) -> dict:
    """player name -> per_game_projection, keyed by a normalized name."""
    lookup = {}
    for _, row in projections.iterrows():
        key = row["player"].lower().strip()
        lookup[key] = row["per_game_projection"]
    return lookup


def _match_player(name: str, lookup: dict) -> float:
    key = name.lower().strip()
    if key in lookup:
        return lookup[key]

    # Fuzzy fallback for spelling/format mismatches (e.g. "D.J. Moore" vs "DJ Moore")
    close = get_close_matches(key, lookup.keys(), n=1, cutoff=0.85)
    if close:
        return lookup[close[0]]

    print(f"  ⚠ no projection found for '{name}', treating as 0 pts/game")
    return 0.0


def compute_team_mu(rosters: dict, projections: pd.DataFrame) -> dict:
    """Sum starters' per-game projections to get each team's projected mu."""
    lookup = build_projection_lookup(projections)
    team_mu = {}
    for team, roster in rosters.items():
        total = sum(_match_player(p, lookup) for p in roster["starters"])
        team_mu[team] = total
    return team_mu


# --------------------------------------------------------------------------
# STEP 4: SIMULATION LOGIC
# --------------------------------------------------------------------------

def simulate_game(mu1, mu2, variance):
    """
    Simulate a single game between Team1 and Team2.

    Returns:
        winner: 1 if Team1 wins, 2 if Team2 wins
        points1: points scored by Team1
        points2: points scored by Team2
    """
    sigma = np.sqrt(variance)

    score1 = np.random.normal(mu1, sigma)
    score2 = np.random.normal(mu2, sigma)

    winner = 1 if score1 > score2 else 2

    return winner, score1, score2


def build_schedule(teams: list, rivals: dict) -> list:
    """
    Build the season schedule as a list of (team1, team2) tuples:
      - Round robin: every unique pair plays once (13 games/team for 14 teams).
      - Rivalry week: every team plays its hardcoded rival a second time.
    """
    schedule = []

    # Round robin - every unique pair once
    for i in range(len(teams)):
        for j in range(i + 1, len(teams)):
            schedule.append((teams[i], teams[j]))

    # Rivalry week - add the second matchup, avoiding duplicate entries
    seen_rival_pairs = set()
    for team, rival in rivals.items():
        pair = tuple(sorted((team, rival)))
        if pair in seen_rival_pairs:
            continue
        seen_rival_pairs.add(pair)
        schedule.append((pair[0], pair[1]))

    return schedule


# --------------------------------------------------------------------------
# STEP 5: RUN MONTE CARLO SIMULATIONS AND BUILD STANDINGS
# --------------------------------------------------------------------------

def simulate_season_once(team_mu: dict, schedule: list, variance: float) -> dict:
    """Simulate one full season and return per-team record for this trial."""
    record = {team: {"wins": 0, "losses": 0, "points_for": 0.0, "points_against": 0.0}
              for team in team_mu}

    for team1, team2 in schedule:
        winner, s1, s2 = simulate_game(team_mu[team1], team_mu[team2], variance)

        record[team1]["points_for"] += s1
        record[team1]["points_against"] += s2
        record[team2]["points_for"] += s2
        record[team2]["points_against"] += s1

        if winner == 1:
            record[team1]["wins"] += 1
            record[team2]["losses"] += 1
        else:
            record[team2]["wins"] += 1
            record[team1]["losses"] += 1

    return record


def run_monte_carlo(team_mu: dict, schedule: list, variance: float,
                     n_simulations: int) -> pd.DataFrame:
    """
    Run many simulated seasons and average results to get expected
    standings (expected wins/losses/points, plus championship-odds proxy:
    fraction of simulations each team finished #1 by wins).
    """
    totals = defaultdict(lambda: {"wins": 0.0, "losses": 0.0,
                                   "points_for": 0.0, "points_against": 0.0,
                                   "first_place_finishes": 0})

    for _ in range(n_simulations):
        record = simulate_season_once(team_mu, schedule, variance)

        # Track who finished with the most wins this trial (ties split credit)
        max_wins = max(r["wins"] for r in record.values())
        leaders = [t for t, r in record.items() if r["wins"] == max_wins]
        credit = 1.0 / len(leaders)

        for team, r in record.items():
            totals[team]["wins"] += r["wins"]
            totals[team]["losses"] += r["losses"]
            totals[team]["points_for"] += r["points_for"]
            totals[team]["points_against"] += r["points_against"]
            if team in leaders:
                totals[team]["first_place_finishes"] += credit

    rows = []
    for team, t in totals.items():
        rows.append({
            "team": team,
            "avg_wins": t["wins"] / n_simulations,
            "avg_losses": t["losses"] / n_simulations,
            "avg_points_for": t["points_for"] / n_simulations,
            "avg_points_against": t["points_against"] / n_simulations,
            "first_place_pct": 100 * t["first_place_finishes"] / n_simulations,
        })

    standings = pd.DataFrame(rows).sort_values(
        by=["avg_wins", "avg_points_for"], ascending=False
    ).reset_index(drop=True)
    standings.index += 1  # 1-indexed rank
    return standings


# --------------------------------------------------------------------------
# MAIN
# --------------------------------------------------------------------------

def main():
    parser = argparse.ArgumentParser(description="Simulate a fantasy football season.")
    parser.add_argument("--year", type=int, default=YEAR,
                         help="Season year (must have an entry in LEAGUE_IDS)")
    parser.add_argument("--week", type=int, default=ROSTER_WEEK,
                         help="Yahoo roster week to pull starters/bench from")
    parser.add_argument("--oauth-file", default=OAUTH_FILE,
                         help="Path to yahoo_oauth credentials json")
    parser.add_argument("--simulations", type=int, default=N_SIMULATIONS,
                         help="Number of Monte Carlo season simulations to run")
    parser.add_argument("--seed", type=int, default=RANDOM_SEED, help="Random seed")
    args = parser.parse_args()

    if args.seed is not None:
        np.random.seed(args.seed)
        random.seed(args.seed)

    print("Step 1/4: Scraping FantasyPros projections...")
    projections = scrape_projections(year=args.year)
    print(f"  Retrieved {len(projections)} player projections.\n")

    print(f"Step 2/4: Loading rosters from Yahoo ({args.year}, week {args.week})...")
    rosters = load_rosters_from_yahoo(year=args.year, week=args.week, oauth_file=args.oauth_file)
    print(f"  Loaded {len(rosters)} team rosters.\n")

    # Sanity-check that RIVALS covers exactly the teams we just loaded
    missing = set(rosters) - set(RIVALS)
    extra = set(RIVALS) - set(rosters)
    if missing:
        print(f"  ⚠ RIVALS is missing entries for: {sorted(missing)}")
    if extra:
        print(f"  ⚠ RIVALS has entries for teams not in this league: {sorted(extra)}")

    print("Step 3/4: Computing team projected points-per-game (mu)...")
    team_mu = compute_team_mu(rosters, projections)
    for team, mu in sorted(team_mu.items(), key=lambda x: -x[1]):
        print(f"  {team:<25} {mu:6.2f} pts/game")
    print()

    schedule = build_schedule(list(rosters.keys()), RIVALS)
    print(f"Step 4/4: Running {args.simulations:,} Monte Carlo season simulations "
          f"({len(schedule)} games/season)...\n")

    standings = run_monte_carlo(team_mu, schedule, VARIANCE, args.simulations)

    pd.set_option("display.float_format", lambda x: f"{x:.2f}")
    print("=== Simulated Standings (averaged across all trials) ===")
    print(standings.to_string())

    standings.to_csv("simulated_standings.csv")
    print("\nSaved full standings to simulated_standings.csv")


if __name__ == "__main__":
    main()