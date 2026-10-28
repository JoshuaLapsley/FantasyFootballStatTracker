"""
Renders the PAR draft board image (and its color legend) from a season's DraftValue.json.

Reads:   ../Data/{year}/DraftValue.json
Writes:  ../Data/{year}/Par/
             draft_board_by_par_{year}.png        grid colored by PAR (red = positive,
                                                  blue = negative, darker = more extreme)
             draft_board_by_par_{year}_colorbar.png   legend strip for the PAR board

Usage:
    python3 RenderDraftBoards.py 2026
or from other code:
    from RenderDraftBoards import generate_par_board_and_legend
    generate_par_board_and_legend(2026)

Paths are resolved relative to this file's directory (same convention as
RunWeekly.py), not the current working directory.
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
    return get_year_dir(year) / "Par"


# --------------------------------------------------------------------------
# DATA LOADING
# --------------------------------------------------------------------------
def load_board(year: int) -> tuple:
    """
    Loads DraftValue.json and returns (board, par_by_id).

    board: list of pick dicts in the same shape the original draft_par.py
           code used (pick, round, team_name, player_id, player_name,
           position), sorted by pick.
    par_by_id: {player_id: PAR}
    """
    path = get_draft_value_path(year)
    if not path.exists():
        raise FileNotFoundError(f"No draft value file found at {path}")

    with open(path, "r", encoding="utf-8") as f:
        rows = json.load(f)

    board = []
    par_by_id = {}
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
        par_by_id[pid] = float(row["PAR"])

    board.sort(key=lambda p: p["pick"])
    return board, par_by_id


# --------------------------------------------------------------------------
# BOARD GRID (rows = round, columns = teams in round-1 draft order)
# --------------------------------------------------------------------------
def build_board_grid(board: list) -> tuple:
    """
    Returns (rounds, columns, cell_by_round_and_team).

    Columns are ordered by each team's round-1 pick (left to right in
    draft order), same convention the website's own Draft.tsx board uses.
    """
    round1_picks = sorted((p for p in board if p["round"] == 1), key=lambda p: p["pick"])
    columns = [{"team_key": p["team_name"], "label": p["team_name"]} for p in round1_picks]

    rounds = sorted({p["round"] for p in board})

    cell_by_round_and_team = {}
    for p in board:
        cell_by_round_and_team[(p["round"], p["team_name"])] = p

    return rounds, columns, cell_by_round_and_team


def _draw_board(
    rounds,
    columns,
    cell_by_round_and_team,
    cell_color_fn,
    text_color_fn,
    cell_label_fn,
    title: str,
    output_path,
    legend_handles=None,
) -> None:
    """
    Shared grid-drawing routine. cell_color_fn/text_color_fn/cell_label_fn
    each take a single pick dict and return what to draw for that cell.
    """
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
    Path(output_path).parent.mkdir(parents=True, exist_ok=True)
    fig.savefig(output_path, dpi=200, bbox_inches="tight")
    plt.close(fig)
    print(f"Saved -> {output_path}")


# --------------------------------------------------------------------------
# PAR BOARD + LEGEND
# --------------------------------------------------------------------------
def render_par_board(rounds, columns, cell_by_round_and_team, par_by_id: dict,
                     year: int, output_dir: Path) -> None:
    """
    Diverging gradient split at zero: positive PAR uses the 'Reds'
    colormap (darker red = higher PAR), negative PAR uses the 'Blues'
    colormap (darker blue = more negative PAR). Each half is normalized
    independently against the actual positive/negative extremes seen this
    run, so both directions get full contrast regardless of scale.
    """
    par_values = [par_by_id.get(p["player_id"], 0.0) for p in cell_by_round_and_team.values()]
    par_max = max((v for v in par_values if v > 0), default=1.0) or 1.0
    par_min = min((v for v in par_values if v < 0), default=-1.0) or -1.0

    reds = matplotlib.colormaps["Reds"]
    blues = matplotlib.colormaps["Blues"]

    def intensity(value: float) -> float:
        """0..1 how far value is toward its side's extreme (0 at zero)."""
        if value >= 0:
            return value / par_max if par_max else 0.0
        return value / par_min if par_min else 0.0  # both negative -> positive ratio

    def cell_color(pick):
        if pick is None:
            return "#FFFFFF"
        par = par_by_id.get(pick["player_id"], 0.0)
        t = intensity(par)
        return reds(t) if par >= 0 else blues(t)

    def text_color(pick):
        if pick is None:
            return DEFAULT_TEXT_COLOR
        par = par_by_id.get(pick["player_id"], 0.0)
        # Flip to white text once the gradient gets dark enough to need it.
        return "#FFFFFF" if intensity(par) > 0.6 else "#111827"

    def label(pick):
        par = par_by_id.get(pick["player_id"], 0.0)
        return f"#{pick['pick']}  {par:+.1f}\n{pick['player_name']}"

    par_board_path = output_dir / f"draft_board_by_par_{year}.png"
    _draw_board(
        rounds, columns, cell_by_round_and_team,
        cell_color_fn=cell_color,
        text_color_fn=text_color,
        cell_label_fn=label,
        title=f"{year} Draft Board -- Points Above Replacement (PAR)",
        output_path=par_board_path,
        legend_handles=None,
    )

    # Colorbar as a separate small legend strip: blue (very negative) on
    # the left, through white at zero, to red (very positive) on the
    # right. Built by stitching the two halves into one diverging map
    # since 'Reds'/'Blues' individually only run light-to-dark, not
    # negative-to-positive.
    n_stops = 256
    blue_half = [blues(1.0 - i / (n_stops // 2 - 1)) for i in range(n_stops // 2)]
    red_half = [reds(i / (n_stops // 2 - 1)) for i in range(n_stops // 2)]
    diverging_cmap = matplotlib.colors.ListedColormap(blue_half + red_half)

    fig, ax = plt.subplots(figsize=(6, 0.6))
    fig.subplots_adjust(bottom=0.5)
    norm = matplotlib.colors.Normalize(vmin=par_min, vmax=par_max)
    cb = matplotlib.colorbar.ColorbarBase(ax, cmap=diverging_cmap, norm=norm, orientation="horizontal")
    cb.set_label("PAR (negative -> positive)", fontsize=9)
    colorbar_path = par_board_path.with_name(par_board_path.stem + "_colorbar.png")
    colorbar_path.parent.mkdir(parents=True, exist_ok=True)
    fig.savefig(colorbar_path, dpi=200, bbox_inches="tight")
    plt.close(fig)
    print(f"Saved -> {colorbar_path}")


# --------------------------------------------------------------------------
# ENTRY POINT
# --------------------------------------------------------------------------
def generate_par_board_and_legend(year: int) -> None:
    board, par_by_id = load_board(year)
    output_dir = get_output_dir(year)
    output_dir.mkdir(parents=True, exist_ok=True)

    rounds, columns, cell_by_round_and_team = build_board_grid(board)
    render_par_board(rounds, columns, cell_by_round_and_team, par_by_id, year, output_dir)


if __name__ == "__main__":
    if len(sys.argv) != 2:
        print("Usage: python3 RenderDraftBoards.py <year>")
        sys.exit(1)
    generate_par_board_and_legend(int(sys.argv[1]))