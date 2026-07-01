import { Year, SubTabContentProps, SubTabConfig } from '../LeagueHistory';


const TeamRankOverTime: React.FC<SubTabContentProps> = ({ year }) => {
  return (
    <div style={{ padding: '20px' }}>
      <h3>Team Rank over Time — {year}</h3>
      <p>Chart or table content for {year} goes here.</p>
    </div>
  );
};

export default TeamRankOverTime;