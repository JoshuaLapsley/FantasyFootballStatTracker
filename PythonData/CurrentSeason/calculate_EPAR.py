"""
Calculate each drafted player's EPAR stat -- Expected Punishments
Above Replacement -- for completed historical seasons (2024 and 2025
only; see YEARS_TO_RUN below).

EPAR is ECAR's mirror image (see calculate_ECAR.py's module
docstring for the shared derivation style this script reuses): instead
of asking how much a player's win-probability-added helps a team win
the CHAMPIONSHIP bracket, EPAR asks how much a player's performance
contributed to a team LOSING the PUNISHMENT bracket (seeds 11-14,
weeks 16-17) -- i.e. ending up in the worst punishment slot. Both
stats share the same underlying per-week WAR formula and the same
general method (a schedule/team-agnostic bracket Monte Carlo ->
league-wide leverage constants -> leverage x WAR_week, summed), but
differ in which bracket is modeled, which regular-season band is used
for the win-value derivative, and -- critically -- the SIGN of the
combination (see "SIGN CONVENTION" below).

--------------------------------------------------------------------------
THE PUNISHMENT BRACKET
--------------------------------------------------------------------------
Per RunWeekly.py's SIM_PUNISHMENT_SPOTS = 4: the bottom 4 regular-season
seeds (11-14) land in a punishment bracket. With exactly 4 teams, this
is a clean 2-round bracket, matching the user's own expectation that
weeks 16-17 are the punishment playoff weeks -- but NOT a standard
"winner stays in" single-elimination bracket. The user confirmed
"winning is always good, you're escaping deeper punishment" (structure
1), and that framing is only internally consistent with a LOSER'S
bracket shape:

  Week 16 (punishment semifinal): seeds paired by seed within the
                                   bottom-4 group (worst-seed vs
                                   3rd-worst, 2nd-worst vs 4th-worst).
                                   WINNERS of this game are safe --
                                   they're done being at risk this
                                   season, 0% chance of ending up
                                   worst_punishment.
  Week 17 (punishment final):     the two week-16 LOSERS play each
                                   other (not the winners -- see note
                                   below). The LOSER of this game is
                                   that trial's "worst_punishment" team
                                   (the single worst outcome in the
                                   whole league that season); the
                                   winner of this consolation-of-
                                   consolations game escapes with the
                                   second-worst finish.

  Why this shape, and not "SF winners play the final": in a standard
  single-elimination bracket, a team that LOSES in the semifinal is
  immediately eliminated and therefore safe from ever becoming
  worst_punishment, while a team that WINS the semifinal has to keep
  playing and risks losing the final -- i.e. winning the SF would be
  WORSE than losing it. That directly contradicts the user's confirmed
  "winning is always good" framing. Routing the SF's LOSERS into the
  punishment final (a loser's-bracket shape) is the only way to keep
  "winning every game is good, all the way through" true at both
  rounds, consistent with how the championship bracket already works
  (winning is always good there too).

PUNISHMENT SIGN CONVENTION (confirmed with the user)
--------------------------------------------------------------------------
"Losing" the punishment bracket means ending up as worst_punishment --
i.e. WINNING punishment-bracket games is the good outcome (you escape
the bottom slot), same logical structure as the championship bracket
(winning is always good, all the way through). EPAR therefore
measures how much a player's performance contributed to LOSING those
specific games (which pushes the team toward worst_punishment), the
opposite framing from WAR/ECAR's "contributed to winning." A player
who played well (positive WAR_week, helped win) should always SUBTRACT
from EPAR (helped the team avoid the worst outcome); a player who
played below replacement level (negative WAR_week) should always ADD
to EPAR (contributed to a loss that pushed the team toward
worst_punishment). This polarity holds for every week, but the two
groups of leverage constants below are each defined with a DIFFERENT
natural sign, so the explicit sign flip needed to reach that polarity
is NOT the same for both groups -- see each constant's description for
which one needs an explicit "-WAR_week" flip and which one already has
the correct sign built in without one. (An earlier draft of this
script applied the flip uniformly to both groups, which is wrong for
the regular season term -- see REG_SEASON_LOSS_LEVERAGE below.)

--------------------------------------------------------------------------
THE THREE LEVERAGE CONSTANTS
--------------------------------------------------------------------------
  REG_SEASON_LOSS_LEVERAGE  -- applied DIRECTLY (no sign flip) to every
                                player's WAR in every regular season
                                week (1-14):

                                    EPAR_week = +WAR_week * REG_SEASON_LOSS_LEVERAGE

                                This constant is dP(bottom4)/dWin (a
                                NEGATIVE quantity -- more wins makes a
                                team LESS likely to land in the
                                bottom-4 tier) times a POSITIVE tier-
                                value gap [P(worst|bottom4) -
                                P(worst|middle)]. The product is
                                therefore already NEGATIVE, and
                                multiplying it directly by WAR_week (no
                                flip) already produces the right
                                polarity: a good week (positive
                                WAR_week) times a negative leverage
                                constant is negative, i.e. SUBTRACTS
                                from EPAR, exactly as intended. Adding
                                an extra "-WAR_week" flip here (as an
                                earlier draft did) would double-negate
                                this and get the sign backwards.

  PUNISHMENT_SF_LEVERAGE / PUNISHMENT_FINAL_LEVERAGE
                           -- applied WITH an explicit sign flip to
                              every player's WAR in week 16 / 17
                              respectively, regardless of whether that
                              player's real team actually played in the
                              real punishment bracket that week (some
                              real teams are playing championship-
                              bracket or consolation games in those same
                              weeks -- EPAR still credits their
                              players' WAR at full punishment-
                              semifinal/final stakes, by design, exactly
                              mirroring ECAR's week-15/16/17
                              treatment):

                                    EPAR_week = -WAR_week * PUNISHMENT_*_LEVERAGE

                              These two constants are each defined as
                              P(worst_punishment | lose round) -
                              P(worst_punishment | win round), which is
                              always POSITIVE (losing a punishment-
                              bracket game always increases your odds
                              of ending up worst_punishment, given the
                              loser's-bracket shape described above).
                              Since this constant's sign is the
                              opposite polarity from
                              REG_SEASON_LOSS_LEVERAGE's, it DOES need
                              the explicit "-WAR_week" flip to reach the
                              same final polarity: a good week (positive
                              WAR_week) times a positive leverage,
                              negated, is negative -- SUBTRACTS from
                              EPAR, matching the regular season term's
                              behavior despite the different-looking
                              formula.

EPAR_player = sum(WAR_week for weeks 1-14) * REG_SEASON_LOSS_LEVERAGE
              - WAR_week16 * PUNISHMENT_SF_LEVERAGE    * (4/14)
              - WAR_week17 * PUNISHMENT_FINAL_LEVERAGE * (2/14)

(Week 15 does not participate in the punishment bracket at all -- the
punishment bracket is only 2 rounds, weeks 16-17, per the user's own
expectation and the SIM_PUNISHMENT_SPOTS=4/loser's-bracket shape.)

The (4/14) and (2/14) factors are ROUND-PARTICIPATION WEIGHTS
(confirmed with the user, mirroring calculate_ECAR.py's identical
mechanism): only 4 of the league's 14 teams reach the punishment
semifinal, and only 2 reach the punishment final. EPAR is meant to
answer "if this player's performance had belonged to a RANDOMLY CHOSEN
one of the 14 teams, what's the expected worst-punishment-probability-
added" -- so a punishment week's leverage should only apply with the
probability that a random team was actually IN that round. See
write_epar_output's docstring for the full rationale and its effect
on rankings (it can reorder players relative to the unweighted
version).

--------------------------------------------------------------------------
HOW THE LEVERAGE CONSTANTS ARE DERIVED
--------------------------------------------------------------------------
Reuses the exact same schedule/team-agnostic bracket Monte Carlo as
ECAR (14 symmetric teams, random weekly pairing, Normal(mu, sigma=
GAME_SIGMA) scores, seeded by (wins, points) descending after 14 weeks)
but this script's simulator ALSO plays out the punishment bracket for
the bottom 4 seeds (seeds 11-14), which ECAR's simulator does not
need and therefore does not compute. Pooling every team x every trial
gives:
  (a) (wins, made_bottom4) pairs -> fit P(bottom4 | wins) logistic curve.
  (b) P(worst_punishment | bottom4 seed) and
      P(worst_punishment | middle seed, i.e. seeds 7-10) -- the two
      regular-season tier values relevant to punishment (a bye/QF/
      champion seed can never end up as worst_punishment, so those
      three tiers are irrelevant here and not computed by this
      simulator run).
  (c) P(worst_punishment | lose SF) vs P(worst_punishment | win SF),
      and the same pair for the punishment Final -- the two
      punishment-round leverage values.

REG_SEASON_LOSS_LEVERAGE is a BLENDED constant, same spirit as ECAR's
REG_SEASON_WIN_LEVERAGE, but using the BOTTOM-4 tier instead of the
bye/QF tiers, and critically using a DIFFERENT band for the win-value
derivative (confirmed with the user): the 2-7 win band, not ECAR's
10th-90th-percentile band (which centers on the 5-9 win middle). The
2-7 win band is deliberately shifted toward the LOSSES-heavy side of
the standings distribution, since it's the bottom-4 bubble (missing
the middle tier and landing in punishment, or vice versa) that matters
for this stat, not the bye/QF bubble:

    REG_SEASON_LOSS_LEVERAGE =
        dP(bottom4)/dWin * [P(worst_punishment | bottom4 seed)
                             - P(worst_punishment | middle seed)]

dP(bottom4)/dWin is a single scalar per season (not per-team,
not per-week), obtained by fitting a logistic regression of
made_bottom4 ~ wins on the pooled (team x trial) dataset, then taking
the BAND-AVERAGED derivative over every integer win total in [2, 7]
(same band-average method as ECAR -- averaging the slope over a
band is more stable than a single point-estimate, since logistic
curves are steepest in the middle of their own range and flatten at
the tails).

Note the sign here: a team's bottom4-seed probability DECREASES as
wins increase (dP(bottom4)/dWin is negative, unlike ECAR's
dP(bye)/dWin which is positive), and P(worst_punishment|bottom4) is
much higher than P(worst_punishment|middle), so the product
REG_SEASON_LOSS_LEVERAGE itself comes out NEGATIVE (more wins -> lower
P(bottom4) -> lower P(worst_punishment), a "good" relationship from
the team's perspective). The -WAR_week sign flip at combination time
(see SIGN CONVENTION above) is what turns this into "a good regular
season week SUBTRACTS from EPAR" as intended -- the two sign flips
(the leverage constant's own natural sign, and the explicit -WAR_week
flip) combine correctly; see compute_leverage_constants' docstring for
the arithmetic detail.

PUNISHMENT_SF_LEVERAGE / PUNISHMENT_FINAL_LEVERAGE are each
P(worst_punishment | lose this round) - P(worst_punishment | win this
round) -- note this is LOSE-minus-WIN, the opposite subtraction order
from ECAR's WIN-minus-LOSE, because here losing is the bad outcome
being measured. Both come out positive (losing a punishment-bracket
game increases your odds of being worst_punishment) given the
loser's-bracket shape described above: losing the SF means you then
play the punishment final (0% -> 50% chance of ending up worst), and
losing the final means certain worst_punishment (0% -> 100%). Both are
estimated directly from the simulator's pooled punishment-bracket game
outcomes.

--------------------------------------------------------------------------
WAR_week
--------------------------------------------------------------------------
Identical formula/plumbing to calculate_ECAR.py (imported from
CalculateWAR.py): P = credited points - replacement level that week,
D_relative = season-long regular-season (weeks 1-14) starter average at
that position, WAR_week = Phi((P-D_relative)/MARGIN_SIGMA) -
Phi((-D_relative)/MARGIN_SIGMA). Weeks 1-17 are all processed (not just
1-14), since weeks 16-17 feed the punishment leverage terms, exactly
like ECAR needed weeks 15-17 for the championship leverage terms.

--------------------------------------------------------------------------
FILES
--------------------------------------------------------------------------
Reads (under PythonData/draftData/):
  draft_{YEAR}.json                    cached/enriched draft board
                                        (shared with CalculateWAR.py /
                                        CalculateHistoricalWAR.py /
                                        calculate_ECAR.py)
  par_zero_score_review_{YEAR}.json    manual "did they actually play?"
                                        log (shared DNP semantics)

Writes (under PythonData/draftData/):
  par_zero_score_review_{YEAR}.json    extended with any newly
                                        auto-flagged zero-score weeks
                                        15-17
  epar_leverage_{YEAR}.json          the three derived leverage
                                        constants + simulator
                                        diagnostics for that season
  epar_{YEAR}.json                   one row per drafted player:
                                        {year, pick, round, player_id,
                                         player_name, position,
                                         war_regular_season,
                                         war_week16_punishment_semifinal,
                                         war_week17_punishment_final,
                                         epar_regular_season,
                                         epar_punishment_semifinal,
                                         epar_punishment_final,
                                         epar_total}
                                        sorted by pick.

Images written (into Website/girderma-gridiron-website/src/
league_stats_output/CurrentSeason/DraftBoards/EPAR/), same visual
convention as CalculateWAR.py's WAR board and calculate_ECAR.py's
ECAR board:
  draft_board_by_epar_{YEAR}.png           grid colored by epar_total
  draft_board_by_epar_{YEAR}_colorbar.png  legend strip for the gradient

Usage:
    python3 calculate_EPAR.py                   # runs 2024 and 2025
    python3 calculate_EPAR.py --years 2024
    python3 calculate_EPAR.py --skip-simulation  # reuse a previously
                                                    # saved leverage file

From another file, reusing an already-authenticated league object:
    from calculate_EPAR import run_year
    run_year(2025, league=lg)
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
# script, so EPAR's underlying win-probability math never drifts
# from WAR's/ECAR's.
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
# YEAR -> LEAGUE ID (same ids as CalculateHistoricalWAR.py / calculate_ECAR.py)
# --------------------------------------------------------------------------
LEAGUE_IDS = {
    2024: "449.l.106896",
    2025: "461.l.111150",
}

# Per explicit instruction: 2024 and 2025 only.
YEARS_TO_RUN = [2024, 2025]

SCRIPT_DIR = os.path.dirname(os.path.abspath(__file__))
PYTHON_DATA_DIR = Path(SCRIPT_DIR) / ".."
DRAFT_DATA_DIR = PYTHON_DATA_DIR / "draftData"
OAUTH_FILE = str(PYTHON_DATA_DIR / "oauth2.json")

# --------------------------------------------------------------------------
# LEAGUE / BRACKET STRUCTURE (same values as RunWeekly.py's SIM_* constants)
# --------------------------------------------------------------------------
NUM_TEAMS = 14
REGULAR_SEASON_WEEKS = 14          # weeks 1-14
PUNISHMENT_WEEKS = {16: "punishment_semifinal", 17: "punishment_final"}

SIM_BYE_SPOTS = 2                  # seeds 1-2 -> bye to semifinals (championship bracket)
SIM_PLAYOFF_SPOTS = 4              # seeds 3-6 -> quarterfinal (championship bracket)
SIM_PUNISHMENT_SPOTS = 4           # seeds 11-14 -> punishment bracket
# seeds 7-10 make neither bracket ("middle" tier, used as the comparison
# tier for the punishment regular-season leverage below)

# Number of teams actually competing in each punishment-bracket round
# (confirmed with the user, same mechanism as calculate_ECAR.py's
# ROUND_PARTICIPANTS): the punishment SF involves all 4 bottom seeds,
# the punishment Final involves the 2 SF LOSERS (still 2 of 14 teams).
# Used to weight each player's punishment-week EPAR contribution by
# the probability that a RANDOMLY CHOSEN one of the 14 teams was even
# in that round -- see write_epar_output's docstring for the full
# rationale.
ROUND_PARTICIPANTS = {"sf": 4, "final": 2}

# --------------------------------------------------------------------------
# LEVERAGE SIMULATOR CONSTANTS
# --------------------------------------------------------------------------
LEVERAGE_N_SIMULATIONS = 20_000
LEVERAGE_LEAGUE_MEAN_SCORE = 110.0   # arbitrary but plausible; irrelevant
                                      # to outcomes since all teams are
                                      # symmetric (only sigma matters)
LEVERAGE_RANDOM_SEED = 42            # fixed seed -> reproducible leverage
                                      # constants across runs
LEVERAGE_BAND = (2, 7)               # band-average window for the
                                      # regular-season win-value
                                      # derivative (confirmed with the
                                      # user: shifted toward the
                                      # losses-heavy side of the
                                      # standings, relevant to the
                                      # bottom-4 bubble, NOT ECAR's
                                      # 10th-90th-percentile middle band)


def draft_cache_path(year: int) -> Path:
    return DRAFT_DATA_DIR / f"draft_{year}.json"


def zero_score_review_path(year: int) -> Path:
    return DRAFT_DATA_DIR / f"par_zero_score_review_{year}.json"


def leverage_output_path(year: int) -> Path:
    return DRAFT_DATA_DIR / f"epar_leverage_{year}.json"


def epar_output_path(year: int) -> Path:
    return DRAFT_DATA_DIR / f"epar_{year}.json"


# --------------------------------------------------------------------------
# DRAFT BOARD IMAGE OUTPUT (same website output tree convention as
# CalculateWAR.py's WAR board / calculate_ECAR.py's ECAR board)
# --------------------------------------------------------------------------
def epar_board_dir(year: int) -> Path:
    return (
        Path(SCRIPT_DIR) / ".." / ".." / "Website" / "girderma-gridiron-website"
        / "src" / "league_stats_output" / "CurrentSeason" / "DraftBoards" / "EPAR"
    ).resolve()


def epar_board_image_path(year: int) -> Path:
    return epar_board_dir(year) / f"draft_board_by_epar_{year}.png"


DEFAULT_TEXT_COLOR = "#374151"


# --------------------------------------------------------------------------
# AUTH
# --------------------------------------------------------------------------
def get_league(year: int):
    league_id = LEAGUE_IDS.get(year)
    if not league_id:
        raise ValueError(
            f"No Yahoo league id configured for {year}. EPAR is only "
            f"configured for {sorted(LEAGUE_IDS)}."
        )
    sc = OAuth2(None, None, from_file=OAUTH_FILE)
    gm = yfa.Game(sc, "nfl")
    return gm.to_league(league_id)


# ==========================================================================
# PART 1: BRACKET MONTE CARLO SIMULATOR (schedule/team-agnostic)
#
# Extends calculate_ECAR.py's simulator with the punishment bracket
# (seeds 11-14, 2-round single elimination: SF then Final). The
# championship-bracket half (byes/QF/SF/Final for seeds 1-6) is NOT
# needed for EPAR and is therefore not simulated here at all -- only
# regular season + punishment bracket are modeled, keeping this
# simulator leaner than ECAR's.
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


def simulate_one_punishment_trial(rng: np.random.Generator, n_teams: int = NUM_TEAMS,
                                   reg_weeks: int = REGULAR_SEASON_WEEKS,
                                   sigma: float = GAME_SIGMA,
                                   mean_score: float = LEVERAGE_LEAGUE_MEAN_SCORE,
                                   bye_spots: int = SIM_BYE_SPOTS,
                                   playoff_spots: int = SIM_PLAYOFF_SPOTS,
                                   punishment_spots: int = SIM_PUNISHMENT_SPOTS) -> dict:
    """
    Simulate one full regular season + punishment bracket for n_teams
    symmetric, schedule-agnostic teams.

    Returns a dict with per-team regular season results, each team's
    tier ("bottom4" for the punishment-bracket seeds, "middle" for
    seeds 7-10, "upper" for seeds 1-6 -- "upper" is a catch-all since
    this simulator doesn't play out the championship bracket, it's only
    needed to exclude those teams from the punishment tier value
    comparison), and the punishment bracket's game-by-game results plus
    which team ended up "worst_punishment" (the loser of the punishment
    final).
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
    # RunWeekly.py's simulate_season / calculate_ECAR.py's simulator.
    ranked = sorted(teams, key=lambda t: (wins[t], points[t]), reverse=True)
    upper_seeds = ranked[:bye_spots + playoff_spots]            # seeds 1-6
    middle_seeds = ranked[bye_spots + playoff_spots:n_teams - punishment_spots]  # seeds 7-10
    bottom4_seeds = ranked[n_teams - punishment_spots:]          # seeds 11-14

    tier_by_team = {t: "upper" for t in teams}
    for t in middle_seeds:
        tier_by_team[t] = "middle"
    for t in bottom4_seeds:
        tier_by_team[t] = "bottom4"

    result = {
        "wins_by_team": wins,
        "tier_by_team": tier_by_team,
        "worst_punishment": None,
        "sf_games": [],      # punishment semifinal games (week 16)
        "final_games": [],   # punishment final game (week 17)
    }

    if punishment_spots != 4:
        # Bracket shape assumed below needs exactly 4 bottom seeds;
        # guard defensively even though this repo's constants satisfy it.
        return result

    # Punishment semifinal: pair by seed within the bottom-4 group --
    # worst seed (bottom4_seeds[3], i.e. dead last) vs 3rd-worst
    # (bottom4_seeds[1]), 2nd-worst (bottom4_seeds[2]) vs 4th-worst-of-
    # the-bottom-4 (bottom4_seeds[0], i.e. the "best of the worst").
    # WINNERS are safe (0% chance of worst_punishment); LOSERS advance
    # to the punishment final -- see module docstring's "THE PUNISHMENT
    # BRACKET" section for why this loser's-bracket shape is the only
    # one consistent with "winning is always good." The exact seeding
    # convention (who plays whom) doesn't bias the leverage estimate
    # since all teams are symmetric; any fixed pairing works.
    sf_pairs = [(bottom4_seeds[0], bottom4_seeds[3]), (bottom4_seeds[1], bottom4_seeds[2])]
    sf_losers = []
    for a, b in sf_pairs:
        a_wins = _play_game(mean_score, mean_score, sigma, rng)
        winner, loser = (a, b) if a_wins else (b, a)
        sf_losers.append(loser)
        result["sf_games"].append({"winner": winner, "loser": loser})

    # Punishment final: the two SF LOSERS play each other. The LOSER of
    # this game is worst_punishment for this trial; the winner escapes
    # with the second-worst finish.
    a, b = sf_losers
    a_wins = _play_game(mean_score, mean_score, sigma, rng)
    final_winner, worst_punishment = (a, b) if a_wins else (b, a)
    result["final_games"].append({"winner": final_winner, "loser": worst_punishment})
    result["worst_punishment"] = worst_punishment

    return result


