from yahoo_oauth import OAuth2
from WriteWeeklyMatchupData import write_week_files
from WriteEarnedWinsData import calculate_earned_wins
import yahoo_fantasy_api as yfa
import glob
import json
import os

sc = OAuth2(None, None, from_file='../oauth2.json')
gm = yfa.Game(sc, 'nfl')



YEAR_ID = '470.l.205662'#Change this every year
lg = gm.to_league(YEAR_ID)

SCRIPT_DIR = os.path.dirname(os.path.abspath(__file__))

CURRENT_SEASON_DATA_DIR = os.path.normpath(os.path.join(
    SCRIPT_DIR, "..", "..", "Website", "girderma-gridiron-website",
    "src", "league_stats_output", "CurrentSeason"
))

MATCHUP_DATA_DIR = os.path.normpath(os.path.join(
    SCRIPT_DIR, "..", "..", "Website", "girderma-gridiron-website",
    "src", "league_stats_output", "CurrentSeason", "MatchupData"
))



def main():
    write_week_files(lg, OUTPUT_DIR=MATCHUP_DATA_DIR)
    calculate_earned_wins(data_directory=MATCHUP_DATA_DIR, output_directory=CURRENT_SEASON_DATA_DIR)

main()
