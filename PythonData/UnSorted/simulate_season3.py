"""
Simulates the rest of the fantasy football season.

1. Build the schedule -- either pulled straight from Yahoo or hardcoded by you.
2. Track odds of someone 2-0ing (or getting 2-0ed by) their rival.
3. Simulate the postseason bracket (top-6 winners bracket w/ byes for 1-2,
   bottom-4 "toilet bowl" where losers advance to determine dead last).
4. Pull projected points for every rostered player, each week.
5. For each team-week, solve for the *optimal* starting lineup given full
   position eligibility (not just primary position), filling any empty
   slot with REPLACEMENT_POINTS.
6. Monte-Carlo simulate each team-week score as Normal(mu, VARIANCE) and
   simulate every remaining game, including the playoff bracket.

TODOs you still need to fill in (flagged inline too):
  - Step 2: your real projections + bye-week loader.
  - build_schedule_from_yahoo(): the exact JSON path for league.matchups()
    responses can vary by yahoo_fantasy_api version -- verify against one
    real response and adjust _parse_yahoo_matchup_week() if needed.
  - HARDCODED_SCHEDULE: fill in by hand if you'd rather not rely on the
    Yahoo matchups call.
"""

import json
import random
from collections import defaultdict

import numpy as np
import pandas as pd

from yahoo_oauth import OAuth2
import yahoo_fantasy_api as yfa

# --------------------------------------------------------------------------
# CONFIG
# --------------------------------------------------------------------------
YEAR = 2026
REGULAR_SEASON_WEEKS = 14           # weeks 1-14 = regular season
PLAYOFF_WEEKS = (15, 16, 17)        # (quarterfinal/round1, semifinal, final)
ALL_WEEKS = list(range(1, REGULAR_SEASON_WEEKS + 1)) + list(PLAYOFF_WEEKS)

VARIANCE = 33 ** 2  # can revisit by looking at past-season score variance
N_SIMULATIONS = 10_000

# Standard 9-starter lineup. Adjust to match your league's actual roster
# settings (league.settings() from yahoo_fantasy_api will tell you this).
ROSTER_SLOTS = {
    "qb": 1,
    "rb": 2,
    "wr": 2,
    "te": 1,
    "flex": 1,   # rb/wr/te
    "k": 1,
    "dst": 1,
}
FLEX_ELIGIBLE = {"rb", "wr", "te"}

LEAGUE_IDS = {
    2026: "485.l.205662",  # <-- replace with your real league id
}

REPLACEMENT_POINTS = {
    "qb": 15,
    "rb": 4,
    "wr": 5.5,
    "te": 7,
    "k": 7.5,
    "dst": 6.5,
}

OAUTH_FILE = "oauth2.json"
ROSTER_WEEK = 1

# Hardcoded rivalry pairs -- every team plays its rival a 2nd time.
RIVALS = {
    "Ma\u00eetre Stick": "Pad D's",
    "Pad D's": "Ma\u00eetre Stick",
    "You gotta be Falcon Kiddin me": "Girder\u2019s 6 Cookies",
    "Girder\u2019s 6 Cookies": "You gotta be Falcon Kiddin me",
    "No Punts Intented": "Hunter\u2019s Hunters",
    "Hunter\u2019s Hunters": "No Punts Intented",
    "Supernova\u2019s Studs": "Revy\u2019s Konstruction",
    "Revy\u2019s Konstruction": "Supernova\u2019s Studs",
    "Omaha Beach Real Estate": "Tsuga\u2019s Tuck Shop",
    "Tsuga\u2019s Tuck Shop": "Omaha Beach Real Estate",
    "Ozzy Stick": "Flow Brrr",
    "Flow Brrr": "Ozzy Stick",
    "Big Bad Hokkkk": "The Sage's Playmakers",
    "The Sage's Playmakers": "Big Bad Hokkkk",
}

# Fill this in by hand if you'd rather hardcode the schedule instead of
# pulling it from Yahoo. Format: {week: [(team1, team2), ...], ...}
HARDCODED_SCHEDULE = None

RANDOM_SEED = None  # set an int for reproducible runs

