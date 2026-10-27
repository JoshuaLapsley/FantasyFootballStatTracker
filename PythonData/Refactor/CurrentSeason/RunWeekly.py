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
from PythonData.Refactor.Functions.DataFunctions.CalculateEarnedWins import calculate_earned_wins
from PythonData.Refactor.Functions.DataFunctions.CalculateEarnedWinsPlus import write_earned_wins_plus
from PythonData.Refactor.Functions.DataFunctions.CalculateWar import write_war
from PythonData.Refactor.Functions.DataFunctions.CalculatePAR import write_par
from PythonData.Refactor.Functions.APIFunctions.GetDraftedPlayerPoints import write_weekly_points_file
from PythonData.Refactor.Functions.DataFunctions.CalculateExpectedWar import write_expected_war

from PythonData.Refactor.Functions.DataFunctions.CombineDraftedPlayerStats import write_draft_value
from PythonData.Refactor.Functions.APIFunctions.GetSchedule import pull_league_schedule

from PythonData.Refactor.Functions.DataFunctions.CalculateWaiverWar import calculate_waiver_war

from PythonData.Refactor.Functions.DataFunctions.DraftBoardWAR import create_war_images

year = 2026
completedWeeks = 7

# Absolute path so this works no matter where you run the script from.
# Adjust if your oauth2.json lives somewhere else.
sc = OAuth2(None, None, from_file=str("oauth2.json"))
gm = yfa.Game(sc, "nfl")

league_ids = gm.league_ids(year=year)
lg = gm.to_league(league_ids[0])

#API Calls

# write_roster_points_file(lg, year)
# write_week_files(lg, year)
# write_transactions_file(lg, year)
# write_weekly_points_file(lg, year)

#Earned Wins

# calculate_earned_wins(year)
# write_earned_wins_plus(year)

#Drafted Players Stats

write_war(year)
write_par(year)
write_expected_war(2026, completedWeeks)
write_draft_value(year)
calculate_waiver_war(lg, year)


#Boards
create_war_images(year)
