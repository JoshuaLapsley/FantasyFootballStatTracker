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



TEAM_TO_NICKNAME = {
    "Ozzy Stick": "Ben", "Mahomes Alone": "Josh_Rubik", "Tsuga\u2019s Tuck Shop": "Caleb", "Revy\u2019s Konstruction": "Connor", "Supernova\u2019s Studs": "Gavin Brodie", "Spirally Things": "Levi", "Hunter\u2019s Hunters": "Hunter", "Omaha Beach Real Estate": "Andrew", "Flows Aggressive Insurance": "Zach", "Go With The Flow": "Zach", "Wicked Wah-Bams": "Nate", "The Sage's Playmakers": "Josh_Sage", "Sparty's Sigmas": "Jackson", "For Pitts and Giggles": "Zach", "The Hunters": "Hunter", "Lawrence & Order": "Andrew", "Oscorps Buns": "Ben", "Bumpin Brasnos": "Ben", "Room 40": "Josh_Rubik", "No Punts Intented": "Josh_Rubik", "Hungry Hungry Hokk": "Nate", "Deej-lanta Falcons": "DJ", "Pad D's": "Sam_Paddy", "Girder\u2019s Grippers": "Sam_Girder", "Ma\u00eetre Magic": "Levi", "Bumpin Brasnos": "Levi"
}