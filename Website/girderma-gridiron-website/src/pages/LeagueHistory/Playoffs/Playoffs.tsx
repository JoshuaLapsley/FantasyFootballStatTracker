import { Year, SubTabContentProps, SubTabConfig } from '../LeagueHistory';

const Playoffs: React.FC<SubTabContentProps> = ({ year }) => {
  return (
    <div style={{ padding: '20px' }}>
      <h3>Playoffs — {year}</h3>
      <p>Playoffs content for {year} goes here.</p>
    </div>
  );
};

export default Playoffs;