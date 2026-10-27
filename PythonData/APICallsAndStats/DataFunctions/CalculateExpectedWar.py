"""
Write the expected WAR for every draft pick in a season.

Takes the full-season numbers from isotonic_expected_war_by_pick.json
(same folder as this script) and scales them by how far into the season
we are:

    expected WAR = curve[pick] * (weeks_completed / full_season_weeks)

weeks_completed is passed in, or counted from
../APIData/{year}/DraftedPlayerWeeklyPoints.json if left out (no file =
full season). The ratio is capped at 1.

Input:
    isotonic_expected_war_by_pick.json   (same folder as this script)
    ../Data/{year}/WAR.json              the year's draft picks
        (falls back to ../APIData/{year}/DraftData.json)

Output:
    ../Data/{year}/ExpectedWAR.json
        {Player, Player ID, Position, Pick, Round, Drafted By,
         Expected WAR, Expected WAR Rank}, sorted by Expected WAR

Usage:
    write_expected_war(2026)
    write_expected_war(2026, weeks_completed=6)
"""

import json
import os

SCRIPT_DIR = os.path.dirname(os.path.abspath(__file__))
DATA_ROOT = os.path.join(SCRIPT_DIR, "..", "Data")
API_DATA_ROOT = os.path.join(SCRIPT_DIR, "..", "APIData")
CURVE_PATH = os.path.join(SCRIPT_DIR, "isotonic_expected_war_by_pick.json")

FULL_SEASON_WEEKS = 14  # regular season length


def load_curve():
    """Returns {pick (int): full-season expected WAR}."""
    with open(CURVE_PATH, "r", encoding="utf-8") as f:
        data = json.load(f)
    return {int(k): float(v) for k, v in data["expected_war_by_pick"].items()}


def curve_value(curve, pick):
    """Past either end of the curve, reuse the edge value."""
    pick = int(pick)
    if pick in curve:
        return curve[pick]
    return curve[max(curve)] if pick > max(curve) else curve[min(curve)]


def load_draft_picks(year):
    war_path = os.path.join(DATA_ROOT, str(year), "WAR.json")
    if os.path.isfile(war_path):
        with open(war_path, "r", encoding="utf-8") as f:
            rows = json.load(f)
        return [
            {
                "Player": r.get("Player"),
                "Player ID": r.get("Player ID"),
                "Position": r.get("Position"),
                "Pick": r.get("Pick"),
                "Round": r.get("Round"),
                "Drafted By": r.get("Drafted By"),
            }
            for r in rows
        ]

    draft_path = os.path.join(API_DATA_ROOT, str(year), "DraftData.json")
    with open(draft_path, "r", encoding="utf-8") as f:
        draft = json.load(f)
    return [
        {
            "Player": p.get("player_name"),
            "Player ID": str(p.get("player_id")),
            "Position": p.get("position"),
            "Pick": p.get("pick"),
            "Round": p.get("round"),
            "Drafted By": p.get("team_name"),
        }
        for p in draft
    ]


def weeks_played(year):
    """Weeks in DraftedPlayerWeeklyPoints.json, or None if the file is missing."""
    path = os.path.join(API_DATA_ROOT, str(year), "DraftedPlayerWeeklyPoints.json")
    if not os.path.isfile(path):
        return None
    with open(path, "r", encoding="utf-8") as f:
        players = json.load(f)
    weeks = {int(e["week"]) for p in players for e in (p.get("weekly_points") or [])}
    return len(weeks)


def write_expected_war(year, weeks_completed=None, full_season_weeks=FULL_SEASON_WEEKS):
    if weeks_completed is None:
        weeks_completed = weeks_played(year)

    ratio = 1.0 if weeks_completed is None else min(1.0, weeks_completed / full_season_weeks)
    print(f"[{year}] weeks completed: {weeks_completed if weeks_completed is not None else 'full season'} "
          f"-> ratio {ratio:.3f}")

    curve = load_curve()

    results = []
    for p in load_draft_picks(year):
        results.append({
            "Player": p["Player"],
            "Player ID": p["Player ID"],
            "Position": p["Position"],
            "Pick": p["Pick"],
            "Round": p["Round"],
            "Drafted By": p["Drafted By"],
            "Expected WAR": round(curve_value(curve, p["Pick"]) * ratio, 4) + 0.0,
        })

    results.sort(key=lambda r: (-r["Expected WAR"], r["Pick"]))
    for rank, row in enumerate(results, start=1):
        row["Expected WAR Rank"] = rank

    output_directory = os.path.join(DATA_ROOT, str(year))
    os.makedirs(output_directory, exist_ok=True)
    output_path = os.path.join(output_directory, "ExpectedWAR.json")
    with open(output_path, "w", encoding="utf-8") as f:
        json.dump(results, f, indent=4)

    print(f"Created: {output_path} ({len(results)} picks)")
    return output_path


if __name__ == "__main__":
    write_expected_war(2026)