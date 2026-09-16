import React from 'react';
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

const EarnedWins: React.FC = () => {
  const data = [...(earnedWinsData as EarnedWinData[])].sort(
    (a, b) => b['Earned Wins'] - a['Earned Wins']
  );

  return (
    <div className="earned-wins-container">
      <div className="earned-wins-header">
        <h3>Earned Wins</h3>
        <p>
          Comparison between expected wins based on performance and actual wins.
        </p>
      </div>

      <div className="earned-wins-table-wrapper">
        <table className="earned-wins-table">
          <thead>
            <tr>
              <th>Luckiness Rank</th>
              <th>Team</th>
              <th>Earned Wins</th>
              <th>Actual Wins</th>
              <th>Difference</th>
              <th>Points For</th>
              <th>Points Against</th>
            </tr>
          </thead>

          <tbody>
            {data.map((team) => (
              <tr key={team.Team}>
                <td className="rank-cell">
                  {team['Difference Rank']}
                </td>

                <td className="team-cell">
                  {team.Team}
                </td>

                <td>
                  {team['Earned Wins'].toFixed(2)}
                </td>

                <td>
                  {team['Actual Wins']}
                </td>

                <td
                  className={
                    team.Difference > 0
                      ? 'difference-positive'
                      : team.Difference < 0
                        ? 'difference-negative'
                        : 'difference-neutral'
                  }
                >
                  {team.Difference > 0 ? '+' : ''}
                  {team.Difference.toFixed(2)}
                </td>

                <td>
                  {team['Points For'].toFixed(2)}
                </td>

                <td>
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

