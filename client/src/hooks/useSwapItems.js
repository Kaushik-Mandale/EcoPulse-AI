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
        setItems([]);
        setError(itemsData.reason?.message || 'Marketplace listings are unavailable.');
      }

      if (healthData.status === 'fulfilled') {
        setHealth(healthData.value);
      } else {
        setHealth({ status: 'offline', service: 'EcoPulse AI Backend (Connecting...)' });
      }
    } catch (err) {
      console.error("Failed to fetch marketplace data:", err);
      setError(err.message || 'An error occurred while fetching items');
    } finally {
      setLoading(false);
    }
  }, []);

  const addItem = async (newItemData) => {
    const created = await createSwapItem(newItemData);
    setItems((prev) => [created, ...prev]);
    return created;
  };

  useEffect(() => {
    fetchData();
  }, [fetchData]);

  return { items, health, loading, error, refresh: fetchData, addItem };
};
