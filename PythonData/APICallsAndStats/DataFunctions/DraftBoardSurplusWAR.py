"""
Renders the Surplus WAR draft board image (and its color legend) from a
season's DraftValue.json.

Reads:   ../Data/{year}/DraftValue.json   (uses each row's "Surplus WAR")
Writes:  ../Data/{year}/SurplusWar/
             draft_board_surplus_war_{year}.png            grid colored by surplus WAR
                                                           (red = positive, blue = negative,
                                                           darker = more extreme)
             draft_board_surplus_war_{year}_colorbar.png   legend strip for the board

Usage:
    python3 RenderSurplusWarBoard.py 2026
or from other code:
    from RenderSurplusWarBoard import generate_surplus_war_board_and_legend
    generate_surplus_war_board_and_legend(2026)

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

DEFAULT_TEXT_COLOR = "#374151"


# --------------------------------------------------------------------------
# PATHS
# --------------------------------------------------------------------------
def get_year_dir(year: int) -> Path:
    return (Path(SCRIPT_DIR) / ".." / "Data" / str(year)).resolve()


def get_draft_value_path(year: int) -> Path:
    return get_year_dir(year) / "DraftValue.json"


def get_output_dir(year: int) -> Path:
    return get_year_dir(year) / "SurplusWar"


# --------------------------------------------------------------------------
# DATA LOADING
# --------------------------------------------------------------------------
def load_board(year: int) -> tuple:
    """
    Loads DraftValue.json and returns (board, surplus_by_id).

    board: list of pick dicts (pick, round, team_name, player_id,
           player_name, position), sorted by pick.
    surplus_by_id: {player_id: Surplus WAR}
    """
    path = get_draft_value_path(year)
    if not path.exists():
        raise FileNotFoundError(f"No draft value file found at {path}")

    with open(path, "r", encoding="utf-8") as f:
        rows = json.load(f)

    board = []
    surplus_by_id = {}
    for row in rows:
        pid = str(row["Player ID"])
        board.append({
            "pick": row["Pick"],
            "round": row["Round"],
            # DraftValue.json only stores the team name ("Drafted By"), so
            # the team name doubles as both the column key and column label.
            "team_name": row["Drafted By"],
            "player_id": pid,
            "player_name": row["Player"],
            "position": row["Position"],
        })
        surplus_by_id[pid] = float(row["Surplus WAR"])

    board.sort(key=lambda p: p["pick"])
    return board, surplus_by_id


# --------------------------------------------------------------------------
# BOARD GRID (rows = round, columns = teams in round-1 draft order)
# --------------------------------------------------------------------------
def build_board_grid(board: list) -> tuple:
    round1_picks = sorted((p for p in board if p["round"] == 1), key=lambda p: p["pick"])
    columns = [{"team_key": p["team_name"], "label": p["team_name"]} for p in round1_picks]

    rounds = sorted({p["round"] for p in board})

    cell_by_round_and_team = {}
    for p in board:
        cell_by_round_and_team[(p["round"], p["team_name"])] = p

    return rounds, columns, cell_by_round_and_team


def _draw_board(rounds, columns, cell_by_round_and_team, cell_color_fn, text_color_fn,
                cell_label_fn, title: str, output_path) -> None:
    """Shared grid-drawing routine."""
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

    # Column headers (team names).
    for col_idx, col in enumerate(columns):
        ax.text(
            col_idx + 0.5, -0.55, col["label"],
            ha="center", va="center", fontsize=10, fontweight="bold", color="#111827",
        )

    # Row headers (round numbers).
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

            ax.text(
                x + 0.5, y + 0.5, cell_label_fn(pick),
                ha="center", va="center", fontsize=7.8,
                color=text_color_fn(pick), linespacing=1.4,
            )

    ax.set_title(title, fontsize=15, fontweight="bold", color="#111827", pad=36)

    fig.tight_layout()
    Path(output_path).parent.mkdir(parents=True, exist_ok=True)
    fig.savefig(output_path, dpi=200, bbox_inches="tight")
    plt.close(fig)
    print(f"Saved -> {output_path}")


def _save_diverging_colorbar(blues, reds, value_min: float, value_max: float,
                             label: str, image_path: Path) -> None:
    """Blue (very negative) -> white (zero) -> red (very positive) legend strip."""
    n_stops = 256
    blue_half = [blues(1.0 - i / (n_stops // 2 - 1)) for i in range(n_stops // 2)]
    red_half = [reds(i / (n_stops // 2 - 1)) for i in range(n_stops // 2)]
    diverging_cmap = matplotlib.colors.ListedColormap(blue_half + red_half)

    fig, ax = plt.subplots(figsize=(6, 0.6))
    fig.subplots_adjust(bottom=0.5)
    norm_ = matplotlib.colors.Normalize(vmin=value_min, vmax=value_max)
    cb = matplotlib.colorbar.ColorbarBase(ax, cmap=diverging_cmap, norm=norm_, orientation="horizontal")
    cb.set_label(label, fontsize=9)
    colorbar_path = Path(image_path).with_name(Path(image_path).stem + "_colorbar.png")
    colorbar_path.parent.mkdir(parents=True, exist_ok=True)
    fig.savefig(colorbar_path, dpi=200, bbox_inches="tight")
    plt.close(fig)
    print(f"Saved -> {colorbar_path}")


# --------------------------------------------------------------------------
# SURPLUS WAR BOARD + LEGEND
# --------------------------------------------------------------------------
def render_surplus_war_board(board: list, surplus_by_id: dict, year: int, output_dir: Path) -> None:
    """
    Diverging gradient split at zero: positive surplus uses 'Reds'
    (darker = higher), negative surplus uses 'Blues' (darker = more
    negative). Each half is normalized independently against the actual
    positive/negative extremes, so both directions get full contrast.
    """
    rounds, columns, cell_by_round_and_team = build_board_grid(board)

    def value_fn(pick):
        return surplus_by_id.get(pick["player_id"], 0.0)

    values = [value_fn(p) for p in cell_by_round_and_team.values()]
    v_max = max((v for v in values if v > 0), default=1.0) or 1.0
    v_min = min((v for v in values if v < 0), default=-1.0) or -1.0

    reds = matplotlib.colormaps["Reds"]
    blues = matplotlib.colormaps["Blues"]

    def intensity(value: float) -> float:
        if value >= 0:
            return value / v_max if v_max else 0.0
        return value / v_min if v_min else 0.0

    def cell_color(pick):
        if pick is None:
            return "#FFFFFF"
        value = value_fn(pick)
        t = intensity(value)
        return reds(t) if value >= 0 else blues(t)

    def text_color(pick):
        if pick is None:
            return DEFAULT_TEXT_COLOR
        return "#FFFFFF" if intensity(value_fn(pick)) > 0.6 else "#111827"

    def label(pick):
        return f"#{pick['pick']}  {value_fn(pick):+.3f}\n{pick['player_name']}"

    output_path = output_dir / f"draft_board_surplus_war_{year}.png"
    _draw_board(
        rounds, columns, cell_by_round_and_team,
        cell_color_fn=cell_color,
        text_color_fn=text_color,
        cell_label_fn=label,
        title=f"{year} Draft Board -- Actual WAR minus Expected WAR (Surplus WAR)",
        output_path=output_path,
    )
    _save_diverging_colorbar(
        blues, reds, v_min, v_max,
        "Surplus WAR: actual - expected (negative -> positive)",
        output_path,
    )


# --------------------------------------------------------------------------
# ENTRY POINT
# --------------------------------------------------------------------------
def generate_surplus_war_board_and_legend(year: int) -> None:
    board, surplus_by_id = load_board(year)
    output_dir = get_output_dir(year)
    output_dir.mkdir(parents=True, exist_ok=True)
    render_surplus_war_board(board, surplus_by_id, year, output_dir)


if __name__ == "__main__":
    if len(sys.argv) != 2:
        print("Usage: python3 RenderSurplusWarBoard.py <year>")
        sys.exit(1)
    generate_surplus_war_board_and_legend(int(sys.argv[1]))