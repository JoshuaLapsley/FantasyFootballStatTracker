"""
Simulate_ROS.py
===============

Monte-Carlo simulation of the rest of the (2026) fantasy regular season.

Pipeline
--------
1.  Build, for every team, its BEST projected starting lineup for each
    remaining week, using the Sleeper projections in
    ``Projections/SleeperProjections/{year}/projections/week_XX.json``.

    Starting lineup slots (9 starters):
        QB x1, RB x2, WR x2, TE x1, FLEX x1 (RB/WR/TE), K x1, DEF x1

    A team's roster membership is taken from the most recent week present
    in ``APIData/{year}/RosterPoints.json`` (IR players excluded).

    Replacement floors (points) are used whenever the best available
    starter for a slot projects BELOW the floor, or when the team simply
    cannot fill a slot (not enough players at that position):

        QB: 15,  RB: 5,  WR: 7,  TE: 8,  K: 7,  DEF: 6

    The FLEX floor is the minimum of the RB/WR/TE floors.

    Summing the 9 slot values gives the team's projected score for a week.

2.  Read the current week + each team's current record (from the completed
    MatchupData weeks) and the remaining schedule.

3.  Monte-Carlo: 50,000 simulations of weeks {current_week .. 14}.
    Each team's weekly score is drawn Normal(mean = projected score,
    sd = 33). Higher score wins that week's head-to-head matchup.

4.  Produce three PNGs in ``CurrentSeason/Simulations/``:

      * record_distribution.png
            Teams (rows) x possible FINAL records (cols); each cell is the
            probability of finishing with that record. Heatmap.

      * playoff_odds.png
            One row per team, grouped bar chart of the three outcome
            buckets: bottom-4 (punishment), top-2 (bye), seeds 3-6
            (playoffs, no bye).

      * conditional_outcomes_by_record.png
            Teams (rows) x possible records over the REMAINING games
            (cols). Each cell is split into three sub-cells coloured
            green (bye), blue (playoff), red (punishment); colour
            intensity encodes the probability of that outcome CONDITIONAL
            on the team posting that remaining-game record.

Run:
    python Simulate_ROS.py            # year defaults to 2026
    python Simulate_ROS.py 2026
"""

import glob
import json
import os
import re
import sys
from collections import Counter, defaultdict
from pathlib import Path

import numpy as np
import matplotlib

matplotlib.use("Agg")
import matplotlib.pyplot as plt
from matplotlib.colors import LinearSegmentedColormap
from matplotlib.patches import Patch

# --------------------------------------------------------------------------
# Paths
# --------------------------------------------------------------------------
SCRIPT_DIR = Path(__file__).resolve().parent
APICALLS_DIR = SCRIPT_DIR.parent                      # .../APICallsAndStats
PYTHONDATA_DIR = APICALLS_DIR.parent                  # .../PythonData
API_DATA_DIR = APICALLS_DIR / "APIData"
DATA_DIR = APICALLS_DIR / "Data"
PROJ_DIR = APICALLS_DIR / "Projections" / "SleeperProjections"
OUT_DIR = PYTHONDATA_DIR / "CurrentSeason" / "Simulations"

# --------------------------------------------------------------------------
# League constants
# --------------------------------------------------------------------------
LAST_REGULAR_WEEK = 14          # schedule only runs through the regular season
N_SIMS = 50_000
SCORE_SD = 33.0

# Starting-lineup slots. FLEX accepts RB/WR/TE.
LINEUP = [
    ("QB", {"QB"}),
    ("RB", {"RB"}),
    ("RB", {"RB"}),
    ("WR", {"WR"}),
    ("WR", {"WR"}),
    ("TE", {"TE"}),
    ("FLEX", {"RB", "WR", "TE"}),
    ("K", {"K"}),
    ("DEF", {"DEF"}),
]

