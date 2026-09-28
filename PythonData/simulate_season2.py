'''
I want this code to simulate the rest of the ff season.
1. Build the schedule (each team plays every other plus rivals)
2. Track the odds of someone 2-0ing or getting 2-0ed by their rival
3. Build the postseason (top 6 and bottom 6 and middle 2)
1. Pull all the projected points for each week for all rostered players
2. For each matchup calculate the starters according to highest projected points
3. If there is a player missing, fill with replacement points (highest projected 
points available on the waiver)
4. Now for every team-week we have a projected points. Use monte-carlo simulation
and assume that points are normally distributed with variance 33^2 pts (can change this maybe
by looking at past seasons)
'''

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

YEAR = 2026
WEEKS = 14
VARIANCE = 33 ** 2 #can change this maybe.
N_SIMULATIONS = 10_000

POSITIONS = ["qb", "rb", "wr", "te", "k", "dst"]

LEAGUE_ID = {"485.l.205662"} #the first 3 numbers of this are placeholder, everything else is right

OAUTH_FILE = "oauth2.json"      # yahoo_oauth credentials file
ROSTER_WEEK = 1                 # which week's roster to pull (update every week)

# Hardcoded rivalry pairs -- every team plays its rival a 2nd time.
# Must be symmetric (if A's rival is B, B's rival must be A) and every
# team must appear exactly once as a key.
RIVALS = {
    "Ma\u00eetre Stick": "Pad D's",
    "Pad D's" : "Ma\u00eetre Stick",
    "You gotta be Falcon Kiddin me": "Girder\u2019s 6 Cookies",
    "Girder\u2019s 6 Cookies": "You gotta be Falcon Kiddin me",
    "No Punts Intented": "Hunter\u2019s Hunters",
    "Hunter\u2019s Hunters": "No Punts Intented",
    "Supernova\u2019s Studs": "Revy\u2019s Konstruction",
    "Revy\u2019s Konstruction": "Supernova\u2019s Studs",
    "Omaha Beach Real Estate": "Tsuga\u2019s Tuck Shop" ,
    "Tsuga\u2019s Tuck Shop" : "Omaha Beach Real Estate",
    "Ozzy Stick": "Flow Brrr",
    "Flow Brrr": "Ozzy Stick",
    "Big Bad Hokkkk": "The Sage's Playmakers",
    "The Sage's Playmakers": "Big Bad Hokkkk",
}

REPLACEMENT_POINTS = {
    QB: 15,
    RB: 4,
    WR: 5.5,
    TE: 7,
    K: 7.5,
    DST: 6.5
}

RANDOM_SEED = None  #for reproducible runs


# --------------------------------------------------------------------------
# STEP 1: LOAD ROSTERS + RIVALS
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

        rosters[team_name] = {"starters": starters, "bench": bench}
        print(f"  Loaded {team_name}:")
        print(f"    Roster: {roster}")
    return rosters



# --------------------------------------------------------------------------
# STEP 2: LOAD Projections + Bye weeks
# --------------------------------------------------------------------------
#code to pull bye weeks + projected points for each week for all rostered players:


# --------------------------------------------------------------------------
# STEP 3: Compute team mu
# --------------------------------------------------------------------------

def compute_weekly_team_points(rosters: dict, projections: pd.DataFrame, current_week: int) -> dict:
    '''based off projections find who should start and then sum projections
    to get team mu for a given week.
    I want a nested dict: for week and then team'''
    week = {}
    team_mu = {}
    for team, roster in rosters.items():
    #first disqualify all players whose bye week = current_week
    #then for each position (QB, WRx2, RBx2, TE, WR/RB/TE, K, DST) find the highest projected points
    #if we cannot fill a position use REPLACEMENT_POINTS
        team_mu[team] = total
    return team_mu

# --------------------------------------------------------------------------
# STEP 4: SIMULATION LOGIC
# --------------------------------------------------------------------------
def simulate_game(team1, team2, current_week, variance):
    """
    Simulate a single game between Team1 and Team2.

    Returns:
        winner: 1 if Team1 wins, 2 if Team2 wins
        points1: points scored by Team1
        points2: points scored by Team2
    """
    sigma = np.sqrt(variance)

    mu1 = week{current_week}

    score1 = np.random.normal(mu1, sigma)
    score2 = np.random.normal(mu2, sigma)

    winner = 1 if score1 > score2 else 2

    return winner, score1, score2


#this code needs to change because it matters what week you play a given team, 
#since teams have different mu's in different weeks
#instead of building the schedule I want to pull it directly from yahoo
#if that isnt possible, I will have to hardcode it
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

