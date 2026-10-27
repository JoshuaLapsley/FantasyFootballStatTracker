"""
Combine ExpectedWAR.json, PAR.json and WAR.json for a season into one
file and add a Surplus WAR stat:

    Surplus WAR = WAR - Expected WAR

Players are matched across the three files by Player ID.

Input (relative to this script):
    ../Data/{year}/ExpectedWAR.json
    ../Data/{year}/PAR.json
    ../Data/{year}/WAR.json

Output:
    ../Data/{year}/DraftValue.json
        one row per drafted player, sorted by Surplus WAR (highest first):
        {Player, Player ID, Position, Pick, Round, Drafted By,
         PAR, PAR Rank, WAR, WAR Rank, Expected WAR, Expected WAR Rank,
         Surplus WAR, Surplus WAR Rank}

A player missing from one of the files gets null for that file's fields,
and a null Surplus WAR if WAR or Expected WAR is missing.

Usage:
    write_draft_value(2026)
"""

import json
import os

SCRIPT_DIR = os.path.dirname(os.path.abspath(__file__))
DATA_ROOT = os.path.join(SCRIPT_DIR, "..", "Data")

INFO_FIELDS = ["Player", "Player ID", "Position", "Pick", "Round", "Drafted By"]


def _load(year, filename):
    path = os.path.join(DATA_ROOT, str(year), filename)
    if not os.path.isfile(path):
        raise FileNotFoundError(f"{path} not found. Create it first.")
    with open(path, "r", encoding="utf-8") as f:
        rows = json.load(f)
    return {str(r["Player ID"]): r for r in rows}


def combine(year):
    expected = _load(year, "ExpectedWAR.json")
    par = _load(year, "PAR.json")
    war = _load(year, "WAR.json")

    all_ids = set(expected) | set(par) | set(war)
    for name, source in (("ExpectedWAR", expected), ("PAR", par), ("WAR", war)):
        missing = all_ids - set(source)
        if missing:
            print(f"Warning: {len(missing)} player(s) missing from {name}.json")

    rows = []
    for pid in all_ids:
        # Player info from whichever file has this player.
        base = war.get(pid) or par.get(pid) or expected.get(pid)

        row = {field: base.get(field) for field in INFO_FIELDS}
        row["PAR"] = par.get(pid, {}).get("PAR")
        row["PAR Rank"] = par.get(pid, {}).get("PAR Rank")
        row["WAR"] = war.get(pid, {}).get("WAR")
        row["WAR Rank"] = war.get(pid, {}).get("WAR Rank")
        row["Expected WAR"] = expected.get(pid, {}).get("Expected WAR")
        row["Expected WAR Rank"] = expected.get(pid, {}).get("Expected WAR Rank")

        if row["WAR"] is not None and row["Expected WAR"] is not None:
            row["Surplus WAR"] = round(row["WAR"] - row["Expected WAR"], 4) + 0.0  # no -0.0
        else:
            row["Surplus WAR"] = None

        rows.append(row)

    # Rank by Surplus WAR; players without one go last.
    rows.sort(key=lambda r: (r["Surplus WAR"] is None,
                             -(r["Surplus WAR"] or 0.0),
                             r["Pick"] if r["Pick"] is not None else 0))
    rank = 0
    for row in rows:
        if row["Surplus WAR"] is None:
            row["Surplus WAR Rank"] = None
        else:
            rank += 1
            row["Surplus WAR Rank"] = rank

    return rows


def write_draft_value(year):
    rows = combine(year)

    output_directory = os.path.join(DATA_ROOT, str(year))
    os.makedirs(output_directory, exist_ok=True)
    output_path = os.path.join(output_directory, "DraftValue.json")

    with open(output_path, "w", encoding="utf-8") as f:
        json.dump(rows, f, indent=4)

    print(f"Created: {output_path} ({len(rows)} players)")
    return output_path


if __name__ == "__main__":
    write_draft_value(2026)