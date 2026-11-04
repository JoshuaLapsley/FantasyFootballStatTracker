import json
import os
import statistics
from collections import Counter, defaultdict
from pathlib import Path

# .../Functions/<this folder>/ -> parents[1] = Functions, which holds APIData/ and Data/
ROOT = Path(__file__).resolve().parents[1]
API_DATA_ROOT = ROOT / "APIData"
GTM_OUTPUT_DIR = ROOT / "Data" / "GTM"

# Hard-coded manager display names, per year, keyed by Yahoo team_key
# (e.g. "470.l.205662.t.9"). Needed because several managers share a nickname
# (two "Josh", two "Sam"). Team keys are unique to a league/season, so each year
# needs its own entries. Look them up in APIData/<year>/Managers.json. Anyone not
# listed uses their nickname. If two teams still end up with the same name, the
# script raises an error.
MANAGER_NAME_OVERRIDES = {
    2023: {
         "423.l.902802.t.11": "The Sage",  # The Sage's Playmakers (nickname: Josh)
         "423.l.902802.t.2": "Rubik",      # No Punts Intented     (nickname: Josh)
    },
    2024: {
        "449.l.106896.t.10": "The Sage",  # The Sage's Playmakers (nickname: Josh)
        "449.l.106896.t.7": "Rubik",      # No Punts Intented     (nickname: Josh)
    },
    2025: {
        "461.l.111150.t.10": "The Sage",  # The Sage's Playmakers (nickname: Josh)
        "461.l.111150.t.4": "Rubik",      # No Punts Intented     (nickname: Josh)
        "461.l.111150.t.14": "Paddy",     # Pad D's               (nickname: Sam)
        "461.l.111150.t.13": "Girder",     # Girder's 6 Cookies    (nickname: Sam)
    },
    2026: {
        "470.l.205662.t.13": "The Sage",  # The Sage's Playmakers (nickname: Josh)
        "470.l.205662.t.7": "Rubik",      # No Punts Intented     (nickname: Josh)
        "470.l.205662.t.10": "Paddy",     # Pad D's               (nickname: Sam)
        "470.l.205662.t.3": "Girder",     # Girder's 6 Cookies    (nickname: Sam)
    },
}

# ---------------------------------------------------------------------------
# Difficulty settings (1 = easiest, 100 = hardest)
# ---------------------------------------------------------------------------
POSITION_SLOTS = {"QB", "RB", "WR", "TE", "K"}  # slots that identify a real position

BASE_DIFFICULTY = 50        # a position-average player lands here
START_Z_SCALE = 35          # same idea, but for start%. Wider than Z_SCALE because
                            # start% is capped at 100%, so even the best players only
                            # sit ~1 SD above average and would otherwise stall ~18.
Z_SCALE = 22                # points of difficulty per standard deviation
                            # (+/-2 SD -> roughly 6 / 94; the very best
                            # players land near 1)

KICKER_CENTER = 80          # an average kicker lands here
KICKER_Z_SCALE = 10         # points of difficulty per SD for kickers
                            # (+/-2 SD -> roughly 60 / 100)
KICKER_MIN, KICKER_MAX = 60, 100

EXCLUDE_ZERO_WEEKS = True   # ignore 0.0 weeks (byes / injuries) in the average

POINTS_WEIGHT = 0.4         # weight of the points-based bell curve score
START_WEIGHT = 0.6          # weight of the start% score
NON_START_SLOTS = {"BN", "IR", "IR+", "NA"}  # any other slot counts as a start
START_PCT_OF_SEASON = True  # True:  starts / every week in the file
                            # False: starts / weeks the player was on any roster
MIN_DIFFICULTY, MAX_DIFFICULTY = 1, 100


def managers_path(year, api_data_root=API_DATA_ROOT):
    return os.path.join(str(api_data_root), str(year), "Managers.json")


def roster_points_path(year, api_data_root=API_DATA_ROOT):
    return os.path.join(str(api_data_root), str(year), "RosterPoints.json")


def gtm_path(year, output_dir=GTM_OUTPUT_DIR):
    return os.path.join(str(output_dir), f"{year}.json")


def _load_json(path):
    with open(path, encoding="utf-8") as f:
        return json.load(f)


def _week_keys(roster_points):
    return sorted((k for k in roster_points if str(k).isdigit()), key=int)


