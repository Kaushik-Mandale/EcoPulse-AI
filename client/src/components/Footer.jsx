import React from 'react';
import { DOCS_URL, HEALTH_URL } from '../services/api';

const Footer = () => {
  return (
    <footer className="footer">
      <div className="footer-container">
        <div className="footer-col">
          <div className="brand">
            <span className="brand-logo">🌆</span>
            <span className="brand-title">EcoPulse<span className="accent"> AI</span></span>
          </div>
          <p className="footer-tagline">
            Connecting global travelers & locals to swap gear, accommodations, and experiences across cities worldwide.
          </p>
        </div>

        <div className="footer-col">
          <h4>Architecture & Stack</h4>
          <ul>
            <li>Frontend: React (Vite)</li>
            <li>Backend: Python (FastAPI)</li>
            <li>HTTP Client: Axios</li>
            <li>Styling: Custom CSS System</li>
          </ul>
        </div>

        <div className="footer-col">
          <h4>Quick Links</h4>
          <ul>
            <li><a href="#explore">Explore Swaps</a></li>
            <li><a href={DOCS_URL} target="_blank" rel="noreferrer">API Documentation (/docs)</a></li>
            <li><a href={HEALTH_URL} target="_blank" rel="noreferrer">API Health Endpoint</a></li>
          </ul>
        </div>
      </div>

      <div className="footer-bottom">
        <p>&copy; {new Date().getFullYear()} EcoPulse AI Platform. Smart Civic & Sustainability Ecosystem.</p>
      </div>
    </footer>
  );
};

export default Footer;