REPLACEMENT = {"QB": 15.0, "RB": 5.0, "WR": 7.0, "TE": 8.0, "K": 7.0, "DEF": 6.0}
# FLEX floor: a flex player can be RB/WR/TE, so the floor is the lowest of those.
FLEX_FLOOR = min(REPLACEMENT["RB"], REPLACEMENT["WR"], REPLACEMENT["TE"])

FIXED_SLOTS = {"QB", "RB", "WR", "TE", "K", "DEF"}  # selected_position == real position


# ==========================================================================
# Loading & projection helpers
# ==========================================================================
def _load_projection_week(year, week):
    """Return (name->proj, name->position, def_lastword->fullname) for a week."""
    path = PROJ_DIR / str(year) / "projections" / f"week_{week:02d}.json"
    name_to_proj, name_to_pos, def_lookup = {}, {}, {}
    if not path.exists():
        return name_to_proj, name_to_pos, def_lookup
    data = json.loads(path.read_text())
    for pl in data.get("players", []):
        name, pos = pl.get("name"), pl.get("position")
        proj = pl.get("projection_ppr")
        if not name or not pos:
            continue
        if proj is not None:
            name_to_proj[name] = float(proj)
        name_to_pos.setdefault(name, pos)
        if pos == "DEF":
            def_lookup.setdefault(name.split()[-1], name)
    return name_to_proj, name_to_pos, def_lookup


def _build_global_position_map(year):
    """
    name -> real position, merged across every projection week, plus a
    DEF nickname (last word) -> full name lookup. Rosters store DEF teams by
    a short nickname ("Seahawks") while projections use the full name
    ("Seattle Seahawks").
    """
    name_to_pos, def_lookup = {}, {}
    for f in sorted(glob.glob(str(PROJ_DIR / str(year) / "projections" / "week_*.json"))):
        data = json.loads(Path(f).read_text())
        for pl in data.get("players", []):
            name, pos = pl.get("name"), pl.get("position")
            if not name or not pos:
                continue
            name_to_pos.setdefault(name, pos)
            if pos == "DEF":
                def_lookup.setdefault(name.split()[-1], name)
    return name_to_pos, def_lookup


def _latest_roster_week(roster_points):
    return max(roster_points.keys(), key=int)


def _resolve_position(player, name_to_pos, def_lookup):
    """Determine a roster player's true position (QB/RB/WR/TE/K/DEF) or None."""
    sp = player.get("selected_position")
    if sp in FIXED_SLOTS:
        return sp
    name = player.get("name")
    if name in name_to_pos:
        return name_to_pos[name]
    if name in def_lookup:          # DEF stored by nickname
        return "DEF"
    return None


def build_team_rosters(year):
    """
    {team_key: [ {name, position} , ... ]}  using the most recent roster week.
    IR players are dropped. Players whose position can't be resolved are kept
    only if they sit in a fixed slot (so their position is known); otherwise
    they are dropped (deep bench with no projection history -> irrelevant to a
    best lineup anyway).
    """
    roster_points = json.loads((API_DATA_DIR / str(year) / "RosterPoints.json").read_text())
    week = _latest_roster_week(roster_points)
    name_to_pos, def_lookup = _build_global_position_map(year)

    rosters = {}
    for team_key, players in roster_points[week].items():
        members = []
        for p in players:
            if p.get("selected_position") == "IR":
                continue
            pos = _resolve_position(p, name_to_pos, def_lookup)
            if pos is None:
                continue
            members.append({"name": p.get("name"), "position": pos})
        rosters[team_key] = members
    return rosters, int(week)


def _player_projection(name, position, name_to_proj, def_lookup):
    """Projection for one player in one week, or None if not projected."""
    if name in name_to_proj:
        return name_to_proj[name]
    if position == "DEF":
        full = def_lookup.get(name) or (def_lookup.get(name.split()[-1]) if name else None)
        if full and full in name_to_proj:
            return name_to_proj[full]
    return None


