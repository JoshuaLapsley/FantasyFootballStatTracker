"""
debug2.py - checks what get_manager_to_team_map actually returns
"""
from yahoo_oauth import OAuth2
import yahoo_fantasy_api as yfa
import json

sc = OAuth2(None, None, from_file='oauth2.json')
gm = yfa.Game(sc, 'nfl')
lg = gm.to_league("461.l.111150")

teams = lg.teams()
print(f"Total teams from lg.teams(): {len(teams)}\n")

mapping = {}
for team_key, team_data in teams.items():
    team_name = team_data.get("name", "Unknown")
    managers = team_data.get("managers", [])

    print(f"Team: {team_name}")
    print(f"  managers list length: {len(managers)}")

    for mgr_entry in managers:
        mgr = mgr_entry.get("manager", {})
        guid = mgr.get("guid")
        nickname = mgr.get("nickname", "Unknown")
        print(f"  guid present: {guid is not None}  |  nickname: {nickname}  |  guid value: {repr(guid)}")

        if guid:
            if guid in mapping:
                print(f"  *** COLLISION: guid already in mapping as {mapping[guid]['team_name']} ***")
            mapping[guid] = {"nickname": nickname, "team_name": team_name}
        else:
            print(f"  *** SKIPPED: guid is None or empty ***")

print(f"\nFinal mapping size: {len(mapping)}")
print(f"Keys: {list(mapping.keys())}")