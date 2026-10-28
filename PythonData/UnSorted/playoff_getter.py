"""
generate_playoff_brackets.py

Generates a JPEG playoff bracket (winners + losers) for each season, using
scores pulled from league_stats_output/<year>/weekly_points.json.

HOW TO USE:
1. Fill in the BRACKETS config below by hand for each season -- who played
   whom, in which round, and which week of the season that round corresponds
   to (playoff weeks are 15, 16, 17).
2. Leave a team slot as "" (empty string) if you don't know it yet / it's a
   placeholder (e.g. "TBD" or a bye). The renderer will just print a
   placeholder box.
3. Run the script. It looks up each team's points_for for the given week in
   weekly_points.json, decides the winner (higher points_for), bolds/colors
   the winner, and draws the full bracket tree round by round.

Nothing here guesses the bracket shape for you -- that's the part you know
and Yahoo's API/the json doesn't encode, so it's intentionally left blank
for you to hardcode.
"""

import json
from pathlib import Path

import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt
from matplotlib.patches import FancyBboxPatch

BASE_DIR = Path(__file__).resolve().parent

# Must match generate_league_stats.py / generate_draft_data.py
SEASONS = {
    2023: "423.l.902802",
    2024: "449.l.106896",
    2025: "461.l.111150",
}

STATS_DIR = (BASE_DIR / "league_stats_output").resolve()
NEW_OUTPUT_DIR = (BASE_DIR / ".." / "Website" / "girderma-gridiron-website" / "src" / "pages" / "LeagueHistory" / "Playoffs").resolve()
NEW_OUTPUT_DIR.mkdir(parents=True, exist_ok=True)