def best_lineup_score(members, name_to_proj, def_lookup, return_detail=False):
    """
    Best projected starting-lineup score for one team in one week.

    Greedy fill: assign the highest-projected eligible player to each slot,
    hardest-to-fill slots first (QB/K/DEF before FLEX). A slot's value is the
    chosen player's projection, floored at that position's replacement value;
    an unfillable slot contributes its replacement floor.

    If return_detail is True, returns (total, lineup) where lineup is a list of
    dicts: {slot, name, position, projection, counted} -- `counted` being the
    value that actually went into the total (floored where applicable).
    """
    # pool: position -> sorted list (desc) of available (projection, name)
    pool = defaultdict(list)
    for m in members:
        proj = _player_projection(m["name"], m["position"], name_to_proj, def_lookup)
        if proj is None:
            continue
        pool[m["position"]].append((proj, m["name"]))
    for pos in pool:
        pool[pos].sort(key=lambda t: t[0], reverse=True)

    # Fill the most constrained slots first so FLEX takes leftovers.
    order = ["QB", "RB", "RB", "WR", "WR", "TE", "K", "DEF", "FLEX"]
    floors = {"QB": REPLACEMENT["QB"], "RB": REPLACEMENT["RB"], "WR": REPLACEMENT["WR"],
              "TE": REPLACEMENT["TE"], "K": REPLACEMENT["K"], "DEF": REPLACEMENT["DEF"],
              "FLEX": FLEX_FLOOR}
    eligible = {"QB": ("QB",), "RB": ("RB",), "WR": ("WR",), "TE": ("TE",),
                "K": ("K",), "DEF": ("DEF",), "FLEX": ("RB", "WR", "TE")}

    total = 0.0
    lineup = []
    for slot in order:
        best_val, best_pos = None, None
        for pos in eligible[slot]:
            if pool[pos]:
                val = pool[pos][0][0]
                if best_val is None or val > best_val:
                    best_val, best_pos = val, pos
        if best_pos is not None:
            proj, pname = pool[best_pos].pop(0)
            counted = max(proj, floors[slot])      # floor if starter is below replacement
            total += counted
            if return_detail:
                lineup.append({"slot": slot, "name": pname, "position": best_pos,
                               "projection": proj, "counted": counted})
        else:
            total += floors[slot]                  # can't fill the slot -> replacement
            if return_detail:
                lineup.append({"slot": slot, "name": "(replacement)", "position": None,
                               "projection": None, "counted": floors[slot]})
    if return_detail:
        return total, lineup
    return total


def projected_scores_by_week(year, rosters, weeks):
    """{team_key: {week: projected_score}} for the given weeks."""
    scores = {tk: {} for tk in rosters}
    for wk in weeks:
        name_to_proj, _pos, def_lookup = _load_projection_week(year, wk)
        for tk, members in rosters.items():
            scores[tk][wk] = best_lineup_score(members, name_to_proj, def_lookup)
    return scores


# ==========================================================================
# Records, names, schedule
# ==========================================================================
def load_matchups_and_records(year):
    """
    Returns:
        names          {team_key: team name}
        name_to_key    {team name: team_key}
        records        {team_key: [wins, losses]} from completed weeks
        points_for     {team_key: total actual points scored so far}
        played_weeks   set of completed week numbers
    """
    names, name_to_key = {}, {}
    records = defaultdict(lambda: [0, 0])
    points_for = defaultdict(float)
    played_weeks = set()

    files = sorted(glob.glob(str(API_DATA_DIR / str(year) / "MatchupData" / "Week*.json")),
                   key=lambda f: int(re.search(r"Week(\d+)", os.path.basename(f)).group(1)))
    for f in files:
        wk = int(re.search(r"Week(\d+)", os.path.basename(f)).group(1))
        if wk > LAST_REGULAR_WEEK:
            continue
        for m in json.loads(Path(f).read_text()):
            if m.get("status") != "postevent" or m.get("is_playoffs") or m.get("is_consolation"):
                continue
            if len(m.get("teams", [])) != 2:
                continue
            a, b = m["teams"]
            for t in (a, b):
                names[t["team_key"]] = t["name"]
                name_to_key[t["name"]] = t["team_key"]
                points_for[t["team_key"]] += float(t.get("points", 0.0))
            played_weeks.add(wk)
            winner = m.get("winner_team_key")
            if winner == a["team_key"]:
                records[a["team_key"]][0] += 1
                records[b["team_key"]][1] += 1
            elif winner == b["team_key"]:
                records[b["team_key"]][0] += 1
                records[a["team_key"]][1] += 1
            else:  # tie (continuous scoring makes this vanishingly rare)
                records[a["team_key"]][0] += 0.5
                records[b["team_key"]][0] += 0.5
    return names, name_to_key, dict(records), dict(points_for), played_weeks


