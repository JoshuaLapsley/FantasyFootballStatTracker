import shutil
import sys
from pathlib import Path



# RunWeekly.py is at <root>/PythonData/Refactor/CurrentSeason/, so parents[3] is the project root
PROJECT_ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(PROJECT_ROOT))

from yahoo_oauth import OAuth2
import yahoo_fantasy_api as yfa

from PythonData.APICallsAndStats.APIFunctions.GetMatchupData import write_week_files
from PythonData.APICallsAndStats.APIFunctions.GetTransactionData import write_transactions_file
from PythonData.APICallsAndStats.APIFunctions.GetRosterData import write_roster_points_file
from PythonData.APICallsAndStats.DataFunctions.CalculateEarnedWins import calculate_earned_wins
from PythonData.APICallsAndStats.DataFunctions.CalculateEarnedWinsPlus import write_earned_wins_plus
from PythonData.APICallsAndStats.DataFunctions.CalculateWar import write_war
from PythonData.APICallsAndStats.DataFunctions.CalculatePAR import write_par
from PythonData.APICallsAndStats.APIFunctions.GetDraftedPlayerPoints import write_weekly_points_file
from PythonData.APICallsAndStats.DataFunctions.CalculateExpectedWar import write_expected_war

from PythonData.APICallsAndStats.DataFunctions.CombineDraftedPlayerStats import write_draft_value
from PythonData.APICallsAndStats.APIFunctions.GetSchedule import pull_league_schedule

from PythonData.APICallsAndStats.DataFunctions.CalculateWaiverWar import calculate_waiver_war

from PythonData.APICallsAndStats.DataFunctions.DraftBoardWAR import create_war_images
from PythonData.APICallsAndStats.DataFunctions.DraftBoardPAR import generate_par_board_and_legend
from PythonData.APICallsAndStats.DataFunctions.DraftBoardSurplusWAR import generate_surplus_war_board_and_legend
from PythonData.APICallsAndStats.DataFunctions.GenerateWaiverWarBoard import generate_waiver_war_board_and_legend
from PythonData.APICallsAndStats.DataFunctions.ScheduleSwapCalculator import compute_schedule_records

from PythonData.APICallsAndStats.Projections.GetSleeperProjections import get_projections


def copy_dir(src, dest):
    """Copy the folder `src` to `dest`, replacing `dest` if it already exists."""
    src, dest = Path(src).resolve(), Path(dest).resolve()

    if not src.is_dir():
        raise NotADirectoryError(f"{src} is not a directory")
    if src == dest or src in dest.parents or dest in src.parents:
        raise ValueError("src and dest can't be the same folder or nested in each other")

    if dest.is_dir():
        shutil.rmtree(dest)      # remove the old copy
    elif dest.exists():
        dest.unlink()            # dest is a file, remove it
    dest.parent.mkdir(parents=True, exist_ok=True)
    shutil.copytree(src, dest)

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
#write_weekly_points_file(lg, year)

#Earned Wins

# calculate_earned_wins(year)
# write_earned_wins_plus(year)

#Drafted Players Stats

# write_war(year)
# write_par(year)
# write_expected_war(2026, completedWeeks)
# write_draft_value(year)
#calculate_waiver_war(lg, year)


#Boards
# create_war_images(year)
#generate_par_board_and_legend(year)
#generate_surplus_war_board_and_legend(year)
#generate_waiver_war_board_and_legend(year)

#compute_schedule_records(2026)

#get_projections(2023, None, "../APICallsAndStats/Projections/SleeperProjections")
#get_projections(2024, None, "../APICallsAndStats/Projections/SleeperProjections")


#copy_dir(f"../APICallsAndStats/Data/{year}", f"../../../Website/girderma-gridiron-website/src/league_stats_output/{year}")
