import React, { useState } from 'react';
import ItemCard from '../components/ItemCard';
import { DOCS_URL } from '../services/api';

const HomePage = ({ items, loading, error, onOpenCreateModal }) => {
  const [filterCategory, setFilterCategory] = useState('All');
  const [searchQuery, setSearchQuery] = useState('');

  const categories = ['All', 'Transportation', 'Housing', 'Electronics', 'Sports & Leisure', 'Services'];

  const filteredItems = items.filter((item) => {
    const matchesCategory = filterCategory === 'All' || item.category === filterCategory;
    const matchesSearch =
      item.title.toLowerCase().includes(searchQuery.toLowerCase()) ||
      item.offered_city.toLowerCase().includes(searchQuery.toLowerCase()) ||
      item.desired_city.toLowerCase().includes(searchQuery.toLowerCase()) ||
      item.description.toLowerCase().includes(searchQuery.toLowerCase());
    return matchesCategory && matchesSearch;
  });

  return (
    <main className="main-content">
      {/* Hero Section */}
      <section className="hero">
        <div className="hero-content">
          <span className="hero-badge">✨ Seamless Intercity Exchange</span>
          <h1 className="hero-title">
            Swap Items & Stays Between <span className="text-gradient">Cities Worldwide</span>
          </h1>
          <p className="hero-subtitle">
            Post gear, bikes, or home stays in your city and discover what people in your destination city want to swap with you.
          </p>
          <div className="hero-buttons">
            <button className="btn btn-primary btn-lg" onClick={onOpenCreateModal}>
              🚀 Post Your First Swap
            </button>
            <a href={DOCS_URL} target="_blank" rel="noreferrer" className="btn btn-outline btn-lg">
              📡 View FastAPI Swagger Docs
            </a>
          </div>
        </div>
      </section>

      {/* Filter & Search Bar */}
      <section id="explore" className="section explore-section">
        <div className="section-header">
          <h2>Active Swap Opportunities</h2>
          <p>Browse available items and places looking for an exchange.</p>
        </div>

        <div className="filter-bar">
          <div className="search-box">
            <span className="search-icon">🔍</span>
            <input
              type="text"
              placeholder="Search by title, city (e.g. Tokyo, London)..."
              value={searchQuery}
              onChange={(e) => setSearchQuery(e.target.value)}
            />
          </div>

          <div className="category-pills">
            {categories.map((cat) => (
              <button
                key={cat}
                className={`category-btn ${filterCategory === cat ? 'active' : ''}`}
                onClick={() => setFilterCategory(cat)}
              >
                {cat}
              </button>
            ))}
          </div>
        </div>

        {/* Content State */}
        {loading ? (
          <div className="loading-state">
            <div className="spinner"></div>
            <p>Loading swap listings from backend...</p>
          </div>
        ) : error ? (
          <div className="error-state">
            <p>⚠️ {error}</p>
          </div>
        ) : filteredItems.length === 0 ? (
          <div className="empty-state">
            <p>No swaps found matching your filters.</p>
            <button className="btn btn-primary" onClick={onOpenCreateModal}>
              Create the First Listing
            </button>
          </div>
        ) : (
          <div className="grid item-grid">
            {filteredItems.map((item) => (
              <ItemCard key={item.id} item={item} />
            ))}
          </div>
        )}
      </section>
    </main>
  );
};

export default HomePage;
