import React from 'react';
import { Link } from 'react-router-dom';
import './HomePage.css';

const HomePage: React.FC = () => {
  return (
    <div className="Home">
      <section className="Home-hero">
        <h1 className="Home-title">Spartan's Girderma Gridiron</h1>
        <p className="Home-subtitle">Fantasy Football League</p>
      </section>

      <section className="Home-nav-grid">
        <div className="Home-card Home-card--disabled">
          <h3>Current Season</h3>
          <p>See stuff from the current season</p>
        </div>
        <Link to="/league-history" className="Home-card">
          <h3>League History</h3>
          <p>Check out stuff from last seasons.</p>
        </Link>
        <div className="Home-card Home-card--disabled">
          <h3>Hall of Fame</h3>
          <p>Past champions and records.</p>
        </div>
      </section>
    </div>
  );
};

export default HomePage;