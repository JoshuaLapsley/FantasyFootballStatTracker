import json
import os
from pathlib import Path


def managers_filename(year, output_dir):
    return os.path.join(str(output_dir), str(year), "Managers.json")


def build_manager_map(lg):
    """Returns {manager_id (str): {...}} using the single lg.teams() call."""
    managers = {}

    for team_key, team in lg.teams().items():
        # Yahoo returns a list of {"manager": {...}} entries (co-managers are possible)
        for entry in team.get("managers", []):
            m = entry.get("manager", entry)
            manager_id = m.get("manager_id")
            if manager_id is None:
                continue

            nickname = m.get("nickname")
            if nickname == "--hidden--":
                nickname = None

            managers[str(manager_id)] = {
                "manager_id": str(manager_id),
                "name": m.get("name"),  # Yahoo usually doesn't return this; null if absent
                "nickname": nickname,
                "guid": m.get("guid"),  # stable across seasons, useful for matching years
                "team_key": team_key,
                "team_name": team.get("name"),
                "is_commissioner": str(m.get("is_commissioner")) == "1",
            }

    return managers


def write_managers_file(lg, year, output_dir):
    """Writes {manager_id: {name, nickname, ...}} to <output_dir>/<year>/Managers.json."""
    path = managers_filename(year, output_dir)
    os.makedirs(os.path.dirname(path), exist_ok=True)

    managers = build_manager_map(lg)

    with open(path, "w", encoding="utf-8") as f:
        json.dump(managers, f, indent=2, ensure_ascii=False)

    print(f"[{year}] Wrote {len(managers)} managers to {path}")
    return path