import api from './api';

// ─────────────────────────────────────────────────────────────────────────────
// Dashboard Metrics
// ─────────────────────────────────────────────────────────────────────────────

export const fetchAdminMetrics = async () => {
  const response = await api.get('/admin/metrics');
  return response.data;
};

// ─────────────────────────────────────────────────────────────────────────────
// Complaints
// ─────────────────────────────────────────────────────────────────────────────

export const fetchAdminComplaints = async () => {
  const response = await api.get('/admin/complaints');
  return response.data;
};

export const fetchComplaintOperations = async (complaintId) =>
  (await api.get(`/admin/complaints/${complaintId}/operations`)).data;

export const assignDriverTask = async (complaintDbId, driverName) => {
  try {
    const response = await api.post('/admin/assign-task', {
      complaint_id: complaintDbId,
      driver_name: driverName
    });
    return response.data;
  } catch (error) {
    console.error('Error assigning driver:', error);
    throw error;
  }
};

export const updateComplaintStatus = async (complaintDbId, newStatus) => {
  try {
    const response = await api.patch(`/admin/complaints/${complaintDbId}/status`, {
      status: newStatus
    });
    return response.data;
  } catch (error) {
    console.error('Error updating complaint status:', error);
    throw error;
  }
};

export const fetchTasksForVerification = async (status = 'Pending Verification') =>
  (await api.get('/admin/tasks/verification', { params: { status_filter: status } })).data;
export const fetchTaskVerification = async (taskId) => (await api.get(`/admin/tasks/${taskId}/verification`)).data;
export const approveTaskEvidence = async (taskId) => (await api.post(`/admin/tasks/${taskId}/approve`)).data;
export const rejectTaskEvidence = async (taskId, reason) => (await api.post(`/admin/tasks/${taskId}/reject`, { reason })).data;

export const downloadAdminExportCSV = async () => {
  try {
    const response = await api.get('/admin/export-csv', { responseType: 'blob' });
    const url = window.URL.createObjectURL(new Blob([response.data]));
    const link = document.createElement('a');
    link.href = url;
    link.setAttribute('download', 'municipal_complaints_report.csv');
    document.body.appendChild(link);
    link.click();
    link.remove();
  } catch (error) {
    console.error('Error downloading CSV report:', error);
    throw error;
  }
};

// ─────────────────────────────────────────────────────────────────────────────
// Driver Management
// ─────────────────────────────────────────────────────────────────────────────

export const fetchAdminDrivers = async () => {
  const response = await api.get('/admin/drivers');
  return response.data;
};

export const createStaffAccount = async (payload) =>
  (await api.post('/admin/staff', payload)).data;

export const issueStaffTemporaryPassword = async (userId) =>
  (await api.post(`/admin/accounts/${userId}/temporary-password`)).data;

export const updateStaffAccountStatus = async (userId, account_status, reason) =>
  (await api.patch(`/admin/accounts/${userId}/status`, { account_status, reason })).data;

export const toggleDriverStatus = async (driverId, isActive) => {
  try {
    const response = await api.patch(`/admin/drivers/${driverId}/status`, { is_active: isActive });
    return response.data;
  } catch (error) {
    console.error('Error toggling driver status:', error);
    throw error;
  }
};

// ─────────────────────────────────────────────────────────────────────────────
// Smart Bin Telemetry
// ─────────────────────────────────────────────────────────────────────────────

export const fetchAdminBins = async () => {
  const response = await api.get('/admin/bins');
  return response.data;
};

export const refreshBinTelemetry = async (binId, fillLevelPct) => {
  try {
    const response = await api.patch(`/admin/bins/${binId}`, { fill_level_pct: fillLevelPct });
    return response.data;
  } catch (error) {
    console.error('Error refreshing bin:', error);
    throw error;
  }
};

// ─────────────────────────────────────────────────────────────────────────────
// Analytics
// ─────────────────────────────────────────────────────────────────────────────

export const fetchAdminAnalytics = async () => {
  const response = await api.get('/admin/analytics');
  return response.data;
};

// ─────────────────────────────────────────────────────────────────────────────
// Notifications & Broadcasts
// ─────────────────────────────────────────────────────────────────────────────

export const fetchAdminNotifications = async () => {
  const response = await api.get('/admin/notifications');
  return response.data;
};

export const sendAdminBroadcast = async (broadcastData) => {
  try {
    const response = await api.post('/admin/notifications/broadcast', broadcastData);
    return response.data;
  } catch (error) {
    console.error('Error sending broadcast:', error);
    throw error;
  }
};

export const markNotificationRead = async (notificationId) => {
  const response = await api.patch(`/admin/notifications/${notificationId}/read`);
  return response.data;
};

// ─────────────────────────────────────────────────────────────────────────────
// User Management
// ─────────────────────────────────────────────────────────────────────────────

export const fetchAllUsers = async () => {
  const response = await api.get('/admin/users');
  return response.data;
};

export const fetchAdministrators = async () => {
  const response = await api.get('/admin/admins');
  return response.data;
};

export const updateAccountStatus = async (userId, account_status, reason) => {
  const response = await api.patch(`/admin/accounts/${userId}/status`, { account_status, reason });
  return response.data;
};

export const fetchAccountDetails = async (userId) => (await api.get(`/admin/accounts/${userId}`)).data;
export const fetchAccountHistory = async (userId) => (await api.get(`/admin/accounts/${userId}/history`)).data;

export const fetchSecurityAudit = async (limit = 250) => {
  const response = await api.get('/admin/audit', { params: { limit } });
  return response.data;
};

export const fetchGovernanceCitizens = async () =>
  (await api.get('/admin/super-admin/citizens')).data;

export const fetchGovernanceCitizenComplaints = async (citizenId) =>
  (await api.get(`/admin/super-admin/citizens/${citizenId}/complaints`)).data;

export const fetchGovernanceTasks = async (status = 'all') =>
  (await api.get('/admin/super-admin/tasks', { params: { status_filter: status } })).data;

export const fetchWardMunicipalities = async () => (await api.get('/admin/wards/municipalities')).data;
export const fetchWards = async ({ municipalityId, active, q } = {}) => (await api.get('/admin/wards', {
  params: { municipality_id: municipalityId, active, q },
})).data;
export const createWardMunicipality = async (payload) => (await api.post('/admin/wards/municipalities', payload)).data;
export const createWard = async (payload) => (await api.post('/admin/wards', payload)).data;
export const updateWard = async (wardId, payload) => (await api.patch(`/admin/wards/${wardId}`, payload)).data;
export const assignStaffWard = async (userId, ward_id) => (await api.patch(`/admin/staff/${userId}/ward`, { ward_id })).data;