def run_leverage_simulation(n_simulations: int = LEVERAGE_N_SIMULATIONS,
                             seed: int = LEVERAGE_RANDOM_SEED) -> dict:
    """
    Run the punishment-bracket Monte Carlo n_simulations times and
    compute:
      - pooled (wins, made_bottom4) samples
      - P(worst_punishment | bottom4 seed), P(worst_punishment | middle seed)
      - P(worst_punishment | win SF) vs P(worst_punishment | lose SF),
        and the same pair for the punishment Final

    Returns a dict of raw pooled arrays + tier/round rate summaries
    (consumed by compute_leverage_constants below).
    """
    rng = np.random.default_rng(seed)

    all_wins = []
    all_made_bottom4 = []

    tier_counts = {"upper": 0, "middle": 0, "bottom4": 0}
    tier_worst_counts = {"upper": 0, "middle": 0, "bottom4": 0}

    round_game_counts = {"sf": 0, "final": 0}
    round_winner_was_worst = {"sf": 0, "final": 0}
    round_loser_was_worst = {"sf": 0, "final": 0}

    for _ in range(n_simulations):
        trial = simulate_one_punishment_trial(rng)
        wins_by_team = trial["wins_by_team"]
        tier_by_team = trial["tier_by_team"]
        worst_punishment = trial["worst_punishment"]

        for t, w in wins_by_team.items():
            tier = tier_by_team[t]
            all_wins.append(w)
            all_made_bottom4.append(1 if tier == "bottom4" else 0)

            tier_counts[tier] += 1
            if t == worst_punishment:
                tier_worst_counts[tier] += 1

        for round_name, games in (("sf", trial["sf_games"]),
                                   ("final", trial["final_games"])):
            for game in games:
                round_game_counts[round_name] += 1
                if game["winner"] == worst_punishment:
                    round_winner_was_worst[round_name] += 1
                if game["loser"] == worst_punishment:
                    round_loser_was_worst[round_name] += 1

    tier_worst_rate = {
        tier: (tier_worst_counts[tier] / tier_counts[tier] if tier_counts[tier] else 0.0)
        for tier in tier_counts
    }

    round_leverage = {}
    for round_name in ("sf", "final"):
        n_games = round_game_counts[round_name]
        p_worst_if_win = round_winner_was_worst[round_name] / n_games if n_games else 0.0
        p_worst_if_lose = round_loser_was_worst[round_name] / n_games if n_games else 0.0
        # LOSE-minus-WIN (opposite order from ECAR's round_leverage),
        # since losing is the bad outcome being measured here -- this
        # comes out positive (losing increases your odds of being
        # worst_punishment).
        round_leverage[round_name] = {
            "p_worst_if_win": p_worst_if_win,
            "p_worst_if_lose": p_worst_if_lose,
            "leverage": p_worst_if_lose - p_worst_if_win,
            "n_games": n_games,
        }

    return {
        "n_simulations": n_simulations,
        "wins": np.array(all_wins, dtype=float),
        "made_bottom4": np.array(all_made_bottom4, dtype=float),
        "tier_worst_rate": tier_worst_rate,
        "round_leverage": round_leverage,
    }


