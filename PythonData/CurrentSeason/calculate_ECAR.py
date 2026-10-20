"""
Calculate each drafted player's ECAR stat -- Expected Championships
Above Replacement -- for completed historical seasons (2023 and 2024
only, for now; see YEARS_TO_RUN below).

ECAR extends WAR (see CalculateWAR.py's module docstring for the full
WAR derivation) one level further up the stack: instead of stopping at
"win probability added in a single game," it asks how much of that
win-probability-add actually moves a team's probability of winning the
league championship, broken into a regular-season leg and a playoff
leg.

This script is intentionally standalone from CalculateHistoricalWAR.py
(even though it duplicates some of its per-week WAR plumbing) because
ECAR needs playoff weeks (15-17) included in the per-player per-week
WAR sum, which the existing WAR scripts deliberately exclude (WAR today
is a regular-season-only stat). Rather than change the meaning of the
existing war_{YEAR}.json dataset, this script recomputes WAR_week for
every week 1-17 itself, reusing the exact same formula/constants
(REPLACEMENT_LEVEL, MARGIN_SIGMA, win_probability_added, etc. -- all
imported directly from CalculateWAR.py so the two stats never drift
apart on the underlying win-probability math).

--------------------------------------------------------------------------
THE CORE PROBLEM THIS STAT SOLVES
--------------------------------------------------------------------------
A player's historical WAR contribution is mechanically entangled with
their real team's other matchups, opponents, and seed trajectory -- two
players with identical weekly stat lines could have wildly different
"effect on their team's championship odds" just because of what team
they happened to be drafted to. ECAR is designed to be independent of
the player's actual team, so a bench player on a 3-10 team and a
starter on the 1-seed get valued on the same scale for the same
performance.

To do that, every player's weekly WAR is multiplied by a LEAGUE-WIDE
LEVERAGE CONSTANT for that week, not by anything about their own team's
actual standing or playoff fate that week. There are exactly four such
constants per season:

  REG_SEASON_WIN_LEVERAGE  -- applied to every player's WAR in every
                              regular season week (1 through
                              playoff_start_week - 1, i.e. weeks 1-14
                              in this 14-team/14-week-regular-season
                              league). Represents the average
                              championship-win-probability value of one
                              marginal regular-season win.

  QF_LEVERAGE / SF_LEVERAGE / FINAL_LEVERAGE
                           -- applied to every player's WAR in week 15
                              / 16 / 17 respectively, regardless of
                              whether that player's real team actually
                              made the real bracket that week (some
                              real teams are playing consolation or
                              punishment games in those same weeks --
                              ECAR still credits their players' WAR
                              at full quarterfinal/semifinal/final
                              stakes, by design, since the stat must not
                              depend on the player's actual team or
                              bracket fate). Represents the
                              championship-win-probability swing from
                              winning vs. losing a single-elimination
                              game at that round.

ECAR_player = sum(WAR_week for weeks 1-14) * REG_SEASON_WIN_LEVERAGE
              + WAR_week15 * QF_LEVERAGE    * (4/14)
              + WAR_week16 * SF_LEVERAGE    * (4/14)
              + WAR_week17 * FINAL_LEVERAGE * (2/14)

The (4/14), (4/14), (2/14) factors are ROUND-PARTICIPATION WEIGHTS
(confirmed with the user): only 4 of the league's 14 teams actually
reach the quarterfinal, only 4 reach the semifinal (the 2 byes + 2 QF
winners), and only 2 reach the Final. ECAR is meant to answer "if
this player's performance had belonged to a RANDOMLY CHOSEN one of the
14 teams, what's the expected championship-probability-added" -- so a
playoff week's leverage should only apply with the probability that a
random team was actually IN that round, not treated as certain to
matter. See write_ecar_output's docstring for the full rationale and
its effect on player rankings (it can reorder players relative to the
unweighted version: a single huge Final-week performance is now
heavily discounted by the Final's 2/14 odds, so it won't automatically
outrank a more consistent regular-season contributor).

--------------------------------------------------------------------------
HOW THE FOUR LEVERAGE CONSTANTS ARE DERIVED
--------------------------------------------------------------------------
All four come from one shared bracket Monte Carlo simulator
(simulate_bracket_season / run_leverage_simulation below), run once per
season, that is deliberately SCHEDULE- and TEAM-AGNOSTIC:

  - 14 symmetric teams, no team identity, no real schedule. Each of the
    14 weeks, teams are paired up uniformly at random (a fresh random
    round-robin-style pairing every trial) -- using the real historical
    schedule would bake in which specific two real teams played each
    other, re-introducing team-dependence into what's supposed to be a
    league-wide constant.
  - Each simulated team-week score ~ Normal(mu=LEAGUE_MEAN_SCORE,
    sigma=GAME_SIGMA), using this league's own empirically-fit
    GAME_SIGMA = 23.3 (imported from CalculateWAR.py, same fit already
    used by WAR and by RunWeekly.py's regular-season simulator). Since
    every team is symmetric (same mu), the league mean score itself is
    irrelevant to any win/seeding outcome -- only sigma matters -- but a
    plausible mu is used anyway so the magnitudes read naturally.
  - After 14 simulated weeks, teams are seeded by (wins, points)
    descending, same convention as RunWeekly.py's simulate_season:
    seeds 1-2 get a bye to the semifinals, seeds 3-6 play a
    quarterfinal, seeds 7-10 make neither bracket, seeds 11-14 land in
    the punishment bracket (SIM_BYE_SPOTS / SIM_PLAYOFF_SPOTS /
    SIM_PUNISHMENT_SPOTS, same values as RunWeekly.py).
  - UNLIKE RunWeekly.py's simulator (which stops at seeding), this one
    keeps playing: seeds 3-6 play the quarterfinal (1v4/2v3 reseeded
    bracket conventions by seed), the two QF winners join the two bye
    seeds in the semifinals, and the two SF winners play the final.
    Each bracket game is simulated the same way (Normal(mu, sigma),
    higher score wins). The final's winner is that trial's champion.
  - Pooling every team x every trial together gives:
      (a) (wins, made_bye) and (wins, made_QF_or_better) pairs -> used
          to fit P(bye | wins) and P(QF+ | wins) logistic curves.
      (b) P(champion | bye seed), P(champion | QF seed),
          P(champion | no-playoff seed) -- the three regular-season
          tier values.
      (c) P(champion | win QF) vs P(champion | lose QF), and the same
          pair for SF and the Final -- the three playoff round
          leverage values.

REG_SEASON_WIN_LEVERAGE is a BLENDED constant (per the user's
confirmed design choice): a single regular-season win doesn't "know"
in advance whether it's the win that pushes a team from no-playoffs to
QF-seed, or from QF-seed to bye-seed, so instead of trying to attribute
each real win to one specific tier jump (which would reintroduce
team-dependence -- it depends on the team's specific trajectory), this
blends both possible tier jumps into one number:

    REG_SEASON_WIN_LEVERAGE =
        dP(bye)/dWin   * [P(champ | bye seed) - P(champ | QF seed)]
      + dP(QF+)/dWin   * [P(champ | QF seed)  - P(champ | no-playoff seed)]

dP(bye)/dWin and dP(QF+)/dWin are each a single scalar per season (not
per-team, not per-week), obtained by:
  1. Fitting a logistic regression of made_bye ~ wins and
     made_QF_or_better ~ wins on the pooled (team x trial) dataset.
  2. Taking the slope (derivative) of that fitted curve at every
     integer win total within the central band of the simulated win
     distribution (the 10th-90th percentile of wins actually observed
     across all team-trials), then averaging those slopes together
     (BAND-AVERAGE, per the user's confirmed choice, rather than a
     single point-estimate at the mean -- logistic curves are steepest
     near the middle and flatten at the tails, so a single-point
     derivative is less stable than a band average).

QF_LEVERAGE / SF_LEVERAGE / FINAL_LEVERAGE are each just
P(champion | win this round) - P(champion | lose this round), estimated
directly from the simulator's pooled bracket-game outcomes (every
simulated QF/SF/Final game across every trial), so they are already
averaged across every possible matchup/seed draw -- not specific to any
one team's bracket slot.

--------------------------------------------------------------------------
WAR_week FOR PLAYOFF WEEKS (15-17)
--------------------------------------------------------------------------
Uses the exact same formula as the regular season (imported from
CalculateWAR.py): P = credited points - replacement level that week,
D_relative = season-long regular-season starter average at that
position (computed from weeks 1-14 only, exactly like the existing WAR
scripts -- D is not re-derived separately for playoff weeks), and
WAR_week = Phi((P - D_relative)/MARGIN_SIGMA) - Phi((-D_relative)/MARGIN_SIGMA).
Every drafted player's actual week 15/16/17 performance counts, whether
or not their real team made the real bracket that week (all 14 teams
play a real game every week of the season, real bracket or
consolation/punishment).

--------------------------------------------------------------------------
FILES
--------------------------------------------------------------------------
Reads (under PythonData/draftData/):
  draft_{YEAR}.json                    cached/enriched draft board
                                        (reused as-is if present; shared
                                        with CalculateWAR.py /
                                        CalculateHistoricalWAR.py)
  par_zero_score_review_{YEAR}.json    manual "did they actually play?"
                                        log (shared DNP semantics)

Writes (under PythonData/draftData/):
  par_zero_score_review_{YEAR}.json    extended with any newly
                                        auto-flagged zero-score weeks
                                        15-17
  ecar_leverage_{YEAR}.json          the four derived leverage
                                        constants + simulator diagnostics
                                        for that season (so the numbers
                                        behind each player's ECAR are
                                        auditable)
  ecar_{YEAR}.json                   one row per drafted player:
                                        {year, pick, round, player_id,
                                         player_name, position,
                                         war_regular_season,
                                         war_week15, war_week16,
                                         war_week17,
                                         ecar_regular_season,
                                         ecar_quarterfinal,
                                         ecar_semifinal,
                                         ecar_final,
                                         ecar_total}
                                        sorted by pick.

Images written (into Website/girderma-gridiron-website/src/
league_stats_output/CurrentSeason/DraftBoards/ECAR/), same visual
convention as CalculateWAR.py's WAR board (rows = draft round, columns
= teams in round-1 pick order, red/blue diverging gradient split at
zero):
  draft_board_by_ecar_{YEAR}.png           grid colored by ecar_total
  draft_board_by_ecar_{YEAR}_colorbar.png  legend strip for the gradient

Usage:
    python3 calculate_ECAR.py                   # runs 2023 and 2024
    python3 calculate_ECAR.py --years 2023
    python3 calculate_ECAR.py --skip-simulation  # reuse a previously
                                                    # saved leverage file
                                                    # instead of re-running
                                                    # the Monte Carlo step

From another file, reusing an already-authenticated league object:
    from calculate_ECAR import run_year
    run_year(2024, league=lg)
"""