def _last_week(roster_points):
    weeks = _week_keys(roster_points)
    if not weeks:
        raise ValueError("RosterPoints.json has no week data.")
    return weeks[-1]


# ---------------------------------------------------------------------------
# Manager names
# ---------------------------------------------------------------------------
def _display_name(manager, year):
    overrides = MANAGER_NAME_OVERRIDES.get(int(year), {})
    team_key = manager.get("team_key")
    if team_key in overrides:
        return overrides[team_key]
    return manager.get("name") or manager.get("nickname") or manager.get("team_name")


def _team_key_to_manager_name(managers, year):
    """{team_key: display name}. Fails loudly if two teams end up with the same name."""
    names = {}
    for manager in managers.values():
        team_key = manager.get("team_key")
        if team_key and team_key not in names:  # co-managers: first one wins
            names[team_key] = _display_name(manager, year)

    by_name = defaultdict(list)
    for team_key, name in names.items():
        by_name[name].append(team_key)
    dupes = {n: keys for n, keys in by_name.items() if len(keys) > 1}
    if dupes:
        raise ValueError(
            f"[{year}] Duplicate manager names after applying overrides: "
            f"{dupes}. Add entries for {year} to MANAGER_NAME_OVERRIDES."
        )

    return names


# ---------------------------------------------------------------------------
# Per-player data pulled from RosterPoints.json
# ---------------------------------------------------------------------------
def _collect_player_data(roster_points):
    """{player_id: {"points": {week: pts}, "slots": Counter, "position": str|None}}"""
    data = {}

    for week in _week_keys(roster_points):
        for roster in roster_points[week].values():
            for p in roster:
                pid = str(p.get("player_id"))
                info = data.setdefault(
                    pid, {"points": {}, "slots": Counter(), "position": None}
                )

                slot = p.get("selected_position")
                if slot:
                    info["slots"][slot] += 1

                pts = p.get("points")
                if pts is not None:
                    info["points"][week] = float(pts)

                # Forward-compatible: use real position data if the file ever has it.
                if info["position"] is None:
                    if p.get("position") in POSITION_SLOTS:
                        info["position"] = p["position"]
                    else:
                        for pos in p.get("eligible_positions") or []:
                            if pos in POSITION_SLOTS:
                                info["position"] = pos
                                break

    return data


def _is_defense(pid, info):
    if info["slots"].get("DEF"):
        return True
    try:
        return int(pid) >= 100000  # Yahoo team-defense IDs are 100001-100034
    except ValueError:
        return False


def _infer_position(info):
    """Real position if known; otherwise the dedicated slot (QB/RB/WR/TE/K) they were
    started in most often. Players only ever seen on BN / IR / W/R/T return None."""
    if info["position"]:
        return info["position"]
    dedicated = Counter({s: n for s, n in info["slots"].items() if s in POSITION_SLOTS})
    return dedicated.most_common(1)[0][0] if dedicated else None


def _average_points(info):
    values = list(info["points"].values())
    if EXCLUDE_ZERO_WEEKS:
        values = [v for v in values if v != 0]
    return statistics.fmean(values) if values else 0.0


def _start_pct(info, season_weeks):
    """Share of weeks the player was in a starting slot (0.0 - 1.0)."""
    rostered = sum(info["slots"].values())
    starts = sum(n for slot, n in info["slots"].items() if slot not in NON_START_SLOTS)
    denominator = season_weeks if START_PCT_OF_SEASON else rostered
    return min(1.0, starts / denominator) if denominator else 0.0


# ---------------------------------------------------------------------------
# Difficulty
# ---------------------------------------------------------------------------
def _clamp(value, low, high):
    return max(low, min(high, value))


def _mean_std(values):
    return statistics.fmean(values), statistics.pstdev(values)


def _group_stats(values_by_position, pooled_values):
    """({position: (mean, std)}, pooled (mean, std)).

    Non-kicker positions with fewer than 2 players or no spread fall back to the
    pooled non-kicker stats."""
    pooled = _mean_std(pooled_values) if pooled_values else (0.0, 0.0)
    stats = {}
    for pos, values in values_by_position.items():
        mean, std = _mean_std(values)
        if pos != "K" and (len(values) < 2 or std == 0):
            mean, std = pooled
        stats[pos] = (mean, std)
    return stats, pooled


def _z(value, mean_std):
    mean, std = mean_std
    return (value - mean) / std if std else 0.0


