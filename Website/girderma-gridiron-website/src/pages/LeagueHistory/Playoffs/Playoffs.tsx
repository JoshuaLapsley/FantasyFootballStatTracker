import { useState } from 'react';
import { SubTabContentProps } from '../LeagueHistory';
import './Playoffs.css';

const Playoffs: React.FC<SubTabContentProps> = ({ year }) => {
  const [view, setView] = useState<string>('winners');

  let imageSrc: string | null = null;
  try {
    imageSrc = require(`../../../league_stats_output/${year}/playoffs_${year}_${view}.jpg`);
  } catch {
    imageSrc = null;
  }

  return (
    <div style={{ padding: '20px' }}>
      <h3>Playoffs — {year}</h3>
      <div className="toggle-group">
        <button
          onClick={() => setView('winners')}
          className={`toggle-btn ${view === 'winners' ? 'toggle-btn-active' : ''}`}
        >
          Winner's Bracket
        </button>
        <button
          onClick={() => setView('losers')}
          className={`toggle-btn ${view === 'losers' ? 'toggle-btn-active' : ''}`}
        >
          Loser's Bracket
        </button>
      </div>

      {imageSrc ? (
        <img
          src={imageSrc}
          alt={`${view} bracket`}
          style={{ maxWidth: '100%', height: 'auto' }}
        />
      ) : (
        <p>No bracket chart available.</p>
      )}
    </div>
  );
};

export default Playoffs;