# ==========================================================================
# PART 2: LOGISTIC FIT + BAND-AVERAGED DERIVATIVE (identical method to
# calculate_ECAR.py's logistic_slope_band_average, just with this
# script's own LEVERAGE_BAND = (2, 7) instead of ECAR's (10, 90)
# percentile-based band)
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
        grad0 = np.sum(y - p)
        grad1 = np.sum((y - p) * x)
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
                                 band: tuple = LEVERAGE_BAND) -> dict:
    """
    Fit a 1-D logistic curve P(y=1 | x) and return the BAND-AVERAGED
    derivative dP/dx, averaged over every integer x within the fixed
    [low, high] win band (confirmed with the user: (2, 7) for EPAR,
    the losses-heavy side of the standings distribution relevant to the
    bottom-4 bubble -- NOT a percentile-derived band like ECAR's).

    dP/dx for a logistic curve P = sigmoid(b0 + b1*x) is:
        b1 * P * (1 - P)
    """
    b0, b1 = _fit_logistic_1d(x, y)

    lo, hi = band
    band_x = np.arange(lo, hi + 1)

    p_band = 1.0 / (1.0 + np.exp(-(b0 + b1 * band_x)))
    slopes = b1 * p_band * (1.0 - p_band)
    band_avg_slope = float(np.mean(slopes))

    return {
        "intercept": float(b0),
        "coef": float(b1),
        "band_low": int(lo),
        "band_high": int(hi),
        "band_avg_derivative": band_avg_slope,
    }


