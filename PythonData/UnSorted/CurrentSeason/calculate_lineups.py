"""
Calculate each team's optimal projected lineup score for every week,
using the per-player Yahoo projections scraped by pull_projections.py.

Lineup rules (standard-ish roster, this league's actual starting slots):
    1 QB, 2 RB, 2 WR, 1 TE, 1 FLEX (RB/WR/TE), 1 K, 1 DEF

For each team-week, this always picks the highest-projected-points lineup
available from that team's full roster (not whatever Yahoo currently has
started/benched) -- i.e. it re-optimizes from scratch every week.

Replacement level
------------------
If the best available player for a slot is projected for fewer points
than that position's replacement level, the replacement level is used
for that slot instead of the player's actual (lower) projection:

    QB = 15, RB = 5, WR = 7, TE = 6, FLEX = 7, K = 7, DEF = 5

Note this means a slot's contribution is max(best_available, replacement)
-- never less than replacement, even if every rostered player at that
position is projected for less (or there's nobody rostered at all).

K / DEF
-------
This league's rosters never include a kicker or defense (confirmed: no
K/DST rows appear on any team's roster page, for any week, despite the
league settings nominally listing 1 K + 1 DEF as required starting
slots). Per instruction, those two slots always contribute exactly their
replacement level (7 and 5) for every team, every week.

Eligibility
-----------
A rostered player is eligible to fill a slot for a given week if:
  - they are NOT on a bye that week (projected_points is null in the
    scraped data), and
  - they are NOT on IR (selected_position == "IR" in the scraped data
    -- IR slots don't count as part of the 9 active starting spots).
Bench ("BN") players ARE eligible -- this script re-solves the lineup
from the whole active roster, it doesn't defer to Yahoo's current
starter/bench split.

Output
------
simulate_season/lineups/week_<N>.json -- for each team:
    {
      "total_points": <float>,
      "slots": {
        "QB": {"player": "...", "projected_points": ..., "used_replacement": bool},
        "RB1": {...}, "RB2": {...},
        "WR1": {...}, "WR2": {...},
        "TE": {...},
        "FLEX": {...},
        "K": {"player": null, "projected_points": 7, "used_replacement": true},
        "DEF": {"player": null, "projected_points": 5, "used_replacement": true}
      }
    }
"""

import argparse
import json
import os

SCRIPT_DIR = os.path.dirname(os.path.abspath(__file__))
PROJECTIONS_DIR = os.path.join(SCRIPT_DIR, "projections")
OUTPUT_DIR = os.path.join(SCRIPT_DIR, "lineups")

REPLACEMENT_POINTS = {
    "QB": 15,
    "RB": 5,
    "WR": 7,
    "TE": 6,
    "FLEX": 7,
    "K": 7,
    "DEF": 5,
}

# Dedicated slots and how many of each. FLEX is handled separately since
# it draws from whichever of RB/WR/TE has the best player left over.
DEDICATED_SLOTS = {
    "QB": ("QB", 1),
    "RB1": ("RB", 1),
    "RB2": ("RB", 1),
    "WR1": ("WR", 1),
    "WR2": ("WR", 1),
    "TE": ("TE", 1),
}
FLEX_ELIGIBLE_POSITIONS = {"RB", "WR", "TE"}


def _eligible_players(players: list) -> list:
    """Players who can legally fill an active slot this week: not on a
    bye (projected_points is not null) and not stashed on IR."""
    return [
        p for p in players
        if p.get("projected_points") is not None
        and p.get("selected_position") != "IR"
    ]