import argparse
import json
import os
from pathlib import Path

import numpy as np

import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt
import matplotlib.colors
import matplotlib.cm

from yahoo_oauth import OAuth2
import yahoo_fantasy_api as yfa

# Reuse the exact same formula constants/helpers as the live WAR
# script, so ECAR's underlying win-probability math never drifts
# from WAR's.
from CalculateWAR import (
    REPLACEMENT_LEVEL,
    POSITION_ALIASES,
    NON_STARTER_SLOTS,
    GAME_SIGMA,
    MARGIN_SIGMA,
    auto_flag_zero_scores,
    player_did_not_play,
    credited_points_for_week,
    calculate_position_averages,
    win_probability_added,
)


# --------------------------------------------------------------------------
# YEAR -> LEAGUE ID (same ids as CalculateHistoricalWAR.py)
# --------------------------------------------------------------------------
LEAGUE_IDS = {
    2023: "423.l.902802",
    2024: "449.l.106896",
}

# Per explicit instruction: 2023 and 2024 only. Do NOT add 2025/2026
# here without re-confirming -- ECAR assumes a fully completed season
# (known final bracket results aren't actually required by this
# script's method, since leverage is schedule/team-agnostic, but the
# per-player WAR_week inputs assume every week 1-17 already happened).
YEARS_TO_RUN = [2023, 2024]

SCRIPT_DIR = os.path.dirname(os.path.abspath(__file__))
PYTHON_DATA_DIR = Path(SCRIPT_DIR) / ".."
DRAFT_DATA_DIR = PYTHON_DATA_DIR / "draftData"
OAUTH_FILE = str(PYTHON_DATA_DIR / "oauth2.json")

# --------------------------------------------------------------------------
# LEAGUE / BRACKET STRUCTURE (same values as RunWeekly.py's SIM_* constants)
# --------------------------------------------------------------------------
NUM_TEAMS = 14
REGULAR_SEASON_WEEKS = 14          # weeks 1-14
PLAYOFF_WEEKS = {15: "quarterfinal", 16: "semifinal", 17: "final"}

