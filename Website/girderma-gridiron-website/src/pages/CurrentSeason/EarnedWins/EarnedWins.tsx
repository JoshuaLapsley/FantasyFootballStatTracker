import React, { useMemo, useState } from 'react';
import './EarnedWins.css';

import earnedWinsData from '../../../league_stats_output/CurrentSeason/EarnedWins.json';

interface EarnedWinData {
  Team: string;
  'Earned Wins': number;
  'Actual Wins': number;
  Difference: number;
  'Points For': number;
  'Points Against': number;
  'Difference Rank': number;
}

type SortKey = keyof EarnedWinData;
type SortDirection = 'asc' | 'desc';

const columns: { key: SortKey; label: string }[] = [
  { key: 'Difference Rank', label: 'Luckiness Rank' },
  { key: 'Team', label: 'Team' },
  { key: 'Earned Wins', label: 'Earned Wins' },
  { key: 'Actual Wins', label: 'Actual Wins' },
  { key: 'Difference', label: 'Difference' },
  { key: 'Points For', label: 'Points For' },
  { key: 'Points Against', label: 'Points Against' },
];

const EarnedWins: React.FC = () => {
  const [sortKey, setSortKey] = useState<SortKey>('Earned Wins');
  const [sortDir, setSortDir] = useState<SortDirection>('desc');

  const handleSort = (key: SortKey) => {
    if (key === sortKey) {
      setSortDir((d) => (d === 'asc' ? 'desc' : 'asc'));
    } else {
      setSortKey(key);
      // Text sorts A-Z first, numbers start highest-first
      setSortDir(key === 'Team' ? 'asc' : 'desc');
    }
  };

  const data = useMemo(() => {
    return [...(earnedWinsData as EarnedWinData[])].sort((a, b) => {
      const av = a[sortKey];
      const bv = b[sortKey];

      const result =
        typeof av === 'string' && typeof bv === 'string'
          ? av.localeCompare(bv)
          : (av as number) - (bv as number);

      return sortDir === 'asc' ? result : -result;
    });
  }, [sortKey, sortDir]);

  // Builds a cell's class list, adding "sorted-col" for the active column
  const cellClass = (key: SortKey, extra = '') =>
    [extra, sortKey === key ? 'sorted-col' : ''].filter(Boolean).join(' ');

  const differenceClass = (value: number) =>
    value > 0
      ? 'difference-positive'
      : value < 0
        ? 'difference-negative'
        : 'difference-neutral';

  return (
    <div className="earned-wins-container">
      <div className="earned-wins-header">
        <h3>Earned Wins</h3>
        <p>
          EW is the average number of wins your team would have if we ran the season over and over again with completely randomized weekly matchups each time. It’s essentially a strength-of-schedule-free metric to track a team’s performance.
        </p>
      </div>

      <div className="earned-wins-table-wrapper">
        <table className="earned-wins-table">
          <thead>
            <tr>
              {columns.map((col) => (
                <th
                  key={col.key}
                  className={cellClass(col.key, 'sortable-header')}
                  onClick={() => handleSort(col.key)}
                  aria-sort={
                    sortKey === col.key
                      ? sortDir === 'asc'
                        ? 'ascending'
                        : 'descending'
                      : 'none'
                  }
                >
                  {col.label}
                  <span className="sort-indicator">
                    {sortKey === col.key ? (sortDir === 'asc' ? ' ▲' : ' ▼') : ''}
                  </span>
                </th>
              ))}
            </tr>
          </thead>

          <tbody>
            {data.map((team) => (
              <tr key={team.Team}>
                <td className={cellClass('Difference Rank', 'rank-cell')}>
                  {team['Difference Rank']}
                </td>
                <td className={cellClass('Team', 'team-cell')}>{team.Team}</td>
                <td className={cellClass('Earned Wins')}>
                  {team['Earned Wins'].toFixed(2)}
                </td>
                <td className={cellClass('Actual Wins')}>
                  {team['Actual Wins']}
                </td>
                <td
                  className={cellClass(
                    'Difference',
                    differenceClass(team.Difference)
                  )}
                >
                  {team.Difference > 0 ? '+' : ''}
                  {team.Difference.toFixed(2)}
                </td>
                <td className={cellClass('Points For')}>
                  {team['Points For'].toFixed(2)}
                </td>
                <td className={cellClass('Points Against')}>
                  {team['Points Against'].toFixed(2)}
                </td>
              </tr>
            ))}
          </tbody>
        </table>
      </div>
    </div>
  );
};

export default EarnedWins;