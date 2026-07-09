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
from pathlib import Path

import numpy as np
import pandas as pd

import time
import requests
from io import StringIO


import matplotlib.pyplot as plt
import os
import argparse
import pickle


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
    2023: "423.l.902802",
    2024: "449.l.106896",
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


HEADERS_POOL = [
    {
        "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
                      "(KHTML, like Gecko) Chrome/124.0 Safari/537.36",
        "Accept-Language": "en-US,en;q=0.9",
    },
    {
        "User-Agent": "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/605.1.15 "
                      "(KHTML, like Gecko) Version/17.4 Safari/605.1.15",
        "Accept-Language": "en-US,en;q=0.9",
    },
    {
        "User-Agent": "Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 "
                      "(KHTML, like Gecko) Chrome/124.0 Safari/537.36",
        "Accept-Language": "en-US,en;q=0.9",
    },
]

CACHE_DIR = "cache/fantasypros"

MIN_ROWS = {
    "qb": 30,
    "rb": 50,
    "wr": 60,
    "te": 20,
    "k": 20,
    "dst": 28,
}


def _cache_path(pos: str, year: int, kind: str) -> str:
    os.makedirs(CACHE_DIR, exist_ok=True)
    ext = "html" if kind == "html" else "pkl"
    return os.path.join(CACHE_DIR, f"{pos}_{year}.{ext}")


def _load_cached_df(pos: str, year: int):
    path = _cache_path(pos, year, "df")
    if os.path.exists(path):
        with open(path, "rb") as f:
            return pickle.load(f)
    return None


def _save_cached_df(pos: str, year: int, df: pd.DataFrame) -> None:
    with open(_cache_path(pos, year, "df"), "wb") as f:
        pickle.dump(df, f)


def _is_complete(pos: str, df) -> bool:
    if df is None:
        return False
    return len(df) >= MIN_ROWS.get(pos, 5)


def _fetch_tables(url: str, pos: str, year: int, min_len: int = 500) -> list:
    """
    Always issues a brand-new request with its own Session (so no cookies
    carry over from a prior attempt) and a randomly chosen User-Agent from
    HEADERS_POOL. This matters because the gating we've observed (exactly
    10 rows, identical players, unchanged across quick retries) behaves
    like a per-session/per-identity gate rather than a per-request random
    limit -- reusing the same session or headers on retry just re-triggers
    the same gate. No HTML caching here anymore: a cached page is only
    ever useful if it was a *complete* page, and completeness is checked
    by the caller before deciding whether to fetch at all.
    """
    session = requests.Session()
    headers = random.choice(HEADERS_POOL)
    resp = session.get(url, headers=headers, timeout=15)
    resp.raise_for_status()
    if len(resp.text) < min_len:
        raise ValueError(
            f"Suspiciously short response ({len(resp.text)} chars) — "
            f"likely blocked/interstitial rather than the real page"
        )
    return pd.read_html(StringIO(resp.text))


def _flatten_columns(df: pd.DataFrame) -> pd.DataFrame:
    if isinstance(df.columns, pd.MultiIndex):
        df.columns = [
            " ".join(str(level) for level in col if "Unnamed" not in str(level)).strip()
            for col in df.columns
        ]
    return df


def _clean_player_name(raw_name: str) -> str:
    name = str(raw_name)
    name = re.sub(r"\(.*?\)", "", name)
    for code in sorted(NFL_TEAM_CODES, key=len, reverse=True):
        pattern = re.compile(rf"(?<=[a-z\.\']){code}$")
        if pattern.search(name):
            name = pattern.sub(f" {code}", name)
            break
    tokens = name.split()
    while tokens and tokens[-1] in NFL_TEAM_CODES:
        tokens.pop()
    while tokens and re.fullmatch(r"[A-Z]", tokens[-1]) and len(tokens) > 1:
        tokens.pop()
    return " ".join(tokens).strip()


def _normalize_name(name: str) -> str:
    name = str(name).lower().strip()
    name = name.replace(".", "").replace("'", "")
    tokens = [t for t in name.split() if t not in NAME_SUFFIXES]
    return " ".join(tokens)


