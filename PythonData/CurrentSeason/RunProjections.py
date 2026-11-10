import sys
import os

sys.path.append(os.path.abspath(os.path.join(os.path.dirname(__file__), "..", "..")))

from PythonData.APICallsAndStats.Projections.GetSleeperProjections import get_projections

year = 2026
currentWeek = 9

get_projections(year, currentWeek, "../APICallsAndStats/Projections/SleeperProjections")