SIM_BYE_SPOTS = 2                  # seeds 1-2 -> bye to semifinals
SIM_PLAYOFF_SPOTS = 4              # seeds 3-6 -> quarterfinal
SIM_PUNISHMENT_SPOTS = 4           # seeds 11-14 -> punishment bracket
# seeds 7-10 make neither bracket

# Number of teams actually competing in each championship-bracket round
# (confirmed with the user): QF has 4 teams (seeds 3-6), SF has 4 teams
# (the 2 bye seeds + 2 QF winners), the Final has 2 teams. Used to
# weight each player's playoff-week ECAR contribution by the
# probability that a RANDOMLY CHOSEN one of the 14 teams was even in
# that round -- see write_ecar_output's ROUND_PARTICIPATION_WEIGHT
# usage for the full rationale.
ROUND_PARTICIPANTS = {"qf": 4, "sf": 4, "final": 2}

# --------------------------------------------------------------------------
# LEVERAGE SIMULATOR CONSTANTS
# --------------------------------------------------------------------------
LEVERAGE_N_SIMULATIONS = 20_000
LEVERAGE_LEAGUE_MEAN_SCORE = 110.0   # arbitrary but plausible; irrelevant
                                      # to outcomes since all teams are
                                      # symmetric (only sigma matters)
LEVERAGE_RANDOM_SEED = 42            # fixed seed -> reproducible leverage
                                      # constants across runs
LEVERAGE_BAND_PERCENTILES = (10, 90)  # band-average window for the
                                       # win-value derivative


def draft_cache_path(year: int) -> Path:
    return DRAFT_DATA_DIR / f"draft_{year}.json"


def zero_score_review_path(year: int) -> Path:
    return DRAFT_DATA_DIR / f"par_zero_score_review_{year}.json"


def leverage_output_path(year: int) -> Path:
    return DRAFT_DATA_DIR / f"ecar_leverage_{year}.json"


def ecar_output_path(year: int) -> Path:
    return DRAFT_DATA_DIR / f"ecar_{year}.json"


# --------------------------------------------------------------------------
# DRAFT BOARD IMAGE OUTPUT (same website output tree as CalculateWAR.py's
# WAR boards, parameterized by year since this script runs historical
# seasons, not just one hardcoded year)
# --------------------------------------------------------------------------
def ecar_board_dir(year: int) -> Path:
    return (
        Path(SCRIPT_DIR) / ".." / ".." / "Website" / "girderma-gridiron-website"
        / "src" / "league_stats_output" / "CurrentSeason" / "DraftBoards" / "ECAR"
    ).resolve()


def ecar_board_image_path(year: int) -> Path:
    return ecar_board_dir(year) / f"draft_board_by_ecar_{year}.png"


DEFAULT_TEXT_COLOR = "#374151"


# --------------------------------------------------------------------------
# AUTH
# --------------------------------------------------------------------------
def get_league(year: int):
    league_id = LEAGUE_IDS.get(year)
    if not league_id:
        raise ValueError(
            f"No Yahoo league id configured for {year}. ECAR is only "
            f"configured for {sorted(LEAGUE_IDS)}."
        )
    sc = OAuth2(None, None, from_file=OAUTH_FILE)
    gm = yfa.Game(sc, "nfl")
    return gm.to_league(league_id)


# ==========================================================================
# PART 1: BRACKET MONTE CARLO SIMULATOR (schedule/team-agnostic)
# ==========================================================================
def _play_game(mu_a: float, mu_b: float, sigma: float, rng: np.random.Generator):
    """Simulate one game: returns True if team A wins."""
    score_a = rng.normal(mu_a, sigma)
    score_b = rng.normal(mu_b, sigma)
    if score_a == score_b:
        # Continuous draw, ties are vanishingly rare, but break them
        # with a coin flip rather than biasing toward either side.
        return rng.random() < 0.5
    return score_a > score_b


def simulate_one_bracket_trial(rng: np.random.Generator, n_teams: int = NUM_TEAMS,
                                reg_weeks: int = REGULAR_SEASON_WEEKS,
                                sigma: float = GAME_SIGMA,
                                mean_score: float = LEVERAGE_LEAGUE_MEAN_SCORE,
                                bye_spots: int = SIM_BYE_SPOTS,
                                playoff_spots: int = SIM_PLAYOFF_SPOTS,
                                punishment_spots: int = SIM_PUNISHMENT_SPOTS) -> dict:
    """
    Simulate one full season (regular season + full single-elimination
    bracket) for n_teams symmetric, schedule-agnostic teams.

    Returns a dict with per-team regular season results and, for the
    bracket games actually played this trial, which teams won/lost each
    round and who the champion was.
    """
    teams = list(range(n_teams))
    wins = {t: 0 for t in teams}
    points = {t: 0.0 for t in teams}

    # Regular season: each week, pair all teams up uniformly at random.
    for _ in range(reg_weeks):
        order = teams.copy()
        rng.shuffle(order)
        for i in range(0, n_teams, 2):
            a, b = order[i], order[i + 1]
            score_a = rng.normal(mean_score, sigma)
            score_b = rng.normal(mean_score, sigma)
            points[a] += score_a
            points[b] += score_b
            if score_a > score_b:
                wins[a] += 1
            else:
                wins[b] += 1

    # Seed by (wins, points) descending, same convention as
    # RunWeekly.py's simulate_season.
    ranked = sorted(teams, key=lambda t: (wins[t], points[t]), reverse=True)
    bye_seeds = ranked[:bye_spots]
    qf_seeds = ranked[bye_spots:bye_spots + playoff_spots]
    # seeds 7-10 (middle) and punishment seeds (bottom) don't participate
    # in the championship bracket at all.

    tier_by_team = {t: "no_playoff" for t in teams}
    for t in bye_seeds:
        tier_by_team[t] = "bye"
    for t in qf_seeds:
        tier_by_team[t] = "qf"

    result = {
        "wins_by_team": wins,
        "tier_by_team": tier_by_team,
        "champion": None,
        "qf_games": [],   # list of (winner_tier_dummy, won: bool) per team per QF game
        "sf_games": [],
        "final_games": [],
    }

    if playoff_spots < 4 or bye_spots < 2:
        # Bracket shape assumed below needs exactly 4 QF seeds + 2 byes;
        # guard defensively even though this repo's constants satisfy it.
        return result

    # Quarterfinals: standard reseeding bracket by seed within the QF
    # group -- best seed (qf_seeds[0]) plays worst (qf_seeds[3]), and
    # the middle two play each other.
    qf_pairs = [(qf_seeds[0], qf_seeds[3]), (qf_seeds[1], qf_seeds[2])]
    qf_winners = []
    for a, b in qf_pairs:
        a_wins = _play_game(mean_score, mean_score, sigma, rng)
        winner, loser = (a, b) if a_wins else (b, a)
        qf_winners.append(winner)
        result["qf_games"].append({"winner": winner, "loser": loser})

    # Semifinals: the two bye seeds face the two QF winners. Standard
    # reseeding: better bye seed plays the "weaker" QF winner slot
    # (i.e. bye_seeds[0] vs qf_pairs[1]'s winner, bye_seeds[1] vs
    # qf_pairs[0]'s winner) -- the exact pairing convention doesn't
    # bias the leverage estimate since all teams are symmetric; any
    # fixed convention works.
    sf_pairs = [(bye_seeds[0], qf_winners[1]), (bye_seeds[1], qf_winners[0])]
    sf_winners = []
    for a, b in sf_pairs:
        a_wins = _play_game(mean_score, mean_score, sigma, rng)
        winner, loser = (a, b) if a_wins else (b, a)
        sf_winners.append(winner)
        result["sf_games"].append({"winner": winner, "loser": loser})

    # Final.
    a, b = sf_winners
    a_wins = _play_game(mean_score, mean_score, sigma, rng)
    champion, runner_up = (a, b) if a_wins else (b, a)
    result["final_games"].append({"winner": champion, "loser": runner_up})
    result["champion"] = champion

    return result


