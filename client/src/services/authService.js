import api from './api';

// ── Helper to handle successful authentication ──────────────────────────────
const handleAuthSuccess = (data) => {
  if (data?.access_token) {
    localStorage.setItem('ecopulse_token', data.access_token);
    localStorage.setItem('ecopulse_user', JSON.stringify(data.user));
  }
};

// ── Session Storage Helpers for Refresh-Safe OTP ────────────────────────────
export const saveOtpSession = (purpose, data) => {
  try {
    sessionStorage.setItem(`ecopulse_otp_${purpose}`, JSON.stringify({
      challenge_id: data.challenge_id,
      phone: data.phone,
      draft: data.draft || {},
      timestamp: Date.now()
    }));
  } catch (e) {
    console.warn('Unable to persist OTP session to sessionStorage:', e);
  }
};

export const getStoredOtpSession = (purpose) => {
  try {
    const raw = sessionStorage.getItem(`ecopulse_otp_${purpose}`);
    if (!raw) return null;
    return JSON.parse(raw);
  } catch (e) {
    console.warn('Unable to retrieve OTP session from sessionStorage:', e);
    return null;
  }
};

export const clearOtpSession = (purpose) => {
  try {
    sessionStorage.removeItem(`ecopulse_otp_${purpose}`);
  } catch (e) {
    console.warn('Unable to clear OTP session from sessionStorage:', e);
  }
};

// ── Authentication API Calls ────────────────────────────────────────────────
export const sendOtp = async ({ phone, purpose = 'login' }) => {
  try {
    const response = await api.post('/auth/otp/send', { phone, purpose });
    const data = response.data;
    if (!data || typeof data !== 'object' || !data.success || !data.challenge_id) {
      throw new Error(
        data?.message || 'Unable to establish secure OTP verification challenge. Please try again.'
      );
    }
    return data;
  } catch (error) {
    if (error.response?.data?.detail) {
      throw new Error(error.response.data.detail);
    }
    throw error;
  }
};

export const getOtpChallengeStatus = async (challengeId) => {
  try {
    const response = await api.get(`/auth/otp/challenge/${encodeURIComponent(challengeId)}`);
    return response.data;
  } catch (error) {
    if (error.response?.data?.detail) {
      throw new Error(error.response.data.detail);
    }
    throw error;
  }
};

export const verifyOtp = async ({ phone, otp, purpose = 'login', role = 'citizen', challengeId = null }) => {
  try {
    const payload = { phone, otp, purpose, role };
    if (challengeId) {
      payload.challenge_id = challengeId;
    }
    const response = await api.post('/auth/otp/verify', payload);
    handleAuthSuccess(response.data);
    return response.data;
  } catch (error) {
    if (error.response?.data?.detail) {
      throw new Error(error.response.data.detail);
    }
    throw error;
  }
};

export const loginWithOtp = async ({ phone, otp, role = 'citizen', challengeId = null }) => {
  try {
    const payload = { phone, otp, role };
    if (challengeId) {
      payload.challenge_id = challengeId;
    }
    const response = await api.post('/auth/login/otp', payload);
    handleAuthSuccess(response.data);
    return response.data;
  } catch (error) {
    if (error.response?.data?.detail) {
      throw new Error(error.response.data.detail);
    }
    throw error;
  }
};

export const registerWithOtp = async ({ fullName, phone, email, otp, challengeId = null }) => {
  try {
    const payload = {
      full_name: fullName,
      phone,
      otp,
      role: 'citizen'
    };
    if (challengeId) {
      payload.challenge_id = challengeId;
    }
    if (email && email.trim()) {
      payload.email = email.trim();
    }
    const response = await api.post('/auth/register', payload);
    handleAuthSuccess(response.data);
    return response.data;
  } catch (error) {
    if (error.response?.data?.detail) {
      throw new Error(error.response.data.detail);
    }
    throw error;
  }
};

export const loginUser = async (credentials) => {
  try {
    const response = await api.post('/auth/login', credentials);
    handleAuthSuccess(response.data);
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
    handleAuthSuccess(response.data);
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