# --------------------------------------------------------------------------
# BRACKET CONFIG -- fill this in by hand for each season.
#
# Each bracket is a list of "rounds". Each round is a list of matchups.
# Each matchup is a dict: {"week": <int, 15/16/17>, "team1": <name or "">,
#                          "team2": <name or "">}
#
# Round 0 = first playoff round, last round = championship / bracket final.
# The number of matchups must exactly halve each round
# (e.g. 4 matchups -> 2 matchups -> 1 matchup).
#
# If a team has a bye in round 0, set team2 to "" (BYE) -- the winner slot
# in the next round should just be filled in with team1's name directly by
# you, since there's no game to score.
# --------------------------------------------------------------------------
BRACKETS = {
    2023: {
        "winners": [
            # Round 0 (e.g. week 15)
            [
                
                {"week": 15, "team1": "The Hunters", "team2": "Sparty's Sigmas"},
                {"week": 15, "team1": "Wicked Wah-Bams", "team2": ""},
                {"week": 15, "team1": "For Pitts and Giggles", "team2": ""},
                {"week": 15, "team1": "Tsuga\u2019s Tuck Shop", "team2": "Lawrence & Order"}                


            ],
            # Round 1 (e.g. week 16)
            [
                {"week": 16, "team1": "Wicked Wah-Bams", "team2": "The Hunters"},
                {"week": 16, "team1": "For Pitts and Giggles", "team2": "Lawrence & Order"}        
            ],
            # Round 2 / Final (e.g. week 17)
            [
                {"week": 17, "team1": "For Pitts and Giggles", "team2": "Wicked Wah-Bams"}
            ],
        ],
        "losers": [
            [
                {"week": 15, "team1": "", "team2": ""},
                {"week": 15, "team1": "", "team2": ""},
            ],
            [
                {"week": 16, "team1": "", "team2": ""},
            ],
            [
                {"week": 17, "team1": "", "team2": ""},
            ],
        ],
    },
    2024: {
        "winners": [
            # Round 0 (e.g. week 15)
            [
                {"week": 15, "team1": "Ozzy Stick", "team2": ""},
                {"week": 15, "team1": "Tsuga\u2019s Tuck Shop", "team2": "Spirally Things"},
                {"week": 15, "team1": "Revy\u2019s Konstruction", "team2": "Supernova\u2019s Studs"},
                {"week": 15, "team1": "Mahomes Alone", "team2": ""}


            ],
            # Round 1 (e.g. week 16)
            [
                {"week": 16, "team1": "Ozzy Stick", "team2": "Spirally Things"},
                {"week": 16, "team1": "Mahomes Alone", "team2": "Revy\u2019s Konstruction"}        
            ],
            # Round 2 / Final (e.g. week 17)
            [
                {"week": 17, "team1": "Revy\u2019s Konstruction", "team2": "Spirally Things"}
            ],
        ],
        "losers": [
            [
                {"week": 15, "team1": "Wicked Wah-Bams", "team2": "The Sage's Playmakers"},
                {"week": 15, "team1": "Flows Aggressive Insurance", "team2": "Sparty's Sigmas"}
            ],
            [
                {"week": 16, "team1": "The Sage's Playmakers", "team2": "Sparty's Sigmas"},
                
            ]
        ],
    },
    2025: {
        "winners": [
            # Round 0 (e.g. week 15)
            [
                {"week": 15, "team1": "No Punts Intented", "team2": "Supernova\u2019s Studs"},
                {"week": 15, "team1": "Hungry Hungry Hokk", "team2": "Tsuga\u2019s Tuck Shop"}, 
                {"week": 15, "team1": "The Sage's Playmakers", "team2": "Pad D's"},
                {"week": 15, "team1": "Deej-lanta Falcons", "team2": "Go With The Flow"}

                               


            ],
            # Round 1 (e.g. week 16)
            [
                {"week": 16, "team1": "No Punts Intented", "team2": "Tsuga\u2019s Tuck Shop"},
                {"week": 16, "team1": "Go With The Flow", "team2": "Pad D's"}        
            ],
            # Round 2 / Final (e.g. week 17)
            [
                {"week": 17, "team1": "Go With The Flow", "team2": "Tsuga\u2019s Tuck Shop"}
            ],
        ],
        "losers": [
            [
                {"week": 16, "team1": "Ozzy Stick", "team2": "Revy\u2019s Konstruction"},
                {"week": 16, "team1": "Omaha Beach Real Estate", "team2": "Hunter\u2019s Hunters"}
            ],
            [
                {"week": 17, "team1": "Omaha Beach Real Estate", "team2": "Revy\u2019s Konstruction"},
                
            ]
        ],
    },
}

# --------------------------------------------------------------------------
# Rendering config
# --------------------------------------------------------------------------
BOX_W = 2.6
BOX_H = 0.9
ROUND_GAP = 3.2
MATCH_GAP = 1.4

COLOR_BG = "#0f172a"
COLOR_BOX = "#1e293b"
COLOR_BOX_EDGE = "#334155"
COLOR_TEXT = "#e2e8f0"
COLOR_WINNER = "#22c55e"
COLOR_LOSER = "#ef4444"
COLOR_SCORE = "#94a3b8"
COLOR_LINE = "#475569"
COLOR_TITLE = "#f8fafc"


def load_weekly_points(season_year: int):
    path = STATS_DIR / str(season_year) / "weekly_points.json"
    if not path.exists():
        raise FileNotFoundError(f"Could not find weekly_points.json for {season_year} at {path}")
    with open(path, "r") as f:
        return json.load(f)


def get_points_for(weekly_points: dict, team_name: str, week: int):
    if not team_name:
        return None
    team_data = weekly_points.get(team_name)
    if not team_data:
        return None
    week_data = team_data.get(f"week_{week}")
    if not week_data:
        return None
    pts = week_data.get("points_for")
    return pts


