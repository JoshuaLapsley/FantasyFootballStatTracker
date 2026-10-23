import React, { useMemo, useState } from 'react';
import './EarnedWinsPlus.css';

import earnedWinsPlusData from '../../../league_stats_output/CurrentSeason/EarnedWinsPlus.json';

interface EarnedWinsPlusData {
  Team: string;
  'Earned Wins Plus': number;
  'Points For (K/DEF excluded)': number;
  'Earned Wins Plus Rank': number;
}

type SortKey = keyof EarnedWinsPlusData;
type SortDirection = 'asc' | 'desc';

const columns: { key: SortKey; label: string }[] = [
  { key: 'Earned Wins Plus Rank', label: 'Rank' },
  { key: 'Team', label: 'Team' },
  { key: 'Earned Wins Plus', label: 'Earned Wins Plus' },
  { key: 'Points For (K/DEF excluded)', label: 'Points For (K/DEF excluded)' },
];

const EarnedWinsPlus: React.FC = () => {
  const [sortKey, setSortKey] = useState<SortKey>('Earned Wins Plus');
  const [sortDir, setSortDir] = useState<SortDirection>('desc');

  const handleSort = (key: SortKey) => {
    if (key === sortKey) {
      setSortDir((d) => (d === 'asc' ? 'desc' : 'asc'));
    } else {
      setSortKey(key);
      // Team A-Z and rank 1-14 start ascending, other numbers start highest-first
      setSortDir(
        key === 'Team' || key === 'Earned Wins Plus Rank' ? 'asc' : 'desc'
      );
    }
  };

  const data = useMemo(() => {
    return [...(earnedWinsPlusData as EarnedWinsPlusData[])].sort((a, b) => {
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

  return (
    <div className="earned-wins-plus-container">
      <div className="earned-wins-plus-header">
        <h3>Earned Wins Plus</h3>
        <p>
          EW+ starts by removing each team's K/DEF points, since those are mostly noise (Brandon Aubrey drafters can disagree). Then, for each week, every team is compared pairwise against each of the other 13 teams: the win probability for team i against team j is calculated, where σ ≈ 29 is the standard deviation of the score margin between two teams, calibrated empirically from our league's historical (K/DEF-excluded) team scores. A team's EW+ for the week is the average of those 13 pairwise win probabilities; and then we sum this up over a full season. It gives a deeper picture than EW because it accounts for the fact that beating a team by 20 points tells us more about the relative strengths of the teams than beating a team by 1 point does. Levi thinks this is the best all-in-one metric for a team’s fantasy performance so far.

        </p>
      </div>

      <div className="earned-wins-plus-table-wrapper">
        <table className="earned-wins-plus-table">
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
                <td className={cellClass('Earned Wins Plus Rank', 'rank-cell')}>
                  {team['Earned Wins Plus Rank']}
                </td>
                <td className={cellClass('Team', 'team-cell')}>{team.Team}</td>
                <td className={cellClass('Earned Wins Plus')}>
                  {team['Earned Wins Plus'].toFixed(4)}
                </td>
                <td className={cellClass('Points For (K/DEF excluded)')}>
                  {team['Points For (K/DEF excluded)'].toFixed(2)}
                </td>
              </tr>
            ))}
          </tbody>
        </table>
      </div>
    </div>
  );
};

export default EarnedWinsPlus;