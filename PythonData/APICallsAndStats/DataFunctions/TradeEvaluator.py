import json
from dataclasses import dataclass, field
from datetime import date, datetime
from pathlib import Path
import re
import unicodedata
from functools import lru_cache

DATA_DIR = Path(__file__).resolve().parent.parent / "APIData"
TRANSACTION_FILENAME = "TransactionData.json"
ROSTER_FILENAME = "RosterPoints.json"

# Tuesday before NFL Week 1 kickoff. Weeks roll over every 7 days from here.
# Add each year you use.
SEASON_START = {
    2026: date(2026, 9, 8),
}

POSITION_ORDER = ["QB", "RB", "WR", "TE", "W/R/T", "K", "DEF", "BN", "IR"]


# --------------------------------------------------------------------------
# Data classes
# --------------------------------------------------------------------------
@dataclass
class TradedPlayer:
    name: str
    position: str
    nfl_team: str
    from_team: str
    to_team: str


@dataclass
class Trade:
    transaction_id: str
    date: str
    trader_team: str
    tradee_team: str
    players: list = field(default_factory=list)
    trader_team_key: str = None   # e.g. "470.l.205662.t.9"
    tradee_team_key: str = None
    week: int = None              # fantasy week the trade completed in

    @classmethod
    def from_transaction(cls, t, year):
        trade = cls(
            transaction_id=t["transaction_id"],
            date=t["date"],
            trader_team=t["trader_team_name"],
            tradee_team=t["tradee_team_name"],
            trader_team_key=t.get("trader_team_key"),
            tradee_team_key=t.get("tradee_team_key"),
            players=[
                TradedPlayer(
                    name=p["player_name"],
                    position=p["position"],
                    nfl_team=p["nfl_team"],
                    from_team=p["source_team_name"],
                    to_team=p["destination_team_name"],
                )
                for p in t["players"]
            ],
        )
        trade.week = effective_trade_week(trade.date, year, t.get("week"))
        return trade


