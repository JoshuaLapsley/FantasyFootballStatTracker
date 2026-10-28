"""
Render the WAR draft board images from the pre-computed draft value JSON.

Reads:   ../Data/{YEAR}/DraftValue.JSON
Writes:  ../Data/{YEAR}/War/draft_board_by_war_{YEAR}.png
         ../Data/{YEAR}/War/draft_board_by_war_{YEAR}_colorbar.png

Usage:
    python3 DraftBoardWAR.py 2026       # year is required

The board is a grid (rows = draft rounds, columns = teams in round-1 pick
order). Cells are colored by season WAR: red gradient for positive WAR
(darker = higher), blue gradient for negative WAR (darker = more negative),
white at zero.
"""

import json
import sys
from pathlib import Path

import matplotlib
matplotlib.use("Agg")
import matplotlib.cm
import matplotlib.colors
import matplotlib.pyplot as plt

DEFAULT_TEXT_COLOR = "#374151"

SCRIPT_DIR = Path(__file__).resolve().parent


# --------------------------------------------------------------------------
# DATA
# --------------------------------------------------------------------------
def load_draft_value(year: int) -> list:
    path = SCRIPT_DIR / ".." / "Data" / str(year) / "DraftValue.JSON"
    with open(path, "r", encoding="utf-8") as f:
        return json.load(f)


def build_board_grid(picks: list) -> tuple:
    """
    Returns (rounds, columns, cell_by_round_and_team).
    Columns are teams ("Drafted By") ordered by their round-1 pick.
    """
    round1 = sorted((p for p in picks if p["Round"] == 1), key=lambda p: p["Pick"])
    columns = [p["Drafted By"] for p in round1]

    # Fallback: any team with no round-1 pick in the data goes at the end.
    for p in sorted(picks, key=lambda p: p["Pick"]):
        if p["Drafted By"] not in columns:
            columns.append(p["Drafted By"])

    rounds = sorted({p["Round"] for p in picks})
    cells = {(p["Round"], p["Drafted By"]): p for p in picks}
    return rounds, columns, cells


# --------------------------------------------------------------------------
# DRAWING
# --------------------------------------------------------------------------
def draw_board(rounds, columns, cells, cell_color_fn, text_color_fn,
               cell_label_fn, title: str, output_path: Path) -> None:
    n_rows, n_cols = len(rounds), len(columns)

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

    for col_idx, label in enumerate(columns):
        ax.text(col_idx + 0.5, -0.55, label, ha="center", va="center",
                fontsize=10, fontweight="bold", color="#111827")

    for row_idx, round_num in enumerate(rounds):
        ax.text(-0.3, row_idx + 0.5, f"R{round_num}", ha="center", va="center",
                fontsize=9, fontweight="bold", color="#6B7280")

    for row_idx, round_num in enumerate(rounds):
        for col_idx, team in enumerate(columns):
            pick = cells.get((round_num, team))
            ax.add_patch(plt.Rectangle(
                (col_idx, row_idx), 1, 1,
                facecolor=cell_color_fn(pick), edgecolor="white", linewidth=1.5,
            ))
            if pick is None:
                continue
            ax.text(col_idx + 0.5, row_idx + 0.5, cell_label_fn(pick),
                    ha="center", va="center", fontsize=7.8,
                    color=text_color_fn(pick), linespacing=1.4)

    ax.set_title(title, fontsize=15, fontweight="bold", color="#111827", pad=36)

    fig.tight_layout()
    fig.savefig(output_path, dpi=200, bbox_inches="tight")
    plt.close(fig)
    print(f"Saved -> {output_path}")


def render_war_images(picks: list, year: int, output_dir: Path) -> None:
    rounds, columns, cells = build_board_grid(picks)

    war_values = [p["WAR"] for p in cells.values()]
    war_max = max((v for v in war_values if v > 0), default=1.0) or 1.0
    war_min = min((v for v in war_values if v < 0), default=-1.0) or -1.0

    reds = matplotlib.colormaps["Reds"]
    blues = matplotlib.colormaps["Blues"]

    def intensity(value: float) -> float:
        return value / war_max if value >= 0 else value / war_min

    def cell_color(pick):
        if pick is None:
            return "#FFFFFF"
        war = pick["WAR"]
        t = intensity(war)
        return reds(t) if war >= 0 else blues(t)

    def text_color(pick):
        if pick is None:
            return DEFAULT_TEXT_COLOR
        return "#FFFFFF" if intensity(pick["WAR"]) > 0.6 else "#111827"

    def label(pick):
        return f"#{pick['Pick']}  {pick['WAR']:+.3f}\n{pick['Player']}"

    output_dir.mkdir(parents=True, exist_ok=True)
    board_path = output_dir / f"draft_board_by_war_{year}.png"

    draw_board(
        rounds, columns, cells,
        cell_color_fn=cell_color,
        text_color_fn=text_color,
        cell_label_fn=label,
        title=f"{year} Draft Board -- Wins Above Replacement (WAR)",
        output_path=board_path,
    )

    # Colorbar legend strip: blue (very negative) -> white (zero) -> red (very positive)
    n_stops = 256
    half = n_stops // 2
    blue_half = [blues(1.0 - i / (half - 1)) for i in range(half)]
    red_half = [reds(i / (half - 1)) for i in range(half)]
    diverging_cmap = matplotlib.colors.ListedColormap(blue_half + red_half)

    fig, ax = plt.subplots(figsize=(6, 0.6))
    fig.subplots_adjust(bottom=0.5)
    mappable = matplotlib.cm.ScalarMappable(
        norm=matplotlib.colors.Normalize(vmin=war_min, vmax=war_max),
        cmap=diverging_cmap,
    )
    cb = fig.colorbar(mappable, cax=ax, orientation="horizontal")
    cb.set_label("WAR (negative -> positive)", fontsize=9)
    colorbar_path = board_path.with_name(board_path.stem + "_colorbar.png")
    fig.savefig(colorbar_path, dpi=200, bbox_inches="tight")
    plt.close(fig)
    print(f"Saved -> {colorbar_path}")


# --------------------------------------------------------------------------
# MAIN
# --------------------------------------------------------------------------
def create_war_images(year: int) -> None:
    """Entry point: give it a year, it reads the JSON and writes both images."""
    picks = load_draft_value(year)
    output_dir = (SCRIPT_DIR / ".." / "Data" / str(year) / "War").resolve()
    render_war_images(picks, year, output_dir)


def main():
    if len(sys.argv) != 2:
        sys.exit("Usage: python3 DraftBoardWAR.py <year>")
    try:
        year = int(sys.argv[1])
    except ValueError:
        sys.exit(f"Invalid year: {sys.argv[1]!r}. Usage: python3 DraftBoardWAR.py <year>")
    create_war_images(year)


if __name__ == "__main__":
    main()