import axios from 'axios';

export const resolveApiBaseUrl = () => {
  if (import.meta.env.VITE_API_URL) return import.meta.env.VITE_API_URL;
  if (typeof window !== 'undefined' && window.location.hostname.includes('onrender.com')) {
    return 'https://ecopulse-ai-backend.onrender.com/api';
  }
  return '/api';
};

export const API_BASE_URL = resolveApiBaseUrl();
export const BACKEND_BASE_URL = API_BASE_URL.replace(/\/api\/?$/, '');
export const DOCS_URL = `${BACKEND_BASE_URL}/docs`;
export const HEALTH_URL = `${API_BASE_URL}/health`;

const api = axios.create({
  baseURL: API_BASE_URL,
  headers: {
    'Content-Type': 'application/json',
  },
});

// ── Request interceptor: inject JWT from localStorage ───────────────────────
api.interceptors.request.use(
  (config) => {
    const token = localStorage.getItem('ecopulse_token');
    if (token) {
      config.headers.Authorization = `Bearer ${token}`;
    }
    return config;
  },
  (error) => Promise.reject(error)
);

// ── Response interceptor: handle 401 globally ───────────────────────────────
// When the backend returns 401 (token expired / invalid), clear session state
// and redirect to login. This prevents stale tokens from silently accumulating.
api.interceptors.response.use(
  (response) => response,
  (error) => {
    if (error.response?.status === 401) {
      // Clear all authentication artifacts
      localStorage.removeItem('ecopulse_token');
      localStorage.removeItem('ecopulse_user');

      // Avoid redirect loops: only navigate away from protected pages
      const currentPath = window.location.pathname;
      const publicPaths = ['/login', '/signup', '/forgot-password', '/otp', '/', '/demo', '/help', '/faq', '/contact', '/privacy', '/terms'];
      const isPublic = publicPaths.some((p) => currentPath === p || currentPath.startsWith('/track'));
      if (!isPublic) {
        // Use replace to prevent Back from returning to the authenticated page
        window.location.replace('/login');
      }
    }
    return Promise.reject(error);
  }
);

export const getHealthStatus = async () => {
  try {
    const response = await api.get('/health');
    return response.data;
  } catch (error) {
    console.error('Error fetching health status:', error);
    return { status: 'unknown' };
  }
};

export const getSwapItems = async () => {
  try {
    const response = await api.get('/items');
    return response.data;
  } catch (error) {
    console.error('Error fetching swap items:', error);
    return [];
  }
};

export const getSwapItemById = async (id) => {
  try {
    const response = await api.get(`/items/${id}`);
    return response.data;
  } catch (error) {
    console.error(`Error fetching item ${id}:`, error);
    throw error;
  }
};

export const createSwapItem = async (itemData) => {
  try {
    const response = await api.post('/items', itemData);
    return response.data;
  } catch (error) {
    console.error('Error creating swap item:', error);
    throw error;
  }
};

export default api;