def run_leverage_simulation(n_simulations: int = LEVERAGE_N_SIMULATIONS,
                             seed: int = LEVERAGE_RANDOM_SEED) -> dict:
    """
    Run the full bracket Monte Carlo n_simulations times and compute:
      - pooled (wins, made_bye) / (wins, made_qf_or_better) samples
      - P(champion | bye seed), P(champion | qf seed), P(champion | no-playoff seed)
      - P(champion | win QF) vs P(champion | lose QF), and the same for SF/Final

    Returns a dict of raw pooled arrays + tier/round win-rate summaries
    (consumed by fit_regular_season_leverage / compute_playoff_leverage
    below).
    """
    rng = np.random.default_rng(seed)

    all_wins = []
    all_made_bye = []
    all_made_qf_plus = []

    tier_counts = {"bye": 0, "qf": 0, "no_playoff": 0}
    tier_champ_counts = {"bye": 0, "qf": 0, "no_playoff": 0}

    # Playoff-game outcome pools: for each round, track whether the
    # eventual trial champion came from the winning or losing side of
    # that specific game -> P(champ | win round) vs P(champ | lose round).
    round_game_counts = {"qf": 0, "sf": 0, "final": 0}
    round_winner_became_champ = {"qf": 0, "sf": 0, "final": 0}
    round_loser_became_champ = {"qf": 0, "sf": 0, "final": 0}

    for _ in range(n_simulations):
        trial = simulate_one_bracket_trial(rng)
        wins_by_team = trial["wins_by_team"]
        tier_by_team = trial["tier_by_team"]
        champion = trial["champion"]

        for t, w in wins_by_team.items():
            tier = tier_by_team[t]
            all_wins.append(w)
            all_made_bye.append(1 if tier == "bye" else 0)
            all_made_qf_plus.append(1 if tier in ("bye", "qf") else 0)

            tier_counts[tier] += 1
            if t == champion:
                tier_champ_counts[tier] += 1

        for round_name, games in (("qf", trial["qf_games"]),
                                   ("sf", trial["sf_games"]),
                                   ("final", trial["final_games"])):
            for game in games:
                round_game_counts[round_name] += 1
                if game["winner"] == champion:
                    round_winner_became_champ[round_name] += 1
                if game["loser"] == champion:
                    round_loser_became_champ[round_name] += 1

    tier_champ_rate = {
        tier: (tier_champ_counts[tier] / tier_counts[tier] if tier_counts[tier] else 0.0)
        for tier in tier_counts
    }

    round_leverage = {}
    for round_name in ("qf", "sf", "final"):
        n_games = round_game_counts[round_name]
        p_champ_if_win = round_winner_became_champ[round_name] / n_games if n_games else 0.0
        p_champ_if_lose = round_loser_became_champ[round_name] / n_games if n_games else 0.0
        round_leverage[round_name] = {
            "p_champion_if_win": p_champ_if_win,
            "p_champion_if_lose": p_champ_if_lose,
            "leverage": p_champ_if_win - p_champ_if_lose,
            "n_games": n_games,
        }

    return {
        "n_simulations": n_simulations,
        "wins": np.array(all_wins, dtype=float),
        "made_bye": np.array(all_made_bye, dtype=float),
        "made_qf_plus": np.array(all_made_qf_plus, dtype=float),
        "tier_champion_rate": tier_champ_rate,
        "round_leverage": round_leverage,
    }


# ==========================================================================
# PART 2: LOGISTIC FIT + BAND-AVERAGED DERIVATIVE
# ==========================================================================
def _fit_logistic_1d(x: np.ndarray, y: np.ndarray) -> tuple:
    """
    Fit y ~ Bernoulli(sigmoid(b0 + b1*x)) via simple Newton-Raphson
    (no external ML dependency needed for a 1-D logistic fit). Returns
    (b0, b1).
    """
    b0, b1 = 0.0, 0.0
    for _ in range(100):
        z = b0 + b1 * x
        p = 1.0 / (1.0 + np.exp(-z))
        # Gradient of the log-likelihood.
        grad0 = np.sum(y - p)
        grad1 = np.sum((y - p) * x)
        # Hessian (2x2), using the standard IRLS weight p*(1-p).
        w = p * (1.0 - p)
        w = np.clip(w, 1e-10, None)
        h00 = -np.sum(w)
        h01 = -np.sum(w * x)
        h11 = -np.sum(w * x * x)
        hessian = np.array([[h00, h01], [h01, h11]])
        grad = np.array([grad0, grad1])
        try:
            delta = np.linalg.solve(hessian, -grad)
        except np.linalg.LinAlgError:
            break
        b0 += delta[0]
        b1 += delta[1]
        if np.max(np.abs(delta)) < 1e-10:
            break
    return b0, b1


