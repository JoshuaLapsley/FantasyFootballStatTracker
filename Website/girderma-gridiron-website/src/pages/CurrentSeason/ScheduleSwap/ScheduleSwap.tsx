import React, { useMemo } from 'react';

import './ScheduleSwap.css';

export type WLT = { wins: number; losses: number; ties: number };

export type TeamEntry = {
  team_key: string;
  vs_schedule_of: Record<string, WLT>;
};

/** Shape of the JSON written by schedule_swap.py */
export type ScheduleData = Record<string, TeamEntry>;

let data: ScheduleData = {};
try {
  data = require('../../../league_stats_output/CurrentSeason/StrengthOfSchedule.json');
} catch {
  data = {};
}

const winPct = (r: WLT) => {
  const games = r.wins + r.losses + r.ties;
  return games === 0 ? 0 : (r.wins + r.ties / 2) / games;
};

const formatRecord = (r: WLT) =>
  r.ties > 0 ? `${r.wins}-${r.losses}-${r.ties}` : `${r.wins}-${r.losses}`;

const EPSILON = 1e-9;

/** Compare a swapped record to the team's actual record. */
const outcome = (rec: WLT, actual: WLT): 'better' | 'worse' | 'same' => {
  const diff = winPct(rec) - winPct(actual);
  if (diff > EPSILON) return 'better';
  if (diff < -EPSILON) return 'worse';
  return 'same';
};

const ScheduleSwap: React.FC = () => {
  const { teams, avgWinsByTeam, avgWinsBySchedule } = useMemo(() => {
    // Order teams (rows and columns) by their actual record, best first
    const names = Object.keys(data).sort((a, b) => {
      const ra = data[a].vs_schedule_of[a];
      const rb = data[b].vs_schedule_of[b];
      return winPct(rb) - winPct(ra) || rb.wins - ra.wins;
    });

    const avg = (records: WLT[]) =>
      records.reduce((sum, r) => sum + r.wins + r.ties / 2, 0) / (records.length || 1);

    // Row average: one team across every schedule
    const byTeam: Record<string, number> = {};
    // Column average: every team on one schedule
    const bySchedule: Record<string, number> = {};

    for (const t of names) {
      byTeam[t] = avg(names.map((s) => data[t].vs_schedule_of[s]).filter(Boolean));
    }
    for (const s of names) {
      bySchedule[s] = avg(names.map((t) => data[t].vs_schedule_of[s]).filter(Boolean));
    }

    return { teams: names, avgWinsByTeam: byTeam, avgWinsBySchedule: bySchedule };
  }, []);

  if (teams.length === 0) {
    return <p className="sm-empty">No matchup data found. Run schedule_swap.py to generate it.</p>;
  }

  return (
    <section className="sm">
      <header className="sm-head">
        <h2 className="sm-title">Schedule swap</h2>
        <p className="sm-sub">
          Each row is a team. Each column is a schedule it could have played.
          Outlined cells are actual records.
        </p>
      </header>

      <ul className="sm-legend" aria-label="Color key">
        <li>
          <span className="sm-swatch is-better" aria-hidden="true" />
          Better than actual
        </li>
        <li>
          <span className="sm-swatch is-same" aria-hidden="true" />
          Same as actual
        </li>
        <li>
          <span className="sm-swatch is-worse" aria-hidden="true" />
          Worse than actual
        </li>
      </ul>

      <div className="sm-scroll" role="region" aria-label="Schedule swap records" tabIndex={0}>
        <table className="sm-table">
          <thead>
            <tr>
              <th className="sm-corner" scope="col">
                Team
              </th>
              {teams.map((col) => (
                <th key={col} scope="col" className="sm-colhead" title={`${col}’s schedule`}>
                  <span>{col}</span>
                </th>
              ))}
              <th className="sm-avghead" scope="col">
                <span>Avg wins</span>
              </th>
            </tr>
          </thead>
          <tbody>
            {teams.map((row) => (
              <tr key={row}>
                <th scope="row" className="sm-rowhead" title={row}>
                  {row}
                </th>
                {teams.map((col) => {
                  const rec = data[row].vs_schedule_of[col];
                  if (!rec) return <td key={col} className="sm-cell sm-empty-cell">–</td>;

                  const kind = outcome(rec, data[row].vs_schedule_of[row]);
                  const classes = ['sm-cell', `is-${kind}`];
                  if (row === col) classes.push('is-own');

                  return (
                    <td
                      key={col}
                      className={classes.join(' ')}
                      title={`${row} with ${col}’s schedule: ${formatRecord(rec)}`}
                    >
                      {formatRecord(rec)}
                    </td>
                  );
                })}
                <td className="sm-avg">{avgWinsByTeam[row].toFixed(1)}</td>
              </tr>
            ))}
          </tbody>
          <tfoot>
            <tr>
              <th scope="row" className="sm-rowhead sm-foothead">
                Avg wins
              </th>
              {teams.map((col) => (
                <td key={col} className="sm-avg sm-footcell">
                  {avgWinsBySchedule[col].toFixed(1)}
                </td>
              ))}
              <td className="sm-footcell sm-footcorner" />
            </tr>
          </tfoot>
        </table>
      </div>
    </section>
  );
};

export default ScheduleSwap;
