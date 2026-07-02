import { Year, SubTabContentProps, SubTabConfig } from '../LeagueHistory';

const TeamRankOverTime: React.FC<SubTabContentProps> = ({ year }) => {

  let imageSrc: string | null = null;
  try {
    imageSrc = require(`../../../league_stats_output/${year}/bump_chart.jpg`);
  } catch {
    imageSrc = null;
  }

  return (
    <div style={{ padding: '20px' }}>
      <h3>Team Rank over Time — {year}</h3>
      {imageSrc ? (
        <img
          src={imageSrc}
          alt={`Team rank bump chart for ${year}`}
          style={{ maxWidth: '100%', height: 'auto' }}
        />
      ) : (
        <p>No bump chart available for {year}.</p>
      )}
    </div>
  );
};

export default TeamRankOverTime;