def logistic_slope_band_average(x: np.ndarray, y: np.ndarray,
                                 percentiles: tuple = LEVERAGE_BAND_PERCENTILES) -> dict:
    """
    Fit a 1-D logistic curve P(y=1 | x) and return the BAND-AVERAGED
    derivative dP/dx, averaged over every integer x within the
    [low_pct, high_pct] percentile band of the observed x distribution
    (per the user's confirmed choice -- more stable than a single
    point-estimate derivative at the mean, since logistic curves are
    steepest in the middle and flatten at the tails).

    dP/dx for a logistic curve P = sigmoid(b0 + b1*x) is:
        b1 * P * (1 - P)
    """
    b0, b1 = _fit_logistic_1d(x, y)

    lo, hi = np.percentile(x, percentiles)
    lo_int, hi_int = int(np.floor(lo)), int(np.ceil(hi))
    band_x = np.arange(lo_int, hi_int + 1)
    if len(band_x) == 0:
        band_x = np.array([np.mean(x)])

    p_band = 1.0 / (1.0 + np.exp(-(b0 + b1 * band_x)))
    slopes = b1 * p_band * (1.0 - p_band)
    band_avg_slope = float(np.mean(slopes))

    return {
        "intercept": float(b0),
        "coef": float(b1),
        "band_low": int(lo_int),
        "band_high": int(hi_int),
        "band_avg_derivative": band_avg_slope,
    }


# ==========================================================================
# PART 3: COMBINE INTO THE FOUR LEVERAGE CONSTANTS
# ==========================================================================
def compute_leverage_constants(sim_results: dict) -> dict:
    """
    Combines the raw simulator output into the four ECAR leverage
    constants (REG_SEASON_WIN_LEVERAGE, QF_LEVERAGE, SF_LEVERAGE,
    FINAL_LEVERAGE), plus full diagnostics for auditability.
    """
    bye_fit = logistic_slope_band_average(sim_results["wins"], sim_results["made_bye"])
    qf_plus_fit = logistic_slope_band_average(sim_results["wins"], sim_results["made_qf_plus"])

    tier_rate = sim_results["tier_champion_rate"]
    bye_value_over_qf = tier_rate["bye"] - tier_rate["qf"]
    qf_value_over_none = tier_rate["qf"] - tier_rate["no_playoff"]

    reg_season_leverage = (
        bye_fit["band_avg_derivative"] * bye_value_over_qf
        + qf_plus_fit["band_avg_derivative"] * qf_value_over_none
    )

    round_leverage = sim_results["round_leverage"]

    return {
        "REG_SEASON_WIN_LEVERAGE": reg_season_leverage,
        "QF_LEVERAGE": round_leverage["qf"]["leverage"],
        "SF_LEVERAGE": round_leverage["sf"]["leverage"],
        "FINAL_LEVERAGE": round_leverage["final"]["leverage"],
        "diagnostics": {
            "n_simulations": sim_results["n_simulations"],
            "dP_bye_dWin": bye_fit,
            "dP_qfplus_dWin": qf_plus_fit,
            "tier_champion_rate": tier_rate,
            "bye_value_over_qf": bye_value_over_qf,
            "qf_value_over_none": qf_value_over_none,
            "round_leverage": round_leverage,
        },
    }


def get_or_run_leverage_constants(year: int, skip_simulation: bool = False) -> dict:
    """
    Loads ecar_leverage_{YEAR}.json if --skip-simulation was passed
    and the file already exists; otherwise runs the Monte Carlo
    simulator fresh and writes it. The simulator itself does not depend
    on `year` at all (it's schedule/team-agnostic, using fixed league
    structure constants) -- it's re-run per year only so each season's
    leverage file is self-contained/auditable, and so a different
    LEVERAGE_RANDOM_SEED or league-structure change could in principle
    be applied retroactively per year if ever needed.
    """
    out_path = leverage_output_path(year)
    if skip_simulation and out_path.exists():
        print(f"[{year}] Reusing cached leverage constants -> {out_path}")
        with open(out_path, "r") as f:
            return json.load(f)

    print(f"[{year}] Running bracket leverage Monte Carlo "
          f"({LEVERAGE_N_SIMULATIONS:,} trials)...")
    sim_results = run_leverage_simulation()
    leverage = compute_leverage_constants(sim_results)

    print(f"[{year}] REG_SEASON_WIN_LEVERAGE = {leverage['REG_SEASON_WIN_LEVERAGE']:+.5f}")
    print(f"[{year}] QF_LEVERAGE    = {leverage['QF_LEVERAGE']:+.5f}")
    print(f"[{year}] SF_LEVERAGE    = {leverage['SF_LEVERAGE']:+.5f}")
    print(f"[{year}] FINAL_LEVERAGE = {leverage['FINAL_LEVERAGE']:+.5f}")

    DRAFT_DATA_DIR.mkdir(parents=True, exist_ok=True)
    with open(out_path, "w") as f:
        json.dump(leverage, f, indent=2)
    print(f"[{year}] Saved -> {out_path}")

    return leverage


# ==========================================================================
# PART 4: DRAFT BOARD (same enrichment as CalculateHistoricalWAR.py)
# ==========================================================================
def load_draft_board(league, year: int, force_refresh: bool = False) -> list:
    cache_path = draft_cache_path(year)
    if cache_path.exists() and not force_refresh:
        with open(cache_path, "r") as f:
            return json.load(f)

    print(f"[{year}] Pulling draft results from Yahoo...")
    draft_results = league.draft_results()
    teams = league.teams()

    player_ids = [pick["player_id"] for pick in draft_results if pick.get("player_id")]
    details_list = league.player_details(player_ids)
    details_by_id = {str(d.get("player_id")): d for d in details_list}

    board = []
    for pick in sorted(draft_results, key=lambda p: p["pick"]):
        pid = str(pick.get("player_id"))
        detail = details_by_id.get(pid, {})

        team_key = pick.get("team_key")
        team_info = teams.get(team_key, {})
        team_name = team_info.get("name", team_key)
        managers = team_info.get("managers", [])
        manager_nickname = None
        if managers:
            manager_nickname = managers[0].get("manager", {}).get("nickname")

        position = detail.get("display_position") or detail.get("primary_position")
        position = POSITION_ALIASES.get(position, position)

        name = detail.get("name", {})
        player_name = name.get("full") if isinstance(name, dict) else name

        bye_week = None
        bye_info = detail.get("bye_weeks")
        if isinstance(bye_info, dict) and bye_info.get("week"):
            try:
                bye_week = int(bye_info["week"])
            except (TypeError, ValueError):
                bye_week = None

        board.append({
            "pick": pick.get("pick"),
            "round": pick.get("round"),
            "team_key": team_key,
            "team_name": team_name,
            "manager_nickname": manager_nickname,
            "player_id": pid,
            "player_name": player_name,
            "position": position,
            "bye_week": bye_week,
        })

    DRAFT_DATA_DIR.mkdir(parents=True, exist_ok=True)
    with open(cache_path, "w") as f:
        json.dump(board, f, indent=2)

    return board


