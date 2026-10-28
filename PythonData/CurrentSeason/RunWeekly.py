import json
import os
import sys
import shutil
from pathlib import Path
from datetime import datetime as dt, timezone

PROJECT_ROOT = Path(__file__).resolve().parents[2]
SCRIPT_DIR = Path(__file__).resolve().parent
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
    """Copy folder `src` to `dest`, replacing `dest` if it already exists.

    Copies to a temp folder first, so the old copy is only removed once
    the new one is fully written.
    """
    src, dest = Path(src).resolve(), Path(dest).resolve()

    if not src.is_dir():
        raise NotADirectoryError(f"{src} is not a directory")
    if src == dest or src in dest.parents or dest in src.parents:
        raise ValueError("src and dest can't be the same folder or nested in each other")

    dest.parent.mkdir(parents=True, exist_ok=True)

    tmp = dest.with_name(dest.name + ".tmp")
    if tmp.exists():
        shutil.rmtree(tmp)
    shutil.copytree(src, tmp)

    if dest.is_dir():
        shutil.rmtree(dest)
    elif dest.exists():
        dest.unlink()
    os.replace(tmp, dest)


def write_meta(league, data_dir, year=2026):
    """
    Records which week the data is current through, as meta.json inside
    data_dir. Written atomically (temp file + rename).
    """
    current_week = league.current_week()
    meta = {
        "season": year,
        "current_week": current_week,                    # week Yahoo says is in progress
        "data_through_week": max(current_week - 1, 0),   # last fully finished week
        "updated_at": dt.now(timezone.utc).isoformat(),
    }

    data_dir = Path(data_dir)
    data_dir.mkdir(parents=True, exist_ok=True)
    path = data_dir / "meta.json"
    tmp_path = path.with_name("meta.json.tmp")
    with open(tmp_path, "w") as f:
        json.dump(meta, f, indent=2)
    os.replace(tmp_path, path)
    print(f"Saved -> {path}")


year = 2026
completedWeeks = 7

# Where the generated data lives, and where the website reads it from
DATA_DIR = SCRIPT_DIR / ".." / "APICallsAndStats" / "Data" / str(year)
WEBSITE_DIR = (PROJECT_ROOT / "Website" / "girderma-gridiron-website"
               / "src" / "league_stats_output" / str(year))

# Anchored to the script so it works no matter where you run it from.
sc = OAuth2(None, None, from_file=str(SCRIPT_DIR / "oauth2.json"))
gm = yfa.Game(sc, "nfl")

league_ids = gm.league_ids(year=year)
lg = gm.to_league(league_ids[0])

#Sleeper API Caall
get_projections(year, None, "../APICallsAndStats/Projections/SleeperProjections")

#Yahoo API Calls
write_roster_points_file(lg, year)
write_week_files(lg, year)
write_transactions_file(lg, year)
write_weekly_points_file(lg, year)

#Earned Wins
calculate_earned_wins(year)
write_earned_wins_plus(year)

#Drafted Players Stats
write_war(year)
write_par(year)
write_expected_war(year, completedWeeks)
write_draft_value(year)

#Waiver WAR (Uses yahoo api to get individual waiver stats)
calculate_waiver_war(lg, year)

#Generate Boards
create_war_images(year)
generate_par_board_and_legend(year)
generate_surplus_war_board_and_legend(year)
generate_waiver_war_board_and_legend(year)

#MISC
compute_schedule_records(year)

#Tells Website it has been updated (written into Data first so it gets copied)
write_meta(lg, DATA_DIR, year)

#Copy To Website
copy_dir(DATA_DIR, WEBSITE_DIR)