def load_schedule(year):
    """{week:int -> [(name_a, name_b), ...]}."""
    raw = json.loads((API_DATA_DIR / str(year) / "schedule.json").read_text())
    return {int(w): [tuple(p) for p in pairs] for w, pairs in raw.items()}


def load_current_week(year):
    meta = json.loads((DATA_DIR / str(year) / "meta.json").read_text())
    return int(meta.get("current_week"))


# ==========================================================================
# Monte-Carlo simulation
# ==========================================================================
def simulate(team_keys, names, name_to_key, records, points_for,
             schedule, proj_scores, remaining_weeks, n_sims=N_SIMS, seed=20261103):
    """
    Vectorised Monte-Carlo.

    Returns a dict of result arrays, all indexed by team order == team_keys:
        remaining_wins   (n_sims, n_teams)  wins over the remaining weeks
        final_wins       (n_sims, n_teams)  wins over the full regular season
        seed_rank        (n_sims, n_teams)  1 = best .. n_teams = worst
    plus the derived outcome masks (bye / playoff / punishment) per sim.
    """
    rng = np.random.default_rng(seed)
    n_teams = len(team_keys)
    key_idx = {k: i for i, k in enumerate(team_keys)}

    base_wins = np.array([records.get(k, [0, 0])[0] for k in team_keys], dtype=float)
    base_pf = np.array([points_for.get(k, 0.0) for k in team_keys], dtype=float)

    remaining_wins = np.zeros((n_sims, n_teams))
    sim_points = np.zeros((n_sims, n_teams))

    for wk in remaining_weeks:
        # means for this week
        means = np.array([proj_scores[k][wk] for k in team_keys])          # (n_teams,)
        draws = rng.normal(loc=means, scale=SCORE_SD, size=(n_sims, n_teams))
        sim_points += draws
        for name_a, name_b in schedule[wk]:
            ka, kb = name_to_key.get(name_a), name_to_key.get(name_b)
            if ka is None or kb is None:
                continue
            ia, ib = key_idx[ka], key_idx[kb]
            a_wins = draws[:, ia] > draws[:, ib]
            remaining_wins[:, ia] += a_wins
            remaining_wins[:, ib] += ~a_wins

    final_wins = base_wins[None, :] + remaining_wins
    final_pf = base_pf[None, :] + sim_points

    # Standings: sort by wins desc, then points-for desc. Rank 1 = best.
    # Build a sort key: large number so wins dominate, pf as tiebreaker.
    order_key = final_wins * 1e6 + final_pf                # (n_sims, n_teams)
    # argsort descending -> ranking
    order = np.argsort(-order_key, axis=1)                 # team indices best->worst
    seed_rank = np.empty((n_sims, n_teams), dtype=int)
    rows = np.arange(n_sims)[:, None]
    seed_rank[rows, order] = np.arange(1, n_teams + 1)[None, :]

    return {
        "remaining_wins": remaining_wins.astype(int),
        "final_wins": final_wins,
        "seed_rank": seed_rank,
    }


# ==========================================================================
# Plotting
# ==========================================================================
def _team_order_by_strength(team_keys, sim, records):
    """Order teams for display: by mean final wins (best at top)."""
    mean_final = sim["final_wins"].mean(axis=0)
    idx = sorted(range(len(team_keys)), key=lambda i: -mean_final[i])
    return idx