# ==========================================================================
# PART 5: PER-WEEK WAR, EXTENDED THROUGH PLAYOFF WEEKS 15-17
# ==========================================================================
def fetch_actuals_for_week(league, player_ids, week: int) -> dict:
    actuals = {}
    batch_size = 25
    for i in range(0, len(player_ids), batch_size):
        batch = [int(pid) for pid in player_ids[i:i + batch_size]]
        stats = league.player_stats(batch, "week", week=week)
        for row in stats:
            pid = str(row.get("player_id"))
            try:
                pts = float(row.get("total_points", 0.0))
            except (TypeError, ValueError):
                pts = 0.0
            actuals[pid] = pts
    return actuals


def fetch_starters_for_week(league, week: int) -> set:
    starters = set()
    teams_info = league.teams()
    for team_key in teams_info:
        team = yfa.Team(league.sc, team_key)
        try:
            roster = team.roster(week=week)
        except Exception as e:
            print(f"  \u26a0 could not fetch roster for {team_key} (week {week}): {e}")
            continue
        for player in roster:
            selected_pos = player.get("selected_position")
            if selected_pos in NON_STARTER_SLOTS:
                continue
            pid = str(player.get("player_id"))
            starters.add(pid)
    return starters


def determine_all_weeks_to_process(league) -> list:
    """
    Weeks 1 through 17 (regular season 1-14 + quarterfinal/semifinal/
    final weeks 15-17). Confirms playoff_start_week == 15 against
    Yahoo's own league settings rather than hardcoding it blindly, since
    this script's week-15/16/17 round labels depend on that assumption.
    """
    settings = league.settings()
    playoff_start = int(settings.get("playoff_start_week", 15))
    if playoff_start != 15:
        print(f"  \u26a0 league.settings()['playoff_start_week'] = {playoff_start}, "
              f"expected 15. Playoff round week labels (QF=15/SF=16/Final=17) "
              f"may not line up correctly for this season.")
    return list(range(1, 18))


def calculate_war_by_week(league, board: list) -> tuple:
    """
    Returns (war_by_id_by_week, position_averages).

    war_by_id_by_week: {week: {player_id: WAR_week}} for weeks 1-17.
    position_averages: {position: D} computed from REGULAR SEASON weeks
    only (1-14), exactly like the existing WAR scripts -- D is not
    re-derived separately for playoff weeks, it's the same baseline
    applied uniformly to every week including 15-17.
    """
    player_ids = [p["player_id"] for p in board]
    position_by_id = {p["player_id"]: p["position"] for p in board}

    review_path = zero_score_review_path(year_for_review[0])
    zero_score_review = {}
    if review_path.exists():
        with open(review_path, "r") as f:
            zero_score_review = json.load(f)

    weeks = determine_all_weeks_to_process(league)
    reg_season_weeks = [w for w in weeks if w <= REGULAR_SEASON_WEEKS]
    print(f"Weeks to process: {weeks} (regular season: {reg_season_weeks}, "
          f"playoffs: {[w for w in weeks if w > REGULAR_SEASON_WEEKS]})")

    par_by_id_by_week = {}
    starters_by_week = {}
    actuals_by_week = {}

    for week in weeks:
        print(f"  Fetching actuals + starters for week {week}...")
        actuals = fetch_actuals_for_week(league, player_ids, week)
        actuals_by_week[week] = actuals
        zero_score_review = auto_flag_zero_scores(week, board, actuals, zero_score_review)

        credited = credited_points_for_week(week, board, position_by_id, actuals, zero_score_review)
        par_this_week = {}
        for pid, credited_pts in credited.items():
            replacement = REPLACEMENT_LEVEL.get(position_by_id.get(pid))
            if replacement is None:
                continue
            par_this_week[pid] = credited_pts - replacement
        par_by_id_by_week[week] = par_this_week

        starters_by_week[week] = fetch_starters_for_week(league, week)

    with open(review_path, "w") as f:
        json.dump(zero_score_review, f, indent=2)

    # D is computed from regular season weeks only, same convention as
    # the existing WAR scripts (which never see weeks 15-17 at all).
    position_averages = calculate_position_averages(
        board, reg_season_weeks, starters_by_week, actuals_by_week
    )
    print(f"D (raw points, regular season only) by position: "
          f"{ {pos: round(d, 2) for pos, d in position_averages.items()} }")

    position_averages_relative = {
        pos: d - REPLACEMENT_LEVEL[pos]
        for pos, d in position_averages.items()
        if pos in REPLACEMENT_LEVEL
    }

    war_by_id_by_week = {week: {} for week in weeks}
    for week in weeks:
        par_this_week = par_by_id_by_week.get(week, {})
        for pid in player_ids:
            pos = position_by_id.get(pid)
            if pos not in REPLACEMENT_LEVEL:
                continue
            d_relative = position_averages_relative.get(pos)
            if d_relative is None:
                continue
            p = par_this_week.get(pid)
            if p is None:
                continue
            war_by_id_by_week[week][pid] = win_probability_added(p, d_relative)

    return war_by_id_by_week, position_averages


# A tiny single-element holder so calculate_war_by_week (called once
# per year from run_year) can resolve the correct year's zero-score
# review path without changing its signature. Set at the top of
# run_year before this function is called.
year_for_review = [None]


