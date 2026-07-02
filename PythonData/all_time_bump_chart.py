"""
generate_bump_charts.py

Reads compiled_stats.json and produces three season-over-season line charts
(JPEG) showing each team's actual value (not rank) for:
  1. Regular season points-for
  2. Regular season points-against
  3. Regular season wins

Output files are written to:
  (BASE_DIR / ".." / "Website" / "girderma-gridiron-website" / "src")
"""

import json
from pathlib import Path

import matplotlib
matplotlib.use("Agg")  # headless-safe backend, still writes JPEGs fine
import matplotlib.pyplot as plt

# ---------------------------------------------------------------------------
# Paths
# ---------------------------------------------------------------------------
BASE_DIR = Path(__file__).resolve().parent
STATS_FILE = BASE_DIR / "league_stats_output" / "compiled_stats.json"

output_dir = (BASE_DIR / ".." / "Website" / "girderma-gridiron-website" / "src").resolve()
output_dir.mkdir(parents=True, exist_ok=True)


# ---------------------------------------------------------------------------
# Data loading / shaping
# ---------------------------------------------------------------------------
def load_stats(path: Path) -> dict:
    with open(path, "r", encoding="utf-8") as f:
        return json.load(f)


def collect_seasons(data: dict) -> list[str]:
    """All seasons that appear anywhere in the data, sorted chronologically."""
    seasons = set()
    for team_data in data.values():
        seasons.update(team_data.get("seasons", {}).keys())
    return sorted(seasons)


def build_metric_values(data: dict, seasons: list[str], metric: str) -> dict:
    """
    Returns {season: {team_key: value}} for regular_season[metric],
    only including teams that actually played that season.
    """
    values_by_season = {season: {} for season in seasons}
    for team_key, team_data in data.items():
        for season, season_data in team_data.get("seasons", {}).items():
            reg = season_data.get("regular_season", {})
            if metric in reg:
                values_by_season[season][team_key] = reg[metric]
    return values_by_season


def build_values_by_team(values_by_season: dict, seasons: list[str], ascending: bool) -> dict:
    """
    Returns {team_key: {season: cumulative_value}}, i.e. the running total of
    the metric across seasons played, in chronological order.
    """
    values_by_team: dict = {}
    for season in seasons:
        teams_values = values_by_season[season]
        ordered = sorted(teams_values.items(), key=lambda kv: kv[1], reverse=not ascending)
        for team_key, val in ordered:
            prior_total = 0
            if team_key in values_by_team and season != seasons[0]:
                # get the most recent cumulative value recorded for this team
                prior_seasons = [s for s in seasons if s in values_by_team[team_key]]
                if prior_seasons:
                    prior_total = values_by_team[team_key][prior_seasons[-1]]
            values_by_team.setdefault(team_key, {})[season] = prior_total + val
    return values_by_team


NICKNAME_ALIASES = {
    ("Josh", "No Punts Intented"):      "Josh_Rubik",
    ("Josh", "The Sage's Playmakers"):  "Josh_Sage",
    ("Josh", "Room 40"):                "Josh_Rubik",
    ("Josh", "Mahomes Alone"):          "Josh_Rubik",
    ("Sam",  "Pad D's"):                "Sam_Paddy",
    ("Sam",  "Girder\u2019s Grippers"): "Sam_Girder",
}


def team_label(data: dict, team_key: str) -> str:
    team_data = data[team_key]
    nickname = team_data.get("nickname", team_key)

    for season_data in team_data.get("seasons", {}).values():
        team_name = season_data.get("team_name")
        if (nickname, team_name) in NICKNAME_ALIASES:
            return NICKNAME_ALIASES[(nickname, team_name)]

    return nickname


# ---------------------------------------------------------------------------
# Plotting
# ---------------------------------------------------------------------------
def declutter_positions(items, min_gap):
    """items: list of [key, y_value]. Nudges y-values apart so labels don't overlap."""
    items = sorted(items, key=lambda kv: kv[1])
    for i in range(1, len(items)):
        if items[i][1] - items[i-1][1] < min_gap:
            items[i][1] = items[i-1][1] + min_gap
    return {k: y for k, y in items}

