import sys
from pathlib import Path







# RunWeekly.py is at <root>/PythonData/Refactor/CurrentSeason/, so parents[3] is the project root
PROJECT_ROOT = Path(__file__).resolve().parents[3]
sys.path.insert(0, str(PROJECT_ROOT))

from yahoo_oauth import OAuth2
import yahoo_fantasy_api as yfa

from PythonData.Refactor.Functions.APIFunctions.GetMatchupData import write_week_files
from PythonData.Refactor.Functions.APIFunctions.GetTransactionData import write_transactions_file
from PythonData.Refactor.Functions.APIFunctions.GetRosterData import write_roster_points_file

year = 2026

# Absolute path so this works no matter where you run the script from.
# Adjust if your oauth2.json lives somewhere else.
sc = OAuth2(None, None, from_file=str("oauth2.json"))
gm = yfa.Game(sc, "nfl")

league_ids = gm.league_ids(year=year)
lg = gm.to_league(league_ids[0])

#write_week_files(lg, year)
#write_transactions_file(lg, year)
write_roster_points_file(lg, year)