# ==========================================================================
# PART 3: COMBINE INTO THE THREE LEVERAGE CONSTANTS
# ==========================================================================
def compute_leverage_constants(sim_results: dict) -> dict:
    """
    Combines the raw simulator output into the three EPAR leverage
    constants (REG_SEASON_LOSS_LEVERAGE, PUNISHMENT_SF_LEVERAGE,
    PUNISHMENT_FINAL_LEVERAGE), plus full diagnostics for auditability.

    SIGN NOTE: REG_SEASON_LOSS_LEVERAGE itself comes out NEGATIVE here
    (dP(bottom4)/dWin is negative -- more wins means less likely to be
    in the bottom-4 tier -- multiplied by a POSITIVE tier-value gap
    [P(worst|bottom4) - P(worst|middle)], since landing in the bottom-4
    tier is worse). write_epar_output applies this constant DIRECTLY
    to WAR_week with NO extra sign flip (unlike the punishment SF/Final
    terms, which do get an explicit flip -- see module docstring's
    "THE THREE LEVERAGE CONSTANTS" section for the full derivation of
    why these two groups need different treatment). A negative
    REG_SEASON_LOSS_LEVERAGE times a positive WAR_week (a good week) is
    already negative, i.e. already SUBTRACTS from EPAR without any
    extra flip -- do not add one.
    """
    bottom4_fit = logistic_slope_band_average(sim_results["wins"], sim_results["made_bottom4"])

    tier_rate = sim_results["tier_worst_rate"]
    bottom4_value_over_middle = tier_rate["bottom4"] - tier_rate["middle"]

    reg_season_loss_leverage = bottom4_fit["band_avg_derivative"] * bottom4_value_over_middle

    round_leverage = sim_results["round_leverage"]

    return {
        "REG_SEASON_LOSS_LEVERAGE": reg_season_loss_leverage,
        "PUNISHMENT_SF_LEVERAGE": round_leverage["sf"]["leverage"],
        "PUNISHMENT_FINAL_LEVERAGE": round_leverage["final"]["leverage"],
        "diagnostics": {
            "n_simulations": sim_results["n_simulations"],
            "dP_bottom4_dWin": bottom4_fit,
            "tier_worst_rate": tier_rate,
            "bottom4_value_over_middle": bottom4_value_over_middle,
            "round_leverage": round_leverage,
        },
    }


