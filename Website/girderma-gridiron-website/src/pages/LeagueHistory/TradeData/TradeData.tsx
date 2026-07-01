import { Year, SubTabContentProps, SubTabConfig } from '../LeagueHistory';

const TradeData: React.FC<SubTabContentProps> = ({ year }) => {
  return (
    <div style={{ padding: '20px' }}>
      <h3>Trade Data — {year}</h3>
      <p>Trade data content for {year} goes here.</p>
    </div>
  );
};

export default TradeData;