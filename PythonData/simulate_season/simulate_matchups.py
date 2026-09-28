"""
Monte Carlo simulate the remaining regular season (week 2 onward) using
each team's optimal projected lineup score (from calculate_lineups.py)
as the mean of a normal distribution with a fixed standard deviation,
and the real schedule (from pull_schedule.py) to know who plays whom.

Each simulated game:
    score ~ Normal(mu=team's lineup total that week, sigma=33)
    higher score wins (a tie has probability 0 under a continuous draw)

Each simulated season:
    starts from each team's REAL record and points-for so far (pulled
    live from Yahoo standings/matchups -- whichever weeks are already
    final), then simulates the remaining weeks using the schedule +
    per-week lineup means. Which weeks count as "already happened" is
    determined automatically from Yahoo's own current_week() each time
    this script runs -- there's nothing to edit week to week.

Playoff seeding, for both the simulation and the odds chart below, ranks
teams by (wins, total points scored) descending -- the same tiebreaker
convention already used elsewhere in this project's simulate_season.py.
Seeds 1-2 get a first-round bye; seeds 3-6 make the playoffs without a
bye; the bottom 4 (seeds 11-14) land in the punishment bracket; seeds
7-10 make neither.

Output
------
simulate_season/record_distribution.jpg -- a heatmap: one row per team,
one column per possible final record, cell value = % of simulations
that team finished with that exact record.

simulate_season/average_weekly_points.jpg -- a heatmap of each team's
points in each week of the season (actual for already-played weeks,
projected optimal lineup total for the rest). This part is deterministic
-- no Monte Carlo needed, since these are just real scores plus the
lineup totals already computed by calculate_lineups.py.

simulate_season/playoff_odds.jpg -- bar chart of, across all
simulations, the % of the time each team finished with a first-round
bye (top 2 seeds), the % of the time it made the playoffs without a bye
(seeds 3-6), and the % of the time it landed in the punishment bracket
(bottom 4 seeds).

Also prints a summary table (average final record per team) and saves
the raw record distribution to simulate_season/record_distribution.json.
"""

import argparse
import json
import os

import numpy as np
import matplotlib.pyplot as plt

from yahoo_oauth import OAuth2
import yahoo_fantasy_api as yfa

SCRIPT_DIR = os.path.dirname(os.path.abspath(__file__))
OAUTH_FILE = os.path.join(SCRIPT_DIR, "..", "oauth2.json")
LEAGUE_ID = "470.l.205662"

LINEUPS_DIR = os.path.join(SCRIPT_DIR, "lineups")
SCHEDULE_PATH = os.path.join(SCRIPT_DIR, "schedule.json")

VARIANCE = 33 ** 2
N_SIMULATIONS = 10_000


def get_league(oauth_file: str = OAUTH_FILE, league_id: str = LEAGUE_ID):
    sc = OAuth2(None, None, from_file=oauth_file)
    gm = yfa.Game(sc, "nfl")
    return gm.to_league(league_id)


def get_completed_weeks(league) -> list:
    """
    Weeks that have actually finished, per Yahoo's own current_week().
    Yahoo's current_week() is the week in progress (or about to start),
    so everything strictly before it is final -- this is the same
    convention already used by draft_par.py's determine_weeks_to_process.
    """
    return list(range(1, league.current_week()))


def get_real_records(league) -> dict:
    """Return {team_name: (wins, losses)} from Yahoo's live standings,
    reflecting every game actually played so far."""
    standings = league.standings()
    records = {}
    for team in standings:
        name = team["name"]
        totals = team["outcome_totals"]
        wins = int(totals["wins"])
        losses = int(totals["losses"])
        records[name] = (wins, losses)
    return records


def get_actual_points_for_week(league, week: int) -> dict:
    """Return {team_name: actual_points_scored} for one already-played
    week, via the same matchups parsing convention used elsewhere in this
    project (CurrentSeason/WriteWeeklyMatchupData.py)."""
    raw = league.matchups(week=week)
    scoreboard = raw["fantasy_content"]["league"][1]["scoreboard"]
    sb_key = next(k for k in scoreboard.keys() if k.isdigit())
    matchups_raw = scoreboard[sb_key]["matchups"]
    count = int(matchups_raw["count"])

    points = {}
    for i in range(count):
        matchup = matchups_raw[str(i)]["matchup"]
        teams_raw = matchup["0"]["teams"]
        team_count = int(teams_raw["count"])
        for j in range(team_count):
            team_raw = teams_raw[str(j)]["team"]
            meta = team_raw[0]
            name = next((it["name"] for it in meta if isinstance(it, dict) and "name" in it), None)
            for chunk in team_raw[1:]:
                if isinstance(chunk, dict) and "team_points" in chunk:
                    points[name] = float(chunk["team_points"]["total"])
    return points


