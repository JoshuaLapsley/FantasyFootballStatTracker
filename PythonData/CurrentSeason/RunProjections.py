import sys
import os

sys.path.append(os.path.abspath(os.path.join(os.path.dirname(__file__), "..", "..")))

from PythonData.APICallsAndStats.Projections.GetSleeperProjections import get_projections

year = 2023
currentWeek = 1

get_projections(year, currentWeek, "../APICallsAndStats/Projections/SleeperProjections", keep_previous=False)