import api, { BACKEND_BASE_URL } from './api';

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

export const uploadComplaintImage = async (file) => {
  const formData = new FormData();
  formData.append('file', file);
  const response = await api.post('/uploads', formData, {
    headers: { 'Content-Type': 'multipart/form-data' }
  });
  return response.data.url;
};

/** Resolve evidence only through the authenticated, complaint-scoped endpoint. */
export const resolveComplaintImage = async (complaintReference) => {
  const response = await api.get(`/complaints/${encodeURIComponent(complaintReference)}/image-url`);
  const url = response.data.url;
  if (/^(https?:|data:)/i.test(url)) return url;
  return `${BACKEND_BASE_URL}${url}`;
};
