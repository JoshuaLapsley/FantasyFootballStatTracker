import { useEffect, useMemo, useState } from 'react';
import { Year, SubTabContentProps, SubTabConfig } from '../LeagueHistory';

interface RosterPlayer {
  player_id: number;
  name: string;
  editorial_team_abbr: string;
  position_type: string;
  eligible_positions: string[];
  status: string;
  selected_position: string;
}

// Data is keyed by team name -> { week_X_roster: [...], week_Y_roster: [...] }
type RostersData = Record<string, Record<string, RosterPlayer[]>>;

const STARTING_SLOT_ORDER = ['QB', 'WR', 'RB', 'TE', 'W/R/T', 'BN', 'IR'];

function slotSortValue(slot: string): number {
  const idx = STARTING_SLOT_ORDER.indexOf(slot);
  return idx === -1 ? STARTING_SLOT_ORDER.length : idx;
}

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

const Rosters: React.FC<SubTabContentProps> = ({ year }) => {
  const [data, setData] = useState<RostersData | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [selectedTeam, setSelectedTeam] = useState<string | null>(null);

  useEffect(() => {
    setData(null);
    setError(null);
    setSelectedTeam(null);

    import(`../../../league_stats_output/${year}/rosters_first_last_week.json`)
      .then((mod) => {
        setData(mod.default);
        const firstTeam = Object.keys(mod.default)[0];
        setSelectedTeam(firstTeam ?? null);
      })
      .catch(() => setError(`No roster data found for ${year}.`));
  }, [year]);

  const teamNames = useMemo(() => (data ? Object.keys(data) : []), [data]);

  // Figure out the first/last week roster keys for the selected team
  // (key names like "week_1_roster", "week_17_roster" vary by season length)
  const { firstKey, lastKey, firstWeekLabel, lastWeekLabel } = useMemo(() => {
    if (!data || !selectedTeam) {
      return { firstKey: null, lastKey: null, firstWeekLabel: '', lastWeekLabel: '' };
    }
    const weekKeys = Object.keys(data[selectedTeam])
      .map((key) => {
        const match = key.match(/^week_(\d+)_roster$/);
        return match ? { key, week: parseInt(match[1], 10) } : null;
      })
      .filter((x): x is { key: string; week: number } => x !== null)
      .sort((a, b) => a.week - b.week);

    const first = weekKeys[0];
    const last = weekKeys[weekKeys.length - 1];

    return {
      firstKey: first?.key ?? null,
      lastKey: last?.key ?? null,
      firstWeekLabel: first ? `Week ${first.week}` : '',
      lastWeekLabel: last ? `Week ${last.week}` : '',
    };
  }, [data, selectedTeam]);

  if (error) {
    return <div style={{ padding: '20px', color: '#888' }}>{error}</div>;
  }

  if (!data || !selectedTeam) {
    return <div style={{ padding: '20px', color: '#888' }}>Loading rosters…</div>;
  }

  const firstRoster = firstKey ? data[selectedTeam][firstKey] : [];
  const lastRoster = lastKey ? data[selectedTeam][lastKey] : [];

  return (
    <div style={{ padding: '20px' }}>
      <h3 style={{ marginBottom: '16px' }}>Rosters — {year}</h3>

      <div style={{ marginBottom: '20px' }}>
        <select
          value={selectedTeam}
          onChange={(e) => setSelectedTeam(e.target.value)}
          style={{
            padding: '8px 12px',
            fontSize: '14px',
            borderRadius: '6px',
            border: '1px solid #ccc',
          }}
        >
          {teamNames.map((name) => (
            <option key={name} value={name}>
              {name}
            </option>
          ))}
        </select>
      </div>

      <div
        style={{
          display: 'grid',
          gridTemplateColumns: '1fr 1fr',
          gap: '24px',
        }}
      >
        <RosterTable title={firstWeekLabel || 'First Week'} roster={firstRoster} />
        <RosterTable title={lastWeekLabel || 'Last Week'} roster={lastRoster} />
      </div>
    </div>
  );
};

const RosterTable: React.FC<{ title: string; roster: RosterPlayer[] }> = ({ title, roster }) => {
  return (
    <div>
      <h4 style={{ marginBottom: '10px', fontSize: '15px', color: '#333' }}>{title}</h4>
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

export default Rosters;