def compute_positions(rounds):
    """
    Given a list of rounds (list of list of matchups), compute a y-position
    for each matchup box so that round(n+1) boxes sit centered between their
    two "child" matchups in round(n).
    Returns a list (per round) of lists of y-center positions.
    """
    positions = []

    # First round: evenly spaced from top to bottom.
    n0 = len(rounds[0])
    first_positions = [-(i * MATCH_GAP) for i in range(n0)]
    positions.append(first_positions)

    for r in range(1, len(rounds)):
        prev_positions = positions[r - 1]
        n = len(rounds[r])
        new_positions = []
        for i in range(n):
            child_a = prev_positions[2 * i]
            child_b = prev_positions[2 * i + 1] if (2 * i + 1) < len(prev_positions) else child_a
            new_positions.append((child_a + child_b) / 2)
        positions.append(new_positions)

    return positions


def draw_matchup_box(ax, x, y, team1, team2, pts1, pts2, week, highlight_mode="winner"):
    """Draws a single matchup box with two team rows."""
    box = FancyBboxPatch(
        (x, y - BOX_H / 2), BOX_W, BOX_H,
        boxstyle="round,pad=0.02,rounding_size=0.08",
        linewidth=1.2,
        edgecolor=COLOR_BOX_EDGE,
        facecolor=COLOR_BOX,
        zorder=2,
    )
    ax.add_patch(box)

    # Determine winner (if both scores present)
    winner = None
    if pts1 is not None and pts2 is not None:
        if pts1 > pts2:
            winner = "team1"
        elif pts2 > pts1:
            winner = "team2"

    # Decide which side gets highlighted, and with what color
    if highlight_mode == "loser":
        highlight_side = None
        if winner == "team1":
            highlight_side = "team2"
        elif winner == "team2":
            highlight_side = "team1"
        highlight_color = COLOR_LOSER
    else:
        highlight_side = winner
        highlight_color = COLOR_WINNER

    label1 = team1 if team1 else "TBD"
    label2 = team2 if team2 else ("BYE" if team1 else "TBD")

    score1 = f"{pts1:.2f}" if pts1 is not None else "-"
    score2 = f"{pts2:.2f}" if pts2 is not None else "-"

    row1_y = y + BOX_H / 4
    row2_y = y - BOX_H / 4

    color1 = highlight_color if highlight_side == "team1" else COLOR_TEXT
    color2 = highlight_color if highlight_side == "team2" else COLOR_TEXT
    weight1 = "bold" if highlight_side == "team1" else "normal"
    weight2 = "bold" if highlight_side == "team2" else "normal"

    ax.text(x + 0.12, row1_y, label1, va="center", ha="left",
             fontsize=10, color=color1, fontweight=weight1, zorder=3)
    ax.text(x + BOX_W - 0.12, row1_y, score1, va="center", ha="right",
             fontsize=9.5, color=COLOR_SCORE if highlight_side != "team1" else highlight_color,
             fontweight=weight1, zorder=3)

    ax.text(x + 0.12, row2_y, label2, va="center", ha="left",
             fontsize=10, color=color2, fontweight=weight2, zorder=3)
    ax.text(x + BOX_W - 0.12, row2_y, score2, va="center", ha="right",
             fontsize=9.5, color=COLOR_SCORE if highlight_side != "team2" else highlight_color,
             fontweight=weight2, zorder=3)

    # Divider line between the two team rows
    ax.plot([x + 0.08, x + BOX_W - 0.08], [y, y], color=COLOR_BOX_EDGE, linewidth=0.8, zorder=3)

    # Small week label above the box
    ax.text(x + BOX_W / 2, y + BOX_H / 2 + 0.18, f"Week {week}",
             ha="center", va="bottom", fontsize=8, color="#64748b", zorder=3)


def draw_connector(ax, x1, y1, x2, y2):
    """Draws the bracket connector lines between a matchup and its parent."""
    mid_x = x1 + (ROUND_GAP - BOX_W) / 2 + BOX_W
    ax.plot([x1, mid_x], [y1, y1], color=COLOR_LINE, linewidth=1.2, zorder=1)
    ax.plot([mid_x, mid_x], [y1, y2], color=COLOR_LINE, linewidth=1.2, zorder=1)
    ax.plot([mid_x, x2], [y2, y2], color=COLOR_LINE, linewidth=1.2, zorder=1)


