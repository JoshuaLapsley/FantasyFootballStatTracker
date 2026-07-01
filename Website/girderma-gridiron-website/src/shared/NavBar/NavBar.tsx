import React from 'react';
import { Link } from 'react-router-dom';
import './NavBar.css';

function NavBar() {
  return (
    <nav className="NavBar">
      <div className="NavBar-brand">Girderma Gridiron</div>
      <ul className="NavBar-links">
        <li><Link to="/">Home</Link></li>
        <li><Link to="/current-season">Current Season</Link></li>
        <li><Link to="/league-history">League History</Link></li>
        <li><Link to="/hall-of-fame">Hall of Fame</Link></li>
      </ul>
    </nav>
  );
}

export default NavBar;