# ==========================================================================
# PART 6: COMBINE WAR + LEVERAGE INTO ECAR, WRITE OUTPUT
# ==========================================================================
def write_ecar_output(year: int, board: list, war_by_id_by_week: dict,
                         leverage: dict) -> None:
    """
    ROUND-PARTICIPATION WEIGHTING (confirmed with the user): ECAR is
    meant to answer "if this player's actual 2024 performance had
    belonged to a RANDOMLY CHOSEN one of the 14 teams, what's the
    expected championship-probability-added?" For regular season
    weeks, every team plays every week, so no weighting is needed. But
    only 4 of 14 teams actually reach the quarterfinal, only 4 of 14
    reach the semifinal (2 byes + 2 QF winners), and only 2 of 14 reach
    the Final -- a randomly chosen team has only a 4/14, 4/14, 2/14
    chance (respectively) of that week's QF/SF/Final leverage even
    applying to it at all. Without this weighting, every player's
    playoff-week WAR was being credited at full round-stakes as if
    certain to matter, which overweights a single standout playoff
    week relative to a full season of regular-season weeks (where any
    one week was always guaranteed to count). Multiplying each playoff
    week's contribution by (round_participants / NUM_TEAMS) turns the
    playoff terms into true expectations over random team assignment,
    consistent with the regular season term, and CAN reorder players
    relative to the unweighted version -- a player with one huge
    Final-week performance but an average regular season will now rank
    lower relative to a player who was solidly above-replacement across
    more weeks, since the Final's 2/14 chance heavily discounts that
    one week's weight. This is intentional.
    """
    reg_leverage = leverage["REG_SEASON_WIN_LEVERAGE"]
    qf_leverage = leverage["QF_LEVERAGE"] * (ROUND_PARTICIPANTS["qf"] / NUM_TEAMS)
    sf_leverage = leverage["SF_LEVERAGE"] * (ROUND_PARTICIPANTS["sf"] / NUM_TEAMS)
    final_leverage = leverage["FINAL_LEVERAGE"] * (ROUND_PARTICIPANTS["final"] / NUM_TEAMS)

    rows = []
    for p in board:
        pid = p["player_id"]

        war_reg_season = sum(
            war_by_id_by_week.get(week, {}).get(pid, 0.0)
            for week in range(1, REGULAR_SEASON_WEEKS + 1)
        )
        war_week15 = war_by_id_by_week.get(15, {}).get(pid, 0.0)
        war_week16 = war_by_id_by_week.get(16, {}).get(pid, 0.0)
        war_week17 = war_by_id_by_week.get(17, {}).get(pid, 0.0)

        ecar_reg_season = war_reg_season * reg_leverage
        ecar_qf = war_week15 * qf_leverage
        ecar_sf = war_week16 * sf_leverage
        ecar_final = war_week17 * final_leverage
        ecar_total = ecar_reg_season + ecar_qf + ecar_sf + ecar_final

        rows.append({
            "year": year,
            "pick": p["pick"],
            "round": p["round"],
            "player_id": pid,
            "player_name": p["player_name"],
            "position": p["position"],
            "war_regular_season": war_reg_season,
            "war_week15_quarterfinal": war_week15,
            "war_week16_semifinal": war_week16,
            "war_week17_final": war_week17,
            "ecar_regular_season": ecar_reg_season,
            "ecar_quarterfinal": ecar_qf,
            "ecar_semifinal": ecar_sf,
            "ecar_final": ecar_final,
            "ecar_total": ecar_total,
        })

    rows.sort(key=lambda r: r["pick"])

    out_path = ecar_output_path(year)
    DRAFT_DATA_DIR.mkdir(parents=True, exist_ok=True)
    with open(out_path, "w") as f:
        json.dump(rows, f, indent=2)
    print(f"[{year}] Saved -> {out_path} ({len(rows)} players)")


def print_top_ecar(year: int, rows_path: Path, top_n: int = 15) -> None:
    with open(rows_path, "r") as f:
        rows = json.load(f)
    ranked = sorted(rows, key=lambda r: -r["ecar_total"])
    print(f"\n=== [{year}] Top {top_n} players by ECAR ===")
    for r in ranked[:top_n]:
        print(f"  {r['player_name']:<26} {r['position']:<4} "
              f"ECAR {r['ecar_total']:+.4f}  "
              f"(reg {r['ecar_regular_season']:+.4f}, "
              f"qf {r['ecar_quarterfinal']:+.4f}, "
              f"sf {r['ecar_semifinal']:+.4f}, "
              f"final {r['ecar_final']:+.4f})")


# ==========================================================================
# PART 7: DRAFT BOARD IMAGE (same grid/visual convention as
# CalculateWAR.py's render_war_board -- rows = draft round, columns =
# teams in round-1 pick order, diverging red/blue gradient split at
# zero, each half normalized independently against this run's actual
# max/min ECAR)
# ==========================================================================
def build_board_grid(board: list) -> tuple:
    """Same convention as CalculateWAR.py's build_board_grid -- columns
    ordered by each team's round-1 pick, rows are draft rounds."""
    round1_picks = sorted((p for p in board if p["round"] == 1), key=lambda p: p["pick"])
    columns = [
        {"team_key": p["team_key"], "label": p.get("manager_nickname") or p["team_name"]}
        for p in round1_picks
    ]

    rounds = sorted({p["round"] for p in board})

    cell_by_round_and_team = {}
    for p in board:
        cell_by_round_and_team[(p["round"], p["team_key"])] = p

    return rounds, columns, cell_by_round_and_team


def _draw_board(rounds, columns, cell_by_round_and_team, cell_color_fn, text_color_fn,
                 cell_label_fn, title: str, output_path, legend_handles=None) -> None:
    """Shared grid-drawing routine, identical to CalculateWAR.py's _draw_board."""
    n_rows = len(rounds)
    n_cols = len(columns)

    cell_w, cell_h = 1.9, 1.0
    fig_w = max(10, n_cols * cell_w + 1.5)
    fig_h = n_rows * cell_h + 1.5

    fig, ax = plt.subplots(figsize=(fig_w, fig_h))
    ax.set_xlim(0, n_cols)
    ax.set_ylim(-0.9, n_rows)
    ax.invert_yaxis()
    ax.set_xticks([])
    ax.set_yticks([])
    for spine in ax.spines.values():
        spine.set_visible(False)

    for col_idx, col in enumerate(columns):
        ax.text(
            col_idx + 0.5, -0.55, col["label"],
            ha="center", va="center", fontsize=10, fontweight="bold", color="#111827",
        )

    for row_idx, round_num in enumerate(rounds):
        ax.text(
            -0.3, row_idx + 0.5, f"R{round_num}",
            ha="center", va="center", fontsize=9, fontweight="bold", color="#6B7280",
        )

    for row_idx, round_num in enumerate(rounds):
        for col_idx, col in enumerate(columns):
            pick = cell_by_round_and_team.get((round_num, col["team_key"]))

            x, y = col_idx, row_idx
            face_color = cell_color_fn(pick)
            rect = plt.Rectangle(
                (x, y), 1, 1,
                facecolor=face_color,
                edgecolor="white",
                linewidth=1.5,
            )
            ax.add_patch(rect)

            if pick is None:
                continue

            text_color = text_color_fn(pick)
            label = cell_label_fn(pick)
            ax.text(
                x + 0.5, y + 0.5, label,
                ha="center", va="center", fontsize=7.8, color=text_color, linespacing=1.4,
            )

    ax.set_title(title, fontsize=15, fontweight="bold", color="#111827", pad=36)

    if legend_handles:
        ax.legend(
            handles=legend_handles,
            loc="upper center",
            bbox_to_anchor=(0.5, -0.4 / n_rows),
            ncol=min(len(legend_handles), 6),
            frameon=False,
            fontsize=9,
        )

    fig.tight_layout()
    fig.savefig(output_path, dpi=200, bbox_inches="tight")
    plt.close(fig)
    print(f"Saved -> {output_path}")