def get_or_run_leverage_constants(year: int, skip_simulation: bool = False) -> dict:
    """
    Loads epar_leverage_{YEAR}.json if --skip-simulation was passed
    and the file already exists; otherwise runs the Monte Carlo
    simulator fresh and writes it. The simulator itself does not depend
    on `year` at all (schedule/team-agnostic, fixed league structure
    constants) -- re-run per year only so each season's leverage file is
    self-contained/auditable.
    """
    out_path = leverage_output_path(year)
    if skip_simulation and out_path.exists():
        print(f"[{year}] Reusing cached leverage constants -> {out_path}")
        with open(out_path, "r") as f:
            return json.load(f)

    print(f"[{year}] Running punishment-bracket leverage Monte Carlo "
          f"({LEVERAGE_N_SIMULATIONS:,} trials)...")
    sim_results = run_leverage_simulation()
    leverage = compute_leverage_constants(sim_results)

    print(f"[{year}] REG_SEASON_LOSS_LEVERAGE  = {leverage['REG_SEASON_LOSS_LEVERAGE']:+.5f}")
    print(f"[{year}] PUNISHMENT_SF_LEVERAGE    = {leverage['PUNISHMENT_SF_LEVERAGE']:+.5f}")
    print(f"[{year}] PUNISHMENT_FINAL_LEVERAGE = {leverage['PUNISHMENT_FINAL_LEVERAGE']:+.5f}")

    DRAFT_DATA_DIR.mkdir(parents=True, exist_ok=True)
    with open(out_path, "w") as f:
        json.dump(leverage, f, indent=2)
    print(f"[{year}] Saved -> {out_path}")

    return leverage


