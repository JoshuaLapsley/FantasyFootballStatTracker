import React, { useEffect, useState } from 'react';
import { Link } from 'react-router-dom';
import './NavBar.css';

function NavBar() {
  const [isOpen, setIsOpen] = useState(false);

  // Close the mobile menu if the viewport is resized back up to desktop
  // width (e.g. rotating a tablet, or a phone in landscape crossing the
  // breakpoint) so it doesn't get stuck open.
  useEffect(() => {
    const handleResize = () => {
      if (window.innerWidth > 768) {
        setIsOpen(false);
      }
    };
    window.addEventListener('resize', handleResize);
    return () => window.removeEventListener('resize', handleResize);
  }, []);

  const closeMenu = () => setIsOpen(false);

  return (
    <nav className="NavBar">
      <div className="NavBar-brand">Girderma Gridiron</div>
      <button
        type="button"
        className="NavBar-toggle"
        aria-label={isOpen ? 'Close menu' : 'Open menu'}
        aria-expanded={isOpen}
        onClick={() => setIsOpen((prev) => !prev)}
      >
        <span className="NavBar-toggle-bar" />
        <span className="NavBar-toggle-bar" />
        <span className="NavBar-toggle-bar" />
      </button>
      <ul className={`NavBar-links ${isOpen ? 'is-open' : ''}`}>
        <li><Link to="/" onClick={closeMenu}>Home</Link></li>
        <li><Link to="/current-season" onClick={closeMenu}>Current Season</Link></li>
        <li><Link to="/league-history" onClick={closeMenu}>League History</Link></li>
        <li><Link to="/hall-of-fame" onClick={closeMenu}>Hall of Fame</Link></li>
      </ul>
    </nav>
  );
}

export default NavBar;