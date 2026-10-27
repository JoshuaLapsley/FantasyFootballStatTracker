from yahoo_oauth import OAuth2
import yahoo_fantasy_api as yfa
import json
import os

sc = OAuth2(None, None, from_file="oauth2.json")
gm = yfa.Game(sc, "nfl")

league_ids = gm.league_ids(game_codes=["nfl"])

for league_id in league_ids:
    lg = gm.to_league(league_id)

    print(f"League ID: {league_id}")
    print(f"Name: {lg.settings()['name']}")
    print(f"Season: {lg.settings()['season']}")
    print()