def plot_record_distribution(team_keys, names, sim, total_games, out_path):
    """Heatmap: rows=teams, cols=possible final records, cells=probability."""
    n_sims = sim["final_wins"].shape[0]
    final_wins = np.rint(sim["final_wins"]).astype(int)      # whole-season wins

    win_values = list(range(0, total_games + 1))
    col_labels = [f"{w}-{total_games - w}" for w in win_values]

    order = _team_order_by_strength(team_keys, sim, None)
    matrix = np.zeros((len(team_keys), len(win_values)))
    for row, ti in enumerate(order):
        counts = np.bincount(final_wins[:, ti], minlength=total_games + 1)[: total_games + 1]
        matrix[row] = counts / n_sims
    row_labels = [names[team_keys[ti]] for ti in order]

    fig, ax = plt.subplots(figsize=(1.0 * len(col_labels) + 4, 0.5 * len(row_labels) + 2))
    im = ax.imshow(matrix, aspect="auto", cmap="viridis", vmin=0, vmax=matrix.max())

    ax.set_xticks(range(len(col_labels)))
    ax.set_xticklabels(col_labels, rotation=0, fontsize=8)
    ax.set_yticks(range(len(row_labels)))
    ax.set_yticklabels(row_labels, fontsize=8)
    ax.set_xlabel("Final record (W-L)")
    ax.set_title(f"Final-record probability distribution  ({n_sims:,} sims)")

    thresh = matrix.max() * 0.55
    for i in range(matrix.shape[0]):
        for j in range(matrix.shape[1]):
            v = matrix[i, j]
            if v >= 0.005:
                ax.text(j, i, f"{v*100:.0f}", ha="center", va="center",
                        fontsize=6, color="white" if v < thresh else "black")
    fig.colorbar(im, ax=ax, label="Probability", fraction=0.025, pad=0.01)
    fig.tight_layout()
    fig.savefig(out_path, dpi=150)
    plt.close(fig)


def plot_playoff_odds(team_keys, names, sim, out_path):
    """
    Horizontal grouped bars per team for the three buckets:
      bye       = top-2 seed
      playoff   = seeds 3-6
      punishment= bottom-4 seed
    """
    n_sims = sim["seed_rank"].shape[0]
    n_teams = len(team_keys)
    rank = sim["seed_rank"]

    bye = (rank <= 2).mean(axis=0)
    playoff = ((rank >= 3) & (rank <= 6)).mean(axis=0)
    punish = (rank >= n_teams - 3).mean(axis=0)   # bottom 4

    order = _team_order_by_strength(team_keys, sim, None)
    row_labels = [names[team_keys[ti]] for ti in order]
    bye, playoff, punish = bye[order], playoff[order], punish[order]

    y = np.arange(len(order))
    h = 0.26
    fig, ax = plt.subplots(figsize=(10, 0.55 * len(order) + 2))
    ax.barh(y + h, bye * 100, height=h, color="#2ca02c", label="Bye (top 2)")
    ax.barh(y, playoff * 100, height=h, color="#1f77b4", label="Playoff (seeds 3-6)")
    ax.barh(y - h, punish * 100, height=h, color="#d62728", label="Punishment (bottom 4)")

    for yi, (bv, pv, rv) in zip(y, zip(bye, playoff, punish)):
        ax.text(bv * 100 + 0.5, yi + h, f"{bv*100:.1f}", va="center", fontsize=7)
        ax.text(pv * 100 + 0.5, yi, f"{pv*100:.1f}", va="center", fontsize=7)
        ax.text(rv * 100 + 0.5, yi - h, f"{rv*100:.1f}", va="center", fontsize=7)

    ax.set_yticks(y)
    ax.set_yticklabels(row_labels, fontsize=9)
    ax.invert_yaxis()
    ax.set_xlabel("Probability (%)")
    ax.set_xlim(0, 105)
    ax.set_title(f"Playoff / bye / punishment odds  ({n_sims:,} sims)")
    ax.legend(loc="lower right")
    fig.tight_layout()
    fig.savefig(out_path, dpi=150)
    plt.close(fig)