def get_real_points_by_week(league, completed_weeks: list) -> dict:
    """Return {week: {team_name: actual_points}} for every completed week."""
    return {week: get_actual_points_for_week(league, week) for week in completed_weeks}


def get_total_points_so_far(points_by_week: dict, teams: list) -> dict:
    """Return {team_name: total actual points across all completed weeks}."""
    totals = {t: 0.0 for t in teams}
    for week_points in points_by_week.values():
        for t, pts in week_points.items():
            totals[t] = totals.get(t, 0.0) + pts
    return totals


def load_lineup_means(weeks: list) -> dict:
    """Return {week: {team_name: projected_total_points}}."""
    means = {}
    for week in weeks:
        path = os.path.join(LINEUPS_DIR, f"week_{week}.json")
        if not os.path.exists(path):
            raise FileNotFoundError(
                f"No lineup file for week {week} ({path}). Run "
                f"calculate_lineups.py first."
            )
        with open(path) as f:
            lineups = json.load(f)
        means[week] = {team: data["total_points"] for team, data in lineups.items()}
    return means


def load_schedule(weeks: list) -> dict:
    """Return {week: [(team_a, team_b), ...]} for the requested weeks."""
    with open(SCHEDULE_PATH) as f:
        full_schedule = json.load(f)

    schedule = {}
    for week in weeks:
        key = str(week)
        if key not in full_schedule:
            raise KeyError(f"No schedule entry for week {week} in {SCHEDULE_PATH}")
        schedule[week] = [tuple(pair) for pair in full_schedule[key]]
    return schedule


def simulate_season(teams: list, real_records: dict, points_so_far: dict,
                     lineup_means: dict, schedule: dict, weeks: list,
                     n_simulations: int, variance: float, bye_spots: int = 2,
                     playoff_spots: int = 4, punishment_spots: int = 4,
                     seed: int = None) -> dict:
    """
    Run the Monte Carlo simulation.

    Seeds 1..bye_spots get a first-round bye. Seeds
    (bye_spots+1)..(bye_spots+playoff_spots) make the playoffs without a
    bye. The bottom `punishment_spots` seeds land in the punishment
    bracket. Whatever's left in the middle makes neither.

    Returns a dict with:
      "record_counts": {team_name: {(wins, losses): count}}
      "bye_counts": {team_name: count}          -- trials finishing in the bye seeds
      "playoff_counts": {team_name: count}      -- trials finishing in the non-bye playoff seeds
      "punishment_counts": {team_name: count}   -- trials finishing bottom `punishment_spots`

    Seeding within each trial ranks teams by (wins, total points scored)
    descending, matching the tiebreaker convention used elsewhere in this
    project (simulate_season.py).
    """
    if seed is not None:
        np.random.seed(seed)

    sigma = np.sqrt(variance)
    base_wins = {t: real_records.get(t, (0, 0))[0] for t in teams}
    base_losses = {t: real_records.get(t, (0, 0))[1] for t in teams}
    base_points = {t: points_so_far.get(t, 0.0) for t in teams}

    record_counts = {t: {} for t in teams}
    bye_counts = {t: 0 for t in teams}
    playoff_counts = {t: 0 for t in teams}
    punishment_counts = {t: 0 for t in teams}

    for _ in range(n_simulations):
        wins = dict(base_wins)
        losses = dict(base_losses)
        points_for = dict(base_points)

        for week in weeks:
            means = lineup_means[week]
            for team_a, team_b in schedule[week]:
                mu_a = means[team_a]
                mu_b = means[team_b]
                score_a = np.random.normal(mu_a, sigma)
                score_b = np.random.normal(mu_b, sigma)
                points_for[team_a] += score_a
                points_for[team_b] += score_b
                if score_a > score_b:
                    wins[team_a] += 1
                    losses[team_b] += 1
                else:
                    wins[team_b] += 1
                    losses[team_a] += 1

        for t in teams:
            record = (wins[t], losses[t])
            record_counts[t][record] = record_counts[t].get(record, 0) + 1

        ranked = sorted(teams, key=lambda t: (wins[t], points_for[t]), reverse=True)
        for t in ranked[:bye_spots]:
            bye_counts[t] += 1
        for t in ranked[bye_spots:bye_spots + playoff_spots]:
            playoff_counts[t] += 1
        for t in ranked[-punishment_spots:]:
            punishment_counts[t] += 1

    return {
        "record_counts": record_counts,
        "bye_counts": bye_counts,
        "playoff_counts": playoff_counts,
        "punishment_counts": punishment_counts,
    }


