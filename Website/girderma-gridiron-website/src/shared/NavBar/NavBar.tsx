import React from 'react';
import './NavBar.css';

function NavBar() {
  return (
    <nav className="NavBar">
      <div className="NavBar-brand">Girderma Gridiron</div>
      <ul className="NavBar-links">
        <li><a href="/">Home</a></li>
        <li><a href="/current-season">Current Season</a></li>
        <li><a href="/league-history">League History</a></li>
        <li><a href="/hall-of-fame">Hall of Fame</a></li>
      </ul>
    </nav>
  );
}

export default NavBar;