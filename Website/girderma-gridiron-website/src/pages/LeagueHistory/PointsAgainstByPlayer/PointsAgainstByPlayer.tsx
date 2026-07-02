import React, { useMemo, useState } from 'react';
import '@syncfusion/ej2-base/styles/material.css';
import '@syncfusion/ej2-inputs/styles/material.css';
import '@syncfusion/ej2-popups/styles/material.css';
import '@syncfusion/ej2-dropdowns/styles/material.css';

// Hardcoded so webpack can statically resolve each import.
// If you add/remove a player, add/remove a line here too.
const PLAYERS: { name: string; path: string }[] = [
  { name: 'Andrew', path: require('../../../league_stats_output/histograms/pointsAgainst/Andrew_points_against.png') },
  { name: 'Ben', path: require('../../../league_stats_output/histograms/pointsAgainst/Ben_points_against.png') },
  { name: 'Caleb', path: require('../../../league_stats_output/histograms/pointsAgainst/Caleb_points_against.png') },
  { name: 'Connor', path: require('../../../league_stats_output/histograms/pointsAgainst/Connor_points_against.png') },
  { name: 'DJ', path: require('../../../league_stats_output/histograms/pointsAgainst/DJ_points_against.png') },
  { name: 'Gavin Brodie', path: require('../../../league_stats_output/histograms/pointsAgainst/Gavin_Brodie_points_against.png') },
  { name: 'Hunter', path: require('../../../league_stats_output/histograms/pointsAgainst/Hunter_points_against.png') },
  { name: 'Jackson', path: require('../../../league_stats_output/histograms/pointsAgainst/Jackson_points_against.png') },
  { name: 'Josh Rubik', path: require('../../../league_stats_output/histograms/pointsAgainst/Josh_Rubik_points_against.png') },
  { name: 'Josh Sage', path: require('../../../league_stats_output/histograms/pointsAgainst/Josh_Sage_points_against.png') },
  { name: 'Levi', path: require('../../../league_stats_output/histograms/pointsAgainst/Levi_points_against.png') },
  { name: 'Nate', path: require('../../../league_stats_output/histograms/pointsAgainst/Nate_points_against.png') },
  { name: 'Sam Girder', path: require('../../../league_stats_output/histograms/pointsAgainst/Sam_Girder_points_against.png') },
  { name: 'Sam Paddy', path: require('../../../league_stats_output/histograms/pointsAgainst/Sam_Paddy_points_against.png') },
  { name: 'Zach', path: require('../../../league_stats_output/histograms/pointsAgainst/Zach_points_against.png') },
];

const PointsAgainstByPlayer: React.FC = () => {
  const [selectedName, setSelectedName] = useState<string | null>(PLAYERS[0]?.name ?? null);

  const selectedPlayer = useMemo(
    () => PLAYERS.find((p) => p.name === selectedName) ?? null,
    [selectedName]
  );

  return (
    <div style={{ padding: '20px' }}>
      <h3>Points Against By Player</h3>

      <select
        value={selectedName ?? ''}
        onChange={(e) => setSelectedName(e.target.value)}
        style={{
          maxWidth: '300px',
          marginBottom: '20px',
          padding: '8px 12px',
          fontSize: '14px',
          borderRadius: '4px',
          border: '1px solid #ccc',
          display: 'block',
        }}
      >
        {PLAYERS.map((p) => (
          <option key={p.name} value={p.name}>
            {p.name}
          </option>
        ))}
      </select>

      {selectedPlayer ? (
        <img
          src={selectedPlayer.path}
          alt={`${selectedPlayer.name} Points Against`}
          style={{ maxWidth: '100%', height: 'auto' }}
        />
      ) : (
        <p>No points against chart available.</p>
      )}
    </div>
  );
};

export default PointsAgainstByPlayer;