def _week_range_label(weeks: list) -> str:
    if not weeks:
        return "none"
    if len(weeks) == 1:
        return str(weeks[0])
    return f"{weeks[0]}-{weeks[-1]}"


def plot_record_distribution(record_counts: dict, n_simulations: int,
                              total_games: int, completed_weeks: list,
                              simulated_weeks: list, out_file: str) -> None:
    """
    Heatmap: one row per team (sorted by average wins, best first), one
    column per possible final win count (0..total_games), cell = % of
    simulations in which that team finished with that many wins (summed
    across whatever the loss count works out to, since wins+losses is
    always total_games with no ties possible under a continuous draw).
    """
    teams = list(record_counts.keys())

    # Collapse each team's {(w,l): count} into wins -> count, since
    # w + l == total_games always (no ties), so wins alone is sufficient
    # to identify the record.
    win_counts = {t: np.zeros(total_games + 1) for t in teams}
    for t, records in record_counts.items():
        for (w, l), count in records.items():
            win_counts[t][w] += count

    avg_wins = {t: sum(w * c for w, c in enumerate(win_counts[t])) / n_simulations for t in teams}
    teams_sorted = sorted(teams, key=lambda t: -avg_wins[t])

    n = len(teams_sorted)
    data = np.zeros((n, total_games + 1))
    for i, t in enumerate(teams_sorted):
        data[i] = win_counts[t] / n_simulations * 100

    fig, ax = plt.subplots(figsize=(16, 0.55 * n + 2))
    im = ax.imshow(data, aspect="auto", cmap="viridis")

    ax.set_xticks(range(total_games + 1))
    ax.set_xticklabels([f"{w}-{total_games - w}" for w in range(total_games + 1)], rotation=45, ha="right")
    ax.set_yticks(range(n))
    ax.set_yticklabels([f"{t} (avg {avg_wins[t]:.1f}-{total_games - avg_wins[t]:.1f})" for t in teams_sorted])

    for i in range(n):
        for j in range(total_games + 1):
            val = data[i, j]
            if val >= 0.5:
                ax.text(j, i, f"{val:.0f}", ha="center", va="center", fontsize=7,
                         color="white" if val < 40 else "black")

    cbar = plt.colorbar(im, ax=ax)
    cbar.set_label("% of simulations")

    completed_label = _week_range_label(completed_weeks)
    simulated_label = _week_range_label(simulated_weeks)

    ax.set_xlabel("Final record (wins-losses)")
    ax.set_title(f"Final Record Distribution -- {n_simulations:,} simulated seasons "
                 f"(weeks {completed_label} actual + weeks {simulated_label} simulated)")

    plt.tight_layout()
    plt.savefig(out_file, dpi=220, bbox_inches="tight")
    plt.close()


def plot_average_weekly_points(real_points_by_week: dict, lineup_means: dict,
                                completed_weeks: list, simulated_weeks: list,
                                teams: list, out_file: str) -> None:
    """
    Heatmap: one row per team, one column per week of the season (actual
    score for already-played weeks, projected optimal lineup total for
    the rest), cell value = that team's points that week. Deterministic
    -- no Monte Carlo needed, since these are just real scores plus the
    lineup totals.

    Teams are sorted by season-long average points, best first.
    """
    all_weeks = completed_weeks + simulated_weeks

    def points_for_week(team, week):
        if week in real_points_by_week:
            return real_points_by_week[week].get(team, 0.0)
        return lineup_means[week][team]

    points = {t: [points_for_week(t, w) for w in all_weeks] for t in teams}
    avg_points = {t: float(np.mean(points[t])) for t in teams}
    teams_sorted = sorted(teams, key=lambda t: -avg_points[t])

    n = len(teams_sorted)
    data = np.array([points[t] for t in teams_sorted])

    fig, ax = plt.subplots(figsize=(1.1 * len(all_weeks) + 3, 0.5 * n + 2))
    im = ax.imshow(data, aspect="auto", cmap="YlGn")

    ax.set_xticks(range(len(all_weeks)))
    ax.set_xticklabels([f"Wk {w}" for w in all_weeks])
    ax.set_yticks(range(n))
    ax.set_yticklabels([f"{t} (avg {avg_points[t]:.1f})" for t in teams_sorted])

    vmax = data.max()
    for i in range(n):
        for j in range(len(all_weeks)):
            val = data[i, j]
            ax.text(j, i, f"{val:.1f}", ha="center", va="center", fontsize=7,
                     color="white" if val > 0.6 * vmax else "black")

    cbar = plt.colorbar(im, ax=ax)
    cbar.set_label("Points")

    completed_label = _week_range_label(completed_weeks)
    simulated_label = _week_range_label(simulated_weeks)

    ax.set_xlabel("Week")
    ax.set_title(f"Average Points Per Week (weeks {completed_label} actual, "
                 f"weeks {simulated_label} projected optimal lineup)")

    plt.tight_layout()
    plt.savefig(out_file, dpi=220, bbox_inches="tight")
    plt.close()


