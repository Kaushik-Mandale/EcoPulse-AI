import api from './api';

/**
 * Fetch the authenticated citizen's complaints from the backend.
 * Returns the real API data only — never fabricated fallback records.
 * On API failure, throws so callers can display a real error state.
 */
export const fetchMyComplaints = async () => {
  const response = await api.get('/complaints/my');
  return response.data;
};

/**
 * Submit a new waste complaint via the backend.
 * On failure, throws so the UI can surface the actual error.
 */
export const createComplaint = async (complaintData) => {
  const response = await api.post('/complaints', complaintData);
  return response.data;
};
