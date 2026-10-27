import json
import os
from datetime import datetime, timezone
from pathlib import Path

# GetTransactionData.py is at .../Functions/APIFunctions/
# parents[1] = Functions  ->  .../Functions/APIData/{Year}
API_DATA_ROOT = Path(__file__).resolve().parents[1] / "APIData"

# Fetched separately so one problem type can't break the rest.
# "add,drop" covers waiver/free agent moves; trades and commish are isolated.
TRANSACTION_TYPE_GROUPS = ["add,drop", "trade", "commish"]


def transaction_dir(year, root=API_DATA_ROOT):
    return os.path.join(str(root), str(year))


def transaction_filename(year, root=API_DATA_ROOT):
    return os.path.join(transaction_dir(year, root), "TransactionData.json")


def _build_team_lookup(lg):
    """Returns {team_key: team_name}."""
    return {key: team.get("name") for key, team in lg.teams().items()}


def _to_iso(timestamp):
    try:
        return datetime.fromtimestamp(int(timestamp), tz=timezone.utc).isoformat()
    except (TypeError, ValueError, OSError):
        return None


def _flatten_player_meta(meta_list):
    """player[0] is a list of single-key dicts; merge them into one dict."""
    merged = {}
    for item in meta_list:
        if isinstance(item, dict):
            merged.update(item)
    return merged


def _extract_players(players_raw, team_lookup):
    """Turn the Yahoo 'players' block into a clean list of player movements."""
    players = []
    if not isinstance(players_raw, dict):
        return players

    for key, value in players_raw.items():
        if not key.isdigit():
            continue  # skip the "count" key

        player = value.get("player") if isinstance(value, dict) else None
        if not player:
            continue

        meta = _flatten_player_meta(player[0]) if isinstance(player[0], list) else {}

        tdata = {}
        if len(player) > 1 and isinstance(player[1], dict):
            tdata = player[1].get("transaction_data", {})
            if isinstance(tdata, list):  # trades sometimes return a list
                tdata = tdata[0] if tdata else {}

        name = meta.get("name")
        if isinstance(name, dict):
            name = name.get("full")

        source_team_key = tdata.get("source_team_key")
        dest_team_key = tdata.get("destination_team_key")

        players.append({
            "player_id": str(meta.get("player_id")) if meta.get("player_id") is not None else None,
            "player_name": name,
            "position": meta.get("display_position"),
            "nfl_team": meta.get("editorial_team_abbr"),
            "movement_type": tdata.get("type"),  # add / drop / trade
            "source_type": tdata.get("source_type"),  # waivers / freeagents / team
            "source_team_key": source_team_key,
            "source_team_name": team_lookup.get(source_team_key),
            "destination_type": tdata.get("destination_type"),
            "destination_team_key": dest_team_key,
            "destination_team_name": team_lookup.get(dest_team_key),
        })

    return players


def parse_transactions(raw_transactions, team_lookup):
    """Turn lg.transactions() output into a clean list of transaction dicts."""
    transactions = []
    for t in raw_transactions or []:
        trader_key = t.get("trader_team_key")
        tradee_key = t.get("tradee_team_key")

        transactions.append({
            "transaction_id": str(t.get("transaction_id")) if t.get("transaction_id") is not None else None,
            "transaction_key": t.get("transaction_key"),
            "type": t.get("type"),
            "status": t.get("status"),
            "timestamp": t.get("timestamp"),
            "date": _to_iso(t.get("timestamp")),
            "trader_team_key": trader_key,
            "trader_team_name": team_lookup.get(trader_key),
            "tradee_team_key": tradee_key,
            "tradee_team_name": team_lookup.get(tradee_key),
            "players": _extract_players(t.get("players"), team_lookup),
        })

    # oldest first
    transactions.sort(key=lambda x: int(x["timestamp"]) if x.get("timestamp") else 0)
    return transactions


def _fetch_all_transactions(lg, count=""):
    combined = {}
    for group in TRANSACTION_TYPE_GROUPS:
        try:
            raw = lg.transactions(group, count)
        except StopIteration:
            print(f"Warning: library failed on transaction type(s) '{group}', skipping.")
            continue
        except Exception as e:
            print(f"Warning: error fetching '{group}': {e}")
            continue

        for t in raw or []:
            key = t.get("transaction_key") or t.get("transaction_id")
            combined[key] = t  # dedupe across groups
    return list(combined.values())


def write_transactions_file(lg, year, root=API_DATA_ROOT, overwrite=False, count=""):
    path = transaction_filename(year, root)
    if os.path.exists(path) and not overwrite:
        print(f"[{year}] Transaction file already exists, skipped: {path}")
        return None

    os.makedirs(transaction_dir(year, root), exist_ok=True)

    raw = _fetch_all_transactions(lg, count)
    if not raw:
        print(f"[{year}] No transactions returned.")
        return None

    team_lookup = _build_team_lookup(lg)
    transactions = parse_transactions(raw, team_lookup)

    with open(path, "w", encoding="utf-8") as f:
        json.dump(transactions, f, indent=2, ensure_ascii=False)

    print(f"[{year}] Wrote {len(transactions)} transactions to {path}")
    return path