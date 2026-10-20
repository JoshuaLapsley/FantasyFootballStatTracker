"""
Render two novelty/joke variants of the EPAR draft board (see
calculate_EPAR.py for the actual stat derivation -- this script does
NOT change EPAR's methodology or values at all, it only rescales the
already-computed epar_total by a flat constant per player and
relabels the board for display, purely for a fun unit reskin requested
by the user. Reads the existing epar_{YEAR}.json output; does not
recompute anything or touch WAR/CWPAAR/EPAR's own files.

2024 board: "Expected Hours Of Vegetarianism Added"
    value_per_player = epar_total * 732

2025 board: "Expected KM's, Donuts, Beers, FT's Added"
    4 values per player, all derived from the same epar_total:
        km     = epar_total * 24
        donuts = epar_total * 18
        beers  = epar_total * 12
        fts    = epar_total * 6

Color scheme: identical diverging red/blue scheme as the real EPAR
board (calculate_EPAR.py's render_epar_board) -- since every value
shown is epar_total times a POSITIVE constant, the sign and relative
ordering of every player are unchanged, so cell coloring is computed
from the player's original epar_total (equivalent to using any one
of the scaled values, since they're all positive multiples of each
other).

Images written (into Website/girderma-gridiron-website/src/
league_stats_output/CurrentSeason/DraftBoards/EPAR/):
  draft_board_by_epar_2024_vegetarian_hours.png (+ _colorbar.png)
  draft_board_by_epar_2025_km_donuts_beers_fts.png (+ _colorbar.png)

Usage:
    python3 calculate_EPAR_novelty_boards.py
"""

import json

import matplotlib
matplotlib.use("Agg")
import matplotlib.colors
import matplotlib.cm

from calculate_EPAR import (
    draft_cache_path,
    epar_output_path,
    epar_board_dir,
    build_board_grid,
    _draw_board,
    DEFAULT_TEXT_COLOR,
)

# --------------------------------------------------------------------------
# 2024: "Expected Hours Of Vegetarianism Added"
# --------------------------------------------------------------------------
VEGETARIAN_HOURS_MULTIPLIER = 732

# --------------------------------------------------------------------------
# 2025: "Expected KM's, Donuts, Beers, FT's Added"
# --------------------------------------------------------------------------
KM_MULTIPLIER = 24
DONUTS_MULTIPLIER = 18
BEERS_MULTIPLIER = 12
FTS_MULTIPLIER = 6


def load_board_and_epar(year: int) -> tuple:
    with open(draft_cache_path(year), "r") as f:
        board = json.load(f)
    with open(epar_output_path(year), "r") as f:
        rows = json.load(f)
    epar_by_id = {r["player_id"]: r["epar_total"] for r in rows}
    return board, epar_by_id


def _render_novelty_board(year: int, board: list, epar_by_id: dict, title: str,
                           label_fn, output_filename: str) -> None:
    """
    Shared rendering routine for both novelty boards: same diverging
    red/blue gradient (computed from each player's raw epar_total,
    identical to calculate_EPAR.py's render_epar_board) but with a
    custom title and a custom per-cell label function supplied by the
    caller.
    """
    rounds, columns, cell_by_round_and_team = build_board_grid(board)

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

    board_dir = epar_board_dir(year)
    board_dir.mkdir(parents=True, exist_ok=True)
    output_path = board_dir / output_filename

    _draw_board(
        rounds, columns, cell_by_round_and_team,
        cell_color_fn=cell_color,
        text_color_fn=text_color,
        cell_label_fn=lambda pick: label_fn(pick, epar_by_id.get(pick["player_id"], 0.0)),
        title=title,
        output_path=output_path,
        legend_handles=None,
    )

    # Colorbar legend strip, same convention as the real EPAR board.
    n_stops = 256
    blue_half = [blues(1.0 - i / (n_stops // 2 - 1)) for i in range(n_stops // 2)]
    red_half = [reds(i / (n_stops // 2 - 1)) for i in range(n_stops // 2)]
    diverging_cmap = matplotlib.colors.ListedColormap(blue_half + red_half)

    import matplotlib.pyplot as plt
    fig, ax = plt.subplots(figsize=(6, 0.6))
    fig.subplots_adjust(bottom=0.5)
    norm_ = matplotlib.colors.Normalize(vmin=epar_min, vmax=epar_max)
    mappable = matplotlib.cm.ScalarMappable(norm=norm_, cmap=diverging_cmap)
    cb = fig.colorbar(mappable, cax=ax, orientation="horizontal")
    cb.set_label("EPAR (helped avoid punishment -> contributed to punishment loss)", fontsize=9)
    colorbar_path = output_path.with_name(output_path.stem + "_colorbar.png")
    fig.savefig(colorbar_path, dpi=200, bbox_inches="tight")
    plt.close(fig)
    print(f"Saved -> {colorbar_path}")
    print(f"Saved -> {output_path}")


def render_2024_vegetarian_hours_board() -> None:
    year = 2024
    board, epar_by_id = load_board_and_epar(year)

    def label_fn(pick, epar_total):
        hours = epar_total * VEGETARIAN_HOURS_MULTIPLIER
        return f"#{pick['pick']}  {hours:+.1f} hrs\n{pick['player_name']}"

    _render_novelty_board(
        year, board, epar_by_id,
        title=f"{year} Draft Board -- Expected Hours Of Vegetarianism Added",
        label_fn=label_fn,
        output_filename=f"draft_board_by_epar_{year}_vegetarian_hours.png",
    )


def render_2025_km_donuts_beers_fts_board() -> None:
    year = 2025
    board, epar_by_id = load_board_and_epar(year)

    def label_fn(pick, epar_total):
        km = epar_total * KM_MULTIPLIER
        donuts = epar_total * DONUTS_MULTIPLIER
        beers = epar_total * BEERS_MULTIPLIER
        fts = epar_total * FTS_MULTIPLIER
        return (
            f"#{pick['pick']}  {pick['player_name']}\n"
            f"{km:+.2f} km  {donuts:+.2f} donuts\n"
            f"{beers:+.2f} beers  {fts:+.2f} ft's"
        )

    _render_novelty_board(
        year, board, epar_by_id,
        title=f"{year} Draft Board -- Expected KM's, Donuts, Beers, FT's Added",
        label_fn=label_fn,
        output_filename=f"draft_board_by_epar_{year}_km_donuts_beers_fts.png",
    )


def main():
    render_2024_vegetarian_hours_board()
    render_2025_km_donuts_beers_fts_board()


if __name__ == "__main__":
    main()