# ==========================================================================
# PART 4: DRAFT BOARD (identical enrichment to calculate_ECAR.py /
# CalculateHistoricalWAR.py)
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
# PART 5: PER-WEEK WAR, EXTENDED THROUGH WEEKS 15-17 (week 15 is
# computed for parity/consistency with ECAR's shared plumbing and the
# zero-score review file, even though EPAR itself only uses weeks
# 1-14, 16, 17)
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
    Weeks 1 through 17. Confirms playoff_start_week == 15 against
    Yahoo's own league settings rather than hardcoding it blindly,
    since this script's week-16/17 punishment-round labels depend on
    that assumption.
    """
    settings = league.settings()
    playoff_start = int(settings.get("playoff_start_week", 15))
    if playoff_start != 15:
        print(f"  \u26a0 league.settings()['playoff_start_week'] = {playoff_start}, "
              f"expected 15. Punishment round week labels (SF=16/Final=17) "
              f"may not line up correctly for this season.")
    return list(range(1, 18))


def calculate_war_by_week(league, board: list) -> tuple:
    """
    Returns (war_by_id_by_week, position_averages).

    war_by_id_by_week: {week: {player_id: WAR_week}} for weeks 1-17.
    position_averages: {position: D} computed from REGULAR SEASON weeks
    only (1-14), exactly like the existing WAR scripts / calculate_ECAR.py.
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
          f"playoff/punishment weeks: {[w for w in weeks if w > REGULAR_SEASON_WEEKS]})")

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
# PART 6: COMBINE WAR + LEVERAGE INTO EPAR, WRITE OUTPUT
# ==========================================================================
def write_epar_output(year: int, board: list, war_by_id_by_week: dict,
                         leverage: dict) -> None:
    """
    SIGN CONVENTION (see module docstring's "THE THREE LEVERAGE
    CONSTANTS" section for the full derivation): the two leverage
    groups have opposite natural polarity, so they are combined with
    WAR_week differently to reach the same final polarity (good
    performance subtracts from EPAR, bad performance adds to it):
      - regular season: EPAR_week = +WAR_week * REG_SEASON_LOSS_LEVERAGE
                         (REG_SEASON_LOSS_LEVERAGE is already negative,
                         no extra flip needed)
      - punishment SF/Final: EPAR_week = -WAR_week * PUNISHMENT_*_LEVERAGE
                         (PUNISHMENT_*_LEVERAGE is always positive,
                         needs the explicit flip)

    ROUND-PARTICIPATION WEIGHTING (confirmed with the user, same
    mechanism as calculate_ECAR.py's write_ecar_output): EPAR is
    meant to answer "if this player's performance had belonged to a
    RANDOMLY CHOSEN one of the 14 teams, what's the expected
    worst-punishment-probability-added?" Only 4 of 14 teams reach the
    punishment semifinal and only 2 of 14 reach the punishment final,
    so each punishment week's leverage is scaled by
    (round_participants / NUM_TEAMS) before combining with WAR_week --
    without this, every player's punishment-week WAR was credited at
    full round-stakes as if certain to matter, overweighting a single
    bad punishment-final week relative to a full season of regular-
    season weeks. This can reorder players relative to the unweighted
    version.
    """
    reg_leverage = leverage["REG_SEASON_LOSS_LEVERAGE"]
    sf_leverage = leverage["PUNISHMENT_SF_LEVERAGE"] * (ROUND_PARTICIPANTS["sf"] / NUM_TEAMS)
    final_leverage = leverage["PUNISHMENT_FINAL_LEVERAGE"] * (ROUND_PARTICIPANTS["final"] / NUM_TEAMS)

    rows = []
    for p in board:
        pid = p["player_id"]

        war_reg_season = sum(
            war_by_id_by_week.get(week, {}).get(pid, 0.0)
            for week in range(1, REGULAR_SEASON_WEEKS + 1)
        )
        war_week16 = war_by_id_by_week.get(16, {}).get(pid, 0.0)
        war_week17 = war_by_id_by_week.get(17, {}).get(pid, 0.0)

        epar_reg_season = war_reg_season * reg_leverage
        epar_punishment_sf = -war_week16 * sf_leverage
        epar_punishment_final = -war_week17 * final_leverage
        epar_total = epar_reg_season + epar_punishment_sf + epar_punishment_final

        rows.append({
            "year": year,
            "pick": p["pick"],
            "round": p["round"],
            "player_id": pid,
            "player_name": p["player_name"],
            "position": p["position"],
            "war_regular_season": war_reg_season,
            "war_week16_punishment_semifinal": war_week16,
            "war_week17_punishment_final": war_week17,
            "epar_regular_season": epar_reg_season,
            "epar_punishment_semifinal": epar_punishment_sf,
            "epar_punishment_final": epar_punishment_final,
            "epar_total": epar_total,
        })

    rows.sort(key=lambda r: r["pick"])

    out_path = epar_output_path(year)
    DRAFT_DATA_DIR.mkdir(parents=True, exist_ok=True)
    with open(out_path, "w") as f:
        json.dump(rows, f, indent=2)
    print(f"[{year}] Saved -> {out_path} ({len(rows)} players)")


