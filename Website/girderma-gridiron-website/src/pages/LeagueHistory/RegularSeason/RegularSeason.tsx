import { useEffect, useState } from 'react';
import { Year, SubTabContentProps, SubTabConfig } from '../LeagueHistory';

interface TeamStanding {
  team_key: string;
  name: string;
  rank: number | string;
  playoff_seed?: string;
  outcome_totals: {
    wins: string;
    losses: string;
    ties: number;
    percentage: string;
  };
  divisional_outcome_totals?: {
    wins: string;
    losses: string;
    ties: number;
  };
  streak: {
    type: 'win' | 'loss' | 'tie';
    value: string;
  };
  points_for: string;
  points_against: number;
}

const RegularSeason: React.FC<SubTabContentProps> = ({ year }) => {
  const [standings, setStandings] = useState<TeamStanding[] | null>(null);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    setStandings(null);
    setError(null);

    import(`../../../league_stats_output/${year}/standings.json`)
      .then((mod) => setStandings(mod.default.regular_season_standings))
      .catch(() => setError(`No standings found for ${year}.`));
  }, [year]);

  if (error) {
    return <div style={{ padding: '20px', color: '#888' }}>{error}</div>;
  }

  if (!standings) {
    return <div style={{ padding: '20px', color: '#888' }}>Loading standings…</div>;
  }

  // Sort by actual regular-season performance (win %, then points_for as tiebreak).
  // Note: the raw "rank" field in this data is NOT sorted by record — it's some
  // other Yahoo ordering — so we can't just sort by it.
  const sorted = [...standings].sort((a, b) => {
    const pctA = parseFloat(a.outcome_totals.percentage);
    const pctB = parseFloat(b.outcome_totals.percentage);
    if (pctB !== pctA) return pctB - pctA;
    return parseFloat(b.points_for) - parseFloat(a.points_for);
  });

  const hasDivisions = sorted.some((t) => t.divisional_outcome_totals);

  return (
    <div style={{ padding: '20px' }}>
      <i>*Note: Divisions not displayed for 2023 and 2024. Will be updated in future</i>
      <h3 style={{ marginBottom: '16px' }}> Regular Season Standings — {year}</h3>

      <div style={{ overflowX: 'auto' }}>
        <table style={{ width: '100%', borderCollapse: 'collapse', fontSize: '14px', fontFamily: 'inherit' }}>
          <thead>
            <tr style={{ borderBottom: '2px solid #ddd', textAlign: 'left' }}>
              <th style={thStyle}>#</th>
              <th style={thStyle}>Team</th>
              <th style={thStyle}>Record</th>
              <th style={thStyle}>Pct</th>
              {hasDivisions && <th style={thStyle}>Div</th>}
              <th style={thStyle}>Streak</th>
              <th style={thStyle}>PF</th>
              <th style={thStyle}>PA</th>
              <th style={thStyle}>Seed</th>
            </tr>
          </thead>
          <tbody>
            {sorted.map((team, index) => {
              const seedNum = team.playoff_seed ? parseInt(team.playoff_seed, 10) : null;
              const isPlayoffSeed = seedNum !== null && seedNum <= 6;
              return (
                <tr
                  key={team.team_key}
                  style={{
                    borderBottom: '1px solid #eee',
                    backgroundColor: isPlayoffSeed ? '#f7faf7' : 'transparent',
                  }}
                >
                  <td style={tdStyle}>{index + 1}</td>
                  <td style={{ ...tdStyle, fontWeight: 600 }}>{team.name}</td>
                  <td style={tdStyle}>
                    {team.outcome_totals.wins}-{team.outcome_totals.losses}
                    {Number(team.outcome_totals.ties) > 0 ? `-${team.outcome_totals.ties}` : ''}
                  </td>
                  <td style={tdStyle}>{team.outcome_totals.percentage}</td>
                  {hasDivisions && (
                    <td style={tdStyle}>
                      {team.divisional_outcome_totals
                        ? `${team.divisional_outcome_totals.wins}-${team.divisional_outcome_totals.losses}`
                        : '—'}
                    </td>
                  )}
                  <td style={tdStyle}>
                    <span
                      style={{
                        color: team.streak.type === 'win' ? '#2a8a4a' : '#c0392b',
                        fontWeight: 600,
                      }}
                    >
                      {team.streak.type === 'win' ? 'W' : 'L'}
                      {team.streak.value}
                    </span>
                  </td>
                  <td style={tdStyle}>{parseFloat(team.points_for).toFixed(2)}</td>
                  <td style={tdStyle}>{team.points_against.toFixed(2)}</td>
                  <td style={tdStyle}>{team.playoff_seed ?? '—'}</td>
                </tr>
              );
            })}
          </tbody>
        </table>
      </div>

      <p style={{ marginTop: '12px', fontSize: '12px', color: '#999' }}>
        Shaded rows indicate a playoff seed (top 6). Sorted by regular-season win percentage.
      </p>
    </div>
  );
};

const thStyle: React.CSSProperties = {
  padding: '8px 12px',
  fontSize: '12px',
  textTransform: 'uppercase',
  letterSpacing: '0.03em',
  color: '#666',
};

const tdStyle: React.CSSProperties = { padding: '8px 12px' };

export default RegularSeason;
