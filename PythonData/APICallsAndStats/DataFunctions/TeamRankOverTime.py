"""
bump_chart.py

Create a bump chart (team rank over time) from a yahoo_fantasy_api League object.

Usage from another file:

    from yahoo_oauth import OAuth2
    import yahoo_fantasy_api as yfa
    from bump_chart import create_bump_chart

    sc = OAuth2(None, None, from_file="oauth2.json")
    league = yfa.League(sc, "449.l.123456")

    path = create_bump_chart(league, "output/charts")
    print(path)

Rankings are computed week by week from completed head-to-head matchups:
cumulative wins (ties count as half a win), with cumulative points-for as the
tiebreaker. This is an approximation of Yahoo's standings, so the final week may
differ slightly from the official standings (playoff seeding rules, custom
tiebreakers, etc.).
"""

from __future__ import annotations

from pathlib import Path
from typing import Optional, Union

import matplotlib.pyplot as plt
import pandas as pd

__all__ = ["create_bump_chart", "build_rank_history", "plot_bump_chart"]


# ----------------------------------------------------------------------------
# Parsing helpers (Yahoo's JSON is deeply nested and uses numeric string keys)
# ----------------------------------------------------------------------------
def _numbered_items(d: dict):
    """Yield the values of a Yahoo dict whose keys are '0', '1', ... plus 'count'."""
    for key, value in d.items():
        if key != "count":
            yield value


def _flatten(info) -> dict:
    """Merge Yahoo's list-of-single-key-dicts into one dict."""
    if isinstance(info, dict):
        return info
    merged = {}
    for item in info:
        if isinstance(item, dict):
            merged.update(item)
    return merged


def _parse_week_matchups(raw: dict) -> list[dict]:
    """Turn the raw league.matchups() response into a list of simple dicts."""
    league_data = raw["fantasy_content"]["league"]
    scoreboard = league_data[1]["scoreboard"]
    matchups = scoreboard["0"]["matchups"]

    parsed = []
    for entry in _numbered_items(matchups):
        m = entry["matchup"]
        teams = []
        for t in _numbered_items(m["0"]["teams"]):
            team = t["team"]
            info = _flatten(team[0])
            stats = team[1]
            points = float(stats.get("team_points", {}).get("total", 0) or 0)
            teams.append(
                {"key": info["team_key"], "name": info["name"], "points": points}
            )
        parsed.append(
            {
                "status": m.get("status"),
                "winner": m.get("winner_team_key"),
                "tied": str(m.get("is_tied", 0)) == "1",
                "teams": teams,
            }
        )
    return parsed


# ----------------------------------------------------------------------------
# Data building
# ----------------------------------------------------------------------------
def build_rank_history(league, start_week: Optional[int] = None,
                       end_week: Optional[int] = None) -> pd.DataFrame:
    """
    Build a long-format DataFrame with columns: week, team, rank.

    Only weeks with completed matchups are included. Defaults to every week
    from the league's start week through the last completed week.
    """
    settings = league.settings()
    if start_week is None:
        start_week = int(settings.get("start_week", 1))
    if end_week is None:
        # current_week() is usually in progress, so cap at it and skip
        # unfinished matchups below.
        season_end = int(settings.get("end_week", league.current_week()))
        end_week = min(int(league.current_week()), season_end)

    wins: dict[str, float] = {}
    points: dict[str, float] = {}
    names: dict[str, str] = {}
    rows = []

    for week in range(start_week, end_week + 1):
        matchups = _parse_week_matchups(league.matchups(week=week))

        # Skip weeks that haven't finished yet
        if not matchups or any(m["status"] != "postevent" for m in matchups):
            continue

        for m in matchups:
            for t in m["teams"]:
                names[t["key"]] = t["name"]
                wins.setdefault(t["key"], 0.0)
                points.setdefault(t["key"], 0.0)
                points[t["key"]] += t["points"]
                if m["tied"]:
                    wins[t["key"]] += 0.5
                elif m["winner"] == t["key"]:
                    wins[t["key"]] += 1.0

        ordered = sorted(wins, key=lambda k: (wins[k], points[k]), reverse=True)
        for rank, key in enumerate(ordered, start=1):
            rows.append({"week": week, "team": names[key], "rank": rank})

    if not rows:
        raise ValueError("No completed weeks found for this league yet.")

    return pd.DataFrame(rows)


# ----------------------------------------------------------------------------
# Plotting
# ----------------------------------------------------------------------------
def plot_bump_chart(df: pd.DataFrame, title: str, outfile: Path,
                    dpi: int = 300, figsize: tuple = (16, 10)) -> Path:
    """Plot a long-format (week, team, rank) DataFrame and save it to outfile."""
    rankings = df.pivot(index="week", columns="team", values="rank").sort_index()
    last_week = rankings.index.max()

    fig, ax = plt.subplots(figsize=figsize)

    for team in rankings.columns:
        ax.plot(rankings.index, rankings[team], marker="o", linewidth=2)
        ax.text(
            last_week + 0.25,
            rankings.loc[last_week, team],
            team,
            fontsize=9,
            va="center",
        )

    ax.invert_yaxis()
    ax.set_title(title, fontsize=18)
    ax.set_xlabel("Week")
    ax.set_ylabel("Rank")
    ax.set_xticks(rankings.index)
    ax.set_yticks(range(1, len(rankings.columns) + 1))
    ax.grid(axis="y", linestyle="--", alpha=0.3)
    ax.spines["top"].set_visible(False)
    ax.spines["right"].set_visible(False)
    ax.set_xlim(rankings.index.min(), last_week + 2)

    fig.tight_layout()
    fig.savefig(outfile, dpi=dpi, bbox_inches="tight")
    plt.close(fig)
    return outfile


# ----------------------------------------------------------------------------
# Public entry point
# ----------------------------------------------------------------------------
def create_bump_chart(league, output_dir: Union[str, Path],
                      filename: Optional[str] = None,
                      title: Optional[str] = None,
                      start_week: Optional[int] = None,
                      end_week: Optional[int] = None,
                      dpi: int = 300) -> Path:
    """
    Create a bump chart of team rank over time and save it to output_dir.

    Parameters
    ----------
    league : yahoo_fantasy_api.League
        An authenticated League object.
    output_dir : str | Path
        Directory to save the chart in (created if missing).
    filename : str, optional
        Output file name. Defaults to "bump_chart_<season>.jpg". The extension
        (.jpg, .png, .svg, ...) controls the image format.
    title : str, optional
        Chart title. Defaults to "<season> Fantasy League Standings".
    start_week, end_week : int, optional
        Restrict the range of weeks plotted.
    dpi : int
        Image resolution.

    Returns
    -------
    Path to the saved image.
    """
    output_dir = Path(output_dir).expanduser().resolve()
    output_dir.mkdir(parents=True, exist_ok=True)

    settings = league.settings()
    season = settings.get("season", "")

    df = build_rank_history(league, start_week=start_week, end_week=end_week)

    filename = filename or f"bump_chart_{season}.jpg"
    title = title or f"{season} Fantasy League Standings".strip()

    return plot_bump_chart(df, title, output_dir / filename, dpi=dpi)