def print_top_epar(year: int, rows_path: Path, top_n: int = 15) -> None:
    """Prints the top players by epar_total -- i.e. the players who
    contributed MOST to a punishment-bracket loss (highest EPAR =
    worst contribution, due to the sign convention)."""
    with open(rows_path, "r") as f:
        rows = json.load(f)
    ranked = sorted(rows, key=lambda r: -r["epar_total"])
    print(f"\n=== [{year}] Top {top_n} players by EPAR "
          f"(highest = most contribution to a punishment-bracket loss) ===")
    for r in ranked[:top_n]:
        print(f"  {r['player_name']:<26} {r['position']:<4} "
              f"EPAR {r['epar_total']:+.4f}  "
              f"(reg {r['epar_regular_season']:+.4f}, "
              f"punishment_sf {r['epar_punishment_semifinal']:+.4f}, "
              f"punishment_final {r['epar_punishment_final']:+.4f})")


# ==========================================================================
# PART 7: DRAFT BOARD IMAGE (same grid/visual convention as
# CalculateWAR.py's render_war_board and calculate_ECAR.py's
# render_ecar_board)
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


def render_epar_board(year: int, rounds, columns, cell_by_round_and_team,
                         epar_by_id: dict) -> None:
    """
    Diverging gradient split at zero, identical scheme to
    CalculateWAR.py's render_war_board / calculate_ECAR.py's
    render_ecar_board: positive EPAR (contributed to a punishment
    loss -- a BAD outcome for that player) uses 'Reds' (darker =
    worse), negative EPAR (helped avoid the punishment loss) uses
    'Blues' (darker = more negative/better). Each half normalized
    independently against this run's actual max/min.
    """
    epar_values = [epar_by_id.get(p["player_id"], 0.0) for p in cell_by_round_and_team.values()]
    epar_max = max((v for v in epar_values if v > 0), default=1.0) or 1.0
    epar_min = min((v for v in epar_values if v < 0), default=-1.0) or -1.0

    reds = matplotlib.colormaps["Reds"]
    blues = matplotlib.colormaps["Blues"]

    def intensity(value: float) -> float:
        if value >= 0:
            return value / epar_max if epar_max else 0.0
        return value / epar_min if epar_min else 0.0

    def cell_color(pick):
        if pick is None:
            return "#FFFFFF"
        epar = epar_by_id.get(pick["player_id"], 0.0)
        t = intensity(epar)
        return reds(t) if epar >= 0 else blues(t)

    def text_color(pick):
        if pick is None:
            return DEFAULT_TEXT_COLOR
        epar = epar_by_id.get(pick["player_id"], 0.0)
        return "#FFFFFF" if intensity(epar) > 0.6 else "#111827"

    def label(pick):
        epar = epar_by_id.get(pick["player_id"], 0.0)
        return f"#{pick['pick']}  {epar:+.3f}\n{pick['player_name']}"

    board_dir = epar_board_dir(year)
    board_dir.mkdir(parents=True, exist_ok=True)
    board_image_path = epar_board_image_path(year)

    _draw_board(
        rounds, columns, cell_by_round_and_team,
        cell_color_fn=cell_color,
        text_color_fn=text_color,
        cell_label_fn=label,
        title=f"{year} Draft Board -- Expected Punishments "
              f"Above Replacement (EPAR)",
        output_path=board_image_path,
        legend_handles=None,
    )

    # Colorbar legend strip: blue (very negative -> helped avoid
    # punishment) on the left, through white at zero, to red (very
    # positive -> contributed to punishment loss) on the right.
    n_stops = 256
    blue_half = [blues(1.0 - i / (n_stops // 2 - 1)) for i in range(n_stops // 2)]
    red_half = [reds(i / (n_stops // 2 - 1)) for i in range(n_stops // 2)]
    diverging_cmap = matplotlib.colors.ListedColormap(blue_half + red_half)

    fig, ax = plt.subplots(figsize=(6, 0.6))
    fig.subplots_adjust(bottom=0.5)
    norm_ = matplotlib.colors.Normalize(vmin=epar_min, vmax=epar_max)
    mappable = matplotlib.cm.ScalarMappable(norm=norm_, cmap=diverging_cmap)
    cb = fig.colorbar(mappable, cax=ax, orientation="horizontal")
    cb.set_label("EPAR (helped avoid punishment -> contributed to punishment loss)", fontsize=9)
    colorbar_path = board_image_path.with_name(board_image_path.stem + "_colorbar.png")
    fig.savefig(colorbar_path, dpi=200, bbox_inches="tight")
    plt.close(fig)
    print(f"Saved -> {colorbar_path}")


def render_epar_draft_board(year: int, board: list, rows_path: Path) -> None:
    """Loads the just-written epar_{YEAR}.json rows and renders the
    draft board image colored by epar_total."""
    with open(rows_path, "r") as f:
        rows = json.load(f)
    epar_by_id = {r["player_id"]: r["epar_total"] for r in rows}

    rounds, columns, cell_by_round_and_team = build_board_grid(board)
    render_epar_board(year, rounds, columns, cell_by_round_and_team, epar_by_id)


# ==========================================================================
# ORCHESTRATION
# ==========================================================================
def run_year(year: int, force_refresh_draft: bool = False, skip_simulation: bool = False,
             league=None) -> None:
    """
    league: optional already-authenticated league for `year`. If
    omitted, authenticates fresh (same convention as
    CalculateHistoricalWAR.run_year / calculate_ECAR.run_year).
    """
    if year not in LEAGUE_IDS:
        raise ValueError(
            f"EPAR is only configured to run on {sorted(LEAGUE_IDS)}. "
            f"Got year={year}."
        )

    print(f"\n{'=' * 72}\n{year} SEASON -- EPAR\n{'=' * 72}")

    leverage = get_or_run_leverage_constants(year, skip_simulation=skip_simulation)

    if league is None:
        league = get_league(year)

    board = load_draft_board(league, year, force_refresh=force_refresh_draft)

    year_for_review[0] = year
    war_by_id_by_week, position_averages = calculate_war_by_week(league, board)

    write_epar_output(year, board, war_by_id_by_week, leverage)
    print_top_epar(year, epar_output_path(year))
    render_epar_draft_board(year, board, epar_output_path(year))


def main():
    parser = argparse.ArgumentParser(
        description="Calculate EPAR (Expected Punishments Above "
                    "Replacement) for completed historical seasons."
    )
    parser.add_argument("--years", type=int, nargs="+", default=YEARS_TO_RUN,
                         help=f"Seasons to process (default: {YEARS_TO_RUN}). "
                              f"Only {sorted(LEAGUE_IDS)} are currently configured.")
    parser.add_argument("--force-refresh-draft", action="store_true",
                         help="Re-pull draft results/enrichment from Yahoo even if a "
                              "draft_{YEAR}.json cache already exists.")
    parser.add_argument("--skip-simulation", action="store_true",
                         help="Reuse a previously saved epar_leverage_{YEAR}.json "
                              "instead of re-running the bracket Monte Carlo step.")
    args = parser.parse_args()

    for year in args.years:
        run_year(year, force_refresh_draft=args.force_refresh_draft,
                  skip_simulation=args.skip_simulation)


if __name__ == "__main__":
    main()