def _find_projections_table(tables: list, pos: str):
    for i, t in enumerate(tables):
        t = _flatten_columns(t.copy())
        fpts_candidates = [c for c in t.columns if "FPTS" in str(c).upper()]
        if fpts_candidates and len(t) >= 5:
            return t, fpts_candidates, i
    return None, None, None


def _select_fpts_column(fpts_candidates: list):
    exact = [c for c in fpts_candidates if str(c).strip().upper() == "FPTS"]
    return exact[0] if exact else fpts_candidates[-1]


def _scrape_one_position(pos: str, year: int, debug: bool) -> pd.DataFrame:
    url = f"https://www.fantasypros.com/nfl/projections/{pos}.php?week=draft&scoring=PPR&year={year}"
    tables = _fetch_tables(url, pos, year)
    if debug:
        print(f"  [debug] {pos.upper()}: {len(tables)} table(s) found on page, "
              f"shapes={[t.shape for t in tables]}")

    df, fpts_candidates, table_idx = _find_projections_table(tables, pos)
    if df is None:
        raise ValueError(
            f"No table on the page had an FPTS column with >=5 rows "
            f"(checked {len(tables)} tables)"
        )
    fpts_col = _select_fpts_column(fpts_candidates)
    if debug:
        print(f"  [debug] {pos.upper()}: using table index {table_idx}, "
              f"fpts column '{fpts_col}' (candidates were {fpts_candidates}), "
              f"{len(df)} rows")

    player_col = df.columns[0]
    clean = pd.DataFrame({
        "player": df[player_col].apply(_clean_player_name),
        "season_projection": pd.to_numeric(df[fpts_col], errors="coerce"),
    })
    clean["season"] = year
    clean["position"] = pos.upper()

    n_before = len(clean)
    clean = clean.dropna(subset=["season_projection"])
    if debug and n_before != len(clean):
        dropped = df[player_col][pd.to_numeric(df[fpts_col], errors="coerce").isna()].tolist()
        print(f"  [debug] {pos.upper()}: dropped {n_before - len(clean)} rows with "
              f"unparsable FPTS (column used: '{fpts_col}'), dropped players={dropped}")

    if debug:
        print(f"  [debug] {pos.upper()}: {len(clean)} rows survived cleaning, "
              f"sample={clean['player'].head(5).tolist()}")

    return clean.reset_index(drop=True)


def scrape_projections(positions=POSITIONS, year=YEAR, debug: bool = True,
                        force_refresh: bool = False,
                        max_retries: int = 1, base_retry_delay: float = 20.0) -> pd.DataFrame:
    """
    Per-position cache + retry, with retries designed to actually differ
    from each other (fresh session, new User-Agent, longer/backing-off
    delay with jitter) since quick same-session retries were observed to
    return the identical truncated 10-row result every time.
    """
    all_projections = []

    for pos in positions:
        cached_df = None if force_refresh else _load_cached_df(pos, year)

        if cached_df is not None and _is_complete(pos, cached_df):
            print(f"[cache] {pos.upper()}: using cached data ({len(cached_df)} rows, meets minimum)")
            all_projections.append(cached_df)
            continue

        if cached_df is not None:
            print(f"[cache] {pos.upper()}: cached data looks truncated "
                  f"({len(cached_df)} rows, expected >= {MIN_ROWS.get(pos, 5)}) -- rescraping")

        clean = None
        for attempt in range(1, max_retries + 1):
            try:
                clean = _scrape_one_position(pos, year, debug)
            except Exception as e:
                print(f"✗ {pos.upper()} {year} attempt {attempt}/{max_retries}: {e}")
                clean = None

            if _is_complete(pos, clean):
                print(f"✓ {pos.upper()} {year}: {len(clean)} rows (attempt {attempt}/{max_retries})")
                break

            if clean is not None:
                print(f"  [warn] {pos.upper()}: attempt {attempt}/{max_retries} only returned "
                      f"{len(clean)} rows (need >= {MIN_ROWS.get(pos, 5)}) -- looks gated")

            if attempt < max_retries:
                # Exponential backoff with jitter, not a fixed short delay --
                # a flat 5s retry on the same kind of request was observed
                # to hit the identical gate every time.
                delay = base_retry_delay * (2 ** (attempt - 1)) + random.uniform(0, 5)
                print(f"  [warn] {pos.upper()}: waiting {delay:.1f}s before retry with a fresh session")
                time.sleep(delay)

        if clean is None:
            print(f"✗ {pos.upper()} {year}: no data collected after {max_retries} attempts, skipping")
            continue

        if not _is_complete(pos, clean):
            print(f"  [warn] {pos.upper()}: still only {len(clean)} rows after {max_retries} attempts "
                  f"this run -- saving partial data; this gate seems to persist for the whole run, "
                  f"so plan to re-run the script later rather than retrying more right now")
        else:
            # only sleep normally between positions when we didn't just do a long backoff
            time.sleep(1.5)

        _save_cached_df(pos, year, clean)
        all_projections.append(clean)

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