def week_from_date(date_str, year):
    start = SEASON_START.get(year)
    if start is None:
        raise KeyError(f"Add {year} to SEASON_START to derive the week from a date.")
    d = datetime.fromisoformat(date_str[:19]).date()
    return max(1, (d - start).days // 7 + 1)

def effective_trade_week(date_str, year, week=None):
    """Week a trade starts counting. Monday trades roll to the next week."""
    base = week or week_from_date(date_str, year)
    d = datetime.fromisoformat(date_str[:19]).date()
    return base + 1 if d.weekday() == 0 else base   # 0 = Monday


# --------------------------------------------------------------------------
# Loading
# --------------------------------------------------------------------------
def get_data_path(year, filename):
    return DATA_DIR / str(year) / filename


def get_valid_trades(year):
    """Load the transactions file for `year` and return a list of Trade objects."""
    path = get_data_path(year, TRANSACTION_FILENAME)
    if not path.exists():
        raise FileNotFoundError(f"No transactions file found for {year}: {path}")

    with open(path, encoding="utf-8") as f:
        transactions = json.load(f)

    trades = [
        Trade.from_transaction(t, year)
        for t in transactions
        # Valid = an actual trade that went through (excludes vetoed trades)
        if t["type"] == "trade" and t["status"] == "successful"
    ]
    trades.sort(key=lambda tr: tr.date)  # oldest first
    return trades


def load_roster_points(year):
    path = get_data_path(year, ROSTER_FILENAME)
    if not path.exists():
        raise FileNotFoundError(f"No roster points file found for {year}: {path}")
    with open(path, encoding="utf-8") as f:
        return json.load(f)


# --------------------------------------------------------------------------
# Core logic
# --------------------------------------------------------------------------
def get_trade_rosters(trade, year):
    """
    Returns (trader_roster, tradee_roster, trader_swapped, tradee_swapped).

    - trader_roster / tradee_roster: each team's roster in the week of the trade.
    - trader_swapped / tradee_swapped: the same rosters with the trade reversed.

    A traded player who isn't found on the team they were sent to is ignored
    completely (neither removed from one roster nor added to the other).
    """
    if not (trade.trader_team_key and trade.tradee_team_key):
        raise ValueError(
            f"Trade {trade.transaction_id} has no team keys; can't look up rosters."
        )

    weeks = load_roster_points(year)
    week_data = weeks.get(str(trade.week))
    if week_data is None:
        raise KeyError(f"Week {trade.week} not found in {ROSTER_FILENAME} for {year}.")

    keys = {trade.trader_team: trade.trader_team_key,
            trade.tradee_team: trade.tradee_team_key}

    trader_roster = list(week_data.get(trade.trader_team_key, []))
    tradee_roster = list(week_data.get(trade.tradee_team_key, []))
    rosters = {trade.trader_team: trader_roster, trade.tradee_team: tradee_roster}

    swapped = {trade.trader_team: list(trader_roster),
               trade.tradee_team: list(tradee_roster)}

    for p in trade.players:
        dest, src = p.to_team, p.from_team
        if dest not in rosters or src not in swapped:
            continue
        match = next((r for r in rosters[dest] if r["name"] == p.name), None)
        if match is None:
            continue  # pretend this player doesn't exist

        swapped[dest] = [r for r in swapped[dest] if r["name"] != p.name]
        swapped[src].append({**match, "selected_position": "BN", "swapped": True})

    return (trader_roster, tradee_roster,
            swapped[trade.trader_team], swapped[trade.tradee_team])


# --------------------------------------------------------------------------
# Printing
# --------------------------------------------------------------------------
def _print_roster(title, roster):
    print(f"\n  {title}  ({len(roster)} players)")
    print("  " + "-" * 46)
    roster = sorted(
        roster,
        key=lambda r: POSITION_ORDER.index(r["selected_position"])
        if r["selected_position"] in POSITION_ORDER else len(POSITION_ORDER),
    )
    for r in roster:
        mark = "*" if r.get("swapped") else " "
        print(f"  {mark} {r['selected_position']:<6} {r['name']:<26} {r['points']:>6.1f}")


def print_trade_rosters(trade, year):
    t_roster, o_roster, t_swapped, o_swapped = get_trade_rosters(trade, year)

    print("=" * 60)
    print(f"Trade {trade.transaction_id}  |  {trade.date[:10]}  |  Week {trade.week}")
    print(f"{trade.trader_team} <-> {trade.tradee_team}")
    for p in trade.players:
        print(f"    {p.name} ({p.position}, {p.nfl_team}): {p.from_team} -> {p.to_team}")
    print("=" * 60)

    _print_roster(f"{trade.trader_team} - actual roster", t_roster)
    _print_roster(f"{trade.trader_team} - trade reversed (* = returned)", t_swapped)
    _print_roster(f"{trade.tradee_team} - actual roster", o_roster)
    _print_roster(f"{trade.tradee_team} - trade reversed (* = returned)", o_swapped)
    print()


PROJECTIONS_DIR = Path(__file__).resolve().parent.parent / "Projections" / "SleeperProjections"

# Yahoo uses the team nickname for defenses, Sleeper uses the full name.
DEF_NAMES = {
    "Cardinals": "Arizona Cardinals", "Falcons": "Atlanta Falcons",
    "Ravens": "Baltimore Ravens", "Bills": "Buffalo Bills",
    "Panthers": "Carolina Panthers", "Bears": "Chicago Bears",
    "Bengals": "Cincinnati Bengals", "Browns": "Cleveland Browns",
    "Cowboys": "Dallas Cowboys", "Broncos": "Denver Broncos",
    "Lions": "Detroit Lions", "Packers": "Green Bay Packers",
    "Texans": "Houston Texans", "Colts": "Indianapolis Colts",
    "Jaguars": "Jacksonville Jaguars", "Chiefs": "Kansas City Chiefs",
    "Raiders": "Las Vegas Raiders", "Chargers": "Los Angeles Chargers",
    "Rams": "Los Angeles Rams", "Dolphins": "Miami Dolphins",
    "Vikings": "Minnesota Vikings", "Patriots": "New England Patriots",
    "Saints": "New Orleans Saints", "Giants": "New York Giants",
    "Jets": "New York Jets", "Eagles": "Philadelphia Eagles",
    "Steelers": "Pittsburgh Steelers", "49ers": "San Francisco 49ers",
    "Seahawks": "Seattle Seahawks", "Buccaneers": "Tampa Bay Buccaneers",
    "Titans": "Tennessee Titans", "Commanders": "Washington Commanders",
}

# Manual fixes for one-off name differences: {"Yahoo name": "Sleeper name"}
NAME_OVERRIDES = {
}

_SUFFIXES = {"jr", "sr", "ii", "iii", "iv", "v"}


# --------------------------------------------------------------------------
# Name translation
# --------------------------------------------------------------------------
def normalize_name(name):
    """Lowercase, strip accents/punctuation and generational suffixes."""
    name = unicodedata.normalize("NFKD", name).encode("ascii", "ignore").decode()
    name = re.sub(r"[.'’,]", "", name.lower()).replace("-", " ")
    parts = name.split()
    while len(parts) > 1 and parts[-1] in _SUFFIXES:
        parts.pop()
    return " ".join(parts)


def to_sleeper_name(yahoo_name):
    """Translate a Yahoo player name into the name Sleeper uses."""
    if yahoo_name in NAME_OVERRIDES:
        return NAME_OVERRIDES[yahoo_name]
    if yahoo_name in DEF_NAMES:
        return DEF_NAMES[yahoo_name]
    return yahoo_name


# --------------------------------------------------------------------------
# Sleeper data
# --------------------------------------------------------------------------
@lru_cache(maxsize=None)
def load_sleeper_week(year, week):
    """Returns (exact_index, normalized_index) for a week, or None if no file."""
    path = PROJECTIONS_DIR / str(year) / "projections" / f"week_{week:02d}.json"
    if not path.exists():
        return None
    with open(path, encoding="utf-8") as f:
        data = json.load(f)
    exact, norm = {}, {}
    for p in data.get("players", []):
        exact.setdefault(p["name"], p)
        norm.setdefault(normalize_name(p["name"]), p)
    return exact, norm


def lookup_player(name, year, week):
    idx = load_sleeper_week(year, week)
    if idx is None:
        return None
    exact, norm = idx
    sleeper_name = to_sleeper_name(name)
    return exact.get(sleeper_name) or norm.get(normalize_name(sleeper_name))


def last_finished_week(year, today=None):
    """Last week that has been completed, capped at the newest projections file."""
    start = SEASON_START[year]
    today = today or date.today()
    current_week = (today - start).days // 7 + 1
    folder = PROJECTIONS_DIR / str(year) / "projections"
    available = [int(m.group(1)) for f in folder.glob("week_*.json")
                 if (m := re.search(r"week_(\d+)", f.name))]
    if not available:
        raise FileNotFoundError(f"No projection files found in {folder}")
    return min(current_week - 1, max(available))


# --------------------------------------------------------------------------
# Per-player stats
# --------------------------------------------------------------------------
def get_player_stats(name, year, weeks):
    """Projection and points for each week. Missing player / null value -> 0."""
    per_week, found = {}, False
    for w in weeks:
        rec = lookup_player(name, year, w)
        if rec is not None:
            found = True
        rec = rec or {}
        per_week[w] = {
            "projection": rec.get("projection_ppr") or 0.0,
            "points": rec.get("pts_ppr") or 0.0,
        }
    return {
        "name": name,
        "weeks": per_week,
        "found": found,   # False = never matched a Sleeper name (check spelling)
        "total_projection": sum(v["projection"] for v in per_week.values()),
        "total_points": sum(v["points"] for v in per_week.values()),
    }


def get_trade_player_stats(trade, year, last_week=None):
    """
    Returns (trader_stats, tradee_stats, trader_swapped_stats, tradee_swapped_stats),
    each a list of per-player stat dicts covering trade.week .. last finished week.
    """
    last_week = last_week or last_finished_week(year)
    weeks = list(range(trade.week, last_week + 1))

    rosters = get_trade_rosters(trade, year)
    results = []
    for roster in rosters:
        stats = []
        for r in roster:
            s = get_player_stats(r["name"], year, weeks)
            s["position"] = r["selected_position"]
            s["swapped"] = r.get("swapped", False)
            stats.append(s)
        results.append(stats)
    return tuple(results), weeks


# --------------------------------------------------------------------------
# Printing
# --------------------------------------------------------------------------
def _print_stats(title, stats, weeks):
    print(f"\n  {title}")
    header = f"  {'':1} {'Pos':<6} {'Player':<24}" + "".join(f"{'W' + str(w):>13}" for w in weeks)
    header += f"{'Tot Proj':>10}{'Tot Pts':>9}"
    print(header)
    print(f"  {'':1} {'':<6} {'':<24}" + "".join(f"{'proj|pts':>13}" for _ in weeks))
    print("  " + "-" * (len(header) - 2))

    stats = sorted(
        stats,
        key=lambda s: POSITION_ORDER.index(s["position"])
        if s["position"] in POSITION_ORDER else len(POSITION_ORDER),
    )
    for s in stats:
        mark = "*" if s["swapped"] else ("?" if not s["found"] else " ")
        cells = "".join(
            f"{s['weeks'][w]['projection']:>6.1f}|{s['weeks'][w]['points']:<6.1f}" for w in weeks
        )
        print(f"  {mark} {s['position']:<6} {s['name']:<24}{cells}"
              f"{s['total_projection']:>10.1f}{s['total_points']:>9.1f}")

    tp = sum(s["total_projection"] for s in stats)
    tpts = sum(s["total_points"] for s in stats)
    print("  " + "-" * (len(header) - 2))
    print(f"  {'':1} {'Total':<31}{'':<{13 * len(weeks)}}{tp:>10.1f}{tpts:>9.1f}")


def print_trade_stats(trade, year, last_week=None):
    (t_stats, o_stats, t_sw, o_sw), weeks = get_trade_player_stats(trade, year, last_week)

    print("=" * 70)
    print(f"Trade {trade.transaction_id}  |  {trade.date[:10]}  |  "
          f"Weeks {weeks[0]}-{weeks[-1]}")
    print(f"{trade.trader_team} <-> {trade.tradee_team}")
    print("=" * 70)
    print("  * = player returned by the reversed trade   ? = not found in Sleeper data")

    _print_stats(f"{trade.trader_team} - actual roster", t_stats, weeks)
    _print_stats(f"{trade.trader_team} - trade reversed", t_sw, weeks)
    _print_stats(f"{trade.tradee_team} - actual roster", o_stats, weeks)
    _print_stats(f"{trade.tradee_team} - trade reversed", o_sw, weeks)
    print()


# --------------------------------------------------------------------------
# Lineup optimisation
# --------------------------------------------------------------------------
REPLACEMENT_POINTS = {"QB": 15, "RB": 5, "WR": 7, "TE": 8, "K": 8, "DEF": 5}

# (slot label, positions allowed). Fixed slots are filled before the flex.
LINEUP_SLOTS = [
    ("QB", {"QB"}),
    ("RB", {"RB"}),
    ("RB", {"RB"}),
    ("WR", {"WR"}),
    ("WR", {"WR"}),
    ("TE", {"TE"}),
    ("W/R/T", {"WR", "RB", "TE"}),
    ("K", {"K"}),
    ("DEF", {"DEF"}),
]
FLEX_LABEL = "W/R/T"
POS_MAP = {"FB": "RB"}            # Sleeper position -> lineup position
VALID_POS = set(REPLACEMENT_POINTS)


def resolve_position(stat, year, weeks):
    """Real position from Sleeper (roster file only has the lineup slot)."""
    for w in weeks:
        rec = lookup_player(stat["name"], year, w)
        if rec:
            return POS_MAP.get(rec["position"], rec["position"])
    slot = stat["position"]
    return slot if slot in VALID_POS else None   # W/R/T, BN, IR -> unknown


def build_pool(players, week):
    """Candidates for one week: real players plus unlimited replacements."""
    pool = []
    for p in players:
        if p["pos"] not in VALID_POS:
            continue  # position unknown / not startable
        wk = p["stat"]["weeks"][week]
        pool.append({"name": p["stat"]["name"], "pos": p["pos"],
                     "proj": wk["projection"], "pts": wk["points"],
                     "replacement": False})
    for pos, pts in REPLACEMENT_POINTS.items():
        for _ in range(3):  # enough copies to fill every slot at that position
            pool.append({"name": f"Replacement {pos}", "pos": pos,
                         "proj": pts, "pts": pts, "replacement": True})
    return pool


def pick_lineup(pool):
    """Highest projected lineup. A real player wins ties against replacement."""
    used = set()
    chosen = {}

    def fill(i, allowed):
        options = [(j, c) for j, c in enumerate(pool)
                   if j not in used and c["pos"] in allowed]
        j, c = max(options, key=lambda jc: (jc[1]["proj"], not jc[1]["replacement"]))
        used.add(j)
        chosen[i] = c

    for i, (label, allowed) in enumerate(LINEUP_SLOTS):
        if label != FLEX_LABEL:
            fill(i, allowed)
    for i, (label, allowed) in enumerate(LINEUP_SLOTS):
        if label == FLEX_LABEL:
            fill(i, allowed)

    return [(LINEUP_SLOTS[i][0], chosen[i]) for i in range(len(LINEUP_SLOTS))]


def simulate_roster(stats, year, weeks):
    """Start the best lineup every week. Returns one dict per week."""
    players = [{"stat": s, "pos": resolve_position(s, year, weeks)} for s in stats]
    results = []
    for w in weeks:
        lineup = pick_lineup(build_pool(players, w))
        results.append({
            "week": w,
            "lineup": lineup,
            "proj": sum(c["proj"] for _, c in lineup),
            "pts": sum(c["pts"] for _, c in lineup),
        })
    return results


# --------------------------------------------------------------------------
# Printing
# --------------------------------------------------------------------------
def _cell(c, traded):
    mark = "*" if c["name"] in traded else " "
    return f"{mark}{c['name']:<22.22}{c['proj']:>5.1f} {c['pts']:>5.1f}"


def _print_team(team, actual, reversed_, traded):
    print("\n" + "#" * 78)
    print(f"  {team}")
    print("#" * 78)
    blank = " " * 34
    for a, r in zip(actual, reversed_):
        print(f"\n  Week {a['week']}")
        print(f"  {'Slot':<6} {'ACTUAL (proj  pts)':<34}   |   REVERSED (proj  pts)")
        print("  " + "-" * 76)
        for (slot, ca), (_, cr) in zip(a["lineup"], r["lineup"]):
            print(f"  {slot:<6} {_cell(ca, traded)}   |   {_cell(cr, traded)}")
        print("  " + "-" * 76)
        print(f"  {'Total':<6} {'':<23}{a['proj']:>5.1f} {a['pts']:>5.1f}   |   "
              f"{'':<23}{r['proj']:>5.1f} {r['pts']:>5.1f}")

    print(f"\n  {team} - weekly points summary")
    print(f"  {'Week':<6}{'Actual':>9}{'Reversed':>10}{'Diff':>8}")
    print("  " + "-" * 33)
    for a, r in zip(actual, reversed_):
        print(f"  {a['week']:<6}{a['pts']:>9.1f}{r['pts']:>10.1f}{a['pts'] - r['pts']:>8.1f}")
    ta = sum(a["pts"] for a in actual)
    tr = sum(r["pts"] for r in reversed_)
    print("  " + "-" * 33)
    print(f"  {'Total':<6}{ta:>9.1f}{tr:>10.1f}{ta - tr:>8.1f}")
    return ta, tr


def print_trade_lineups(trade, year, last_week=None):
    (t_act, o_act, t_rev, o_rev), weeks = get_trade_player_stats(trade, year, last_week)
    traded = {p.name for p in trade.players}

    print("=" * 78)
    print(f"Trade {trade.transaction_id}  |  {trade.date[:10]}  |  Weeks {weeks[0]}-{weeks[-1]}")
    print(f"{trade.trader_team} <-> {trade.tradee_team}")
    for p in trade.players:
        print(f"    {p.name} ({p.position}, {p.nfl_team}): {p.from_team} -> {p.to_team}")
    print("  * = player involved in the trade")
    print("=" * 78)

    t_total = _print_team(trade.trader_team,
                          simulate_roster(t_act, year, weeks),
                          simulate_roster(t_rev, year, weeks), traded)
    o_total = _print_team(trade.tradee_team,
                          simulate_roster(o_act, year, weeks),
                          simulate_roster(o_rev, year, weeks), traded)

    print("\n" + "=" * 78)
    print("TRADE RESULT (points gained by making the trade, weeks "
          f"{weeks[0]}-{weeks[-1]})")
    print(f"  {trade.trader_team:<30}{t_total[0] - t_total[1]:>+9.1f}")
    print(f"  {trade.tradee_team:<30}{o_total[0] - o_total[1]:>+9.1f}")
    print("=" * 78 + "\n")


# --------------------------------------------------------------------------
# JSON output
# --------------------------------------------------------------------------
OUTPUT_DIR = Path(__file__).resolve().parent.parent / "Data"
OUTPUT_FILENAME = "trade_evaluation.json"


def _team_to_json(team, actual, reversed_):
    weekly = [
        {"week": a["week"], "points_gained": round(a["pts"] - r["pts"], 2)}
        for a, r in zip(actual, reversed_)
    ]
    net = sum(a["pts"] - r["pts"] for a, r in zip(actual, reversed_))
    avg = net / len(weekly) if weekly else 0.0
    return {
        "team": team,
        "weekly_points_gained": weekly,
        "net_points_gained": round(net, 2),
        "avg_points_gained_per_week": round(avg, 2),
    }


def build_trade_result(trade, year, last_week=None):
    (t_act, o_act, t_rev, o_rev), weeks = get_trade_player_stats(trade, year, last_week)

    return {
        "transaction_id": trade.transaction_id,
        "date": trade.date,
        "players": [
            {
                "name": p.name,
                "position": p.position,
                "from_team": p.from_team,
                "to_team": p.to_team,
            }
            for p in trade.players
        ],
        "managers": [
            _team_to_json(trade.trader_team,
                          simulate_roster(t_act, year, weeks),
                          simulate_roster(t_rev, year, weeks)),
            _team_to_json(trade.tradee_team,
                          simulate_roster(o_act, year, weeks),
                          simulate_roster(o_rev, year, weeks)),
        ],
    }

def write_trade_evaluations(year, last_week=None, print_results=True):
    results = []
    for trade in get_valid_trades(year):
        try:
            results.append(build_trade_result(trade, year, last_week))
            if print_results:
                print_trade_lineups(trade, year, last_week)
        except (KeyError, ValueError) as e:
            # e.g. a trade whose week is beyond the last finished week, or missing team keys
            results.append({
                "transaction_id": trade.transaction_id,
                "date": trade.date,
                "error": str(e),
            })
            if print_results:
                print(f"Trade {trade.transaction_id} skipped: {e}\n")

    out_dir = OUTPUT_DIR / str(year)
    out_dir.mkdir(parents=True, exist_ok=True)
    out_path = out_dir / OUTPUT_FILENAME
    with open(out_path, "w", encoding="utf-8") as f:
        json.dump({"year": year, "trades": results}, f, indent=2, ensure_ascii=False)
    return out_path


if __name__ == "__main__":
    YEAR = 2026
    path = write_trade_evaluations(YEAR)
    print(f"Wrote trade evaluations to {path}")