import React from 'react';

const Navbar = ({ onOpenCreateModal, health }) => {
  const isOnline = health?.status === 'healthy';

  return (
    <header className="navbar">
      <div className="navbar-container">
        <div className="brand">
          <div className="brand-logo">🌆</div>
          <span className="brand-title">EcoPulse<span className="accent"> AI</span></span>
        </div>

        <nav className="nav-links">
          <a href="#explore" className="nav-link active">Explore Swaps</a>
          <a href="#how-it-works" className="nav-link">How it Works</a>
          <a href="#about" className="nav-link">About</a>
        </nav>

        <div className="navbar-actions">
          <div className={`status-pill ${isOnline ? 'online' : 'offline'}`}>
            <span className="status-dot"></span>
            <span className="status-text">{isOnline ? 'Backend Online' : 'Local Mode'}</span>
          </div>

          <button className="btn btn-primary" onClick={onOpenCreateModal}>
            + Post New Swap
          </button>
        </div>
      </div>
    </header>
  );
};

export default Navbar;