def plot_playoff_odds(bye_counts: dict, playoff_counts: dict, punishment_counts: dict,
                       n_simulations: int, bye_spots: int, playoff_spots: int,
                       punishment_spots: int, out_file: str) -> None:
    """
    Horizontal bar chart: for each team, % of simulations it landed in
    each of three tiers -- first-round bye (top `bye_spots` seeds),
    playoffs without a bye (next `playoff_spots` seeds), and the
    punishment bracket (bottom `punishment_spots` seeds). Teams sorted by
    combined bye+playoff odds, best first.
    """
    teams = list(playoff_counts.keys())
    bye_pct = {t: bye_counts[t] / n_simulations * 100 for t in teams}
    playoff_pct = {t: playoff_counts[t] / n_simulations * 100 for t in teams}
    punishment_pct = {t: punishment_counts[t] / n_simulations * 100 for t in teams}

    teams_sorted = sorted(teams, key=lambda t: -(bye_pct[t] + playoff_pct[t]))
    n = len(teams_sorted)
    y = np.arange(n)

    fig, ax = plt.subplots(figsize=(10, 0.5 * n + 2))

    bar_height = 0.26
    ax.barh(y + bar_height, [bye_pct[t] for t in teams_sorted],
            height=bar_height, color="#1b4332", label=f"First-round bye (top {bye_spots})")
    ax.barh(y, [playoff_pct[t] for t in teams_sorted],
            height=bar_height, color="#2b8a3e",
            label=f"Playoffs, no bye (seeds {bye_spots + 1}-{bye_spots + playoff_spots})")
    ax.barh(y - bar_height, [punishment_pct[t] for t in teams_sorted],
            height=bar_height, color="#c92a2a", label=f"Punishment bracket (bottom {punishment_spots})")

    for i, t in enumerate(teams_sorted):
        ax.text(bye_pct[t] + 1, i + bar_height, f"{bye_pct[t]:.0f}%", va="center", fontsize=8)
        ax.text(playoff_pct[t] + 1, i, f"{playoff_pct[t]:.0f}%", va="center", fontsize=8)
        ax.text(punishment_pct[t] + 1, i - bar_height, f"{punishment_pct[t]:.0f}%", va="center", fontsize=8)

    ax.set_yticks(y)
    ax.set_yticklabels(teams_sorted)
    ax.invert_yaxis()
    ax.set_xlim(0, 105)
    ax.set_xlabel("% of simulations")
    ax.set_title(f"Playoff / Punishment Bracket Odds -- {n_simulations:,} simulated seasons")
    ax.legend(loc="lower right")
    ax.grid(axis="x", alpha=0.3)

    plt.tight_layout()
    plt.savefig(out_file, dpi=220, bbox_inches="tight")
    plt.close()


