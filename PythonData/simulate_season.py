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


import matplotlib.pyplot as plt
import os
import argparse

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

# NFL team abbreviations FantasyPros glues onto player names, e.g.
# "Justin HerbertLAC". Used to reliably split name from code even when
# there's no space between them.
NFL_TEAM_CODES = {
    "ARI", "ATL", "BAL", "BUF", "CAR", "CHI", "CIN", "CLE", "DAL", "DEN",
    "DET", "GB", "HOU", "IND", "JAC", "JAX", "KC", "LAC", "LAR", "LV",
    "MIA", "MIN", "NE", "NO", "NYG", "NYJ", "PHI", "PIT", "SEA", "SF",
    "TB", "TEN", "WAS", "FA",
}

# Common suffixes that show up inconsistently between Yahoo and
# FantasyPros (present on one side, absent on the other).
NAME_SUFFIXES = {"jr", "sr", "ii", "iii", "iv", "v"}


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
    'Christian McCaffrey SF Q', and sometimes the team code is glued
    directly onto the name with no space at all, e.g. 'Justin HerbertLAC'
    or 'WashingtonWAS' (DST rows). Strip trailing team/injury codes
    regardless of whether they're space-separated or glued on.
    """
    name = str(raw_name)
    # Drop anything in parentheses, e.g. "(Out)"
    name = re.sub(r"\(.*?\)", "", name)

    # If a known team code is glued onto the end with no preceding space,
    # insert a space so the token-based stripping below can find it.
    # e.g. "Justin HerbertLAC" -> "Justin Herbert LAC"
    for code in sorted(NFL_TEAM_CODES, key=len, reverse=True):
        pattern = re.compile(rf"(?<=[a-z\.\']){code}$")
        if pattern.search(name):
            name = pattern.sub(f" {code}", name)
            break

    # Drop trailing 1-3 letter uppercase tokens (team abbreviation / status)
    tokens = name.split()
    while tokens and re.fullmatch(r"[A-Z]{1,3}", tokens[-1]):
        tokens.pop()
    return " ".join(tokens).strip()


def _normalize_name(name: str) -> str:
    """
    Normalize a player/team name for matching purposes only (not for
    display). Lowercases, strips punctuation, and drops suffixes like
    'Jr.'/'Sr.'/'III' that are inconsistently present between Yahoo and
    FantasyPros, so e.g. 'Aaron Jones Sr.' and 'Aaron Jones' match.
    """
    name = str(name).lower().strip()
    name = name.replace(".", "").replace("'", "")
    tokens = [t for t in name.split() if t not in NAME_SUFFIXES]
    return " ".join(tokens)


def _find_projections_table(tables: list, pos: str):
    """
    pd.read_html() often returns several tables per page (ad widgets,
    "trending" boxes, etc.) -- the real projections table isn't
    guaranteed to be tables[0], especially on the K and DST pages which
    are laid out differently than QB/RB/WR/TE. Scan all returned tables
    and pick the first one that actually looks like a projections table:
    has an FPTS-like column and a reasonable number of rows.
    """
    for i, t in enumerate(tables):
        t = _flatten_columns(t.copy())
        fpts_candidates = [c for c in t.columns if "FPTS" in str(c).upper()]
        if fpts_candidates and len(t) >= 5:
            return t, fpts_candidates[-1], i
    return None, None, None


def scrape_projections(positions=POSITIONS, year=YEAR, debug: bool = True) -> pd.DataFrame:
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
            if debug:
                print(f"  [debug] {pos.upper()}: {len(tables)} table(s) found on page, "
                      f"shapes={[t.shape for t in tables]}")

            df, fpts_col, table_idx = _find_projections_table(tables, pos)
            if df is None:
                raise ValueError(
                    f"No table on the page had an FPTS column with >=5 rows "
                    f"(checked {len(tables)} tables)"
                )
            if debug:
                print(f"  [debug] {pos.upper()}: using table index {table_idx}, "
                      f"fpts column '{fpts_col}', {len(df)} rows")

            player_col = df.columns[0]

            clean = pd.DataFrame({
                "player": df[player_col].apply(_clean_player_name),
                "season_projection": pd.to_numeric(df[fpts_col], errors="coerce"),
            })
            clean["season"] = year
            clean["position"] = pos.upper()
            clean = clean.dropna(subset=["season_projection"])

            if debug:
                print(f"  [debug] {pos.upper()}: {len(clean)} rows survived cleaning, "
                      f"sample={clean['player'].head(5).tolist()}")

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
        print(f"    Starters: {starters}")
        print(f"    Bench:    {bench}")

    return rosters


# --------------------------------------------------------------------------
# STEP 3: MATCH ROSTER PLAYERS TO PROJECTIONS + COMPUTE TEAM MU
# --------------------------------------------------------------------------

def build_projection_lookup(projections: pd.DataFrame, debug: bool = True) -> dict:
    """
    normalized name -> per_game_projection.

    DST rows get an extra fallback entry keyed by just the nickname
    (last word of the team name), since Yahoo reports DSTs by nickname
    only (e.g. "Commanders") while FantasyPros lists the full team name
    (e.g. "Washington Commanders").
    """
    lookup = {}
    for _, row in projections.iterrows():
        norm = _normalize_name(row["player"])
        lookup[norm] = row["per_game_projection"]

        if row["position"] == "DST" and norm:
            nickname = norm.split()[-1]
            lookup.setdefault(nickname, row["per_game_projection"])

    if debug:
        # Row counts per position -- if a whole position group is thin or
        # missing here, that's a scrape/parsing problem for that position's
        # page, not a name-matching problem, and no amount of fuzzy
        # matching downstream will fix it.
        counts = projections["position"].value_counts().to_dict()
        print(f"  [debug] projection rows by position: {counts}")
        for pos in POSITIONS:
            sample = projections.loc[projections["position"] == pos.upper(), "player"].head(5).tolist()
            print(f"  [debug] {pos.upper()} sample names: {sample}")

    return lookup


def _match_player(name: str, lookup: dict, debug: bool = True) -> float:
    key = _normalize_name(name)
    if key in lookup:
        return lookup[key]

    # DST fallback: Yahoo may hand us just the nickname directly.
    if key.split() and key.split()[-1] in lookup:
        return lookup[key.split()[-1]]

    # Fuzzy fallback for spelling/format mismatches (e.g. "D.J. Moore" vs "DJ Moore")
    close = get_close_matches(key, lookup.keys(), n=1, cutoff=0.85)
    if close:
        return lookup[close[0]]

    print(f"  ⚠ no projection found for '{name}', treating as 0 pts/game")
    if debug:
        # Show the nearest keys we *do* have, even well below the match
        # cutoff, so we can see what the scraper actually produced for
        # this player (or confirm it produced nothing at all).
        nearby = get_close_matches(key, lookup.keys(), n=3, cutoff=0.4)
        if nearby:
            print(f"    [debug] closest available keys: {nearby}")
        else:
            print(f"    [debug] no keys in lookup resemble '{key}' at all "
                  f"(lookup has {len(lookup)} total entries)")

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


def run_monte_carlo(team_mu, schedule, variance, n_sims):
    teams = list(team_mu.keys())
    n = len(teams)

    totals = defaultdict(lambda: {
        "wins": 0.0,
        "losses": 0.0,
        "points_for": 0.0,
        "points_against": 0.0
    })

    # position matrix: team -> [14]
    pos_counts = {t: np.zeros(n, dtype=int) for t in teams}

    for _ in range(n_sims):
        rec = simulate_season_once(team_mu, schedule, variance)

        ranked = sorted(
            rec.items(),
            key=lambda x: (x[1]["wins"], x[1]["points_for"]),
            reverse=True
        )

        for pos, (team, _) in enumerate(ranked):
            pos_counts[team][pos] += 1

        for t, r in rec.items():
            totals[t]["wins"] += r["wins"]
            totals[t]["losses"] += r["losses"]
            totals[t]["points_for"] += r["points_for"]
            totals[t]["points_against"] += r["points_against"]

    rows = []
    for t in teams:
        rows.append({
            "team": t,
            "avg_wins": totals[t]["wins"] / n_sims,
            "avg_losses": totals[t]["losses"] / n_sims,
            "avg_points_for": totals[t]["points_for"] / n_sims,
            "avg_points_against": totals[t]["points_against"] / n_sims
        })

    standings = pd.DataFrame(rows)
    standings = standings.sort_values("avg_wins", ascending=False).reset_index(drop=True)

    return standings, pos_counts

#-------
# Plot results
#-------
def plot_league_heatmap(standings, pos_counts, n_sims, out_file="league_heatmap.jpg"):
    teams = standings["team"].tolist()
    n = len(teams)

    data = np.zeros((n, n))

    for i, team in enumerate(teams):
        data[i] = pos_counts[team] / n_sims * 100

    fig, ax = plt.subplots(figsize=(14, 10))

    im = ax.imshow(data)

    # axis labels
    ax.set_xticks(range(n))
    ax.set_yticks(range(n))

    ax.set_xticklabels([str(i+1) for i in range(n)])
    ax.set_yticklabels(
        [
            f"{row.team} | {row.avg_wins:.1f}-{row.avg_losses:.1f} | "
            f"{row.avg_points_for:.1f}-{row.avg_points_against:.1f}"
            for row in standings.itertuples()
        ]
    )

    plt.setp(ax.get_xticklabels(), rotation=0, ha="center")

    # write percentages in cells
    for i in range(n):
        for j in range(n):
            val = data[i, j]
            ax.text(j, i, f"{val:.1f}%", ha="center", va="center", fontsize=7)

    cbar = plt.colorbar(im, ax=ax)
    cbar.set_label("Finish Probability (%)")

    ax.set_xlabel("Finishing Position")
    ax.set_ylabel("Teams")
    ax.set_title("Season Outcome Distribution (Monte Carlo)")

    plt.tight_layout()
    plt.savefig(out_file, dpi=250, bbox_inches="tight")
    plt.close()

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

    standings, pos_counts = run_monte_carlo(team_mu, schedule, VARIANCE, args.simulations)
    plot_league_heatmap(standings, pos_counts, args.simulations)

    pd.set_option("display.float_format", lambda x: f"{x:.2f}")
    print("=== Simulated Standings (averaged across all trials) ===")
    print(standings.to_string())

    standings.to_csv("simulated_standings.csv")
    print("\nSaved full standings to simulated_standings.csv")


if __name__ == "__main__":
    main()
