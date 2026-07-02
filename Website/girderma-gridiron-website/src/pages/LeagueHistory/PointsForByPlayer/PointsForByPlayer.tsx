import React, { useMemo, useState } from 'react';
import '@syncfusion/ej2-base/styles/material.css';
import '@syncfusion/ej2-inputs/styles/material.css';
import '@syncfusion/ej2-popups/styles/material.css';
import '@syncfusion/ej2-dropdowns/styles/material.css';

// Hardcoded so webpack can statically resolve each import.
// If you add/remove a player, add/remove a line here too.
const PLAYERS: { name: string; path: string }[] = [
  { name: 'Andrew', path: require('../../../league_stats_output/histograms/pointsFor/Andrew_points_for.png') },
  { name: 'Ben', path: require('../../../league_stats_output/histograms/pointsFor/Ben_points_for.png') },
  { name: 'Caleb', path: require('../../../league_stats_output/histograms/pointsFor/Caleb_points_for.png') },
  { name: 'Connor', path: require('../../../league_stats_output/histograms/pointsFor/Connor_points_for.png') },
  { name: 'DJ', path: require('../../../league_stats_output/histograms/pointsFor/DJ_points_for.png') },
  { name: 'Gavin Brodie', path: require('../../../league_stats_output/histograms/pointsFor/Gavin_Brodie_points_for.png') },
  { name: 'Hunter', path: require('../../../league_stats_output/histograms/pointsFor/Hunter_points_for.png') },
  { name: 'Jackson', path: require('../../../league_stats_output/histograms/pointsFor/Jackson_points_for.png') },
  { name: 'Josh Rubik', path: require('../../../league_stats_output/histograms/pointsFor/Josh_Rubik_points_for.png') },
  { name: 'Josh Sage', path: require('../../../league_stats_output/histograms/pointsFor/Josh_Sage_points_for.png') },
  { name: 'Levi', path: require('../../../league_stats_output/histograms/pointsFor/Levi_points_for.png') },
  { name: 'Nate', path: require('../../../league_stats_output/histograms/pointsFor/Nate_points_for.png') },
  { name: 'Sam Girder', path: require('../../../league_stats_output/histograms/pointsFor/Sam_Girder_points_for.png') },
  { name: 'Sam Paddy', path: require('../../../league_stats_output/histograms/pointsFor/Sam_Paddy_points_for.png') },
  { name: 'Zach', path: require('../../../league_stats_output/histograms/pointsFor/Zach_points_for.png') },
];

const PointsForByPlayer: React.FC = () => {
  const [selectedName, setSelectedName] = useState<string | null>(PLAYERS[0]?.name ?? null);

  const selectedPlayer = useMemo(
    () => PLAYERS.find((p) => p.name === selectedName) ?? null,
    [selectedName]
  );

  return (
    <div style={{ padding: '20px' }}>
      <h3>Points For By Player</h3>

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
          alt={`${selectedPlayer.name} Points For`}
          style={{ maxWidth: '100%', height: 'auto' }}
        />
      ) : (
        <p>No points for chart available.</p>
      )}
    </div>
  );
};

export default PointsForByPlayer;