def draw_bracket(season_year, bracket_label, rounds, weekly_points, output_path, highlight_mode="winner"):
    if not rounds:
        print(f"  Skipping {bracket_label} bracket for {season_year} -- no rounds configured.")
        return

    positions = compute_positions(rounds)

    # Flatten every round's y-positions to find the TRUE global extent.
    # Later rounds are centered averages of their children, so they can sit
    # well inside the range of round 0 -- but round 0 isn't guaranteed to be
    # the global min/max for every bracket shape, so we can't just look at
    # positions[0] / positions[-1] in isolation.
    all_positions = [p for round_positions in positions for p in round_positions]
    global_max = max(all_positions)
    global_min = min(all_positions)

    n_rounds = len(rounds)
    max_height = global_max - global_min
    fig_w = n_rounds * ROUND_GAP + 2
    fig_h = max(max_height + 4, 4)

    fig, ax = plt.subplots(figsize=(fig_w, fig_h))
    fig.patch.set_facecolor(COLOR_BG)
    ax.set_facecolor(COLOR_BG)

    round_x = [r * ROUND_GAP for r in range(n_rounds)]

    # Draw connectors first (so boxes sit on top)
    for r in range(1, n_rounds):
        for i, matchup in enumerate(rounds[r]):
            parent_x = round_x[r]
            parent_y = positions[r][i]
            child_a_x = round_x[r - 1] + BOX_W
            child_a_y = positions[r - 1][2 * i]
            draw_connector(ax, child_a_x, child_a_y, parent_x, parent_y)
            if 2 * i + 1 < len(positions[r - 1]):
                child_b_y = positions[r - 1][2 * i + 1]
                draw_connector(ax, child_a_x, child_b_y, parent_x, parent_y)

    # Draw all matchup boxes
    for r, matchups in enumerate(rounds):
        for i, matchup in enumerate(matchups):
            x = round_x[r]
            y = positions[r][i]
            team1 = matchup.get("team1", "")
            team2 = matchup.get("team2", "")
            week = matchup.get("week")
            pts1 = get_points_for(weekly_points, team1, week)
            pts2 = get_points_for(weekly_points, team2, week)
            draw_matchup_box(ax, x, y, team1, team2, pts1, pts2, week, highlight_mode=highlight_mode)

    ax.set_title(f"{season_year} {bracket_label} Bracket", fontsize=18,
                 color=COLOR_TITLE, fontweight="bold", pad=20)

    ax.set_xlim(-0.5, max(round_x) + BOX_W + 0.5)
    ax.set_ylim(global_min - 2, global_max + 2)
    ax.axis("off")

    fig.tight_layout()
    fig.savefig(output_path, format="jpg", dpi=180, facecolor=COLOR_BG)
    plt.close(fig)
    print(f"  Saved {bracket_label} bracket -> {output_path}")


def main():
    for season_year in SEASONS:
        print(f"Generating playoff brackets for {season_year}...")
        try:
            weekly_points = load_weekly_points(season_year)
        except FileNotFoundError as e:
            print(f"  {e}")
            continue

        season_brackets = BRACKETS.get(season_year, {})

        winners_rounds = season_brackets.get("winners", [])
        losers_rounds = season_brackets.get("losers", [])

        winners_path = NEW_OUTPUT_DIR / f"playoffs_{season_year}_winners.jpg"
        losers_path = NEW_OUTPUT_DIR / f"playoffs_{season_year}_losers.jpg"

        draw_bracket(season_year, "Winners", winners_rounds, weekly_points, winners_path, highlight_mode="winner")
        draw_bracket(season_year, "Losers", losers_rounds, weekly_points, losers_path, highlight_mode="loser")


if __name__ == "__main__":
    main()