def plot_bump_chart(
    data: dict,
    seasons: list[str],
    values_by_team: dict,
    y_label: str,
    title: str,
    filename: str,
    output_dir: Path,
):
    n_teams = len(values_by_team)
    x_positions = list(range(len(seasons)))

    fig_height = max(10, n_teams * 0.9)
    fig, ax = plt.subplots(figsize=(max(12, len(seasons) * 3.0), fig_height))
 
    cmap = matplotlib.colormaps["tab20"].resampled(n_teams)
    team_keys_sorted = sorted(
        values_by_team.keys(),
        key=lambda tk: values_by_team[tk].get(seasons[0], float("-inf")),
        reverse=True,
    )

    seasons_present = {}  # team_key -> (xs, ys)
    for idx, team_key in enumerate(team_keys_sorted):
        team_values = values_by_team[team_key]
        xs, ys = [], []
        for x, season in zip(x_positions, seasons):
            if season in team_values:
                xs.append(x)
                ys.append(team_values[season])

        if not xs:
            continue

        seasons_present[team_key] = (xs, ys)

        color = cmap(idx)
        ax.plot(
            xs, ys,
            marker="o",
            markersize=7,
            linewidth=2,
            color=color,
            zorder=3,
        )

    all_values_for_gap = [v for team_values in values_by_team.values() for v in team_values.values()]
    y_range_for_gap = max(all_values_for_gap) - min(all_values_for_gap) if all_values_for_gap else 1
    min_gap = y_range_for_gap * 0.035

    start_items = [[tk, xy[1][0]] for tk, xy in seasons_present.items()]
    end_items = [[tk, xy[1][-1]] for tk, xy in seasons_present.items()]
    start_y = declutter_positions(start_items, min_gap)
    end_y = declutter_positions(end_items, min_gap)

    for idx, team_key in enumerate(team_keys_sorted):
        if team_key not in seasons_present:
            continue
        xs, ys = seasons_present[team_key]
        color = cmap(idx)
        label = team_label(data, team_key)

        ax.text(
            xs[0] - 0.12, start_y[team_key], label,
            ha="right", va="center", fontsize=9, fontweight="bold", color=color,
        )
        ax.text(
            xs[-1] + 0.12, end_y[team_key], label,
            ha="left", va="center", fontsize=9, fontweight="bold", color=color,
        )

    all_values = [v for team_values in values_by_team.values() for v in team_values.values()]
    y_min, y_max = min(all_values), max(all_values)
    y_range = y_max - y_min
    padding = y_range * 0.08 if y_range > 0 else 1
    ax.set_ylim(y_min - padding, y_max + padding)

    ax.set_xticks(x_positions)
    ax.set_xticklabels(seasons, fontsize=11, fontweight="bold")
    ax.set_xlim(-1.3, len(seasons) - 1 + 1.3)

    ax.set_ylabel(y_label, fontsize=11, fontweight="bold")

    ax.set_title(title, fontsize=15, fontweight="bold", pad=15)
    ax.grid(True, axis="y", linestyle="--", alpha=0.4)
    ax.grid(False, axis="x")

    for spine in ("top", "right"):
        ax.spines[spine].set_visible(False)

    fig.tight_layout()

    out_path = output_dir / filename
    fig.savefig(out_path, format="jpeg", dpi=200)
    plt.close(fig)
    print(f"Saved: {out_path}")


# ---------------------------------------------------------------------------
# Main
# ---------------------------------------------------------------------------
def main():
    data = load_stats(STATS_FILE)
    seasons = collect_seasons(data)

    metrics = [
        {
            "key": "points_for",
            "ascending": False,  # higher PF sorts first in initial label order
            "y_label": "Points For",
            "title": "Regular Season Points For — Bump Chart",
            "filename": "bump_chart_points_for.jpeg",
        },
        {
            "key": "points_against",
            "ascending": True,  # lower PA sorts first in initial label order
            "y_label": "Points Against",
            "title": "Regular Season Points Against — Bump Chart",
            "filename": "bump_chart_points_against.jpeg",
        },
        {
            "key": "wins",
            "ascending": False,  # more wins sorts first in initial label order
            "y_label": "Wins",
            "title": "Regular Season Wins — Bump Chart",
            "filename": "bump_chart_wins.jpeg",
        },
    ]

    for m in metrics:
        values_by_season = build_metric_values(data, seasons, m["key"])
        values_by_team = build_values_by_team(values_by_season, seasons, ascending=m["ascending"])
        plot_bump_chart(
            data=data,
            seasons=seasons,
            values_by_team=values_by_team,
            y_label=m["y_label"],
            title=m["title"],
            filename=m["filename"],
            output_dir=output_dir,
        )


if __name__ == "__main__":
    main()