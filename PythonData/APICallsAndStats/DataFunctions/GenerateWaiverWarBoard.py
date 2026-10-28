"""
Renders the Waiver WAR board image (and its color legend) from a season's
WaiverWar.json.

Reads:   ../Data/{year}/WaiverWar.json   (written by CalculateWaiverWAR.py)
         ../Data/{year}/DraftValue.json  (optional -- only used for column order)
Writes:  ../Data/{year}/WaiverWar/
             waiver_war_board_{year}.png            one column per team, pickups sorted
                                                    by WAR (high to low), colored by WAR
             waiver_war_board_{year}_colorbar.png   legend strip for the board

Column order matches the old board: teams in round-1 draft order, taken from
DraftValue.json. Any team not found there is appended after, sorted by team
key. If DraftValue.json is missing, every team falls into that second group.

Usage:
    python3 RenderWaiverWarBoard.py 2026
or from other code:
    from RenderWaiverWarBoard import generate_waiver_war_board_and_legend
    generate_waiver_war_board_and_legend(2026)

Paths are resolved relative to this file's directory, not the current
working directory.
"""

import json
import os
import sys
from pathlib import Path

import matplotlib
matplotlib.use("Agg")
import matplotlib.colorbar
import matplotlib.colors
import matplotlib.pyplot as plt

SCRIPT_DIR = os.path.dirname(os.path.abspath(__file__))


# --------------------------------------------------------------------------
# PATHS
# --------------------------------------------------------------------------
def get_year_dir(year: int) -> Path:
    return (Path(SCRIPT_DIR) / ".." / "Data" / str(year)).resolve()


def get_waiver_war_path(year: int) -> Path:
    return get_year_dir(year) / "WaiverWar.json"


def get_draft_value_path(year: int) -> Path:
    return get_year_dir(year) / "DraftValue.json"


def get_output_dir(year: int) -> Path:
    return get_year_dir(year) / "WaiverWar"


# --------------------------------------------------------------------------
# DATA LOADING
# --------------------------------------------------------------------------
def load_rows(year: int) -> list:
    """
    Loads WaiverWar.json and returns rows in the shape the original board
    code used: team_key, team_name, manager, player_id, player_name,
    position, weeks_rostered, war.
    """
    path = get_waiver_war_path(year)
    if not path.exists():
        raise FileNotFoundError(f"No waiver WAR file found at {path}")

    with open(path, "r", encoding="utf-8") as f:
        raw = json.load(f)

    rows = []
    for r in raw:
        rows.append({
            "team_key": r["Team Key"],
            "team_name": r["Team"],
            "manager": r.get("Manager"),
            "player_id": str(r["Player ID"]),
            "player_name": r["Player"],
            "position": r["Position"],
            "weeks_rostered": r["Weeks Rostered"],
            "war": float(r["WAR"]),
        })
    return rows


def load_round1_team_order(year: int) -> list:
    """Team names in round-1 draft order, from DraftValue.json ([] if missing)."""
    path = get_draft_value_path(year)
    if not path.exists():
        print(f"[{year}] {path.name} not found -- columns will be ordered by team key "
              f"instead of round-1 draft order.")
        return []
    with open(path, "r", encoding="utf-8") as f:
        raw = json.load(f)
    round1 = sorted((p for p in raw if p["Round"] == 1), key=lambda p: p["Pick"])
    return [p["Drafted By"] for p in round1]