def _sim_game_winner(team_a: str, team_b: str, team_mu: dict, variance: float) -> str:
    """Play one head-to-head game between two teams, return the winning team name."""
    winner, _, _ = simulate_game(team_mu[team_a], team_mu[team_b], variance)
    return team_a if winner == 1 else team_b


def simulate_playoffs(seeds: list, team_mu: dict, variance: float) -> dict:
    """
    Simulate an 8-team single-elimination playoff bracket.
    seeds: list of teams ordered [seed1, seed2, ..., seed8]
    Bracket: 1v8, 2v7, 3v6, 4v5 -> semis -> final. No reseeding between rounds.
    """
    seed1, seed2, seed3, seed4, seed5, seed6, seed7, seed8 = seeds

    # Quarterfinals
    qf1_winner = _sim_game_winner(seed1, seed8, team_mu, variance)
    qf2_winner = _sim_game_winner(seed2, seed7, team_mu, variance)
    qf3_winner = _sim_game_winner(seed3, seed6, team_mu, variance)
    qf4_winner = _sim_game_winner(seed4, seed5, team_mu, variance)

    # Semifinals (bracket-fixed: qf1 vs qf4, qf2 vs qf3)
    sf1_winner = _sim_game_winner(qf1_winner, qf4_winner, team_mu, variance)
    sf2_winner = _sim_game_winner(qf2_winner, qf3_winner, team_mu, variance)

    # Final
    champion = _sim_game_winner(sf1_winner, sf2_winner, team_mu, variance)
    runner_up = sf2_winner if champion == sf1_winner else sf1_winner

    return {
        "quarterfinalists": seeds,
        "semifinalists": [sf1_winner, sf2_winner],
        "champion": champion,
        "runner_up": runner_up,
    }


def simulate_punishment_bracket(bottom_seeds: list, team_mu: dict, variance: float) -> dict:
    """
    Simulate the bottom-4 punishment bracket.
    bottom_seeds: list of teams ordered [seed11, seed12, seed13, seed14]
    11v14, 12v13; the two losers then play each other; the loser of THAT game
    is the one who receives the punishment.
    """
    seed11, seed12, seed13, seed14 = bottom_seeds

    winner_a = _sim_game_winner(seed11, seed14, team_mu, variance)
    loser_a = seed14 if winner_a == seed11 else seed11

    winner_b = _sim_game_winner(seed12, seed13, team_mu, variance)
    loser_b = seed13 if winner_b == seed12 else seed12

    punishment_game_winner = _sim_game_winner(loser_a, loser_b, team_mu, variance)
    punished_team = loser_b if punishment_game_winner == loser_a else loser_a

    return {
        "punishment_game_participants": [loser_a, loser_b],
        "punished_team": punished_team,
    }


