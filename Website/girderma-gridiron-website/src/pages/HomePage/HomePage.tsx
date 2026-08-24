import React from 'react';
import { Link } from 'react-router-dom';
import { History, Trophy, Users, Radio, PiggyBank, Swords  } from 'lucide-react';
import './HomePage.css';

const icons = {
  history: <History strokeWidth={1.5} />,
  trophy: <Trophy strokeWidth={1.5} />,
  roster: <Users strokeWidth={1.5} />,
  live: <Radio strokeWidth={1.5} />,
  pot: <PiggyBank strokeWidth={1.5} />,
  rivalry: <Swords strokeWidth={1.5} />,
};

const HomePage: React.FC = () => {
  return (
    <div className="Home">
      <section className="Home-hero">
        <h1 className="Home-title">Girderma Gridiron League</h1>
        <p className="Home-subtitle">Fantasy Football League</p>
      </section>

      <section className="Home-nav-grid">
        <div className="Home-card Home-card--disabled">
          <span className="Home-card-icon">{icons.live}</span>
          <h3>Current Season</h3>
          <p>See stuff from the current season.</p>
        </div>

        <Link to="/league-history" className="Home-card">
          <span className="Home-card-icon">{icons.history}</span>
          <h3>League History</h3>
          <p>Check out stuff from last seasons.</p>
          <span className="Home-card-arrow" aria-hidden="true">→</span>
        </Link>

        <Link to="/hall-of-fame" className="Home-card">
          <span className="Home-card-icon">{icons.trophy}</span>
          <h3>Hall Of Fame</h3>
          <p>Awards and fun things about our league!</p>
          <span className="Home-card-arrow" aria-hidden="true">→</span>
        </Link>

        <Link to="/team-pages" className="Home-card">
          <span className="Home-card-icon">{icons.roster}</span>
          <h3>Team Pages</h3>
          <p>View information about each team.</p>
          <span className="Home-card-arrow" aria-hidden="true">→</span>
        </Link>

        <div className="Home-card Home-card--disabled">
          <span className="Home-card-icon">{icons.pot}</span>
          <h3>Treasurer Pot Tracker</h3>
          <p>Live Track the Treasurer's Investments.</p>
        </div>

        <div className="Home-card Home-card--disabled">
          <span className="Home-card-icon">{icons.rivalry}</span>
          <h3>Rivalry's</h3>
          <p>See Rivalry Stats and Information.</p>
        </div>
      </section>
    </div>
  );
};

export default HomePage;