def plot_conditional_outcomes(team_keys, names, sim, n_remaining, out_path):
    """
    Rows = teams, cols = possible records over the REMAINING games
    (0-N .. N-0). Each cell is split into 3 vertical strips:
        green  = P(bye       | that remaining record)
        blue   = P(playoff   | that remaining record)
        red    = P(punishment| that remaining record)
    Intensity of each strip encodes its conditional probability (0..1).
    """
    n_sims = sim["seed_rank"].shape[0]
    n_teams = len(team_keys)
    rank = sim["seed_rank"]
    rwins = sim["remaining_wins"]

    bye_mask = rank <= 2
    play_mask = (rank >= 3) & (rank <= 6)
    pun_mask = rank >= n_teams - 3

    win_values = list(range(0, n_remaining + 1))
    col_labels = [f"{w}-{n_remaining - w}" for w in win_values]

    order = _team_order_by_strength(team_keys, sim, None)
    row_labels = [names[team_keys[ti]] for ti in order]

    # Start each ramp from a faint tint (not pure white) so a 0% strip is
    # still a visible coloured box against the white background rather than
    # blending in and looking blank.
    green = LinearSegmentedColormap.from_list("g", ["#eaf6ea", "#2ca02c"])
    blue = LinearSegmentedColormap.from_list("b", ["#e8f1fb", "#1f77b4"])
    red = LinearSegmentedColormap.from_list("r", ["#fdeaea", "#d62728"])

    n_rows, n_cols = len(order), len(win_values)
    fig, ax = plt.subplots(figsize=(1.15 * n_cols + 3, 0.62 * n_rows + 2.5))

    for r, ti in enumerate(order):
        for c, w in enumerate(win_values):
            sel = rwins[:, ti] == w
            n_sel = int(sel.sum())
            # When no simulation produced this remaining-game record, the
            # conditional probabilities are undefined; show them as 0 so the
            # cell is still drawn (white strips) rather than left blank.
            if n_sel == 0:
                p_bye = p_play = p_pun = 0.0
            else:
                p_bye = bye_mask[sel, ti].mean()
                p_play = play_mask[sel, ti].mean()
                p_pun = pun_mask[sel, ti].mean()
            # three vertical strips within the cell (always drawn); thin grey
            # dividers keep the three visible even when all are pale.
            ax.add_patch(plt.Rectangle((c, r), 1 / 3, 1,
                                       facecolor=green(p_bye), edgecolor="#bbbbbb", lw=0.4))
            ax.add_patch(plt.Rectangle((c + 1 / 3, r), 1 / 3, 1,
                                       facecolor=blue(p_play), edgecolor="#bbbbbb", lw=0.4))
            ax.add_patch(plt.Rectangle((c + 2 / 3, r), 1 / 3, 1,
                                       facecolor=red(p_pun), edgecolor="#bbbbbb", lw=0.4))
            # black border around the group of three strips (one cell)
            ax.add_patch(plt.Rectangle((c, r), 1, 1, facecolor="none",
                                       edgecolor="black", lw=0.8, zorder=5))
            # always label each strip, including 0%
            for k, pv in enumerate((p_bye, p_play, p_pun)):
                ax.text(c + (k + 0.5) / 3, r + 0.5, f"{pv*100:.0f}",
                        ha="center", va="center", fontsize=5.5,
                        color="white" if pv > 0.6 else "black")

    ax.set_xlim(0, n_cols)
    ax.set_ylim(0, n_rows)
    ax.invert_yaxis()
    ax.set_xticks([c + 0.5 for c in range(n_cols)])
    ax.set_xticklabels(col_labels, fontsize=8)
    ax.set_yticks([r + 0.5 for r in range(n_rows)])
    ax.set_yticklabels(row_labels, fontsize=8)
    ax.set_xlabel(f"Record over remaining {n_remaining} games (W-L)")
    ax.set_title("Conditional outcome odds by remaining-game record\n"
                 "(cell strips: green=bye, blue=playoff, red=punishment; "
                 "intensity = conditional probability)")
    ax.set_xticks(range(n_cols + 1), minor=True)
    ax.set_yticks(range(n_rows + 1), minor=True)

    legend = [Patch(facecolor="#2ca02c", label="Bye (top 2)"),
              Patch(facecolor="#1f77b4", label="Playoff (seeds 3-6)"),
              Patch(facecolor="#d62728", label="Punishment (bottom 4)")]
    ax.legend(handles=legend, loc="upper left", bbox_to_anchor=(1.01, 1.0),
              fontsize=8, frameon=False)
    fig.tight_layout()
    fig.savefig(out_path, dpi=150)
    plt.close(fig)


