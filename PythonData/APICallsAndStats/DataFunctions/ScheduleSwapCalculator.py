"""
Computes every team's record against every other team's schedule.

For team T and schedule S, each week T's score is compared to the score of
whoever S actually played that week. If S actually played T that week, T is
credited with their earned wins for that week.
When T == S, you get T's actual record.

Reads:   ../APIData/{year}/MatchupData/Week*.json
Writes:  ../Data/{year}/StrengthOfSchedule.json

Only the first 14 weeks (the regular season) are used; any Week15+ files
in the folder are ignored.

Use as a function:
    from StrengthOfScheduleCalculator import compute_schedule_records
    compute_schedule_records(2026)

Or from the command line:
    python StrengthOfScheduleCalculator.py 2026

Paths are resolved relative to this file's directory, not the current
working directory.
"""
import glob
import json
import os
import re
import sys
from pathlib import Path

SCRIPT_DIR = os.path.dirname(os.path.abspath(__file__))
API_DATA_DIR = (Path(SCRIPT_DIR) / ".." / "APIData").resolve()   # input
DATA_DIR = (Path(SCRIPT_DIR) / ".." / "Data").resolve()          # output

MAX_WEEKS = 14
OUTPUT_FILENAME = "StrengthOfSchedule.json"


def _load_weeks(input_folder, max_week=MAX_WEEKS):
    files = glob.glob(os.path.join(input_folder, "Week*.json"))
    if not files:
        raise FileNotFoundError(f"No Week*.json files found in '{input_folder}'")
    files.sort(key=lambda f: int(re.search(r"Week(\d+)", os.path.basename(f)).group(1)))
    files = [f for f in files
             if int(re.search(r"Week(\d+)", os.path.basename(f)).group(1)) <= max_week]
    if not files:
        raise FileNotFoundError(f"No Week*.json files for weeks 1-{max_week} found in '{input_folder}'")
    weeks = []
    for f in files:
        with open(f, encoding="utf-8") as fh:
            weeks.append(json.load(fh))
    return weeks


def _earned_wins_for_week(points):
    """
    Returns {team_key: earned_win_fraction} for a single week's
    `points` dict ({team_key: score}), using the same formula as
    WriteEarnedWinsData.py's season-long Earned Wins: for each team,
    the fraction of the OTHER teams that week whose score they beat
    (ties split evenly), i.e. rank-based so it's always in [0, 1].

    e.g. for N teams, the best score earns (N-1)/(N-1) = 1.0, the
    worst earns 0/(N-1) = 0.0, and two teams tied for a rank each earn
    the average of the ranks they'd otherwise have split.
    """
    n = len(points)
    if n < 2:
        return {k: 0.0 for k in points}

    earned = {}
    for team, score in points.items():
        beaten = sum(1 for other, other_score in points.items()
                     if other != team and score > other_score)
        tied = sum(1 for other, other_score in points.items()
                   if other != team and score == other_score)
        # Ties split the win fraction they'd otherwise fully win/lose:
        # beating `beaten` teams outright plus half-credit for each
        # tied team, out of the (n - 1) other teams.
        earned[team] = (beaten + 0.5 * tied) / (n - 1)
    return earned


