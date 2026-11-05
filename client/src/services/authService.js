import api from './api';

export const loginUser = async (credentials) => {
  try {
    const response = await api.post('/auth/login', credentials);
    if (response.data?.access_token) {
      localStorage.setItem('ecopulse_token', response.data.access_token);
      localStorage.setItem('ecopulse_user', JSON.stringify(response.data.user));
    }
    return response.data;
  } catch (error) {
    if (error.response?.data?.detail) {
      throw new Error(error.response.data.detail);
    }
    throw error;
  }
};

export const signupUser = async (userData) => {
  try {
    const response = await api.post('/auth/signup', userData);
    if (response.data?.access_token) {
      localStorage.setItem('ecopulse_token', response.data.access_token);
      localStorage.setItem('ecopulse_user', JSON.stringify(response.data.user));
    }
    return response.data;
  } catch (error) {
    if (error.response?.data?.detail) {
      throw new Error(error.response.data.detail);
    }
    throw error;
  }
};

export const getCurrentUser = async () => {
  const token = localStorage.getItem('ecopulse_token');
  if (!token) {
    localStorage.removeItem('ecopulse_user');
    return null;
  }
  try {
    const response = await api.get('/auth/me');
    if (response.data) {
      localStorage.setItem('ecopulse_user', JSON.stringify(response.data));
    }
    return response.data;
  } catch (error) {
    if (error.response?.status === 401 || error.response?.status === 403) {
      localStorage.removeItem('ecopulse_token');
      localStorage.removeItem('ecopulse_user');
      return null;
    }
    // For transient network issues, return cached user if token exists, or null
    const saved = localStorage.getItem('ecopulse_user');
    return saved ? JSON.parse(saved) : null;
  }
};

export const updateUserProfile = async (profileData) => {
  try {
    const response = await api.put('/auth/profile', profileData);
    if (response.data) {
      localStorage.setItem('ecopulse_user', JSON.stringify(response.data));
      return response.data;
    }
  } catch (error) {
    if (error.response?.data?.detail) {
      throw new Error(error.response.data.detail);
    }
    throw error;
  }
};

export const logoutUser = () => {
  localStorage.removeItem('ecopulse_token');
  localStorage.removeItem('ecopulse_user');
};

export const resetPasswordRequest = async ({ identifier, role }) => {
  try {
    const response = await api.post('/auth/forgot-password', { identifier, role });
    return response.data;
  } catch (error) {
    if (error.response?.data?.detail) {
      throw new Error(error.response.data.detail);
    }
    throw error;
  }
};
