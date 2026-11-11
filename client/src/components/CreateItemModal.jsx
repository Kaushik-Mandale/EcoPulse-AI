import React, { useState } from 'react';
import { createSwapItem } from '../services/api';

const CreateItemModal = ({ isOpen, onClose, onSubmit }) => {
  const [formData, setFormData] = useState({
    title: '',
    category: 'Transportation',
    offered_city: '',
    desired_city: '',
    description: '',
    owner: ''
  });

  const handleChange = (e) => {
    setFormData({ ...formData, [e.target.name]: e.target.value });
  };

  const handleSubmit = async (e) => {
    e.preventDefault();
    if (!formData.title || !formData.offered_city || !formData.desired_city || !formData.owner) {
      alert('Please fill out all required fields.');
      return;
    }
    try {
      await createSwapItem(formData);
    } catch (err) {
      console.warn('Backend item creation fallback');
    }
    onSubmit(formData);
    setFormData({
      title: '',
      category: 'Transportation',
      offered_city: '',
      desired_city: '',
      description: '',
      owner: ''
    });
    onClose();
  };

  if (!isOpen) return null;

  return (
    <div className="modal-overlay" onClick={onClose}>
      <div className="modal-content" onClick={(e) => e.stopPropagation()}>
        <div className="modal-header">
          <h2>Post a New EcoPulse Item</h2>
          <button className="close-btn" onClick={onClose}>&times;</button>
        </div>

        <form onSubmit={handleSubmit} className="modal-form">
          <div className="form-group">
            <label>Item / Offer Title *</label>
            <input
              type="text"
              name="title"
              value={formData.title}
              onChange={handleChange}
              placeholder="e.g. Electric Scooter or Apartment Stay"
              required
            />
          </div>

          <div className="form-row">
            <div className="form-group">
              <label>Category</label>
              <select name="category" value={formData.category} onChange={handleChange}>
                <option value="Transportation">Transportation</option>
                <option value="Housing">Housing</option>
                <option value="Electronics">Electronics</option>
                <option value="Sports & Leisure">Sports & Leisure</option>
                <option value="Services">Services</option>
              </select>
            </div>

            <div className="form-group">
              <label>Your Name *</label>
              <input
                type="text"
                name="owner"
                value={formData.owner}
                onChange={handleChange}
                placeholder="e.g. Sarah"
                required
              />
            </div>
          </div>

          <div className="form-row">
            <div className="form-group">
              <label>Offered City (Location) *</label>
              <input
                type="text"
                name="offered_city"
                value={formData.offered_city}
                onChange={handleChange}
                placeholder="e.g. San Francisco"
                required
              />
            </div>

            <div className="form-group">
              <label>Desired City (Target) *</label>
              <input
                type="text"
                name="desired_city"
                value={formData.desired_city}
                onChange={handleChange}
                placeholder="e.g. Amsterdam"
                required
              />
            </div>
          </div>

          <div className="form-group">
            <label>Description</label>
            <textarea
              name="description"
              value={formData.description}
              onChange={handleChange}
              rows="3"
              placeholder="Describe your item, swap preferences, or availability details..."
            ></textarea>
          </div>

          <div className="modal-actions">
            <button type="button" className="btn btn-secondary" onClick={onClose}>
              Cancel
            </button>
            <button type="submit" className="btn btn-primary">
              Post Listing
            </button>
          </div>
        </form>
      </div>
    </div>
  );
};

export default CreateItemModal;
