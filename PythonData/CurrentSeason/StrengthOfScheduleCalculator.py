"""
Computes every team's record against every other team's schedule.

For team T and schedule S, each week T's score is compared to the score of
whoever S actually played that week. If S actually played T that week, T is
treated as playing S's score (i.e. the real T-vs-S game).
When T == S, you get T's actual record.

Use as a function:
    from schedule_swap import compute_schedule_records
    compute_schedule_records("MatchupData", "output")

Or from the command line:
    python schedule_swap.py MatchupData output
    python schedule_swap.py MatchupData output --include-playoffs
"""
import argparse
import glob
import json
import os
import re


def _load_weeks(input_folder):
    files = glob.glob(os.path.join(input_folder, "Week*.json"))
    if not files:
        raise FileNotFoundError(f"No Week*.json files found in '{input_folder}'")
    files.sort(key=lambda f: int(re.search(r"Week(\d+)", os.path.basename(f)).group(1)))
    weeks = []
    for f in files:
        with open(f, encoding="utf-8") as fh:
            weeks.append(json.load(fh))
    return weeks


def compute_schedule_records(input_folder, output_dir,
                             output_filename="schedule_records.json",
                             include_playoffs=False):
    """
    Read Week*.json files from `input_folder`, compute every team's record
    against every team's schedule, and write the result as JSON into
    `output_dir` (created if it doesn't exist).

    Returns the path of the written file.
    """
    names = {}      # team_key -> name
    week_data = []  # list of {"points": {key: pts}, "opp": {key: opp_key}}

    for matchups in _load_weeks(input_folder):
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
            week_data.append({"points": points, "opp": opp})

    keys = sorted(names, key=lambda k: int(k.rsplit(".", 1)[-1]))
    result = {}

    for t in keys:
        result[names[t]] = {"team_key": t, "vs_schedule_of": {}}
        for s in keys:
            w = l = ties = 0
            for wk in week_data:
                if t not in wk["points"] or s not in wk["opp"]:
                    continue  # bye week / missing data
                o = wk["opp"][s]
                if o == t:
                    ties += 1  # S played T this week, so T would be playing itself
                    continue
                opp_score = wk["points"][o]
                my_score = wk["points"][t]
                if my_score > opp_score:
                    w += 1
                elif my_score < opp_score:
                    l += 1
                else:
                    ties += 1
            result[names[t]]["vs_schedule_of"][names[s]] = {
                "wins": w, "losses": l, "ties": ties
            }

    os.makedirs(output_dir, exist_ok=True)
    out_path = os.path.join(output_dir, output_filename)
    with open(out_path, "w", encoding="utf-8") as fh:
        json.dump(result, fh, indent=2, ensure_ascii=False)

    print(f"Wrote {out_path} ({len(keys)} teams, {len(week_data)} weeks)")
    return out_path


if __name__ == "__main__":
    ap = argparse.ArgumentParser(description=__doc__,
                                 formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("input_folder", help="Folder containing Week1.json, Week2.json, ...")
    ap.add_argument("output_dir", help="Folder to write the results into")
    ap.add_argument("--filename", default="schedule_records.json",
                    help="Output file name (default: schedule_records.json)")
    ap.add_argument("--include-playoffs", action="store_true",
                    help="Include playoff and consolation games (default: regular season only)")
    args = ap.parse_args()

    compute_schedule_records(args.input_folder, args.output_dir,
                             args.filename, args.include_playoffs)