# --------------------------------------------------------------------------
# IMAGE: waiver WAR board -- one column per team, pickups sorted by WAR
# descending top-to-bottom, colored by WAR
# --------------------------------------------------------------------------
def render_waiver_war_board(rows: list, round1_team_order: list, year: int,
                            output_directory) -> None:
    # Column order: each team's round-1 pick order, falling back to team
    # key order for any team not in that list.
    # Each column is identified by team name; its label is the manager
    # nickname if known, else the team name (same as the old board).
    label_by_team = {}
    for r in rows:
        label_by_team.setdefault(r["team_name"], r["manager"] or r["team_name"])

    columns = [
        {"team_key": team_name, "label": label_by_team.get(team_name, team_name)}
        for team_name in round1_team_order
    ]
    known_team_keys = {c["team_key"] for c in columns}

    team_key_by_name = {}
    for r in rows:
        team_key_by_name.setdefault(r["team_name"], r["team_key"])
    extra_teams = sorted(
        {r["team_name"] for r in rows if r["team_name"] not in known_team_keys},
        key=lambda name: team_key_by_name[name],
    )
    for team_name in extra_teams:
        columns.append({"team_key": team_name, "label": label_by_team[team_name]})

    rows_by_team = {}
    for r in rows:
        rows_by_team.setdefault(r["team_name"], []).append(r)
    for team_key in rows_by_team:
        rows_by_team[team_key].sort(key=lambda r: r["war"], reverse=True)

    max_pickups = max((len(v) for v in rows_by_team.values()), default=0)
    if max_pickups == 0:
        print(f"[{year}] No waiver pickups found -- skipping board image.")
        return

    all_war_values = [r["war"] for r in rows]
    v_max = max((v for v in all_war_values if v > 0), default=1.0) or 1.0
    v_min = min((v for v in all_war_values if v < 0), default=-1.0) or -1.0

    reds = matplotlib.colormaps["Reds"]
    blues = matplotlib.colormaps["Blues"]

    def intensity(value: float) -> float:
        if value >= 0:
            return value / v_max if v_max else 0.0
        return value / v_min if v_min else 0.0

    n_rows = max_pickups
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

    for col_idx, col in enumerate(columns):
        team_rows = rows_by_team.get(col["team_key"], [])
        for row_idx in range(n_rows):
            x, y = col_idx, row_idx
            if row_idx < len(team_rows):
                r = team_rows[row_idx]
                war = r["war"]
                t = intensity(war)
                face_color = reds(t) if war >= 0 else blues(t)
            else:
                face_color = "#FFFFFF"

            rect = plt.Rectangle(
                (x, y), 1, 1,
                facecolor=face_color,
                edgecolor="white",
                linewidth=1.5,
            )
            ax.add_patch(rect)

            if row_idx >= len(team_rows):
                continue

            r = team_rows[row_idx]
            text_color = "#FFFFFF" if intensity(r["war"]) > 0.6 else "#111827"
            n_weeks = len(r["weeks_rostered"])
            label = f"{r['war']:+.3f}\n{r['player_name']}\n({n_weeks}wk)"
            ax.text(
                x + 0.5, y + 0.5, label,
                ha="center", va="center", fontsize=7.2, color=text_color, linespacing=1.3,
            )

    ax.set_title(f"{year} Waiver Wire / Free Agent Pickup WAR (scoped to weeks rostered)",
                 fontsize=15, fontweight="bold", color="#111827", pad=36)

    fig.tight_layout()
    output_directory = Path(output_directory)
    output_directory.mkdir(parents=True, exist_ok=True)
    output_path = output_directory / f"waiver_war_board_{year}.png"
    fig.savefig(output_path, dpi=200, bbox_inches="tight")
    plt.close(fig)
    print(f"Saved -> {output_path}")

    n_stops = 256
    blue_half = [blues(1.0 - i / (n_stops // 2 - 1)) for i in range(n_stops // 2)]
    red_half = [reds(i / (n_stops // 2 - 1)) for i in range(n_stops // 2)]
    diverging_cmap = matplotlib.colors.ListedColormap(blue_half + red_half)

    fig2, ax2 = plt.subplots(figsize=(6, 0.6))
    fig2.subplots_adjust(bottom=0.5)
    norm_ = matplotlib.colors.Normalize(vmin=v_min, vmax=v_max)
    cb = matplotlib.colorbar.ColorbarBase(ax2, cmap=diverging_cmap, norm=norm_, orientation="horizontal")
    cb.set_label("WAR, scoped to weeks rostered (negative -> positive)", fontsize=9)
    colorbar_path = output_path.with_name(output_path.stem + "_colorbar.png")
    fig2.savefig(colorbar_path, dpi=200, bbox_inches="tight")
    plt.close(fig2)
    print(f"Saved -> {colorbar_path}")


# --------------------------------------------------------------------------
# ENTRY POINT
# --------------------------------------------------------------------------
def generate_waiver_war_board_and_legend(year: int) -> None:
    rows = load_rows(year)
    round1_team_order = load_round1_team_order(year)
    output_dir = get_output_dir(year)
    output_dir.mkdir(parents=True, exist_ok=True)
    render_waiver_war_board(rows, round1_team_order, year, output_dir)


if __name__ == "__main__":
    if len(sys.argv) != 2:
        print("Usage: python3 RenderWaiverWarBoard.py <year>")
        sys.exit(1)
    generate_waiver_war_board_and_legend(int(sys.argv[1]))