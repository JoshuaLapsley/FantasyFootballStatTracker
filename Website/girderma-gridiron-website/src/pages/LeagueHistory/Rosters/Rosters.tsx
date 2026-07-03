import { useEffect, useMemo, useState } from 'react';
import { SubTabContentProps } from '../LeagueHistory';
import RosterTable from '../../Components/RosterTable';

type RostersData = Record<string, Record<string, unknown>>;

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

  if (error) {
    return <div style={{ padding: '20px', color: '#888' }}>{error}</div>;
  }

  if (!data || !selectedTeam) {
    return <div style={{ padding: '20px', color: '#888' }}>Loading rosters…</div>;
  }

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

      <div style={{ display: 'grid', gridTemplateColumns: '1fr 1fr', gap: '24px' }}>
        <RosterTable team={selectedTeam} year={year} week="first" />
        <RosterTable team={selectedTeam} year={year} week="last" />
      </div>
    </div>
  );
};

export default Rosters;