def render_ecar_board(year: int, rounds, columns, cell_by_round_and_team,
                         ecar_by_id: dict) -> None:
    """
    Diverging gradient split at zero, identical scheme to
    CalculateWAR.py's render_war_board: positive ECAR uses 'Reds'
    (darker = higher), negative ECAR uses 'Blues' (darker = more
    negative). Each half normalized independently against this run's
    actual max/min.
    """
    ecar_values = [ecar_by_id.get(p["player_id"], 0.0) for p in cell_by_round_and_team.values()]
    ecar_max = max((v for v in ecar_values if v > 0), default=1.0) or 1.0
    ecar_min = min((v for v in ecar_values if v < 0), default=-1.0) or -1.0

    reds = matplotlib.colormaps["Reds"]
    blues = matplotlib.colormaps["Blues"]

    def intensity(value: float) -> float:
        if value >= 0:
            return value / ecar_max if ecar_max else 0.0
        return value / ecar_min if ecar_min else 0.0

    def cell_color(pick):
        if pick is None:
            return "#FFFFFF"
        ecar = ecar_by_id.get(pick["player_id"], 0.0)
        t = intensity(ecar)
        return reds(t) if ecar >= 0 else blues(t)

    def text_color(pick):
        if pick is None:
            return DEFAULT_TEXT_COLOR
        ecar = ecar_by_id.get(pick["player_id"], 0.0)
        return "#FFFFFF" if intensity(ecar) > 0.6 else "#111827"

    def label(pick):
        ecar = ecar_by_id.get(pick["player_id"], 0.0)
        return f"#{pick['pick']}  {ecar:+.3f}\n{pick['player_name']}"

    board_dir = ecar_board_dir(year)
    board_dir.mkdir(parents=True, exist_ok=True)
    board_image_path = ecar_board_image_path(year)

    _draw_board(
        rounds, columns, cell_by_round_and_team,
        cell_color_fn=cell_color,
        text_color_fn=text_color,
        cell_label_fn=label,
        title=f"{year} Draft Board -- Expected Championships "
              f"Above Replacement (ECAR)",
        output_path=board_image_path,
        legend_handles=None,
    )

    # Colorbar legend strip: blue (very negative) on the left, through
    # white at zero, to red (very positive) on the right.
    n_stops = 256
    blue_half = [blues(1.0 - i / (n_stops // 2 - 1)) for i in range(n_stops // 2)]
    red_half = [reds(i / (n_stops // 2 - 1)) for i in range(n_stops // 2)]
    diverging_cmap = matplotlib.colors.ListedColormap(blue_half + red_half)

    fig, ax = plt.subplots(figsize=(6, 0.6))
    fig.subplots_adjust(bottom=0.5)
    norm_ = matplotlib.colors.Normalize(vmin=ecar_min, vmax=ecar_max)
    mappable = matplotlib.cm.ScalarMappable(norm=norm_, cmap=diverging_cmap)
    cb = fig.colorbar(mappable, cax=ax, orientation="horizontal")
    cb.set_label("ECAR (negative -> positive)", fontsize=9)
    colorbar_path = board_image_path.with_name(board_image_path.stem + "_colorbar.png")
    fig.savefig(colorbar_path, dpi=200, bbox_inches="tight")
    plt.close(fig)
    print(f"Saved -> {colorbar_path}")


def render_ecar_draft_board(year: int, board: list, rows_path: Path) -> None:
    """Loads the just-written ecar_{YEAR}.json rows and renders the
    draft board image colored by ecar_total."""
    with open(rows_path, "r") as f:
        rows = json.load(f)
    ecar_by_id = {r["player_id"]: r["ecar_total"] for r in rows}

    rounds, columns, cell_by_round_and_team = build_board_grid(board)
    render_ecar_board(year, rounds, columns, cell_by_round_and_team, ecar_by_id)


# ==========================================================================
# ORCHESTRATION
# ==========================================================================
def run_year(year: int, force_refresh_draft: bool = False, skip_simulation: bool = False,
             league=None) -> None:
    """
    league: optional already-authenticated league for `year`. If
    omitted, authenticates fresh (same convention as
    CalculateHistoricalWAR.run_year).
    """
    if year not in LEAGUE_IDS:
        raise ValueError(
            f"ECAR is only configured to run on {sorted(LEAGUE_IDS)}. "
            f"Got year={year}."
        )

    print(f"\n{'=' * 72}\n{year} SEASON -- ECAR\n{'=' * 72}")

    leverage = get_or_run_leverage_constants(year, skip_simulation=skip_simulation)

    if league is None:
        league = get_league(year)

    board = load_draft_board(league, year, force_refresh=force_refresh_draft)

    year_for_review[0] = year
    war_by_id_by_week, position_averages = calculate_war_by_week(league, board)

    write_ecar_output(year, board, war_by_id_by_week, leverage)
    print_top_ecar(year, ecar_output_path(year))
    render_ecar_draft_board(year, board, ecar_output_path(year))


def main():
    parser = argparse.ArgumentParser(
        description="Calculate ECAR (Expected Championships Above "
                    "Replacement) for completed historical seasons."
    )
    parser.add_argument("--years", type=int, nargs="+", default=YEARS_TO_RUN,
                         help=f"Seasons to process (default: {YEARS_TO_RUN}). "
                              f"Only {sorted(LEAGUE_IDS)} are currently configured.")
    parser.add_argument("--force-refresh-draft", action="store_true",
                         help="Re-pull draft results/enrichment from Yahoo even if a "
                              "draft_{YEAR}.json cache already exists.")
    parser.add_argument("--skip-simulation", action="store_true",
                         help="Reuse a previously saved ecar_leverage_{YEAR}.json "
                              "instead of re-running the bracket Monte Carlo step.")
    args = parser.parse_args()

    for year in args.years:
        run_year(year, force_refresh_draft=args.force_refresh_draft,
                  skip_simulation=args.skip_simulation)


if __name__ == "__main__":
    main()