def main():
    parser = argparse.ArgumentParser(
        description="Monte Carlo simulate the remaining regular season and chart each team's final record distribution."
    )
    parser.add_argument("--simulations", type=int, default=N_SIMULATIONS,
                         help="Number of Monte Carlo season simulations to run")
    parser.add_argument("--start-week", type=int, default=None,
                         help="First week to simulate. Defaults to Yahoo's current week "
                              "(i.e. the first week that hasn't finished yet) -- you "
                              "shouldn't normally need to set this.")
    parser.add_argument("--end-week", type=int, default=14,
                         help="Last week of the regular season to simulate through")
    parser.add_argument("--variance", type=float, default=VARIANCE,
                         help="Variance of each team's weekly score (default 33^2)")
    parser.add_argument("--seed", type=int, default=None, help="Random seed for reproducibility")
    parser.add_argument("--bye-spots", type=int, default=2, help="Number of top seeds that get a first-round bye")
    parser.add_argument("--playoff-spots", type=int, default=4,
                         help="Number of teams that make the playoffs WITHOUT a bye "
                              "(i.e. seeds bye_spots+1 .. bye_spots+playoff_spots)")
    parser.add_argument("--punishment-spots", type=int, default=4, help="Number of teams in the punishment bracket")
    parser.add_argument("--oauth-file", default=OAUTH_FILE)
    parser.add_argument("--league-id", default=LEAGUE_ID)
    parser.add_argument("--output-image", default=os.path.join(SCRIPT_DIR, "record_distribution.jpg"))
    parser.add_argument("--output-json", default=os.path.join(SCRIPT_DIR, "record_distribution.json"))
    parser.add_argument("--weekly-points-image", default=os.path.join(SCRIPT_DIR, "average_weekly_points.jpg"))
    parser.add_argument("--playoff-odds-image", default=os.path.join(SCRIPT_DIR, "playoff_odds.jpg"))
    args = parser.parse_args()

    league = get_league(oauth_file=args.oauth_file, league_id=args.league_id)
    completed_weeks = get_completed_weeks(league)
    start_week = args.start_week if args.start_week is not None else league.current_week()
    weeks = list(range(start_week, args.end_week + 1))

    print(f"Yahoo current week: {league.current_week()}. "
          f"Treating weeks {completed_weeks or 'none'} as already played.")

    print("\nFetching real results so far from Yahoo...")
    real_records = get_real_records(league)
    real_points_by_week = get_real_points_by_week(league, completed_weeks)
    teams = list(real_records.keys())
    points_so_far = get_total_points_so_far(real_points_by_week, teams)
    for t, (w, l) in real_records.items():
        print(f"  {t:<32} {w}-{l}  ({points_so_far.get(t, 0):.2f} pts so far)")

    print(f"\nLoading lineup projections for weeks {weeks}...")
    lineup_means = load_lineup_means(weeks)

    print(f"Loading schedule for weeks {weeks}...")
    schedule = load_schedule(weeks)

    total_games = len(completed_weeks) + len(weeks)
    print(f"\nRunning {args.simulations:,} simulations of weeks {weeks[0]}-{weeks[-1]} "
          f"(final records will be out of {total_games} games)...")

    results = simulate_season(
        teams, real_records, points_so_far, lineup_means, schedule, weeks,
        n_simulations=args.simulations, variance=args.variance,
        bye_spots=args.bye_spots, playoff_spots=args.playoff_spots,
        punishment_spots=args.punishment_spots, seed=args.seed,
    )
    record_counts = results["record_counts"]
    bye_counts = results["bye_counts"]
    playoff_counts = results["playoff_counts"]
    punishment_counts = results["punishment_counts"]

    # Save raw distribution as JSON (records as "W-L" string keys).
    serializable = {
        team: {f"{w}-{l}": count for (w, l), count in records.items()}
        for team, records in record_counts.items()
    }
    with open(args.output_json, "w") as f:
        json.dump(serializable, f, indent=2)
    print(f"\nSaved raw distribution -> {args.output_json}")

    plot_record_distribution(record_counts, args.simulations, total_games,
                              completed_weeks, weeks, args.output_image)
    print(f"Saved chart -> {args.output_image}")

    plot_average_weekly_points(real_points_by_week, lineup_means, completed_weeks,
                                weeks, teams, args.weekly_points_image)
    print(f"Saved chart -> {args.weekly_points_image}")

    plot_playoff_odds(bye_counts, playoff_counts, punishment_counts, args.simulations,
                       args.bye_spots, args.playoff_spots, args.punishment_spots,
                       args.playoff_odds_image)
    print(f"Saved chart -> {args.playoff_odds_image}")

    # Console summary: average final record per team, sorted best to worst.
    avg_summary = []
    for t, records in record_counts.items():
        avg_w = sum(w * c for (w, l), c in records.items()) / args.simulations
        avg_l = total_games - avg_w
        avg_summary.append((t, avg_w, avg_l))
    avg_summary.sort(key=lambda x: -x[1])

    print("\n=== Average final record (sorted) ===")
    for t, avg_w, avg_l in avg_summary:
        pct_bye = bye_counts[t] / args.simulations * 100
        pct_playoff = playoff_counts[t] / args.simulations * 100
        pct_punish = punishment_counts[t] / args.simulations * 100
        print(f"  {t:<32} {avg_w:5.2f}-{avg_l:5.2f}   "
              f"bye {pct_bye:5.1f}%   playoffs(no bye) {pct_playoff:5.1f}%   punishment {pct_punish:5.1f}%")


if __name__ == "__main__":
    main()
