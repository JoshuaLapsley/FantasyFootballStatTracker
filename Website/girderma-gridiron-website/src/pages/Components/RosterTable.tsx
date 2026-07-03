import { useEffect, useMemo, useState } from 'react';
import { Year } from '../LeagueHistory/LeagueHistory';

interface RosterPlayer {
  player_id: number;
  name: string;
  editorial_team_abbr: string;
  position_type: string;
  eligible_positions: string[];
  status: string;
  selected_position: string;
}

type RostersData = Record<string, Record<string, RosterPlayer[]>>;

function statusColor(status: string): string {
  switch (status) {
    case 'Q':
      return '#c9820a';
    case 'NA':
    case 'DNR':
      return '#c0392b';
    case 'IR':
      return '#c0392b';
    default:
      return 'transparent';
  }
}

interface RosterTableProps {
  team: string;
  year: Year;
  week: 'first' | 'last';
}

const RosterTable: React.FC<RosterTableProps> = ({ team, year, week }) => {
  const [data, setData] = useState<RostersData | null>(null);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    setData(null);
    setError(null);

    import(`../../league_stats_output/${year}/rosters_first_last_week.json`)
      .then((mod) => setData(mod.default))
      .catch(() => setError(`No roster data found for ${year}.`));
  }, [year]);

  const { roster, weekLabel } = useMemo(() => {
    if (!data || !data[team]) {
      return { roster: [] as RosterPlayer[], weekLabel: '' };
    }

    const weekKeys = Object.keys(data[team])
      .map((key) => {
        const match = key.match(/^week_(\d+)_roster$/);
        return match ? { key, week: parseInt(match[1], 10) } : null;
      })
      .filter((x): x is { key: string; week: number } => x !== null)
      .sort((a, b) => a.week - b.week);

    const target = week === 'first' ? weekKeys[0] : weekKeys[weekKeys.length - 1];

    return {
      roster: target ? data[team][target.key] : [],
      weekLabel: target ? `Week ${target.week}` : '',
    };
  }, [data, team, week]);

  if (error) {
    return <div style={{ padding: '20px', color: '#888' }}>{error}</div>;
  }

  if (!data) {
    return <div style={{ padding: '20px', color: '#888' }}>Loading roster…</div>;
  }

  return (
    <div>
      <h4 style={{ marginBottom: '10px', fontSize: '15px', color: '#333' }}>
        {weekLabel || (week === 'first' ? 'First Week' : 'Last Week')}
      </h4>
      <table style={{ width: '100%', borderCollapse: 'collapse', fontSize: '13px' }}>
        <thead>
          <tr style={{ borderBottom: '2px solid #ddd', textAlign: 'left' }}>
            <th style={thStyle}>Slot</th>
            <th style={thStyle}>Player</th>
            <th style={thStyle}>Team</th>
          </tr>
        </thead>
        <tbody>
          {roster.map((player) => (
            <tr key={player.player_id} style={{ borderBottom: '1px solid #eee' }}>
              <td style={{ ...tdStyle, fontWeight: 600, color: '#666' }}>
                {player.selected_position}
              </td>
              <td style={tdStyle}>
                {player.name}
                {player.status && (
                  <span
                    style={{
                      marginLeft: '6px',
                      fontSize: '11px',
                      fontWeight: 700,
                      color: statusColor(player.status),
                    }}
                  >
                    {player.status}
                  </span>
                )}
              </td>
              <td style={{ ...tdStyle, color: '#888' }}>{player.editorial_team_abbr}</td>
            </tr>
          ))}
        </tbody>
      </table>
    </div>
  );
};

const thStyle: React.CSSProperties = {
  padding: '6px 10px',
  fontSize: '11px',
  textTransform: 'uppercase',
  letterSpacing: '0.03em',
  color: '#666',
};

const tdStyle: React.CSSProperties = { padding: '6px 10px' };

export default RosterTable;