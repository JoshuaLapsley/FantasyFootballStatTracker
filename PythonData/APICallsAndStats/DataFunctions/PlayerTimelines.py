import json
from datetime import date, datetime, timedelta, timezone
from pathlib import Path

# Same layout as trade_evaluator.py: ../APIData/{year} in, ../Data/All out
API_DATA_ROOT = Path(__file__).resolve().parent.parent / "APIData"
OUTPUT_DIR = Path(__file__).resolve().parent.parent / "Data" / "All"
OUTPUT_FILENAME = "PlayerTimelines.json"

DRAFT_FILENAME = "DraftData.json"
TRANSACTION_FILENAME = "TransactionData.json"

# Optional manual overrides if a season's start ever differs: {year: date(...)}
SEASON_START_OVERRIDES = {}
LAST_NFL_WEEK = 18   # anything after this week counts as offseason


# --------------------------------------------------------------------------
# Weeks
# --------------------------------------------------------------------------
def season_start(year):
    """Tuesday after Labor Day (first Monday of September), same as the trade evaluator."""
    if year in SEASON_START_OVERRIDES:
        return SEASON_START_OVERRIDES[year]
    d = date(year, 9, 1)
    labor_day = d + timedelta(days=(0 - d.weekday()) % 7)
    return labor_day + timedelta(days=1)


def parse_date(tx):
    """Transaction time as a datetime (UTC). Falls back to the unix timestamp."""
    if tx.get("date"):
        return datetime.fromisoformat(tx["date"])
    try:
        return datetime.fromtimestamp(int(tx["timestamp"]), tz=timezone.utc)
    except (TypeError, ValueError, KeyError):
        return None


def classify(dt, year):
    """Returns (phase, week). Weeks run Tuesday to Monday."""
    if dt is None:
        return None, None
    d = dt.date()
    start = season_start(year)
    if d < start:
        return "preseason", None
    week = (d - start).days // 7 + 1
    if week > LAST_NFL_WEEK:
        return "offseason", None
    return "regular_season", week


# --------------------------------------------------------------------------
# Loading
# --------------------------------------------------------------------------
def find_years(root=API_DATA_ROOT):
    return sorted(int(p.name) for p in root.iterdir() if p.is_dir() and p.name.isdigit())


def load_json(path):
    if not path.exists():
        return []
    with open(path, encoding="utf-8") as f:
        return json.load(f)


# --------------------------------------------------------------------------
# Building timelines
# --------------------------------------------------------------------------
def get_player(players, player_id, name=None, position=None):
    p = players.setdefault(player_id, {
        "player_id": player_id,
        "name": name,
        "position": position,
        "seasons": [],
        "timeline": [],
    })
    # Years are processed oldest to newest, so the latest name/position wins
    if name:
        p["name"] = name
    if position:
        p["position"] = position
    return p


def add_draft_events(year, picks, players):
    """Adds a 'drafted' event per pick. Returns {team_key: manager_nickname} for the year."""
    managers = {}
    for pick in picks:
        pid = pick.get("player_id")
        managers[pick.get("team_key")] = pick.get("manager_nickname")
        if not pid:
            continue
        player = get_player(players, str(pid), pick.get("player_name"), pick.get("position"))
        player["timeline"].append({
            "type": "drafted",
            "year": year,
            "phase": "draft",
            "week": None,
            "date": None,
            "team": pick.get("team_name"),
            "team_key": pick.get("team_key"),
            "manager": pick.get("manager_nickname"),
            "round": pick.get("round"),
            "pick": pick.get("pick"),
            "transaction_id": None,
            "_sort": (year, 0, 0, 0),
        })
    return managers


def add_transaction_events(year, transactions, managers, players):
    for tx in transactions:
        # Skip vetoed/pending moves and commissioner entries (they have no players)
        if tx.get("status") != "successful" or not tx.get("players"):
            continue

        dt = parse_date(tx)
        phase, week = classify(dt, year)
        try:
            timestamp = int(tx.get("timestamp"))
        except (TypeError, ValueError):
            timestamp = 0
        try:
            tx_num = int(tx.get("transaction_id"))
        except (TypeError, ValueError):
            tx_num = 0

        for p in tx["players"]:
            pid = p.get("player_id")
            move = p.get("movement_type")
            if not pid or move not in ("add", "drop", "trade"):
                continue

            player = get_player(players, str(pid), p.get("player_name"), p.get("position"))

            event = {
                "year": year,
                "phase": phase,
                "week": week,
                "date": dt.isoformat() if dt else None,
                "transaction_id": tx.get("transaction_id"),
                "_sort": (year, 1, timestamp, tx_num),
            }

            if move == "add":
                key = p.get("destination_team_key")
                event.update({
                    "type": "added",
                    "team": p.get("destination_team_name"),
                    "team_key": key,
                    "manager": managers.get(key),
                    "source": p.get("source_type"),          # waivers / freeagents
                })
            elif move == "drop":
                key = p.get("source_team_key")
                event.update({
                    "type": "dropped",
                    "team": p.get("source_team_name"),
                    "team_key": key,
                    "manager": managers.get(key),
                    "destination": p.get("destination_type"),  # waivers / freeagents
                })
            else:  # trade
                to_key = p.get("destination_team_key")
                from_key = p.get("source_team_key")
                event.update({
                    "type": "traded",
                    "team": p.get("destination_team_name"),   # the team that received him
                    "team_key": to_key,
                    "manager": managers.get(to_key),
                    "from_team": p.get("source_team_name"),
                    "from_team_key": from_key,
                    "from_manager": managers.get(from_key),
                })

            player["timeline"].append(event)


def build_player_timelines(api_root=API_DATA_ROOT):
    players = {}
    years = []

    for year in find_years(api_root):
        year_dir = api_root / str(year)
        picks = load_json(year_dir / DRAFT_FILENAME)
        transactions = load_json(year_dir / TRANSACTION_FILENAME)
        if not picks and not transactions:
            continue
        years.append(year)

        managers = add_draft_events(year, picks, players)
        add_transaction_events(year, transactions, managers, players)

    # Order each player's events oldest to newest, then drop the helper key
    for player in players.values():
        player["timeline"].sort(key=lambda e: e["_sort"])
        for e in player["timeline"]:
            e.pop("_sort")
        player["seasons"] = sorted({e["year"] for e in player["timeline"]})

    return {"years": years, "players": players}


# --------------------------------------------------------------------------
# Output
# --------------------------------------------------------------------------
def write_player_timelines(api_root=API_DATA_ROOT, out_dir=OUTPUT_DIR):
    result = build_player_timelines(api_root)

    out_dir.mkdir(parents=True, exist_ok=True)
    out_path = out_dir / OUTPUT_FILENAME
    with open(out_path, "w", encoding="utf-8") as f:
        json.dump(result, f, indent=2, ensure_ascii=False)

    n_events = sum(len(p["timeline"]) for p in result["players"].values())
    print(f"Years: {result['years']}")
    print(f"Wrote {len(result['players'])} players, {n_events} events to {out_path}")
    return out_path


if __name__ == "__main__":
    write_player_timelines()