def _best_lineup_for_team(players: list) -> dict:
    eligible = _eligible_players(players)

    # Bucket eligible players by position, best-to-worst.
    by_position = {}
    for p in eligible:
        by_position.setdefault(p["position"], []).append(p)
    for pos in by_position:
        by_position[pos].sort(key=lambda p: p["projected_points"], reverse=True)

    used_names = set()
    slots = {}

    def take_best(position: str):
        """Pop the best not-yet-used player at a position, or None."""
        for p in by_position.get(position, []):
            if p["name"] not in used_names:
                used_names.add(p["name"])
                return p
        return None

    def fill_slot(slot_name: str, position: str, replacement_key: str):
        player = take_best(position)
        if player is None:
            slots[slot_name] = {
                "player": None,
                "position": position,
                "projected_points": REPLACEMENT_POINTS[replacement_key],
                "used_replacement": True,
            }
        else:
            pts = player["projected_points"]
            replacement = REPLACEMENT_POINTS[replacement_key]
            if pts < replacement:
                slots[slot_name] = {
                    "player": player["name"],
                    "position": position,
                    "projected_points": replacement,
                    "used_replacement": True,
                }
            else:
                slots[slot_name] = {
                    "player": player["name"],
                    "position": position,
                    "projected_points": pts,
                    "used_replacement": False,
                }

    # Dedicated slots first: QB, RB1, RB2, WR1, WR2, TE.
    for slot_name, (position, _count) in DEDICATED_SLOTS.items():
        fill_slot(slot_name, position, position)

    # FLEX: best remaining player across RB/WR/TE (whichever position
    # that leftover player actually plays).
    flex_candidates = [
        p for pos in FLEX_ELIGIBLE_POSITIONS
        for p in by_position.get(pos, [])
        if p["name"] not in used_names
    ]
    flex_candidates.sort(key=lambda p: p["projected_points"], reverse=True)
    flex_player = flex_candidates[0] if flex_candidates else None
    if flex_player is None:
        slots["FLEX"] = {
            "player": None,
            "position": None,
            "projected_points": REPLACEMENT_POINTS["FLEX"],
            "used_replacement": True,
        }
    else:
        used_names.add(flex_player["name"])
        pts = flex_player["projected_points"]
        replacement = REPLACEMENT_POINTS["FLEX"]
        if pts < replacement:
            slots["FLEX"] = {
                "player": flex_player["name"],
                "position": flex_player["position"],
                "projected_points": replacement,
                "used_replacement": True,
            }
        else:
            slots["FLEX"] = {
                "player": flex_player["name"],
                "position": flex_player["position"],
                "projected_points": pts,
                "used_replacement": False,
            }

    # K / DEF: this league's rosters never carry either, so these are
    # always replacement level.
    slots["K"] = {
        "player": None,
        "position": "K",
        "projected_points": REPLACEMENT_POINTS["K"],
        "used_replacement": True,
    }
    slots["DEF"] = {
        "player": None,
        "position": "DEF",
        "projected_points": REPLACEMENT_POINTS["DEF"],
        "used_replacement": True,
    }

    total_points = round(sum(s["projected_points"] for s in slots.values()), 2)
    return {"total_points": total_points, "slots": slots}


def calculate_week_lineups(week: int) -> dict:
    proj_path = os.path.join(PROJECTIONS_DIR, f"week_{week}.json")
    with open(proj_path) as f:
        week_projections = json.load(f)

    return {
        team_name: _best_lineup_for_team(players)
        for team_name, players in week_projections.items()
    }


def available_projection_weeks() -> list:
    weeks = []
    if not os.path.isdir(PROJECTIONS_DIR):
        return weeks
    for fname in os.listdir(PROJECTIONS_DIR):
        if fname.startswith("week_") and fname.endswith(".json"):
            try:
                weeks.append(int(fname[len("week_"):-len(".json")]))
            except ValueError:
                continue
    return sorted(weeks)


def main():
    parser = argparse.ArgumentParser(
        description="Calculate each team's optimal projected lineup score per week."
    )
    parser.add_argument(
        "--weeks", default="all",
        help="Weeks to calculate: 'all' (every week with a saved projections file, default), "
             "a range like '3-6', or a comma list like '3,5,7'."
    )
    args = parser.parse_args()

    available = available_projection_weeks()
    if not available:
        raise SystemExit(
            f"No projections files found in {PROJECTIONS_DIR}. Run "
            f"pull_projections.py first."
        )

    if args.weeks == "all":
        weeks = available
    elif "-" in args.weeks:
        start, end = args.weeks.split("-", 1)
        weeks = list(range(int(start), int(end) + 1))
    else:
        weeks = [int(w) for w in args.weeks.split(",")]

    os.makedirs(OUTPUT_DIR, exist_ok=True)

    for week in weeks:
        if week not in available:
            print(f"  \u26a0 no projections file for week {week}, skipping")
            continue

        lineups = calculate_week_lineups(week)

        out_path = os.path.join(OUTPUT_DIR, f"week_{week}.json")
        with open(out_path, "w") as f:
            json.dump(lineups, f, indent=2)

        print(f"Week {week}:")
        for team_name, result in sorted(lineups.items(), key=lambda x: -x[1]["total_points"]):
            print(f"  {team_name:<32} {result['total_points']:6.2f} pts")
        print(f"  Saved -> {out_path}\n")


if __name__ == "__main__":
    main()
