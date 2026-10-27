import json
from pathlib import Path

from yahoo_oauth import OAuth2
import yahoo_fantasy_api as yfa

BASE_DIR = Path(__file__).resolve().parent

sc = OAuth2(None, None, from_file='oauth2.json')
gm = yfa.Game(sc, 'nfl')

# Must match generate_league_stats.py
SEASONS = {
    2023: "423.l.902802",
    2024: "449.l.106896",
    2025: "461.l.111150",
}

NEW_OUTPUT_DIR = (BASE_DIR / ".." / "Website" / "girderma-gridiron-website" / "src" / "pages" / "LeagueHistory" / "Draft").resolve()
NEW_OUTPUT_DIR.mkdir(parents=True, exist_ok=True)

# --------------------------------------------------------------------------
# Disambiguation config
# --------------------------------------------------------------------------
NICKNAME_ALIASES = {
    ("Josh", "No Punts Intented"):      "Josh_Rubik",
    ("Josh", "The Sage's Playmakers"):  "Josh_Sage",
    ("Josh", "Room 40"):                "Josh_Rubik",
    ("Josh", "Mahomes Alone"):          "Josh_Rubik",
    ("Sam",  "Pad D's"):                "Sam_Paddy",
    ("Sam",  "Girder\u2019s Grippers"): "Sam_Girder",
}

# --------------------------------------------------------------------------
# Helpers
# --------------------------------------------------------------------------
def resolve_manager_key(nickname, team_name):
    if (nickname, team_name) in NICKNAME_ALIASES:
        return NICKNAME_ALIASES[(nickname, team_name)]

    known_duplicate_nicknames = {n for (n, _) in NICKNAME_ALIASES}
    if nickname in known_duplicate_nicknames:
        raise ValueError(
            f"Duplicate nickname '{nickname}' for '{team_name}' missing alias."
        )

    return nickname


def get_manager_to_team_map(lg):
    teams = lg.teams()
    mapping = {}

    for team_key, team_data in teams.items():
        team_name = team_data.get("name", "Unknown")
        managers = team_data.get("managers", [])

        for mgr_entry in managers:
            mgr = mgr_entry.get("manager", {})
            nickname = mgr.get("nickname", "Unknown")
            manager_key = resolve_manager_key(nickname, team_name)

            mapping[manager_key] = {
                "nickname": nickname,
                "team_name": team_name,
                "team_key": team_key,
            }

    return mapping


def get_team_key_to_manager_map(manager_to_team_map):
    """Invert manager->team map so we can look up manager_key by team_key."""
    team_key_to_manager = {}
    for manager_key, info in manager_to_team_map.items():
        team_key_to_manager[info["team_key"]] = manager_key
    return team_key_to_manager


def get_player_info_map(lg, player_ids):
    """Batch-resolve player_id -> {name, position, nfl_team}."""
    player_info_map = {}
    if not player_ids:
        return player_info_map

    try:
        details = lg.player_details(player_ids)
        for p in details:
            pid = str(p.get('player_id'))
            name = p.get('name', {})
            player_info_map[pid] = {
                "name": name.get("full") if isinstance(name, dict) else name,
                "position": p.get("display_position") or p.get("primary_position"),
                "nfl_team": p.get("editorial_team_abbr"),
            }
    except Exception as e:
        print(f"  Warning: could not fetch player details ({e})")

    return player_info_map


# --------------------------------------------------------------------------
# Core pull
# --------------------------------------------------------------------------
def pull_draft_data_for_season(season_year: int, league_id: str):
    print(f"Pulling draft data for {season_year} (league {league_id})...")
    lg = gm.to_league(league_id)

    manager_to_team_map = get_manager_to_team_map(lg)
    team_key_to_manager = get_team_key_to_manager_map(manager_to_team_map)

    # Returns a list of dicts, one per pick, e.g.:
    # {'pick': 1, 'round': 1, 'team_key': '449.l.106896.t.1', 'player_id': '12345', 'cost': None}
    draft_results = lg.draft_results()

    player_ids = [pick["player_id"] for pick in draft_results if pick.get("player_id")]
    player_info_map = get_player_info_map(lg, player_ids)

    enriched = []
    for pick in draft_results:
        team_key = pick.get("team_key")
        manager_key = team_key_to_manager.get(team_key, team_key)
        team_info = manager_to_team_map.get(manager_key, {})

        pid = str(pick.get("player_id"))
        player_info = player_info_map.get(pid, {})

        enriched.append({
            "pick": pick.get("pick"),
            "round": pick.get("round"),
            "manager_key": manager_key,
            "team_key": team_key,
            "team_name": team_info.get("team_name", team_key),
            "player_id": pick.get("player_id"),
            "player_name": player_info.get("name"),
            "player_position": player_info.get("position"),
            "player_nfl_team": player_info.get("nfl_team"),
            "cost": pick.get("cost"),  # relevant for auction drafts
        })

    return enriched


def main():
    for season_year, league_id in SEASONS.items():
        draft_data = pull_draft_data_for_season(season_year, league_id)

        output_path = NEW_OUTPUT_DIR / f"draft_{season_year}.json"
        with open(output_path, "w") as f:
            json.dump(draft_data, f, indent=2)

        print(f"  Saved {len(draft_data)} picks to {output_path}")


if __name__ == "__main__":
    main()