def compute_schedule_records(year, include_playoffs=False):
    """
    Read Week*.json files (weeks 1-14 only) from ../APIData/{year}/MatchupData,
    compute every team's record against every team's schedule, and write the
    result as JSON to ../Data/{year}/StrengthOfSchedule.json (folder created if
    it doesn't exist).

    For team T against schedule S, each week is scored as:
      - a normal win/loss if S's actual opponent that week was some
        third team (T's score compared to that third team's score),
      - a win/loss split in half (0.5 added to `wins`) if T's score
        exactly tied that third team's score,
      - T's EARNED WINS for that specific week (a fraction EW in
        [0, 1], added to `wins`, with the complementary (1 - EW) added
        to `losses`) if S's actual opponent that week was T itself --
        since there's no third team to compare against, this credits
        T with how it performed relative to the whole field that week
        rather than re-using (or discarding) the real T-vs-S result.
        Splitting EW/(1-EW) between wins/losses keeps wins+losses
        summing to exactly 1 for that week, same as every other week.
        Note this fraction is computed against all 13 other teams that
        week, so dropping it into this single slot does NOT make the
        row average equal season Earned Wins exactly (that identity
        only holds if the self-matchup slot uses the real T-vs-S
        result instead) -- it's used here because it's the
        semantically meaningful value for that slot, not to preserve
        that equality.

    `wins` is therefore a float in general (not just whole/half wins),
    and `losses` only ever accumulates from genuine, non-self-matchup
    losses. There's no `ties` field -- every tie (genuine or the
    self-matchup case) is represented as partial credit inside `wins`.

    When T == S, T's own schedule never contains a week where T "played
    itself", so every week falls through to the normal win/loss/tie
    comparison against T's real opponent -- i.e. T == S still gives
    T's actual record, unaffected by the earned-wins substitution
    above (that substitution only ever applies for S != T, in the one
    week per schedule where S's real opponent happened to be T).

    Returns the path of the written file.
    """
    year = int(year)
    input_folder = API_DATA_DIR / str(year) / "MatchupData"
    output_dir = DATA_DIR / str(year)

    names = {}      # team_key -> name
    week_data = []  # list of {"points": {key: pts}, "opp": {key: opp_key}, "earned": {key: fraction}}

    for matchups in _load_weeks(str(input_folder)):
        points, opp = {}, {}
        for m in matchups:
            if m.get("status") != "postevent":
                continue
            if not include_playoffs and (m.get("is_playoffs") or m.get("is_consolation")):
                continue
            if len(m["teams"]) != 2:
                continue
            a, b = m["teams"]
            for t in (a, b):
                names[t["team_key"]] = t["name"]
                points[t["team_key"]] = t["points"]
            opp[a["team_key"]] = b["team_key"]
            opp[b["team_key"]] = a["team_key"]
        if points:
            week_data.append({
                "points": points,
                "opp": opp,
                "earned": _earned_wins_for_week(points),
            })

    keys = sorted(names, key=lambda k: int(k.rsplit(".", 1)[-1]))
    result = {}

    for t in keys:
        result[names[t]] = {"team_key": t, "vs_schedule_of": {}}
        for s in keys:
            w = l = 0.0
            for wk in week_data:
                if t not in wk["points"] or s not in wk["opp"]:
                    continue  # bye week / missing data
                o = wk["opp"][s]
                if o == t:
                    # S's actual opponent this week was T itself -- no
                    # third-team score to compare against, so credit T
                    # with its earned wins fraction for this week (and
                    # the complementary fractional loss, so wins+losses
                    # still sums to exactly 1 for this week like every
                    # other week).
                    ew = wk["earned"][t]
                    w += ew
                    l += 1 - ew
                    continue
                opp_score = wk["points"][o]
                my_score = wk["points"][t]
                if my_score > opp_score:
                    w += 1
                elif my_score < opp_score:
                    l += 1
                else:
                    w += 0.5  # genuine tie, split the win

            result[names[t]]["vs_schedule_of"][names[s]] = {
                "wins": round(w, 4), "losses": round(l, 4)
            }

    os.makedirs(output_dir, exist_ok=True)
    out_path = os.path.join(output_dir, OUTPUT_FILENAME)
    with open(out_path, "w", encoding="utf-8") as fh:
        json.dump(result, fh, indent=2, ensure_ascii=False)

    print(f"Wrote {out_path} ({len(keys)} teams, {len(week_data)} weeks)")
    return out_path


if __name__ == "__main__":
    if len(sys.argv) != 2:
        print("Usage: python StrengthOfScheduleCalculator.py <year>")
        sys.exit(1)
    compute_schedule_records(int(sys.argv[1]))