def plot_projected_team_points(team_keys, names, proj_scores, remaining_weeks, out_path):
    """
    Heatmap table of each team's projected best-lineup score per remaining
    week. Rows = teams (best season-long average at top), columns = the
    remaining weeks plus an average column. Each cell is annotated with the
    projected points.
    """
    weeks = list(remaining_weeks)
    matrix = np.array([[proj_scores[k][wk] for wk in weeks] for k in team_keys])
    avg = matrix.mean(axis=1, keepdims=True)
    full = np.hstack([matrix, avg])

    # order teams by average projected points (highest at top)
    order = np.argsort(-avg[:, 0])
    full = full[order]
    row_labels = [names[team_keys[i]] for i in order]
    col_labels = [f"Wk {wk}" for wk in weeks] + ["Avg"]

    fig, ax = plt.subplots(figsize=(1.0 * len(col_labels) + 4,
                                    0.5 * len(row_labels) + 2))
    # colour only on the weekly cells (exclude the Avg column from the scale)
    im = ax.imshow(full, aspect="auto", cmap="YlGn",
                   vmin=matrix.min(), vmax=matrix.max())

    ax.set_xticks(range(len(col_labels)))
    ax.set_xticklabels(col_labels, fontsize=9)
    ax.set_yticks(range(len(row_labels)))
    ax.set_yticklabels(row_labels, fontsize=9)
    ax.set_xlabel("Week")
    ax.set_title("Projected best-lineup points by team and week")

    # separator line before the Avg column
    ax.axvline(len(weeks) - 0.5, color="black", lw=1.2)

    thresh = (matrix.min() + matrix.max()) / 2
    for i in range(full.shape[0]):
        for j in range(full.shape[1]):
            v = full[i, j]
            is_avg = (j == len(weeks))
            ax.text(j, i, f"{v:.1f}", ha="center", va="center",
                    fontsize=8,
                    fontweight="bold" if is_avg else "normal",
                    color="black" if (is_avg or v < thresh) else "black")
    fig.colorbar(im, ax=ax, label="Projected points", fraction=0.025, pad=0.01)
    fig.tight_layout()
    fig.savefig(out_path, dpi=150)
    plt.close(fig)


# ==========================================================================
# Terminal diagnostics
# ==========================================================================
def _print_starter_breakdown(year, rosters, names, team_name, week):
    """Print one team's best-lineup starter projections for a single week."""
    key = next((k for k, n in names.items() if n == team_name), None)
    if key is None or key not in rosters:
        print(f"\n[{team_name}] not found; cannot print week {week} starters.")
        return

    name_to_proj, _pos, def_lookup = _load_projection_week(year, week)
    total, lineup = best_lineup_score(rosters[key], name_to_proj, def_lookup,
                                      return_detail=True)

    print(f"\n{team_name} - week {week} starter projections:")
    print(f"  {'Slot':5s} {'Player':26s} {'Pos':4s} {'Proj':>7s} {'Counted':>8s}")
    for s in lineup:
        proj = "  --  " if s["projection"] is None else f"{s['projection']:6.2f}"
        floored = (s["projection"] is not None and
                   abs(s["counted"] - s["projection"]) > 1e-9)
        flag = "  (replacement floor)" if floored or s["position"] is None else ""
        print(f"  {s['slot']:5s} {s['name']:26s} {str(s['position'] or '-'):4s} "
              f"{proj:>7s} {s['counted']:8.2f}{flag}")
    print(f"  {'':5s} {'TOTAL':26s} {'':4s} {'':>7s} {total:8.2f}")