def run_monte_carlo(team_mu, schedule, variance, n_sims):
    teams = list(team_mu.keys())
    n = len(teams)

    totals = defaultdict(lambda: {
        "wins": 0.0,
        "losses": 0.0,
        "points_for": 0.0,
        "points_against": 0.0
    })

    # position matrix: team -> [14]   (unchanged)
    pos_counts = {t: np.zeros(n, dtype=int) for t in teams}

    # playoff / punishment tracking (new)
    playoff_counts = {t: 0 for t in teams}       # made top-8
    semifinalist_counts = {t: 0 for t in teams}  # made final 4
    finalist_counts = {t: 0 for t in teams}      # made championship game
    champion_counts = {t: 0 for t in teams}      # won it all

    punishment_bracket_counts = {t: 0 for t in teams}  # bottom 4, in punishment bracket
    punished_counts = {t: 0 for t in teams}            # actually received the punishment

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

        # --- Playoffs: top 8 seeds ---
        ranked_teams = [team for team, _ in ranked]
        top8_seeds = ranked_teams[:8]

        for t in top8_seeds:
            playoff_counts[t] += 1

        playoff_result = simulate_playoffs(top8_seeds, team_mu, variance)
        for t in playoff_result["semifinalists"]:
            semifinalist_counts[t] += 1
        finalist_counts[playoff_result["champion"]] += 1
        finalist_counts[playoff_result["runner_up"]] += 1
        champion_counts[playoff_result["champion"]] += 1

        # --- Punishment bracket: bottom 4 seeds (11-14) ---
        bottom4_seeds = ranked_teams[10:14]  # indices 10,11,12,13 -> seeds 11-14

        for t in bottom4_seeds:
            punishment_bracket_counts[t] += 1

        punishment_result = simulate_punishment_bracket(bottom4_seeds, team_mu, variance)
        punished_counts[punishment_result["punished_team"]] += 1

    rows = []
    for t in teams:
        rows.append({
            "team": t,
            "avg_wins": totals[t]["wins"] / n_sims,
            "avg_losses": totals[t]["losses"] / n_sims,
            "avg_points_for": totals[t]["points_for"] / n_sims,
            "avg_points_against": totals[t]["points_against"] / n_sims,
            "playoff_pct": playoff_counts[t] / n_sims * 100,
            "semifinalist_pct": semifinalist_counts[t] / n_sims * 100,
            "finalist_pct": finalist_counts[t] / n_sims * 100,
            "champion_pct": champion_counts[t] / n_sims * 100,
            "punishment_bracket_pct": punishment_bracket_counts[t] / n_sims * 100,
            "punished_pct": punished_counts[t] / n_sims * 100,
        })

    standings = pd.DataFrame(rows)
    standings = standings.sort_values("avg_wins", ascending=False).reset_index(drop=True)

    return standings, pos_counts
#-------
# Plot results
#-------
def plot_season_summary_table(standings, out_file="season_summary.jpg"):
    """
    Render the full standings table (record, points, playoff/punishment odds)
    as a color-coded table image.

    Parameters
    ----------
    standings : pd.DataFrame
        Must contain: team, avg_wins, avg_losses, avg_points_for,
        avg_points_against, playoff_pct, semifinalist_pct, finalist_pct,
        champion_pct, punishment_bracket_pct, punished_pct.
    out_file : str
        Path to save the resulting JPEG.
    """
    df = standings.sort_values("avg_wins", ascending=False).reset_index(drop=True)

    # Columns to display, in order, with header labels
    display_cols = [
        ("team", "Team"),
        ("record", "Record"),
        ("points", "PF - PA"),
        ("playoff_pct", "Playoff %"),
        ("semifinalist_pct", "Semifinal %"),
        ("finalist_pct", "Finalist %"),
        ("champion_pct", "Champion %"),
        ("punishment_bracket_pct", "Punish. Bracket %"),
        ("punished_pct", "Punished %"),
    ]

    n_rows = len(df)
    n_cols = len(display_cols)

    # Percentage columns get their own color scale; text-only columns stay plain
    pct_cols = [
        "playoff_pct", "semifinalist_pct", "finalist_pct",
        "champion_pct", "punishment_bracket_pct", "punished_pct"
    ]

    fig, ax = plt.subplots(figsize=(1.6 * n_cols, 0.5 * n_rows + 1.5))
    ax.set_xlim(0, n_cols)
    ax.set_ylim(0, n_rows + 1)
    ax.invert_yaxis()
    ax.axis("off")

    cmap = plt.get_cmap("YlOrRd")

    # Header row
    for j, (_, label) in enumerate(display_cols):
        ax.add_patch(plt.Rectangle((j, 0), 1, 1, facecolor="#333333", edgecolor="white"))
        ax.text(j + 0.5, 0.5, label, ha="center", va="center",
                 fontsize=9, fontweight="bold", color="white")

    # Precompute min/max per pct column for independent normalization
    col_ranges = {c: (df[c].min(), df[c].max()) for c in pct_cols}

    for i, row in enumerate(df.itertuples(index=False)):
        row_dict = row._asdict()
        y = i + 1

        for j, (key, _) in enumerate(display_cols):
            if key == "team":
                text = str(row_dict["team"])
                facecolor = "#f5f5f5" if i % 2 == 0 else "#e8e8e8"
                textcolor = "black"
                ha = "left"
            elif key == "record":
                text = f"{row_dict['avg_wins']:.1f}-{row_dict['avg_losses']:.1f}"
                facecolor = "#f5f5f5" if i % 2 == 0 else "#e8e8e8"
                textcolor = "black"
                ha = "center"
            elif key == "points":
                text = f"{row_dict['avg_points_for']:.1f}-{row_dict['avg_points_against']:.1f}"
                facecolor = "#f5f5f5" if i % 2 == 0 else "#e8e8e8"
                textcolor = "black"
                ha = "center"
            else:
                val = row_dict[key]
                lo, hi = col_ranges[key]
                norm = 0.0 if hi == lo else (val - lo) / (hi - lo)
                facecolor = cmap(0.15 + 0.75 * norm)  # avoid near-white/near-black extremes
                textcolor = "white" if norm > 0.55 else "black"
                text = f"{val:.1f}%"
                ha = "center"

            ax.add_patch(plt.Rectangle((j, y), 1, 1, facecolor=facecolor, edgecolor="white"))
            tx = j + (0.08 if ha == "left" else 0.5)
            ax.text(tx, y + 0.5, text, ha=ha, va="center", fontsize=8.5, color=textcolor)

    ax.set_title("Season Simulation Summary (Monte Carlo)", fontsize=13, fontweight="bold", pad=15)

    plt.tight_layout()
    plt.savefig(out_file, dpi=250, bbox_inches="tight")
    plt.close()
    
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
            ax.text(j, i, f"{val:.1f}%", ha="center", va="center", fontsize=7, color="white")

    cbar = plt.colorbar(im, ax=ax)
    cbar.set_label("Finish Probability (%)")

    ax.set_xlabel("Finishing Position")
    ax.set_ylabel("Teams")
    ax.set_title("Season Outcome Distribution (Monte Carlo)")

    plt.tight_layout()
    plt.savefig(out_file, dpi=250, bbox_inches="tight")
    plt.close()