def calculate_difficulties(roster_points, player_ids):
    """Returns {player_id: difficulty (int)} for the given players.

    Final score = POINTS_WEIGHT * points_score + START_WEIGHT * start_score.

    Both scores are bell-curved within the player's position:
      score = center - z * scale     (scale: Z_SCALE for points, START_Z_SCALE for
                                      start%, KICKER_Z_SCALE for both on kickers)
    where z is how many standard deviations the player's value (average points, or
    start%) sits above their position's average. More points / more starts means
    more recognizable, so lower (easier).

      Non-kickers: center 50, clamped to 1-100.
      Kickers:     center 80, clamped to 60-100.

    Players whose position can't be worked out (only ever on BN / IR / flex) are
    scored against all non-kickers pooled together.
    """
    data = _collect_player_data(roster_points)
    season_weeks = len(_week_keys(roster_points))

    pool = {}
    for pid in player_ids:
        info = data[pid]
        pool[pid] = (
            _infer_position(info),
            _average_points(info),
            _start_pct(info, season_weeks),
        )

    avg_by_pos, start_by_pos = defaultdict(list), defaultdict(list)
    non_k_avgs, non_k_starts = [], []
    for pos, avg, start in pool.values():
        if pos is not None:
            avg_by_pos[pos].append(avg)
            start_by_pos[pos].append(start)
        if pos != "K":
            non_k_avgs.append(avg)
            non_k_starts.append(start)

    avg_stats, pooled_avg = _group_stats(avg_by_pos, non_k_avgs)
    start_stats, pooled_start = _group_stats(start_by_pos, non_k_starts)

    unknown = 0
    result = {}
    for pid, (pos, avg, start) in pool.items():
        if pos is None:
            unknown += 1
            z_points, z_start = _z(avg, pooled_avg), _z(start, pooled_start)
        else:
            z_points, z_start = _z(avg, avg_stats[pos]), _z(start, start_stats[pos])

        if pos == "K":
            low, high = KICKER_MIN, KICKER_MAX
            center = KICKER_CENTER
            points_scale = start_scale = KICKER_Z_SCALE
        else:
            low, high = MIN_DIFFICULTY, MAX_DIFFICULTY
            center = BASE_DIFFICULTY
            points_scale, start_scale = Z_SCALE, START_Z_SCALE

        points_score = _clamp(center - z_points * points_scale, low, high)
        start_score = _clamp(center - z_start * start_scale, low, high)
        score = POINTS_WEIGHT * points_score + START_WEIGHT * start_score

        result[pid] = int(round(_clamp(score, low, high)))

    if unknown:
        print(f"Note: {unknown} players had no detectable position; "
              f"scored against all non-kickers pooled.")

    return result


# ---------------------------------------------------------------------------
# Build / write
# ---------------------------------------------------------------------------
def build_gtm_entries(year, api_data_root=API_DATA_ROOT):
    managers = _load_json(managers_path(year, api_data_root))
    roster_points = _load_json(roster_points_path(year, api_data_root))

    team_to_name = _team_key_to_manager_name(managers, year)
    last_week = _last_week(roster_points)
    data = _collect_player_data(roster_points)

    entries = []
    for team_key, roster in roster_points[last_week].items():
        if team_key not in team_to_name:
            raise KeyError(f"Team {team_key} is in RosterPoints.json but not Managers.json")
        manager_name = team_to_name[team_key]

        for player in roster:
            pid = str(player.get("player_id"))
            if not player.get("name") or _is_defense(pid, data[pid]):
                continue
            entries.append(
                {
                    "player_id": pid,
                    "player_name": player["name"],
                    "manager": manager_name,
                    "year": int(year),
                    "difficulty": None,
                }
            )

    difficulties = calculate_difficulties(roster_points, [e["player_id"] for e in entries])
    for entry in entries:
        entry["difficulty"] = difficulties[entry["player_id"]]

    return entries


def write_gtm_file(year, api_data_root=API_DATA_ROOT, output_dir=GTM_OUTPUT_DIR):
    """Writes <output_dir>/<year>.json: one entry per non-defense player on a roster
    in the last available week."""
    entries = build_gtm_entries(year, api_data_root)

    path = gtm_path(year, output_dir)
    os.makedirs(os.path.dirname(path), exist_ok=True)
    with open(path, "w", encoding="utf-8") as f:
        json.dump(entries, f, indent=2, ensure_ascii=False)

    print(f"[{year}] Wrote {len(entries)} players to {path}")
    return path