# ==========================================================================
# Orchestration
# ==========================================================================
def run(year=2026, n_sims=N_SIMS):
    current_week = load_current_week(year)
    remaining_weeks = [w for w in range(current_week, LAST_REGULAR_WEEK + 1)]
    if not remaining_weeks:
        print("No regular-season weeks left to simulate.")
        return
    n_remaining = len(remaining_weeks)

    print(f"Year {year}: current week {current_week}, "
          f"simulating weeks {remaining_weeks[0]}-{remaining_weeks[-1]} "
          f"({n_remaining} weeks), {n_sims:,} sims.")

    rosters, roster_week = build_team_rosters(year)
    print(f"Built rosters from RosterPoints week {roster_week} "
          f"({len(rosters)} teams).")

    names, name_to_key, records, points_for, played = load_matchups_and_records(year)
    schedule = load_schedule(year)
    team_keys = sorted(names, key=lambda k: int(k.rsplit(".", 1)[-1]))

    proj_scores = projected_scores_by_week(year, rosters, remaining_weeks)

    # Diagnostics: show one week's projected scores.
    wk0 = remaining_weeks[0]
    print(f"\nProjected scores, week {wk0}:")
    for k in sorted(team_keys, key=lambda k: -proj_scores[k][wk0]):
        print(f"  {names[k]:30s} {proj_scores[k][wk0]:6.1f}  "
              f"(record {int(records[k][0])}-{int(records[k][1])})")

    # Maitre Stick's week-9 starter projections (the best-lineup breakdown).
    _print_starter_breakdown(year, rosters, names, "Big Bad Hokkkk", 12)

    sim = simulate(team_keys, names, name_to_key, records, points_for,
                   schedule, proj_scores, remaining_weeks, n_sims=n_sims)

    total_games = int(round(max(records[k][0] + records[k][1] for k in team_keys))) + n_remaining

    OUT_DIR.mkdir(parents=True, exist_ok=True)
    plot_record_distribution(team_keys, names, sim, total_games,
                             OUT_DIR / "record_distribution.png")
    plot_playoff_odds(team_keys, names, sim, OUT_DIR / "playoff_odds.png")
    plot_conditional_outcomes(team_keys, names, sim, n_remaining,
                              OUT_DIR / "conditional_outcomes_by_record.png")
    plot_projected_team_points(team_keys, names, proj_scores, remaining_weeks,
                               OUT_DIR / "projected_team_points.png")

    print(f"\nWrote PNGs to {OUT_DIR}")
    # Summary table
    rank = sim["seed_rank"]
    print("\nPlayoff summary:")
    order = _team_order_by_strength(team_keys, sim, None)
    print(f"  {'Team':30s} {'Bye%':>6s} {'PO%':>6s} {'Pun%':>6s} {'MeanW':>6s}")
    for ti in order:
        bye = (rank[:, ti] <= 2).mean() * 100
        po = ((rank[:, ti] >= 3) & (rank[:, ti] <= 6)).mean() * 100
        pun = (rank[:, ti] >= len(team_keys) - 3).mean() * 100
        print(f"  {names[team_keys[ti]]:30s} {bye:6.1f} {po:6.1f} {pun:6.1f} "
              f"{sim['final_wins'][:, ti].mean():6.2f}")


if __name__ == "__main__":
    yr = int(sys.argv[1]) if len(sys.argv) > 1 else 2026
    run(yr)