def top_bottom_probabilities(standings, pos_counts, n_sims, top_x=4, bottom_y=4):
    """
    Compute probability of finishing in the top X seeds or bottom Y seeds
    for each team, based on Monte Carlo simulation results.
    ...
    """
    teams = standings["team"].tolist()
    n = len(teams)

    if top_x > n or bottom_y > n:
        raise ValueError(f"top_x/bottom_y can't exceed number of teams ({n})")

    playoff_col = "Chance to make Playoffs"
    punishment_col = "Chance to be in punishment contention"

    rows = []
    for team in teams:
        counts = pos_counts[team]
        top_pct = counts[:top_x].sum() / n_sims * 100
        bottom_pct = counts[n - bottom_y:].sum() / n_sims * 100
        rows.append({
            "team": team,
            playoff_col: top_pct,
            punishment_col: bottom_pct,
        })

    result = pd.DataFrame(rows).sort_values(
        playoff_col, ascending=False
    ).reset_index(drop=True)

    return result

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

    # Output directory for generated plots -- lives in the website repo so the
    # frontend can pick them up directly without a manual copy step.
    output_dir = Path(__file__).parent / ".." / "Website" / "girderma-gridiron-website" / "src" / "simulate_season"
    output_dir = output_dir.resolve()
    output_dir.mkdir(parents=True, exist_ok=True)

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
    plot_league_heatmap(standings, pos_counts, args.simulations,
                         out_file=str(output_dir / "league_heatmap.jpg"))

    pd.set_option("display.float_format", lambda x: f"{x:.2f}")
    print("=== Simulated Standings (averaged across all trials) ===")
    print(standings.to_string())

    standings.to_csv("simulated_standings.csv")
    print("\nSaved full standings to simulated_standings.csv")

    plot_season_summary_table(standings, out_file=str(output_dir / "season_summary.jpg"))

    probs = top_bottom_probabilities(standings, pos_counts, N_SIMULATIONS, top_x=8, bottom_y=4)
    print(probs)




if __name__ == "__main__":
    main()