# Yahoo sometimes labels defense as "DEF" instead of "DST".
POSITION_ALIASES = {"def": "dst"}


# --------------------------------------------------------------------------
# STEP 1: LOAD ROSTERS FROM YAHOO
# --------------------------------------------------------------------------
def get_yahoo_league(year: int = YEAR, oauth_file: str = OAUTH_FILE):
    """Authenticate with Yahoo and return (sc, league)."""
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


def _normalize_positions(raw_positions) -> set:
    """Lowercase + alias-map a list of position strings from Yahoo."""
    out = set()
    for p in raw_positions or []:
        p = p.lower()
        p = POSITION_ALIASES.get(p, p)
        out.add(p)
    return out


def load_rosters_from_yahoo(year: int = YEAR, week: int = ROSTER_WEEK,
                             oauth_file: str = OAUTH_FILE) -> dict:
    """
    Pull every team's full roster from Yahoo (starters + bench together --
    _best_lineup_points() re-solves the optimal lineup itself, so which
    slot a player currently sits in doesn't matter).

    Returns: {team_name: [player_dict, ...]} where each player_dict is:
        {
          "name": str,
          "eligible_positions": set[str] (lowercased, e.g. {"rb","flex"}),
          "player_id": ...,
        }

    NOTE: eligible_positions (not just primary position) is what lets the
    lineup optimizer correctly consider a player for FLEX or any other
    slot they qualify for, regardless of whether Yahoo currently has them
    starting or on the bench.
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
            print(f"  \u26a0 could not fetch roster for {team_name} (week {week}): {e}")
            continue

        players = []
        for p in roster:
            # yahoo_fantasy_api typically returns 'eligible_positions' as a
            # list of position codes (e.g. ["RB", "WR"]). Fall back to
            # primary_position/position if eligible_positions is missing.
            eligible = p.get("eligible_positions")
            if not eligible:
                eligible = [p.get("primary_position") or p.get("position")]
            players.append({
                "name": p.get("name"),
                "eligible_positions": _normalize_positions(eligible),
                "player_id": p.get("player_id"),
            })

        rosters[team_name] = players
        print(f"  Loaded {team_name}: {len(players)} rostered players")

    return rosters


# --------------------------------------------------------------------------
# STEP 2: PROJECTIONS + BYE WEEKS
# --------------------------------------------------------------------------
# TODO: plug in your real projections/bye-week source here. The rest of
# this script expects:
#
#   projections: pd.DataFrame with columns ["name", "week", "proj_pts"]
#   bye_weeks: dict {player_name: bye_week_int}


# --------------------------------------------------------------------------
# STEP 3: COMPUTE TEAM MU (PROJECTED POINTS) PER TEAM PER WEEK
# --------------------------------------------------------------------------
def _empty_lineup_replacement_total() -> float:
    total = 0.0
    for pos, count in ROSTER_SLOTS.items():
        for _ in range(count):
            if pos == "flex":
                total += max(REPLACEMENT_POINTS[p] for p in FLEX_ELIGIBLE)
            else:
                total += REPLACEMENT_POINTS[pos]
    return total


def _best_lineup_points(players: list, week: int, projections: pd.DataFrame,
                         bye_weeks: dict) -> float:
    """
    Greedily fill each dedicated slot (qb/rb/wr/te/k/dst) with the
    highest-projected eligible player, then fill FLEX with whoever's left
    over from rb/wr/te with the highest points. This is optimal as long
    as the only shared slot is FLEX (true for standard rosters, where a
    player is really just "their position" plus generically FLEX-eligible
    if that position is rb/wr/te) -- there's no fixed-slot tradeoff greedy
    could miss, since taking the top player at a dedicated slot never
    costs you anything you couldn't also get by taking the next-best
    leftover for FLEX. Empty slots (not enough eligible players) get
    REPLACEMENT_POINTS.

    NOTE: this assumes standard eligibility (a player fills one specific
    position, generically flex-eligible if that's rb/wr/te). If your
    league has genuinely dual-eligible players outside that pattern (e.g.
    Superflex QB/WR), greedy per-position bucketing can still shortchange
    them since it doesn't reason about cross-position tradeoffs -- flag it
    if that's a real case in your league and it's worth revisiting.
    """
    available = [p for p in players if bye_weeks.get(p["name"]) != week]
    if not available:
        return _empty_lineup_replacement_total()

    week_proj = projections[projections["week"] == week]
    proj_lookup = dict(zip(week_proj["name"], week_proj["proj_pts"]))

    # Bucket each player under every specific position they're eligible
    # for (usually just one), sorted best-to-worst within each bucket.
    pools = defaultdict(list)
    for p in available:
        pts = proj_lookup.get(p["name"], 0.0)
        for pos in p["eligible_positions"]:
            if pos in REPLACEMENT_POINTS:  # qb/rb/wr/te/k/dst only
                pools[pos].append((p["name"], pts))
    for pos in pools:
        pools[pos].sort(key=lambda x: x[1], reverse=True)

    total = 0.0
    used = set()

    # Dedicated slots first.
    for pos, count in ROSTER_SLOTS.items():
        if pos == "flex":
            continue
        filled = 0
        for name, pts in pools.get(pos, []):
            if name in used:
                continue
            used.add(name)
            total += pts
            filled += 1
            if filled == count:
                break
        total += REPLACEMENT_POINTS[pos] * (count - filled)

    # FLEX from whoever's left over across rb/wr/te.
    flex_candidates = [
        (name, pts) for pos in FLEX_ELIGIBLE
        for name, pts in pools.get(pos, []) if name not in used
    ]
    flex_candidates.sort(key=lambda x: x[1], reverse=True)

    flex_filled = 0
    for name, pts in flex_candidates:
        if flex_filled == ROSTER_SLOTS["flex"]:
            break
        used.add(name)
        total += pts
        flex_filled += 1
    if flex_filled < ROSTER_SLOTS["flex"]:
        total += max(REPLACEMENT_POINTS[p] for p in FLEX_ELIGIBLE) * (ROSTER_SLOTS["flex"] - flex_filled)

    return total


def compute_weekly_team_points(rosters: dict, projections: pd.DataFrame,
                                bye_weeks: dict, weeks=ALL_WEEKS) -> dict:
    """Returns nested dict: team_mu[week][team] = projected points (float)."""
    team_mu = {week: {} for week in weeks}
    for team, players in rosters.items():
        for week in weeks:
            team_mu[week][team] = _best_lineup_points(players, week, projections, bye_weeks)
    return team_mu


# --------------------------------------------------------------------------
# STEP 4: SCHEDULE
# --------------------------------------------------------------------------
def _parse_yahoo_matchup_week(raw_matchups: dict) -> list:
    """
    Parse one week's worth of raw JSON from league.matchups(week) into a
    list of (team1_name, team2_name) tuples.

    yahoo_fantasy_api's League.matchups() returns the raw Yahoo Fantasy
    API response, which nests data roughly as:
        raw["fantasy_content"]["league"][1]["scoreboard"]["0"]["matchups"]
    with each matchup keyed "0", "1", ... and team names buried a few
    levels deeper under matchup["matchup"]["0"]["teams"][...]["team"][0].

    VERIFY THIS against a real response before relying on it -- the exact
    nesting has changed between yahoo_fantasy_api versions before. Print
    `raw_matchups` once and adjust the path below if it doesn't match.
    """
    pairs = []
    try:
        scoreboard = raw_matchups["fantasy_content"]["league"][1]["scoreboard"]
        matchups = scoreboard["0"]["matchups"]
        count = int(matchups.get("count", 0))
        for i in range(count):
            matchup = matchups[str(i)]["matchup"]
            teams_block = matchup["0"]["teams"]
            team_names = []
            for t_key in ("0", "1"):
                team_meta = teams_block[t_key]["team"][0]
                name = next(
                    (item["name"] for item in team_meta if isinstance(item, dict) and "name" in item),
                    None,
                )
                team_names.append(name)
            if len(team_names) == 2 and all(team_names):
                pairs.append(tuple(team_names))
    except (KeyError, ValueError, TypeError) as e:
        print(f"  \u26a0 could not parse matchups JSON, check the shape manually: {e}")
    return pairs


def build_schedule_from_yahoo(league, weeks: int = REGULAR_SEASON_WEEKS) -> dict:
    """Pull the real regular-season schedule directly from Yahoo, week by week."""
    schedule = {}
    for week in range(1, weeks + 1):
        raw = league.matchups(week)
        schedule[week] = _parse_yahoo_matchup_week(raw)
    return schedule


def build_schedule(league=None, weeks: int = REGULAR_SEASON_WEEKS,
                    hardcoded_schedule: dict = None) -> dict:
    """
    Returns {week: [(team1, team2), ...]}. Prefers hardcoded_schedule if
    given, otherwise pulls from the passed-in Yahoo league object.
    """
    if hardcoded_schedule is not None:
        return hardcoded_schedule
    if league is not None:
        return build_schedule_from_yahoo(league, weeks)
    raise ValueError(
        "build_schedule() needs either a Yahoo `league` object or a "
        "`hardcoded_schedule` dict -- there's no way to derive the real "
        "schedule (which weeks teams play which opponent) from anything "
        "else, since that's league-specific and not computable."
    )


# --------------------------------------------------------------------------
# STEP 5: SIMULATION (regular season + playoff bracket)
# --------------------------------------------------------------------------
def simulate_game(team1: str, team2: str, week: int, team_mu: dict, variance: float):
    """Simulate a single game. Returns (winner, score1, score2); winner is 1 or 2."""
    sigma = np.sqrt(variance)
    mu1 = team_mu[week][team1]
    mu2 = team_mu[week][team2]

    score1 = np.random.normal(mu1, sigma)
    score2 = np.random.normal(mu2, sigma)

    winner = 1 if score1 > score2 else 2
    return winner, score1, score2


def _simulate_playoff_bracket(seeds_ranked: list, team_mu: dict, variance: float) -> dict:
    """
    seeds_ranked: this trial's final regular-season order, best (seed 1)
    to worst (seed 14).

    Winners bracket (top 6): seeds 1-2 bye to semis. Quarterfinal: 3v6,
    4v5. Semis: remaining 4 teams reseeded (best remaining vs worst
    remaining). Final: winners of semis play for the championship.

    Bottom-4 "toilet bowl": round 1 is best-of-4 vs worst-of-4, and
    2nd-of-4 vs 3rd-of-4. The LOSERS of round 1 advance to a final; the
    LOSER of that final is dead last.
    """
    week_qf, week_sf, week_final = PLAYOFF_WEEKS
    top6 = seeds_ranked[:6]
    bottom4 = seeds_ranked[-4:]
    seed_rank = {team: i for i, team in enumerate(seeds_ranked)}

    seed1, seed2, seed3, seed4, seed5, seed6 = top6

    w, *_ = simulate_game(seed3, seed6, week_qf, team_mu, variance)
    qf1_winner = seed3 if w == 1 else seed6
    w, *_ = simulate_game(seed4, seed5, week_qf, team_mu, variance)
    qf2_winner = seed4 if w == 1 else seed5

    remaining = sorted([seed1, seed2, qf1_winner, qf2_winner], key=lambda t: seed_rank[t])
    sf_pair_top = (remaining[0], remaining[-1])   # best remaining vs worst remaining
    sf_pair_bottom = (remaining[1], remaining[-2])

    w, *_ = simulate_game(*sf_pair_top, week_sf, team_mu, variance)
    sf1_winner = sf_pair_top[0] if w == 1 else sf_pair_top[1]
    w, *_ = simulate_game(*sf_pair_bottom, week_sf, team_mu, variance)
    sf2_winner = sf_pair_bottom[0] if w == 1 else sf_pair_bottom[1]

    w, *_ = simulate_game(sf1_winner, sf2_winner, week_final, team_mu, variance)
    champion = sf1_winner if w == 1 else sf2_winner

    b1, b2, b3, b4 = bottom4  # best-to-worst within the bottom 4
    w, *_ = simulate_game(b1, b4, week_qf, team_mu, variance)
    r1a_loser = b4 if w == 1 else b1
    w, *_ = simulate_game(b2, b3, week_qf, team_mu, variance)
    r1b_loser = b3 if w == 1 else b2

    w, *_ = simulate_game(r1a_loser, r1b_loser, week_sf, team_mu, variance)
    dead_last = r1b_loser if w == 1 else r1a_loser  # loser of the toilet-bowl final

    return {"champion": champion, "dead_last": dead_last}


def simulate_season(schedule: dict, team_mu: dict, variance: float = VARIANCE,
                     n_simulations: int = N_SIMULATIONS, rivals: dict = RIVALS,
                     seed: int = RANDOM_SEED):
    """
    Monte-Carlo simulate the remaining regular season + playoffs
    n_simulations times.
    """
    if seed is not None:
        random.seed(seed)
        np.random.seed(seed)

    teams = sorted({t for games in schedule.values() for pair in games for t in pair})

    win_counts = defaultdict(int)
    points_for = defaultdict(float)
    rival_sweep_counts = defaultdict(int)
    rival_swept_counts = defaultdict(int)
    champion_counts = defaultdict(int)
    dead_last_counts = defaultdict(int)

    seen_rival_pairs = {tuple(sorted((t, r))) for t, r in rivals.items()}

    for _ in range(n_simulations):
        sim_wins = defaultdict(int)
        sim_points = defaultdict(float)
        head_to_head = defaultdict(list)

        for week, games in schedule.items():
            for team1, team2 in games:
                winner, score1, score2 = simulate_game(team1, team2, week, team_mu, variance)
                points_for[team1] += score1
                points_for[team2] += score2
                sim_points[team1] += score1
                sim_points[team2] += score2

                if winner == 1:
                    sim_wins[team1] += 1
                else:
                    sim_wins[team2] += 1

                pair = tuple(sorted((team1, team2)))
                if pair in seen_rival_pairs:
                    head_to_head[pair].append(team1 if winner == 1 else team2)

        for team, wins in sim_wins.items():
            win_counts[team] += wins

        for pair, winners in head_to_head.items():
            if len(winners) == 2 and winners[0] == winners[1]:
                rival_sweep_counts[winners[0]] += 1
                loser = pair[0] if pair[1] == winners[0] else pair[1]
                rival_swept_counts[loser] += 1

        # Seed this trial's final standings (wins, then points, as tiebreak)
        # and run the playoff bracket on top of it.
        seeds_ranked = sorted(teams, key=lambda t: (-sim_wins[t], -sim_points[t]))
        if len(seeds_ranked) >= 10:  # need at least top6 + bottom4, no overlap
            bracket_result = _simulate_playoff_bracket(seeds_ranked, team_mu, variance)
            champion_counts[bracket_result["champion"]] += 1
            dead_last_counts[bracket_result["dead_last"]] += 1

    results = pd.DataFrame({
        "team": teams,
        "avg_wins": [win_counts[t] / n_simulations for t in teams],
        "avg_points_for": [points_for[t] / n_simulations for t in teams],
        "rival_sweep_pct": [rival_sweep_counts[t] / n_simulations for t in teams],
        "rival_swept_pct": [rival_swept_counts[t] / n_simulations for t in teams],
        "championship_pct": [champion_counts[t] / n_simulations for t in teams],
        "dead_last_pct": [dead_last_counts[t] / n_simulations for t in teams],
    }).sort_values("avg_wins", ascending=False).reset_index(drop=True)

    return results


# --------------------------------------------------------------------------
# MAIN
# --------------------------------------------------------------------------
if __name__ == "__main__":
    sc, league = get_yahoo_league()
    rosters = load_rosters_from_yahoo()

    # TODO: replace with your real projections/bye-week loaders (Step 2).
    projections = pd.DataFrame(columns=["name", "week", "proj_pts"])
    bye_weeks = {}

    team_mu = compute_weekly_team_points(rosters, projections, bye_weeks)

    # Either pull the real schedule from Yahoo, or set HARDCODED_SCHEDULE
    # above and pass hardcoded_schedule=HARDCODED_SCHEDULE instead.
    schedule = build_schedule(league=league, hardcoded_schedule=HARDCODED_SCHEDULE)

    results = simulate_season(schedule, team_mu)
    print(results)