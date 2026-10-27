import time
from yahoo_oauth import OAuth2
import yahoo_fantasy_api as yfa

# Reuse your existing oauth2.json from the other Girderma Gridiron pipelines
oauth = OAuth2(None, None, from_file='oauth2.json')

game = yfa.Game(oauth, 'nfl')
league = game.to_league('YOUR_LEAGUE_KEY')  # e.g. '423.l.123456'

week = league.current_week()

def get_weekly_projections(league, week):
    """
    Pulls projected weekly points for every rostered player in the league.
    """
    all_projections = []
    teams = league.teams()

    for team_key, team_info in teams.items():
        roster = league.to_team(team_key).roster(week=week)
        player_keys = [p['player_id'] for p in roster]

        # yahoo_fantasy_api batches player_details/stats calls internally,
        # but you can also hit the raw endpoint for more control (see below)
        for p in roster:
            player_id = p['player_id']
            name = p['name']
            pos = p['selected_position']

            stats = league.player_stats([player_id], 'week', week=week)
            proj_points = stats[0].get('projected_points') if stats else None

            all_projections.append({
                'week': week,
                'team': team_info['name'],
                'player': name,
                'position': pos,
                'projected_points': proj_points
            })
            time.sleep(0.3)  # be polite to Yahoo's rate limits

    return all_projections

projections = get_weekly_projections(league, week)

import pandas as pd
df = pd.DataFrame(projections)
df.to_csv(f'projections_week{week}.csv', index=False)
print(df.sort_values('projected_points', ascending=False).head(20))