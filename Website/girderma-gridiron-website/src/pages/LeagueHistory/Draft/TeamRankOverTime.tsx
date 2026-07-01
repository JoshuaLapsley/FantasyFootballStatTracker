import { Year, SubTabContentProps, SubTabConfig } from '../LeagueHistory';


const Draft: React.FC<SubTabContentProps> = ({ year }) => {
  return (
    <div style={{ padding: '20px' }}>
      <h3>Draft — {year}</h3>
      <p>Chart or table content for {year} goes here.</p>
    </div>
  );
};

export default Draft;