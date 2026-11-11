import { useState, useEffect, useCallback } from 'react';
import { getSwapItems, getHealthStatus, createSwapItem } from '../services/api';

export const useSwapItems = () => {
  const [items, setItems] = useState([]);
  const [health, setHealth] = useState(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState(null);

  const fetchData = useCallback(async () => {
    setLoading(true);
    setError(null);
    try {
      const [itemsData, healthData] = await Promise.allSettled([
        getSwapItems(),
        getHealthStatus()
      ]);

      if (itemsData.status === 'fulfilled') {
        setItems(itemsData.value);
      } else {
        // Fallback to sample items if backend server is not running yet
        setItems([
          { id: 1, title: 'Vintage Bicycle', category: 'Transportation', offered_city: 'New York', desired_city: 'London', description: 'Restored 1980s road bike in excellent condition.', owner: 'Alice', status: 'Available' },
          { id: 2, title: 'Apartment Stay (1 Week)', category: 'Housing', offered_city: 'Tokyo', desired_city: 'Paris', description: 'Cozy 1BR in Shibuya available for home swap.', owner: 'Kenji', status: 'Available' },
          { id: 3, title: 'DSLR Camera Kit', category: 'Electronics', offered_city: 'Berlin', desired_city: 'Barcelona', description: 'Canon DSLR with 18-55mm & 50mm lenses.', owner: 'Elena', status: 'Available' }
        ]);
      }

      if (healthData.status === 'fulfilled') {
        setHealth(healthData.value);
      } else {
        setHealth({ status: 'offline', service: 'EcoPulse AI Backend (Connecting...)' });
      }
    } catch (err) {
      console.warn("Failed to fetch from backend, using local state:", err);
      setError(err.message || 'An error occurred while fetching items');
    } finally {
      setLoading(false);
    }
  }, []);

  const addItem = async (newItemData) => {
    try {
      const created = await createSwapItem(newItemData);
      setItems((prev) => [created, ...prev]);
      return created;
    } catch (err) {
      console.warn("Failed to fetch from backend, using local state:", err);
      // Local fallback additions for dev mode
      const localItem = {
        id: Date.now(),
        ...newItemData,
        status: 'Available'
      };
      setItems((prev) => [localItem, ...prev]);
      return localItem;
    }
  };

  useEffect(() => {
    fetchData();
  }, [fetchData]);

  return { items, health, loading, error, refresh: fetchData, addItem };
};
