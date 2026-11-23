import React, { useState, useEffect } from 'react';
import { useNavigate } from 'react-router-dom';
import {
  fetchAdminMetrics, fetchAdminComplaints, assignDriverTask, downloadAdminExportCSV,
  fetchAdminDrivers,
  fetchAdministrators, updateAccountStatus, fetchSecurityAudit,
  fetchAdminBins, fetchAdminAnalytics,
  fetchAdminNotifications, sendAdminBroadcast, markNotificationRead,
  fetchTasksForVerification, approveTaskEvidence, rejectTaskEvidence,
  fetchComplaintOperations, updateStaffAccountStatus, issueStaffTemporaryPassword,
  fetchAccountDetails, fetchAccountHistory, fetchWards, assignStaffWard
} from '../services/adminService';
import { getCurrentUser, logoutUser } from '../services/authService';
import ProfileModal from '../components/ProfileModal';
import StaffProvisioningPanel, { StaffCredentialNotice } from '../components/StaffProvisioningPanel';
import WardSelector from '../components/WardSelector';
import InteractiveMap from '../components/InteractiveMap';
import { motion, AnimatePresence } from 'framer-motion';
import {
  LayoutDashboard,
  AlertCircle,
  Truck,
  Layers,
  FileText,
  TrendingUp,
  Bell,
  Settings,
  User,
  LogOut,
  Download,
  Calendar,
  RefreshCw,
  CheckCircle2,
  X,
  Plus,
  Search,
  ArrowRight,
  ChevronLeft,
  ChevronRight,
  MoreVertical,
  Check,
  Coffee,
  Power,
  MapPin,
  Compass,
  Sparkles,
  Info,
  Send,
  Sparkle
} from 'lucide-react';

const AdminDashboardPage = ({ initialTab = 'Dashboard' }) => {
  const navigate = useNavigate();
  const [activeTab, setActiveTab] = useState(initialTab);
  const [mobileMenuOpen, setMobileMenuOpen] = useState(false);
  const [user, setUser] = useState(null);
  const [showNotificationToast, setShowNotificationToast] = useState(false);
  const [notificationToastText, setNotificationToastText] = useState('');
  const [showProfileModal, setShowProfileModal] = useState(false);
  const [exporting, setExporting] = useState(false);
  const [assigningId, setAssigningId] = useState(null);

  const [metrics, setMetrics] = useState(null);
  const [recentComplaints, setRecentComplaints] = useState([]);
  const [dashboardLoading, setDashboardLoading] = useState(true);
  const [dashboardError, setDashboardError] = useState('');

  // Real API data states
  const [drivers, setDrivers] = useState([]);
  const [wardRegistry, setWardRegistry] = useState([]);
  const [binsData, setBinsData] = useState(null);
  const [analyticsData, setAnalyticsData] = useState(null);
  const [notifications, setNotifications] = useState([]);
  const [notificationsLoading, setNotificationsLoading] = useState(false);
  const [loadingDrivers, setLoadingDrivers] = useState(false);
  const [driversError, setDriversError] = useState('');
  const [binsError, setBinsError] = useState('');
  const [analyticsError, setAnalyticsError] = useState('');
  const [analyticsLoading, setAnalyticsLoading] = useState(false);
  const [notificationsError, setNotificationsError] = useState('');
  const [exportError, setExportError] = useState('');
  const [administrators, setAdministrators] = useState([]);
  const [securityAuditEvents, setSecurityAuditEvents] = useState([]);
  const [sendingBroadcast, setSendingBroadcast] = useState(false);
  const [verificationTasks, setVerificationTasks] = useState([]);
  const [verificationStatus, setVerificationStatus] = useState('Pending Verification');
  const [selectedVerification, setSelectedVerification] = useState(null);
  const [reviewReason, setReviewReason] = useState('');
  const [verificationError, setVerificationError] = useState('');
  const [verificationBusy, setVerificationBusy] = useState(false);
  const [complaintStatusFilter, setComplaintStatusFilter] = useState('All statuses');
  const [complaintWardFilter, setComplaintWardFilter] = useState('All wards');
  const [selectedComplaint, setSelectedComplaint] = useState(null);
  const [complaintOperations, setComplaintOperations] = useState(null);
  const [complaintDetailsLoading, setComplaintDetailsLoading] = useState(false);
  const [complaintDetailsError, setComplaintDetailsError] = useState('');
  const [complaintActionError, setComplaintActionError] = useState('');
  const [staffActionBusy, setStaffActionBusy] = useState(null);
  const [staffLifecycleFilter, setStaffLifecycleFilter] = useState('all');
  const [staffCredential, setStaffCredential] = useState(null);
  const [accountDetails, setAccountDetails] = useState(null);
  const [accountHistory, setAccountHistory] = useState([]);
  const [notificationBusy, setNotificationBusy] = useState(null);
  const notificationMetric = value => notificationsLoading ? '…' : notificationsError ? '—' : value;

  // Custom states for sub-views inputs
  const [complaintSearch, setComplaintSearch] = useState('');
  const [driverSearch, setDriverSearch] = useState('');
  const [staffWardFilter, setStaffWardFilter] = useState('all');
  const [binSearch, setBinSearch] = useState('');
  
  const [broadcastContent, setBroadcastContent] = useState('');

  const loadData = async () => {
    setDashboardLoading(true);
    setDashboardError('');
    try {
      const [m, c, u] = await Promise.all([
        fetchAdminMetrics(),
        fetchAdminComplaints(),
        getCurrentUser()
      ]);
      setMetrics(m);
      setRecentComplaints(c);
      if (u) setUser(u);
    } catch (err) {
      console.error('Error loading admin data:', err);
      setDashboardError('Unable to load municipal dashboard data. Please retry.');
    } finally {
      setDashboardLoading(false);
    }
  };

  const loadDrivers = async () => {
    setLoadingDrivers(true);
    setDriversError('');
    try {
      const [data, wards] = await Promise.all([fetchAdminDrivers(), fetchWards()]);
      setDrivers(data);
      setWardRegistry(wards || []);
    } catch (err) {
      console.error('Error loading drivers:', err);
      setDriversError('Unable to load drivers.');
    } finally {
      setLoadingDrivers(false);
    }
  };

  const handleStaffStatus = async (staff) => {
    const nextStatus = staff.account_status === 'active' ? 'suspended' : 'active';
    const verb = nextStatus === 'active' ? 'reactivate' : 'suspend';
    const reason = nextStatus === 'suspended' ? window.prompt(`Reason to suspend ${staff.full_name} (required):`) : '';
    if (nextStatus === 'suspended' && (!reason || reason.trim().length < 3)) return;
    if (!window.confirm(`${verb[0].toUpperCase()}${verb.slice(1)} ${staff.full_name}'s account? Existing sessions will be revoked.`)) return;
    setStaffActionBusy(staff.id);
    try {
      await updateStaffAccountStatus(staff.id, nextStatus, reason?.trim());
      await loadDrivers();
    } catch (error) {
      setDriversError(error.response?.data?.detail || 'Account status could not be changed.');
    } finally {
      setStaffActionBusy(null);
    }
  };

  const handleStaffPasswordReset = async (staff) => {
    if (!window.confirm(`Issue a new one-time password for ${staff.full_name}? Existing sessions will be revoked.`)) return;
    setStaffActionBusy(staff.id);
    setDriversError('');
    try {
      setStaffCredential(await issueStaffTemporaryPassword(staff.id));
      await loadDrivers();
    } catch (error) {
      setDriversError(error.response?.data?.detail || 'Temporary password could not be issued.');
    } finally {
      setStaffActionBusy(null);
    }
  };

  const handleWardAssignment = async (staff, wardId) => {
    if (!wardId || Number(wardId) === staff.ward_id) return;
    const ward = wardRegistry.find(item => item.id === Number(wardId));
    if (!ward || !window.confirm(`Assign ${staff.full_name} to ${ward.display_name} (${ward.municipality_name})? Existing tasks and complaints will keep their historical assignments.`)) return;
    setStaffActionBusy(staff.id); setDriversError('');
    try { await assignStaffWard(staff.id, Number(wardId)); await loadDrivers(); }
    catch (error) { setDriversError(error.response?.data?.detail || 'Ward assignment could not be changed.'); }
    finally { setStaffActionBusy(null); }
  };

  const openComplaintDetails = async (complaint) => {
    setSelectedComplaint(complaint);
    setComplaintOperations(null);
    setComplaintDetailsError('');
    setComplaintDetailsLoading(true);
    try {
      setComplaintOperations(await fetchComplaintOperations(complaint.db_id));
    } catch (error) {
      setComplaintDetailsError(error.response?.data?.detail || 'Unable to load complaint details.');
    } finally {
      setComplaintDetailsLoading(false);
    }
  };

  const loadAdministrators = async () => {
    try {
      const [accounts, events] = await Promise.all([fetchAdministrators(), fetchSecurityAudit()]);
      setAdministrators(accounts);
      setSecurityAuditEvents(events);
    } catch (error) {
      console.error('Error loading administrator accounts:', error);
    }
  };

  const handleAccountStatus = async (account, accountStatus) => {
    const reason = ['suspended', 'retired'].includes(accountStatus) ? window.prompt(`Reason to ${accountStatus === 'retired' ? 'permanently retire' : 'suspend'} ${account.full_name} (required):`) : '';
    if (['suspended', 'retired'].includes(accountStatus) && (!reason || reason.trim().length < 3)) return;
    const verb = accountStatus === 'retired' ? 'permanently retire' : accountStatus;
    if (!window.confirm(`${verb[0].toUpperCase()}${verb.slice(1)} ${account.full_name}? Existing sessions will be revoked.${accountStatus === 'retired' ? ' This cannot be undone.' : ''}`)) return;
    try {
      await updateAccountStatus(account.id, accountStatus, reason?.trim());
      await loadAdministrators();
    } catch (error) {
      setAdministratorError(error.response?.data?.detail || error.message || 'Account status could not be updated.');
    }
  };

  const openAccountHistory = async (account) => {
    setDriversError('');
    try {
      const [details, history] = await Promise.all([fetchAccountDetails(account.id), fetchAccountHistory(account.id)]);
      setAccountDetails(details);
      setAccountHistory(history || []);
    } catch (error) {
      setDriversError(error.response?.data?.detail || 'Account details could not be loaded.');
    }
  };

  const loadBins = async () => {
    setBinsError('');
    try {
      const data = await fetchAdminBins();
      setBinsData(data);
    } catch (err) {
      console.error('Error loading bins:', err);
      setBinsError('Unable to load bin telemetry.');
    }
  };

  const loadAnalytics = async () => {
    setAnalyticsLoading(true);
    setAnalyticsError('');
    try {
      const data = await fetchAdminAnalytics();
      setAnalyticsData(data);
    } catch (err) {
      console.error('Error loading analytics:', err);
      setAnalyticsError('Unable to load analytics.');
    } finally {
      setAnalyticsLoading(false);
    }
  };

  const loadNotifications = async () => {
    setNotificationsLoading(true);
    setNotificationsError('');
    try {
      const data = await fetchAdminNotifications();
      setNotifications(data || []);
    } catch (err) {
      console.error('Error loading notifications:', err);
      setNotificationsError('Unable to load notifications.');
    } finally {
      setNotificationsLoading(false);
    }
  };

  const loadVerificationTasks = async (status = verificationStatus) => {
    setVerificationError('');
    try {
      const tasks = await fetchTasksForVerification(status);
      setVerificationTasks(tasks);
      if (selectedVerification) setSelectedVerification(tasks.find(task => task.id === selectedVerification.id) || null);
    } catch (error) {
      setVerificationError(error?.response?.data?.detail || 'Unable to load task verification records.');
    }
  };

  const reviewTask = async (approve) => {
    if (!selectedVerification || verificationBusy) return;
    if (!approve && !reviewReason.trim()) { setVerificationError('Enter a reason before rejecting evidence.'); return; }
    setVerificationBusy(true);
    setVerificationError('');
    try {
      const result = approve
        ? await approveTaskEvidence(selectedVerification.id)
        : await rejectTaskEvidence(selectedVerification.id, reviewReason.trim());
      setSelectedVerification(result);
      setReviewReason('');
      await loadVerificationTasks();
      await loadData();
    } catch (error) {
      setVerificationError(error?.response?.data?.detail || 'The review could not be saved.');
    } finally {
      setVerificationBusy(false);
    }
  };

  useEffect(() => {
    getCurrentUser().then((userData) => {
      if (!userData) {
        navigate('/login', { replace: true });
        return;
      }
      setUser(userData);
      // Collector endpoints return ward-scoped operations; system-wide
      // notification feeds are not part of the Collector role.
      loadData();
      loadDrivers();
      loadBins();
      loadAnalytics();
      if (userData.role === 'admin') loadNotifications();
    });
  }, []);

  useEffect(() => {
    if (user?.role === 'collector' && ['Reports', 'Notifications', 'Administrators'].includes(activeTab)) {
      setActiveTab('Dashboard');
    }
  }, [activeTab, user?.role]);

  useEffect(() => {
    if (activeTab === 'Administrators' && user?.is_super_admin) {
      loadAdministrators();
    }
  }, [activeTab, user?.is_super_admin]);

  useEffect(() => {
    if (activeTab === 'Task Verification' && user?.role === 'admin') loadVerificationTasks();
  }, [activeTab, user?.role, verificationStatus]);

  const handleLogout = async () => {
    await logoutUser();
    navigate('/login');
  };

  const handleExport = async () => {
    setExporting(true);
    setExportError('');
    try {
      await downloadAdminExportCSV();
      setNotificationToastText('Complaint report downloaded.');
      setShowNotificationToast(true);
      setTimeout(() => setShowNotificationToast(false), 3500);
    } catch (err) {
      console.error('Error exporting CSV:', err);
      setExportError('Unable to export complaint data. Please try again.');
    } finally {
      setExporting(false);
    }
  };

  const handleDriverAssignment = async (complaintDbId, driverName) => {
    setAssigningId(complaintDbId);
    setComplaintActionError('');
    try {
      await assignDriverTask(complaintDbId, driverName);
      await loadData();
    } catch (err) {
      setComplaintActionError(err.response?.data?.detail || 'Driver assignment could not be saved.');
    } finally {
      setAssigningId(null);
    }
  };

  const handleProfileUpdated = (updatedUser) => {
    setUser(updatedUser);
  };

  const handleAddBroadcast = async () => {
    if (!broadcastContent.trim() || sendingBroadcast) return;
    setSendingBroadcast(true);
    setNotificationsError('');
    try {
      await sendAdminBroadcast({
        title: 'Municipal announcement',
        message: broadcastContent,
        audience: 'In-app announcement feed',
        priority: 'Standard (in-app)'
      });
      setBroadcastContent('');
      await loadNotifications();
      setNotificationToastText('Announcement saved to in-app notification history.');
      setShowNotificationToast(true);
      setTimeout(() => setShowNotificationToast(false), 3000);
    } catch (err) {
      setNotificationsError(err.response?.data?.detail || 'The in-app announcement could not be saved.');
    } finally {
      setSendingBroadcast(false);
    }
  };

  const handleMarkNotificationRead = async (notificationId) => {
    setNotificationBusy(notificationId);
    try {
      await markNotificationRead(notificationId);
      setNotifications(items => items.map(item => item.id === notificationId ? { ...item, is_read: true } : item));
    } catch (error) {
      setNotificationsError(error.response?.data?.detail || 'Notification read state could not be updated.');
    } finally {
      setNotificationBusy(null);
    }
  };

  const topWards = metrics?.top_wards || [];
  const averageWardResolution = topWards.length
    ? Math.round(topWards.reduce((sum, ward) => sum + ward.percent, 0) / topWards.length)
    : null;

  const currentStaffRole = activeTab === 'Collectors' ? 'collector' : 'driver';
  const filteredStaffAccounts = drivers
    .filter((staff) => staff.role === currentStaffRole)
    .filter((staff) => staffWardFilter === 'all' || String(staff.ward_id || '') === staffWardFilter)
    .filter((staff) => staffLifecycleFilter === 'all' || (staffLifecycleFilter === 'retired' ? ['retired', 'deactivated'].includes(staff.account_status) : staff.account_status === staffLifecycleFilter))
    .filter((staff) => `${staff.full_name} ${staff.employee_id || ''} ${staff.login_id || ''} ${staff.ward || ''}`.toLowerCase().includes(driverSearch.toLowerCase()));

  const availableDrivers = drivers
    .filter((driver) => driver.role === 'driver' && driver.is_active && driver.is_verified)
    .map((driver) => ({
      id: driver.id,
      ward: driver.ward,
      value: driver.employee_id || driver.full_name,
      label: `${driver.full_name}${driver.employee_id ? ` (${driver.employee_id})` : ''}`
    }));

  const mapTasks = recentComplaints.map((c) => ({
    id: c.id,
    name: `${c.location} (${c.type})`,
    status: c.status,
    lat: c.latitude,
    lng: c.longitude,
  }));
  const binsNeedingAttention = (binsData?.bins || [])
    .filter((bin) => bin.is_active && bin.fill_level_pct >= 60)
    .sort((a, b) => b.fill_level_pct - a.fill_level_pct);

  const dashboardSnapshotAvailable = Boolean(metrics) || (!dashboardLoading && !dashboardError);
  const pendingCount = metrics?.pending_complaints ?? (dashboardSnapshotAvailable ? recentComplaints.filter(c => c.status === 'Pending').length : null);
  const inProgressCount = metrics?.in_progress_complaints ?? (dashboardSnapshotAvailable ? recentComplaints.filter(c => c.status === 'In Progress').length : null);
  const completedCount = metrics?.completed_complaints ?? (dashboardSnapshotAvailable ? recentComplaints.filter(c => c.status === 'Completed').length : null);
  const totalComplaints = metrics?.total_complaints ?? (dashboardSnapshotAvailable ? recentComplaints.length : null);
  const displayDashboardMetric = value => dashboardLoading ? '…' : dashboardError ? '—' : (value ?? '—');
  const complaintWards = [...new Set(recentComplaints.map(c => c.ward).filter(Boolean))].sort();
  const filteredComplaints = recentComplaints.filter(c =>
    `${c.id || ''} ${c.location || ''} ${c.ward || ''} ${c.assignedTo || ''}`.toLowerCase().includes(complaintSearch.toLowerCase())
    && (complaintStatusFilter === 'All statuses' || c.status === complaintStatusFilter)
    && (complaintWardFilter === 'All wards' || c.ward === complaintWardFilter)
  );

  const pendingPct = totalComplaints > 0 ? (pendingCount / totalComplaints) * 100 : 0;
  const inProgressPct = totalComplaints > 0 ? (inProgressCount / totalComplaints) * 100 : 0;
  const completedPct = totalComplaints > 0 ? (completedCount / totalComplaints) * 100 : 0;

  const sidebarNavItems = [
    { name: 'Dashboard', icon: 'dashboard' },
    { name: 'Complaints', icon: 'report_problem' },
    { name: 'Drivers', icon: 'local_shipping' },
    ...(user?.role === 'admin' ? [{ name: 'Collectors', icon: 'groups' }] : []),
    ...(user?.role === 'admin' ? [{ name: 'Task Verification', icon: 'fact_check' }] : []),
    { name: 'Bins', icon: 'delete' },
    ...(user?.role === 'admin'
      ? [
          { name: 'Reports', icon: 'assessment' },
          { name: 'Notifications', icon: 'notifications' },
        ]
      : []),
    { name: 'Analytics', icon: 'analytics' },
    ...(user?.role === 'admin' && user?.is_super_admin
      ? [{ name: 'Administrators', icon: 'admin_panel_settings' }]
      : []),
  ];

  const getPageHeaderTitle = () => {
    switch (activeTab) {
      case 'Dashboard':
        return 'Municipal Telemetry & OpenStreetMap GIS';
      case 'Complaints':
        return 'Municipal Complaints Management';
      case 'Task Verification':
        return 'Driver Collection Evidence Verification';
      case 'Drivers':
        return 'Municipal Fleet & Driver Directory';
      case 'Collectors':
        return 'Municipal Collector Directory';
      case 'Administrators':
        return 'Restricted Administrator Management';
      case 'Bins':
        return 'Smart Bin Telemetry & Inventory';
      case 'Reports':
        return 'Municipal Compliance & Sustainability Reports';
      case 'Analytics':
        return 'Complaint Analytics & Performance';
      case 'Notifications':
        return 'System Alerts & Communications';
      default:
        return 'EcoPulse AI Admin';
    }
  };

  return (
    <div className="min-h-screen bg-surface-gray font-sans flex text-[#101828] select-none antialiased">
      
      {/* Toast Alert */}
      <AnimatePresence>
        {showNotificationToast && (
          <motion.div
            initial={{ opacity: 0, y: -20, scale: 0.95 }}
            animate={{ opacity: 1, y: 0, scale: 1 }}
            exit={{ opacity: 0, y: -20, scale: 0.95 }}
            transition={{ type: 'spring', stiffness: 300, damping: 25 }}
            className="fixed top-6 right-6 z-[9999] bg-[#005c2b] text-white px-5 py-3 rounded-xl shadow-ambient flex items-center gap-3 font-semibold text-xs border border-white/20"
          >
            <CheckCircle2 className="w-5 h-5 text-success-whatsapp shrink-0" />
            <span>{notificationToastText || 'Action completed.'}</span>
          </motion.div>
        )}
      </AnimatePresence>

      {/* ------------------------------------------------------------- */}
      {/* MOBILE HEADER & DRAWER OVERLAY                                */}
      {/* ------------------------------------------------------------- */}
      <div className="md:hidden fixed top-0 left-0 right-0 h-16 bg-[#003816] text-white flex items-center justify-between px-4 z-[100] shadow-md">
        <div className="flex items-center gap-2.5">
          <button
            onClick={() => setMobileMenuOpen(!mobileMenuOpen)}
            className="p-2 rounded-lg bg-white/10 hover:bg-white/20 text-white cursor-pointer"
            aria-label="Toggle menu"
          >
            <span className="material-symbols-outlined text-xl">{mobileMenuOpen ? 'close' : 'menu'}</span>
          </button>
          <div className="flex items-center gap-2">
            <span className="material-symbols-outlined text-[#b8f0be] text-xl font-bold">eco</span>
            <span className="font-extrabold text-sm tracking-tight">EcoPulse Admin</span>
          </div>
        </div>

        <div className="flex items-center gap-2">
          <button
            onClick={loadData}
            className="p-2 rounded-lg bg-white/10 text-white hover:bg-white/20 cursor-pointer"
            title="Sync Data"
          >
            <RefreshCw className="w-4 h-4" />
          </button>
          <div
            onClick={() => setShowProfileModal(true)}
            className="w-8 h-8 rounded-full bg-[#b8f0be] text-[#003816] flex items-center justify-center font-black text-xs cursor-pointer"
          >
            {user?.name ? user.name.charAt(0).toUpperCase() : 'B'}
          </div>
        </div>
      </div>

      {/* Mobile Drawer Menu */}
      <AnimatePresence>
        {mobileMenuOpen && (
          <>
            <motion.div
              initial={{ opacity: 0 }}
              animate={{ opacity: 1 }}
              exit={{ opacity: 0 }}
              onClick={() => setMobileMenuOpen(false)}
              className="md:hidden fixed inset-0 bg-black/60 backdrop-blur-xs z-[105]"
            />
            <motion.div
              initial={{ x: '-100%' }}
              animate={{ x: 0 }}
              exit={{ x: '-100%' }}
              transition={{ type: 'spring', damping: 25, stiffness: 250 }}
              className="md:hidden fixed left-0 top-0 bottom-0 w-[280px] bg-[#003816] text-white z-[110] flex flex-col py-6 shadow-2xl"
            >
              <div className="px-6 mb-6 flex items-center justify-between">
                <div className="flex items-center gap-2.5">
                  <div className="w-9 h-9 rounded-lg bg-white flex items-center justify-center text-[#00421d] shadow-sm font-bold">
                    <span className="material-symbols-outlined text-xl">eco</span>
                  </div>
                  <div>
                    <h1 className="font-bold text-sm leading-tight text-white">EcoPulse AI</h1>
                    <p className="text-[10px] text-[#b8f0be]/80 font-medium">Admin Portal</p>
                  </div>
                </div>
                <button
                  onClick={() => setMobileMenuOpen(false)}
                  className="p-1.5 rounded-lg bg-white/10 text-white"
                >
                  <X className="w-4 h-4" />
                </button>
              </div>

              <div className="flex-1 overflow-y-auto px-4 space-y-1">
                {sidebarNavItems.map((item) => {
                  const isActive = activeTab === item.name;
                  const isDriverTab = item.name === 'Drivers' && (activeTab === 'Drivers' || activeTab === 'Collectors');
                  const shouldBeHighlighted = isActive || isDriverTab;

                  return (
                    <button
                      key={item.name}
                      onClick={() => {
                        if (item.action) {
                          item.action();
                        } else {
                          setActiveTab(item.name);
                        }
                        setMobileMenuOpen(false);
                      }}
                      className={`w-full flex items-center justify-between px-4 py-3 rounded-lg text-xs font-semibold cursor-pointer ${
                        shouldBeHighlighted
                          ? 'bg-white/10 border-l-4 border-[#b8f0be] text-white font-bold'
                          : 'text-[#84d395]/85 hover:text-white hover:bg-white/5'
                      }`}
                    >
                      <div className="flex items-center gap-3">
                        <span className="material-symbols-outlined text-[18px]">{item.icon}</span>
                        <span>{item.name}</span>
                      </div>
                      {item.badge && (
                        <span className="bg-red-500 text-white text-[9px] px-1.5 py-0.5 rounded-full font-bold">
                          {item.badge}
                        </span>
                      )}
                    </button>
                  );
                })}
              </div>

              <div className="px-4 mt-auto pt-4 border-t border-white/10 space-y-2">
                <button
                  onClick={() => { setShowProfileModal(true); setMobileMenuOpen(false); }}
                  className="w-full flex items-center gap-3 p-2.5 rounded-lg bg-white/5 text-xs font-bold text-white hover:bg-white/10"
                >
                  <User className="w-4 h-4 text-[#b8f0be]" />
                  <span>{user?.name || user?.full_name || 'Municipal Admin'}</span>
                </button>
                <button
                  onClick={handleLogout}
                  className="w-full flex items-center justify-center gap-2 py-2.5 px-3 rounded-lg bg-red-600/20 text-red-300 text-xs font-bold"
                >
                  <span className="material-symbols-outlined text-[16px]">logout</span>
                  <span>Sign Out</span>
                </button>
              </div>
            </motion.div>
          </>
        )}
      </AnimatePresence>

      {/* ------------------------------------------------------------- */}
      {/* LEFT SIDEBAR NAVIGATION: HIGH-CONTRAST SECONDARY GREEN        */}
      {/* ------------------------------------------------------------- */}
      <nav className="hidden md:flex fixed left-0 top-0 h-full w-[280px] bg-[#003816] shadow-[4px_0_24px_rgba(0,0,0,0.15)] flex-col py-6 z-50">
        
        {/* Brand Header with slight hover scaling */}
        <div className="px-6 mb-8">
          <div className="flex items-center gap-3 group cursor-pointer">
            <div className="w-10 h-10 rounded-lg bg-white flex items-center justify-center shadow-md shrink-0 transition-transform duration-300 group-hover:scale-105">
              <span className="material-symbols-outlined text-[#00421d] text-2xl font-bold transition-transform duration-500 group-hover:rotate-[360deg]">eco</span>
            </div>
            <div>
              <h1 className="font-bold text-[15px] leading-tight text-white tracking-tight">EcoPulse AI</h1>
              <p className="text-[11px] text-[#b8f0be]/80 font-medium mt-0.5">Admin Portal</p>
            </div>
          </div>
        </div>

        {/* Navigation List */}
        <div className="flex-1 overflow-y-auto px-4 space-y-1.5">
          {sidebarNavItems.map((item) => {
            const isActive = activeTab === item.name;
            const isDriverTab = item.name === 'Drivers' && (activeTab === 'Drivers' || activeTab === 'Collectors');
            const shouldBeHighlighted = isActive || isDriverTab;

            return (
              <button
                key={item.name}
                onClick={() => {
                  if (item.action) {
                    item.action();
                  } else {
                    setActiveTab(item.name);
                  }
                }}
                className={`w-full flex items-center justify-between px-4 py-3 rounded-lg text-xs font-semibold transition-all duration-200 active:scale-98 cursor-pointer ${
                  shouldBeHighlighted
                    ? 'bg-white/10 border-l-4 border-[#b8f0be] text-white font-bold shadow-[0_0_12px_rgba(184,240,190,0.08)]'
                    : 'text-[#84d395]/85 hover:text-white hover:bg-white/5 hover:pl-5'
                }`}
              >
                <div className="flex items-center gap-3">
                  <span className="material-symbols-outlined text-[20px]">{item.icon}</span>
                  <span>{item.name}</span>
                </div>
                {item.badge && (
                  <span className="bg-red-500 text-white text-[9px] px-1.5 py-0.5 rounded-full font-bold">
                    {item.badge}
                  </span>
                )}
              </button>
            );
          })}
        </div>

        {/* Profile Card & Logout */}
        <div className="px-4 mt-auto pt-4 border-t border-white/10 space-y-3">
          <div
            onClick={() => setShowProfileModal(true)}
            className="flex items-center gap-3 p-2.5 rounded-lg bg-white/5 border border-white/10 hover:border-white/20 transition-all cursor-pointer group"
          >
            <div className="w-8 h-8 rounded-full bg-[#b8f0be] text-[#003816] flex items-center justify-center font-bold text-xs shrink-0 transition-transform duration-300 group-hover:scale-105">
              {user?.name ? user.name.charAt(0).toUpperCase() : 'B'}
            </div>
            <div className="flex-1 min-w-0">
              <div className="text-[11px] font-bold text-white truncate group-hover:text-[#b8f0be] transition-colors">
                {user?.name || user?.full_name || 'Municipal Admin'}
              </div>
              <div className="text-[9px] font-medium text-white/60 truncate">
                {user?.ward || 'Municipal HQ'} • Admin
              </div>
            </div>
            <span className="material-symbols-outlined text-white/40 text-sm group-hover:text-white transition-colors">settings</span>
          </div>
          
          <button
            onClick={handleLogout}
            className="w-full flex items-center justify-center gap-2 py-2.5 px-3 rounded-lg bg-red-600/10 hover:bg-red-600/20 text-red-300 text-xs font-bold transition-all cursor-pointer border border-red-500/20 active:scale-98"
          >
            <span className="material-symbols-outlined text-[16px]">logout</span>
            <span>Sign Out</span>
          </button>
        </div>

      </nav>

      {/* ------------------------------------------------------------- */}
      {/* RIGHT MAIN CONTENT AREA: FIXED TOP-BAR & SCROLLABLE CONTENT   */}
      {/* ------------------------------------------------------------- */}
      <div className="flex-grow ml-0 md:ml-[280px] min-h-screen flex flex-col relative pt-16 md:pt-0">
        
        {/* Top AppBar */}
        <header className="hidden md:flex fixed top-0 right-0 w-[calc(100%-280px)] h-16 bg-white border-b border-border-subtle justify-between items-center px-8 z-40 shadow-xs">
          <div className="flex items-center">
            <h2 className="font-bold text-[16px] text-[#005c2b] tracking-tight">{getPageHeaderTitle()}</h2>
          </div>
          
          <div className="flex items-center gap-4">
            {/* Context Actions based on tab */}
            {activeTab === 'Dashboard' && user?.role === 'admin' && (
              <button
                onClick={handleExport}
                disabled={exporting}
                className="bg-[#005c2b] text-white px-4 py-2 rounded-lg font-semibold text-xs hover:bg-[#004a22] hover:shadow-sm transition-all flex items-center gap-2 shadow-xs cursor-pointer active:scale-98"
              >
                <Download className="w-3.5 h-3.5" />
                <span>{exporting ? 'Exporting...' : 'Export Report'}</span>
              </button>
            )}

            {activeTab === 'Bins' && (
              <button
                onClick={loadData}
                className="bg-[#005c2b] text-white px-4 py-2 rounded-lg font-semibold text-xs hover:bg-[#004a22] hover:shadow-sm transition-all flex items-center gap-2 shadow-xs cursor-pointer active:scale-98"
              >
                <RefreshCw className="w-3.5 h-3.5 animate-spin-slow" />
                <span>Refresh Telemetry</span>
              </button>
            )}

            <button className="p-2 rounded-full text-slate-400 hover:bg-slate-100 hover:text-[#005c2b] transition-all shrink-0">
              <Calendar className="w-4 h-4" />
            </button>

            <button
              onClick={loadData}
              className="p-2 rounded-lg bg-slate-100 hover:bg-slate-200 text-slate-700 hover:text-[#005c2b] transition-all cursor-pointer shrink-0"
              title="Sync PostgreSQL Data"
            >
              <RefreshCw className="w-3.5 h-3.5" />
            </button>

            {/* User Profile Avatar with Online Status Indicator */}
            <div className="relative cursor-pointer shrink-0" onClick={() => setShowProfileModal(true)}>
              <div className="w-8 h-8 rounded-full border border-border-subtle overflow-hidden bg-slate-100 flex items-center justify-center">
                <img
                  alt="Admin"
                  className="w-full h-full object-cover"
                  src="https://lh3.googleusercontent.com/aida-public/AB6AXuCO7E5B130ZuL2MpgYcSu5PD3bNFj_5JCTuTyoveJDJ_SJvF_MhRL2QG4pZmdFcqRWSsgLmiSVNwykEIof30YzfVA3axYAe_Cpd_LqkDnBc1NkBYiKVc4fLyj9_eWB4dsWHoz977isZxXFWDYlMhZKSI70udQjtelgpAVWC7AdOf7GEBaMS0lEIGFwpB5557zwkGiCCJM6UQGqrlwWlQyEjDPmKmkILQr8txzxkLb2a2NglwmaBap6w"
                />
              </div>
              <span className="absolute bottom-0 right-0 w-2.5 h-2.5 bg-success-whatsapp border-2 border-white rounded-full"></span>
            </div>
          </div>
        </header>

        {/* Main Content Area */}
        <main className="flex-1 mt-16 p-8 overflow-y-auto bg-surface-gray">
          
          {/* 1. MAIN DASHBOARD VIEW */}
          {activeTab === 'Dashboard' && (
            <div className="space-y-6">
              {dashboardError && <p role="alert" className="rounded-lg bg-red-50 p-3 text-sm text-red-700">{dashboardError}</p>}
              
              {/* Row 1: KPI Stats */}
              <div className="grid grid-cols-1 md:grid-cols-2 xl:grid-cols-4 gap-6">
                
                <div className="bg-white rounded-xl p-5 border border-border-subtle border-l-4 border-l-[#005c2b] shadow-ambient flex flex-col justify-between h-32 hover:-translate-y-0.5 transition-all duration-300 hover:shadow-md">
                  <div className="flex justify-between items-start">
                    <span className="font-bold text-[11px] text-slate-400 uppercase tracking-wider">Total Complaints</span>
                    <div className="w-8 h-8 rounded-full bg-slate-50 border border-border-subtle flex items-center justify-center text-primary">
                      <span className="material-symbols-outlined text-[18px]">forum</span>
                    </div>
                  </div>
                  <div>
                    <span className="text-3xl font-bold tracking-tight text-slate-900">{displayDashboardMetric(totalComplaints)}</span>
                  </div>
                </div>

                <div className="bg-white rounded-xl p-5 border border-border-subtle border-l-4 border-l-success-whatsapp shadow-ambient flex flex-col justify-between h-32 hover:-translate-y-0.5 transition-all duration-300 hover:shadow-md">
                  <div className="flex justify-between items-start">
                    <span className="font-bold text-[11px] text-slate-400 uppercase tracking-wider">Resolved</span>
                    <div className="w-8 h-8 rounded-full bg-secondary-container flex items-center justify-center text-[#005c2b]">
                      <span className="material-symbols-outlined text-[18px]">check_circle</span>
                    </div>
                  </div>
                  <div>
                    <span className="text-3xl font-bold tracking-tight text-slate-900">{displayDashboardMetric(completedCount)}</span>
                  </div>
                </div>

                <div className="bg-white rounded-xl p-5 border border-border-subtle border-l-4 border-l-status-pending shadow-ambient flex flex-col justify-between h-32 hover:-translate-y-0.5 transition-all duration-300 hover:shadow-md">
                  <div className="flex justify-between items-start">
                    <span className="font-bold text-[11px] text-slate-400 uppercase tracking-wider">In Progress</span>
                    <div className="w-8 h-8 rounded-full bg-[#fbeeb8]/60 flex items-center justify-center text-status-pending">
                      <span className="material-symbols-outlined text-[18px]">hourglass_empty</span>
                    </div>
                  </div>
                  <div>
                    <span className="text-3xl font-bold tracking-tight text-slate-900">{displayDashboardMetric(inProgressCount)}</span>
                  </div>
                </div>

                <div className="bg-white rounded-xl p-5 border border-border-subtle border-l-4 border-l-status-urgent shadow-ambient flex flex-col justify-between h-32 hover:-translate-y-0.5 transition-all duration-300 hover:shadow-md">
                  <div className="flex justify-between items-start">
                    <span className="font-bold text-[11px] text-slate-400 uppercase tracking-wider">Pending</span>
                    <div className="w-8 h-8 rounded-full bg-error-container flex items-center justify-center text-status-urgent">
                      <span className="material-symbols-outlined text-[18px]">warning</span>
                    </div>
                  </div>
                  <div>
                    <span className="text-3xl font-bold tracking-tight text-slate-900">{displayDashboardMetric(pendingCount)}</span>
                  </div>
                </div>

              </div>

              {/* Row 2: Map & Donut Chart */}
              <div className="grid grid-cols-1 xl:grid-cols-12 gap-6">
                
                {/* Telemetry Map */}
                <div className="xl:col-span-8 bg-white rounded-xl border border-border-subtle shadow-ambient flex flex-col overflow-hidden">
                  <div className="p-4 border-b border-border-subtle flex justify-between items-center bg-slate-50">
                    <h3 className="font-bold text-sm text-[#101828]">Reported complaint locations</h3>
                    <span className="text-xs font-semibold text-emerald-700 bg-secondary-container/50 px-2.5 py-0.5 rounded-full border border-success-whatsapp/30">
                      {metrics?.active_trucks ?? '—'} Active Vehicles
                    </span>
                  </div>
                  <div className="relative p-4 flex-1">
                    <InteractiveMap
                      zoom={13}
                      tasks={mapTasks}
                      height="285px"
                    />
                  </div>
                </div>

                {/* Complaint Donut */}
                <div className="xl:col-span-4 bg-white rounded-xl border border-border-subtle shadow-ambient p-5 flex flex-col justify-between">
                  <div className="flex items-center justify-between pb-3 border-b border-border-subtle">
                    <h3 className="font-bold text-sm">Complaint Status Distribution</h3>
                    <span className="text-[10px] font-bold text-slate-500 bg-slate-100 px-2 py-0.5 rounded">
                      API data snapshot
                    </span>
                  </div>

                  <div className="flex flex-col items-center justify-center py-4 flex-1">
                    <div className="relative w-36 h-36 flex items-center justify-center shrink-0">
                      <svg className="w-full h-full transform -rotate-90 drop-shadow-md" viewBox="0 0 36 36">
                        <path
                          className="text-slate-100 stroke-current"
                          strokeWidth="3.8"
                          fill="none"
                          d="M18 2.0845 a 15.9155 15.9155 0 0 1 0 31.831 a 15.9155 15.9155 0 0 1 0 -31.831"
                        />
                        {pendingPct > 0 && (
                          <path
                            className="text-status-urgent stroke-current"
                            strokeWidth="4"
                            strokeDasharray={`${pendingPct}, 100`}
                            strokeDashoffset="0"
                            fill="none"
                            d="M18 2.0845 a 15.9155 15.9155 0 0 1 0 31.831 a 15.9155 15.9155 0 0 1 0 -31.831"
                          />
                        )}
                        {inProgressPct > 0 && (
                          <path
                            className="text-status-pending stroke-current"
                            strokeWidth="4"
                            strokeDasharray={`${inProgressPct}, 100`}
                            strokeDashoffset={`-${pendingPct}`}
                            fill="none"
                            d="M18 2.0845 a 15.9155 15.9155 0 0 1 0 31.831 a 15.9155 15.9155 0 0 1 0 -31.831"
                          />
                        )}
                        {completedPct > 0 && (
                          <path
                            className="text-success-whatsapp stroke-current"
                            strokeWidth="4"
                            strokeDasharray={`${completedPct}, 100`}
                            strokeDashoffset={`-${pendingPct + inProgressPct}`}
                            fill="none"
                            d="M18 2.0845 a 15.9155 15.9155 0 0 1 0 31.831 a 15.9155 15.9155 0 0 1 0 -31.831"
                          />
                        )}
                      </svg>
                      
                      <div className="absolute inset-0 flex flex-col items-center justify-center text-center">
                        <span className="text-2xl font-bold leading-none">{displayDashboardMetric(totalComplaints)}</span>
                        <span className="text-[9px] font-bold text-slate-400 uppercase mt-0.5">Total</span>
                      </div>
                    </div>

                    <div className="w-full grid grid-cols-3 gap-2 mt-4 text-[10px] font-semibold text-slate-600">
                      <div className="flex flex-col items-center p-1 bg-red-50 rounded border border-red-100">
                        <span className="text-status-urgent font-bold">Pending</span>
                        <span className="font-bold">{dashboardLoading ? '…' : dashboardError ? '—' : `${pendingCount} (${Math.round(pendingPct)}%)`}</span>
                      </div>
                      <div className="flex flex-col items-center p-1 bg-yellow-50 rounded border border-yellow-100">
                        <span className="text-status-pending font-bold">Progress</span>
                        <span className="font-bold">{dashboardLoading ? '…' : dashboardError ? '—' : `${inProgressCount} (${Math.round(inProgressPct)}%)`}</span>
                      </div>
                      <div className="flex flex-col items-center p-1 bg-emerald-50 rounded border border-[#a2ecd8]">
                        <span className="text-[#005c2b] font-bold">Resolved</span>
                        <span className="font-bold">{dashboardLoading ? '…' : dashboardError ? '—' : `${completedCount} (${Math.round(completedPct)}%)`}</span>
                      </div>
                    </div>
                  </div>

                  <div className="pt-2.5 border-t border-border-subtle flex items-center justify-between text-[10px] text-slate-400 font-semibold">
                    <span>Request-time data snapshot</span>
                    <span className="text-slate-500 font-bold">No live feed</span>
                  </div>
                </div>

              </div>

              {/* Row 3: Table & Ward Performance */}
              <div className="grid grid-cols-1 xl:grid-cols-12 gap-6">
                
                {/* Complaints Table */}
                <div className="xl:col-span-8 bg-white rounded-xl border border-border-subtle shadow-ambient p-5">
                  <div className="flex items-center justify-between mb-4">
                    <h3 className="font-bold text-sm">Recent Complaints Log</h3>
                    <button
                      onClick={loadData}
                      className="text-xs font-semibold text-blue-600 hover:underline flex items-center gap-1 cursor-pointer"
                    >
                      <RefreshCw className="w-3 h-3" />
                      <span>Sync DB</span>
                    </button>
                  </div>

                  <div className="overflow-x-auto">
                    <table className="w-full text-left text-xs font-semibold text-slate-600">
                      <thead>
                        <tr className="border-b border-border-subtle text-slate-400 font-bold uppercase text-[10px] tracking-wider">
                          <th className="pb-3">Tracking ID</th>
                          <th className="pb-3">Location</th>
                          <th className="pb-3">Type</th>
                          <th className="pb-3">Status</th>
                          <th className="pb-3">Driver Assigned</th>
                        </tr>
                      </thead>
                      <tbody className="divide-y divide-border-subtle">
                        {recentComplaints.slice(0, 4).map((item) => (
                          <tr key={item.id} className="hover:bg-slate-50 transition-colors">
                            <td className="py-3.5 font-bold text-slate-900">{item.id}</td>
                            <td className="py-3.5 text-slate-500 truncate max-w-[200px]">{item.location}</td>
                            <td className="py-3.5 text-slate-700">{item.type}</td>
                            <td className="py-3.5">
                              <span className={`px-2.5 py-0.5 rounded-full text-[10px] font-bold border ${
                                item.status === 'Completed' ? 'bg-[#b6edbb]/50 text-[#005c2b] border-[#005c2b]/30' :
                                item.status === 'In Progress' ? 'bg-yellow-50 text-status-pending border-yellow-200' :
                                'bg-red-50 text-status-urgent border-red-200'
                              }`}>
                                {item.status}
                              </span>
                            </td>
                            <td className="py-3.5 font-bold text-slate-900">
                              {item.assignedTo || 'Unassigned'}
                            </td>
                          </tr>
                        ))}
                      </tbody>
                    </table>
                  </div>
                </div>

                {/* Ward Resolution */}
                <div className="xl:col-span-4 bg-white rounded-xl border border-border-subtle shadow-ambient p-5 flex flex-col justify-between">
                  <div>
                    <div className="flex items-center justify-between mb-4">
                      <h3 className="font-semibold text-sm">Ward Resolution Performance</h3>
                      <span className="text-[10px] font-bold text-[#005c2b] bg-secondary-container px-2 py-0.5 rounded border border-[#a2ecd8]">
                        Top Wards
                      </span>
                    </div>

                    <div className="space-y-4 my-2">
                      {topWards.length ? topWards.map((ward) => (
                        <div key={ward.name} className="flex items-center justify-between gap-3 text-xs font-semibold">
                          <span className="w-16 text-slate-500">{ward.name}</span>
                          <div className="flex-grow bg-slate-100 h-2.5 rounded-full overflow-hidden">
                            <div className="bg-[#005c2b] h-full rounded-full" style={{ width: `${ward.percent}%` }} />
                          </div>
                          <span className="w-10 text-right font-extrabold text-slate-900">{ward.percent}%</span>
                        </div>
                      )) : <p className="text-xs text-slate-500">No ward complaint data available.</p>}
                    </div>
                  </div>

                  <div className="mt-4 p-3 bg-emerald-50 border border-[#a2ecd8] rounded-xl flex items-center justify-between text-[11px] font-semibold text-[#005c2b]">
                    <span className="flex items-center gap-1.5">
                      <span>Average reported ward resolution</span>
                    </span>
                    <span className="font-bold">{averageWardResolution === null ? '—' : `${averageWardResolution}%`}</span>
                  </div>
                </div>

              </div>

            </div>
          )}

          {activeTab === 'Task Verification' && user?.role === 'admin' && (
            <section className="space-y-5">
              <div className="flex flex-wrap items-center justify-between gap-3">
                <div><h3 className="text-lg font-bold">Collection evidence review</h3><p className="text-sm text-slate-600">Only Municipal Admins can approve completion.</p></div>
                <select value={verificationStatus} onChange={event => setVerificationStatus(event.target.value)} className="rounded-lg border p-2 text-sm">
                  <option>Pending Verification</option><option>Requires Rework</option><option>Completed</option>
                </select>
              </div>
              {verificationError && <p role="alert" className="rounded-lg bg-red-50 p-3 text-sm text-red-700">{verificationError}</p>}
              <div className="grid gap-5 xl:grid-cols-[minmax(260px,1fr)_2fr]">
                <div className="space-y-2">
                  {verificationTasks.map(task => <button key={task.id} onClick={() => setSelectedVerification(task)} className={`w-full rounded-xl border p-3 text-left ${selectedVerification?.id === task.id ? 'border-primary bg-emerald-50' : 'border-slate-200 bg-white'}`}>
                    <span className="block text-sm font-bold">Task #{task.id} · {task.location_name}</span><span className="text-xs text-slate-600">{task.driver_name || 'Driver'} · {task.status}</span>
                  </button>)}
                  {!verificationTasks.length && <p className="rounded-xl bg-white p-5 text-sm text-slate-600">No tasks in this review state.</p>}
                </div>
                {selectedVerification ? <article className="space-y-4 rounded-xl border bg-white p-5">
                  <div><h4 className="font-bold">Complaint {selectedVerification.complaint?.tracking_number || `#${selectedVerification.complaint?.id}`}</h4><p className="text-sm text-slate-600">{selectedVerification.complaint?.ward} · {selectedVerification.complaint?.location_address} · {selectedVerification.complaint?.waste_type}</p><p className="mt-1 text-sm">{selectedVerification.complaint?.description}</p></div>
                  {selectedVerification.evidence?.map(item => <div key={item.id} className="space-y-3 border-t pt-4">
                    <div className="grid gap-3 sm:grid-cols-2">{item.before_image_url && <figure><img src={item.before_image_url} alt="Before collection" className="max-h-64 w-full rounded-lg object-contain"/><figcaption className="text-xs">Before collection</figcaption></figure>}<figure><img src={item.after_image_url} alt="After collection" className="max-h-64 w-full rounded-lg object-contain"/><figcaption className="text-xs">After collection</figcaption></figure></div>
                    <p className="text-sm">{item.notes || 'No collection notes.'}</p><p className="text-xs text-slate-500">Collected: {item.collected_at ? new Date(item.collected_at).toLocaleString() : '—'} · Evidence {item.status}</p>
                    {item.rejection_reason && <p className="text-sm text-red-700">Previous rejection: {item.rejection_reason}</p>}
                  </div>)}
                  <div className="border-t pt-3"><h5 className="font-semibold">Verification history</h5><ol className="mt-2 space-y-1 text-xs text-slate-600">{selectedVerification.history?.map((event, index) => <li key={`${event.event_type}-${index}`}>{new Date(event.created_at).toLocaleString()} · {event.event_type.replaceAll('_', ' ')} · {event.from_status || '—'} → {event.to_status || '—'}{event.details ? ` · ${event.details}` : ''}</li>)}</ol></div>
                  {selectedVerification.status === 'Pending Verification' && <div className="space-y-2 border-t pt-4"><textarea value={reviewReason} onChange={event => setReviewReason(event.target.value)} maxLength={2000} placeholder="Required reason if rejecting evidence" className="w-full rounded-lg border p-2 text-sm"/><div className="flex gap-2"><button disabled={verificationBusy} onClick={() => reviewTask(true)} className="rounded-lg bg-primary px-4 py-2 text-sm font-bold text-white">Approve completion</button><button disabled={verificationBusy || !reviewReason.trim()} onClick={() => reviewTask(false)} className="rounded-lg bg-red-700 px-4 py-2 text-sm font-bold text-white">Reject for rework</button></div></div>}
                </article> : <p className="rounded-xl border bg-white p-6 text-sm text-slate-600">Select a task to inspect its evidence and history.</p>}
              </div>
            </section>
          )}

          {/* 2. COMPLAINTS VIEW */}
          {activeTab === 'Complaints' && (
            <div className="space-y-6">
              {dashboardError && <p role="alert" className="rounded-lg bg-red-50 p-3 text-sm text-red-700">{dashboardError}</p>}
              
              {/* Stats Grid */}
              <div className="grid grid-cols-1 md:grid-cols-2 xl:grid-cols-4 gap-6">
                <div className="bg-white border border-border-subtle border-l-4 border-l-[#005c2b] rounded-xl p-5 shadow-ambient flex flex-col justify-between h-28 hover:shadow-md transition-shadow">
                  <span className="font-bold text-[11px] text-slate-400 uppercase tracking-wider">Total Complaints</span>
                  <div className="flex justify-between items-baseline">
                    <span className="text-3xl font-bold">{displayDashboardMetric(totalComplaints)}</span>
                  </div>
                </div>
                <div className="bg-white border border-border-subtle border-l-4 border-l-success-whatsapp rounded-xl p-5 shadow-ambient flex flex-col justify-between h-28 hover:shadow-md transition-shadow">
                  <span className="font-bold text-[11px] text-slate-400 uppercase tracking-wider">Resolved</span>
                  <div className="flex justify-between items-baseline">
                    <span className="text-3xl font-bold">{displayDashboardMetric(completedCount)}</span>
                  </div>
                </div>
                <div className="bg-white border border-border-subtle border-l-4 border-l-status-pending rounded-xl p-5 shadow-ambient flex flex-col justify-between h-28 hover:shadow-md transition-shadow">
                  <span className="font-bold text-[11px] text-slate-400 uppercase tracking-wider">In Progress</span>
                  <div className="flex justify-between items-baseline">
                    <span className="text-3xl font-bold">{displayDashboardMetric(inProgressCount)}</span>
                  </div>
                </div>
                <div className="bg-white border border-border-subtle border-l-4 border-l-status-urgent rounded-xl p-5 shadow-ambient flex flex-col justify-between h-28 hover:shadow-md transition-shadow">
                  <span className="font-bold text-[11px] text-slate-400 uppercase tracking-wider">Pending</span>
                  <div className="flex justify-between items-baseline">
                    <span className="text-3xl font-bold">{displayDashboardMetric(pendingCount)}</span>
                  </div>
                </div>
              </div>

              {/* Layout: Table + Activity Feed */}
              <div className="grid grid-cols-1 xl:grid-cols-12 gap-6">
                
                {/* Table card */}
                <div className="xl:col-span-8 bg-white border border-border-subtle rounded-xl shadow-ambient flex flex-col h-full min-h-[500px]">
                  <div className="p-4 border-b border-border-subtle flex flex-col sm:flex-row justify-between items-start sm:items-center gap-4 bg-slate-50">
                    <h3 className="font-bold text-sm">All Municipal Complaints</h3>
                    <div className="flex flex-wrap gap-2 w-full sm:w-auto">
                      <div className="relative w-full sm:w-60">
                        <Search className="w-4 h-4 text-slate-400 absolute left-3 top-2.5" />
                        <input
                          value={complaintSearch}
                          onChange={(e) => setComplaintSearch(e.target.value)}
                          className="w-full bg-white border border-border-subtle rounded-lg py-1.5 pl-9 pr-3 text-xs font-semibold focus:outline-none focus:border-[#005c2b]"
                          placeholder="Search complaint, area..."
                          type="text"
                        />
                      </div>
                      <label className="sr-only" htmlFor="complaint-status-filter">Filter complaints by status</label>
                      <select id="complaint-status-filter" value={complaintStatusFilter} onChange={event => setComplaintStatusFilter(event.target.value)} className="bg-white border border-border-subtle rounded-lg px-2 py-1.5 text-xs">
                        <option>All statuses</option><option>Pending</option><option>In Progress</option><option>Pending Verification</option><option>Completed</option>
                      </select>
                      <label className="sr-only" htmlFor="complaint-ward-filter">Filter complaints by ward</label>
                      <select id="complaint-ward-filter" value={complaintWardFilter} onChange={event => setComplaintWardFilter(event.target.value)} className="bg-white border border-border-subtle rounded-lg px-2 py-1.5 text-xs">
                        <option>All wards</option>{complaintWards.map(ward => <option key={ward}>{ward}</option>)}
                      </select>
                    </div>
                  </div>

                  <div className="overflow-x-auto flex-1">
                    <table className="w-full text-left text-xs font-semibold text-slate-600">
                      <thead>
                        <tr className="border-b border-border-subtle bg-slate-50 text-slate-400 font-bold uppercase text-[10px] tracking-wider">
                          <th className="py-3 px-4">Tracking ID</th>
                          <th className="py-3 px-4">Reporter</th>
                          <th className="py-3 px-4">Type</th>
                          <th className="py-3 px-4">Ward</th>
                          <th className="py-3 px-4">Date/Time</th>
                          <th className="py-3 px-4">Status</th>
                          <th className="py-3 px-4 text-right">Actions</th>
                        </tr>
                      </thead>
                      <tbody className="divide-y divide-border-subtle">
                        {dashboardLoading ? <tr><td colSpan={7} className="p-8 text-center text-slate-500">Loading complaints…</td></tr> : filteredComplaints.length === 0 ? <tr><td colSpan={7} className="p-8 text-center text-slate-500">{dashboardError ? 'Complaint records are unavailable.' : 'No complaints match these filters.'}</td></tr> : filteredComplaints.map((item) => (
                            <tr key={item.id} className="hover:bg-slate-50/50 transition-colors">
                              <td className="py-3.5 px-4 font-bold text-slate-900">{item.id}</td>
                              <td className="py-3.5 px-4 text-slate-500">Privacy protected</td>
                              <td className="py-3.5 px-4">
                                <div className="flex items-center space-x-2">
                                  <span className={`w-2 h-2 rounded-full ${
                                    item.type.includes('Overflow') ? 'bg-status-urgent' : 'bg-secondary'
                                  }`}></span>
                                  <span>{item.type}</span>
                                </div>
                              </td>
                              <td className="py-3.5 px-4">{item.ward || 'Unassigned'}</td>
                              <td className="py-3.5 px-4 text-slate-500">{item.time || '—'}</td>
                              <td className="py-3.5 px-4">
                                <span className={`px-2 py-0.5 rounded-full text-[10px] font-bold border ${
                                  item.status === 'Completed' ? 'bg-[#b6edbb]/50 text-[#005c2b] border-[#005c2b]/30' :
                                  item.status === 'In Progress' ? 'bg-yellow-50 text-status-pending border-yellow-200' :
                                  'bg-red-50 text-status-urgent border-red-200'
                                }`}>
                                  {item.status}
                                </span>
                              </td>
                              <td className="py-3.5 px-4 text-right">
                                <div className="flex justify-end gap-2">
                                  <button type="button" onClick={() => openComplaintDetails(item)} className="rounded-lg border border-slate-200 px-2.5 py-1 text-[10px] font-bold hover:bg-slate-100">Details</button>
                                  {item.status !== 'Completed' && <select
                                    aria-label={`Assign Driver to complaint ${item.id}`}
                                    value=""
                                    disabled={assigningId === item.db_id}
                                    onChange={(e) => handleDriverAssignment(item.db_id, e.target.value)}
                                    className="max-w-44 px-2.5 py-1 bg-slate-50 border border-slate-200 rounded-lg text-[10px] font-bold text-slate-800 focus:outline-none focus:border-[#005c2b] cursor-pointer"
                                  >
                                    <option value="">{assigningId === item.db_id ? 'Assigning…' : (item.assignedTo && item.assignedTo !== 'Unassigned' ? `Reassign · ${item.assignedTo}` : 'Assign Driver…')}</option>
                                    {availableDrivers.filter(driver => driver.ward && (['', 'unassigned'].includes((item.ward || '').trim().toLowerCase()) || driver.ward.trim().toLowerCase() === item.ward.trim().toLowerCase())).map((driver) => (
                                      <option key={driver.id} value={driver.value}>{driver.label}</option>
                                    ))}
                                  </select>}
                                </div>
                              </td>
                            </tr>
                          ))}
                      </tbody>
                    </table>
                  </div>

                  <div className="p-4 border-t border-border-subtle flex justify-between items-center bg-slate-50 rounded-b-xl">
                    <span className="text-slate-500">Showing {filteredComplaints.length} recorded complaints</span>
                    {complaintActionError && <span role="alert" className="text-red-700">{complaintActionError}</span>}
                  </div>
                </div>

                {/* Timeline activity list */}
                <div className="xl:col-span-4 bg-white border border-border-subtle rounded-xl shadow-ambient p-5 flex flex-col h-full min-h-[500px]">
                  <h3 className="font-semibold text-sm pb-2 border-b border-border-subtle mb-4">Recent Activity Timeline</h3>
                  <div className="relative flex-1">
                    <div className="absolute left-[15px] top-2 bottom-4 w-px bg-border-subtle" />
                    <div className="space-y-6 relative">
                      {recentComplaints.slice(0, 5).map((complaint) => (
                        <div className="flex items-start" key={complaint.db_id}>
                          <div className="w-8 h-8 rounded-full bg-slate-100 flex items-center justify-center text-[#005c2b] border-2 border-white z-10 shadow-sm">
                            <Check className="w-4 h-4" />
                          </div>
                          <div className="ml-3 flex-grow">
                            <p className="text-xs font-bold text-slate-900">
                              Complaint {complaint.id}: {complaint.status}
                            </p>
                            <p className="text-[10px] text-slate-500 mt-0.5">
                              {complaint.ward || 'Ward not recorded'} • {complaint.time || 'Date unavailable'}
                            </p>
                          </div>
                        </div>
                      ))}
                      {recentComplaints.length === 0 && (
                        <p className="text-xs text-slate-500">No complaint activity is available.</p>
                      )}
                    </div>
                  </div>
                  <button onClick={() => setActiveTab('Complaints')} className="mt-4 w-full text-center py-2.5 text-[#005c2b] border border-border-subtle rounded-lg text-xs font-bold hover:bg-slate-50 transition-colors cursor-pointer">
                    View Complaints
                  </button>
                </div>

              </div>

            </div>
          )}

          {/* 3. DRIVERS VIEW */}
          {(activeTab === 'Drivers' || activeTab === 'Collectors') && (
            <div className="space-y-6">
              
              {/* Context Image Header Banner */}
              <div className="w-full h-44 rounded-xl overflow-hidden shadow-sm relative group border border-border-subtle">
                <img
                  alt="Telemetry Context Illustration"
                  className="w-full h-full object-cover opacity-80"
                  src="https://lh3.googleusercontent.com/aida/AP1WRLsx8Y3kT3_RVi7TL0sPvWkeQ17n0t6FdoXG88omtcz8KGSwL_4prMJ6Npgg-LPtW-Sl2O0UpaCyyKp_JHsHlkdTIzAST9uQT8X_iG5T5YirHvPUJH8jZRRHNC8XWKXnxHBQm9ktrQE-LAS5y6A1odryIXPxbbTD3ugj3g3GIVHZ1hagZ_g9twT9tfbaKKyxii_r-04SMUcQpGIq02RssbHOeTm-5zYXPbfwzMZCXwLMOsQCfdunCWOjnw"
                />
                <div className="absolute inset-0 bg-gradient-to-t from-[#003816]/90 to-transparent flex items-end p-6">
                  <div>
                    <p className="text-[#b8f0be] font-bold text-xs uppercase tracking-wider mb-1">Ecosystem Context</p>
                    <h3 className="text-white font-bold text-lg">{activeTab === 'Collectors' ? 'Municipal Collector Directory' : 'Municipal Driver Directory'}</h3>
                  </div>
                </div>
              </div>

              {/* Metrics Row */}
              <div className="grid grid-cols-1 md:grid-cols-2 lg:grid-cols-4 gap-6">
                <div className="bg-white border border-border-subtle rounded-xl p-5 shadow-ambient hover:shadow-md transition-shadow">
                  <p className="font-bold text-xs text-slate-400 uppercase tracking-wider mb-2 flex items-center gap-1.5">
                    <User className="w-4 h-4 text-slate-400" />
                    <span>Total Drivers</span>
                  </p>
                  <div className="flex items-baseline gap-2">
                    <span className="text-3xl font-bold">{loadingDrivers ? '…' : driversError ? '—' : drivers.filter(d => d.role === (activeTab === 'Collectors' ? 'collector' : 'driver')).length}</span>
                    <span className="text-[10px] font-bold bg-[#b6edbb]/50 text-[#005c2b] px-2 py-0.5 rounded-full">registered</span>
                  </div>
                </div>
                <div className="bg-white border border-[#EAECF0] rounded-xl p-5 shadow-ambient border-t-4 border-t-[#005c2b] hover:shadow-md transition-shadow">
                  <p className="font-bold text-xs text-[#005c2b] uppercase tracking-wider mb-2 flex items-center gap-1.5">
                    <Truck className="w-4 h-4 text-[#005c2b]" />
                    <span>Active</span>
                  </p>
                  <div className="flex items-baseline gap-2">
                    <span className="text-3xl font-bold">{loadingDrivers ? '…' : driversError ? '—' : drivers.filter(d => d.role === (activeTab === 'Collectors' ? 'collector' : 'driver') && d.is_active).length}</span>
                    <span className="text-xs text-slate-500 font-semibold">On Roster</span>
                  </div>
                </div>
                <div className="bg-white border border-[#EAECF0] rounded-xl p-5 shadow-ambient border-t-4 border-t-status-pending hover:shadow-md transition-shadow">
                  <p className="font-bold text-xs text-status-pending uppercase tracking-wider mb-2 flex items-center gap-1.5">
                    <Coffee className="w-4 h-4 text-status-pending" />
                    <span>Tasks Done</span>
                  </p>
                  <div className="flex items-baseline gap-2">
                    <span className="text-3xl font-bold">{loadingDrivers ? '…' : driversError ? '—' : drivers.filter(d => d.role === (activeTab === 'Collectors' ? 'collector' : 'driver')).reduce((sum, d) => sum + (d.tasks_completed || 0), 0)}</span>
                    <span className="text-xs text-slate-500 font-semibold">Total</span>
                  </div>
                </div>
                <div className="bg-white border border-[#EAECF0] rounded-xl p-5 shadow-ambient border-t-4 border-t-slate-400 hover:shadow-md transition-shadow">
                  <p className="font-bold text-xs text-slate-400 uppercase tracking-wider mb-2 flex items-center gap-1.5">
                    <Power className="w-4 h-4 text-slate-400" />
                    <span>Inactive</span>
                  </p>
                  <div className="flex items-baseline gap-2">
                    <span className="text-3xl font-bold">{loadingDrivers ? '…' : driversError ? '—' : drivers.filter(d => d.role === (activeTab === 'Collectors' ? 'collector' : 'driver') && !d.is_active).length}</span>
                    <span className="text-xs text-slate-500 font-semibold">Deactivated</span>
                  </div>
                </div>
              </div>

              {/* Filter Toolbar */}
              {user?.role !== 'admin' && (
                <p className="rounded-lg border border-amber-200 bg-amber-50 p-3 text-xs font-semibold text-amber-900">
                  Driver provisioning is restricted to authorized Admin accounts.
                </p>
              )}
              {activeTab === 'Collectors' && <p className="rounded-lg border border-blue-100 bg-blue-50 p-3 text-xs text-blue-900">Collectors receive ward assignments during provisioning. Suspension and reactivation remain restricted to Super Admin governance.</p>}
              {user?.role === 'admin' && ['Collectors', 'Drivers'].includes(activeTab) && <div className="space-y-3">
                <StaffCredentialNotice credential={staffCredential} onDismiss={() => setStaffCredential(null)} />
                <StaffProvisioningPanel
                  key={activeTab}
                  allowedRoles={[activeTab === 'Collectors' ? 'collector' : 'driver']}
                  onCreated={(credentials) => { setStaffCredential(credentials); loadDrivers(); }}
                />
              </div>}
              <div className="flex flex-col sm:flex-row justify-between items-center gap-4">
                <div className="relative w-full sm:w-80">
                  <Search className="w-4 h-4 text-slate-400 absolute left-3 top-2.5" />
                  <input
                    value={driverSearch}
                    onChange={(e) => setDriverSearch(e.target.value)}
                    className="w-full bg-white border border-border-subtle rounded-lg py-1.5 pl-9 pr-3 text-xs font-semibold focus:outline-none focus:border-[#005c2b]"
                  placeholder="Search by name, login ID, or ward..."
                    type="text"
                  />
                </div>
                <label className="w-full text-xs font-semibold text-slate-600 sm:w-auto">Ward
                  <select value={staffWardFilter} onChange={(event) => setStaffWardFilter(event.target.value)} className="ml-2 rounded-lg border border-border-subtle bg-white px-3 py-2 text-xs">
                    <option value="all">All wards</option>
                    {wardRegistry.map((ward) => <option key={ward.id} value={String(ward.id)}>Ward {ward.ward_number} — {ward.display_name}{ward.is_active ? '' : ' (inactive)'}</option>)}
                  </select>
                </label>
                <label className="w-full text-xs font-semibold text-slate-600 sm:w-auto">Account status
                  <select aria-label="Filter staff by account status" value={staffLifecycleFilter} onChange={(event) => setStaffLifecycleFilter(event.target.value)} className="ml-2 rounded-lg border border-border-subtle bg-white px-3 py-2 text-xs">
                    <option value="all">All</option><option value="active">Active</option><option value="suspended">Suspended</option><option value="retired">Retired</option>
                  </select>
                </label>
                <div className="flex gap-2 w-full sm:w-auto">
                </div>
              </div>

              {/* Driver Grid roster cards — REAL DB DATA */}
              {driversError ? <p role="alert" className="rounded-lg bg-red-50 p-3 text-sm text-red-700">{driversError}</p> : loadingDrivers ? (
                <div className="text-center py-12 text-slate-400 font-semibold text-sm">Loading staff from database...</div>
              ) : filteredStaffAccounts.length === 0 ? (
                <div className="text-center py-12 text-slate-400 font-semibold text-sm">No {activeTab.toLowerCase()} found.</div>
              ) : (
              <div className="grid grid-cols-1 md:grid-cols-2 lg:grid-cols-3 gap-6">
                {filteredStaffAccounts.map((driver) => (
                  <div key={driver.id} className="bg-white border border-border-subtle rounded-xl p-5 shadow-ambient relative group hover:shadow-md transition-all duration-300">
                    <div className="absolute top-4 right-4">
                      <span className={`px-2.5 py-0.5 rounded-full text-[10px] font-bold border flex items-center gap-1.5 ${
                        driver.is_active ? 'bg-[#b6edbb]/40 text-[#005c2b] border-[#b6edbb]' : 'bg-slate-100 text-slate-400 border-slate-200'
                      }`}>
                        <span className={`w-1.5 h-1.5 rounded-full ${driver.is_active ? 'bg-success-whatsapp' : 'bg-slate-400'}`}></span>
                        <span>{driver.is_active ? 'Active' : 'Inactive'}</span>
                      </span>
                      <span className="mt-1 block text-right text-[9px] font-semibold text-slate-500">
                        {driver.is_verified ? 'Verified' : 'Verification pending'} · {driver.account_status}
                      </span>
                      <span className="mt-1 block text-right text-[9px] font-semibold text-slate-500">
                        Invitation: {driver.invitation_status || 'unavailable'}{driver.invitation_expires_at && driver.invitation_status === 'pending' ? ` · expires ${new Date(driver.invitation_expires_at).toLocaleString()}` : ''}
                      </span>
                    </div>

                    <div className="flex items-start gap-4 mb-4">
                      <div className="w-16 h-16 rounded-full border-2 border-[#b6edbb] bg-[#b6edbb]/20 flex items-center justify-center text-[#005c2b] font-bold text-xl shadow-sm shrink-0 transition-transform duration-300 group-hover:scale-105">
                        {driver.full_name.charAt(0)}
                      </div>
                      <div className="pt-1.5">
                        <h4 className="font-bold text-sm text-[#101828]">{driver.full_name}</h4>
                        <p className="text-[11px] text-slate-400 font-semibold flex items-center gap-1 mt-0.5">
                          <span className="material-symbols-outlined text-sm">badge</span> {driver.login_id || 'No login ID'}{driver.employee_id ? ` · Official ID ${driver.employee_id}` : ''}
                        </p>
                        <p className="text-[10px] text-slate-400 mt-0.5">{driver.email}</p>
                      </div>
                    </div>

                    <div className="grid grid-cols-2 gap-4 border-y border-border-subtle py-3 mb-4 text-xs font-semibold text-slate-500">
                      <div>
                        <span className="block text-[9px] uppercase tracking-wider text-slate-400">Ward</span>
                        <span className="text-slate-900 font-bold flex items-center gap-1 mt-0.5">
                          <span className="material-symbols-outlined text-sm text-[#005c2b]">location_on</span>
                          <span>{driver.ward_id ? `${wardRegistry.find(ward => ward.id === driver.ward_id)?.display_name || driver.ward} · ${wardRegistry.find(ward => ward.id === driver.ward_id)?.municipality_name || ''}` : driver.ward || 'N/A'}</span>
                        </span>
                      </div>
                      <div>
                        <span className="block text-[9px] uppercase tracking-wider text-slate-400">Activation</span>
                        <span className="text-slate-900 font-bold">{driver.activated_at ? new Date(driver.activated_at).toLocaleDateString() : 'Not activated'}</span>
                      </div>
                      <div>
                        <span className="block text-[9px] uppercase tracking-wider text-slate-400">Tasks Done</span>
                        <span className="text-slate-900 font-bold flex items-center gap-1 mt-0.5">
                          <span className="material-symbols-outlined text-sm text-[#005c2b]">check_circle</span>
                          <span>{driver.tasks_completed}</span>
                        </span>
                      </div>
                      <div>
                        <span className="block text-[9px] uppercase tracking-wider text-slate-400">EcoCoins</span>
                        <span className="text-slate-900 font-bold flex items-center gap-1 mt-0.5">
                          <span className="material-symbols-outlined text-sm text-status-pending">paid</span>
                          <span>{driver.eco_coins}</span>
                        </span>
                      </div>
                      <div>
                        <span className="block text-[9px] uppercase tracking-wider text-slate-400">In Progress</span>
                        <span className="text-slate-900 font-bold flex items-center gap-1 mt-0.5">
                          <span className="material-symbols-outlined text-sm text-status-pending">pending</span>
                          <span>{driver.tasks_in_progress}</span>
                        </span>
                      </div>
                    </div>

                    <div className="flex gap-2">
                      {user?.role === 'admin' && <select aria-label={`Reassign ward for ${driver.full_name}`} disabled={staffActionBusy === driver.id || ['retired', 'deactivated'].includes(driver.account_status)} value={driver.ward_id ? String(driver.ward_id) : ''} onChange={event => handleWardAssignment(driver, event.target.value)} className="max-w-44 rounded-lg border border-slate-300 bg-white px-2 py-2 text-xs"><option value="">Select ward</option>{wardRegistry.filter(ward => ward.is_active).map(ward => <option key={ward.id} value={String(ward.id)}>Ward {ward.ward_number} — {ward.display_name}</option>)}</select>}
                      {driver.is_active ? (
                        <button
                          onClick={() => setActiveTab('Dashboard')}
                          className="flex-1 bg-[#005c2b] text-white font-semibold text-xs py-2.5 rounded-lg flex items-center justify-center gap-2 hover:bg-[#004a22] transition-colors cursor-pointer active:scale-98"
                        >
                          <MapPin className="w-3.5 h-3.5" />
                          <span>View on Map</span>
                        </button>
                      ) : (
                        <button className="flex-1 bg-slate-100 text-slate-400 font-semibold text-xs py-2.5 rounded-lg flex items-center justify-center gap-2 cursor-not-allowed border border-border-subtle">
                          <span>Tracking Paused</span>
                        </button>
                      )}
                      {user?.role === 'admin' && driver.account_status !== 'retired' && driver.account_status !== 'deactivated' && <>
                        {driver.account_status === 'active' && <button onClick={() => handleStaffStatus(driver)} disabled={staffActionBusy === driver.id} className="rounded-lg border border-red-200 px-3 py-2 text-xs font-bold text-red-700 disabled:opacity-50">Suspend</button>}
                        {driver.account_status === 'suspended' && <button onClick={async () => { if (!window.confirm(`Reactivate ${driver.full_name}? Existing sessions remain revoked.`)) return; setStaffActionBusy(driver.id); try { await updateStaffAccountStatus(driver.id, 'active'); await loadDrivers(); } catch (error) { setDriversError(error.response?.data?.detail || 'Account could not be reactivated.'); } finally { setStaffActionBusy(null); } }} disabled={staffActionBusy === driver.id || !driver.is_verified} className="rounded-lg border border-emerald-200 px-3 py-2 text-xs font-bold text-emerald-800 disabled:opacity-50">Reactivate</button>}
                        <button onClick={async () => { const reason = window.prompt(`Reason to permanently retire ${driver.full_name} (required):`); if (!reason || reason.trim().length < 3) return; if (!window.confirm(`Permanently retire ${driver.full_name}? This cannot be undone and existing sessions will be revoked.`)) return; setStaffActionBusy(driver.id); try { await updateStaffAccountStatus(driver.id, 'retired', reason.trim()); await loadDrivers(); } catch (error) { setDriversError(error.response?.data?.detail || 'Account could not be retired.'); } finally { setStaffActionBusy(null); } }} disabled={staffActionBusy === driver.id} className="rounded-lg border border-red-300 px-3 py-2 text-xs font-bold text-red-900 disabled:opacity-50">Retire</button>
                      </>}
                      {user?.role === 'admin' && !['retired', 'deactivated'].includes(driver.account_status) && <button type="button" onClick={() => handleStaffPasswordReset(driver)} disabled={staffActionBusy === driver.id}
                        className="rounded-lg border border-amber-300 px-3 py-2 text-xs font-bold text-amber-900 disabled:opacity-50">{staffActionBusy === driver.id ? 'Issuing…' : 'Reset password'}</button>}
                      {user?.role === 'admin' && <button type="button" onClick={() => openAccountHistory(driver)} className="rounded-lg border border-slate-200 px-3 py-2 text-xs font-bold text-slate-700">Details / history</button>}
                    </div>
                  </div>
                ))}
              </div>
              )}

              {/* Roster footer */}
              <div className="p-4 bg-white rounded-xl border border-border-subtle flex justify-between items-center shadow-ambient text-xs font-semibold">
                <span className="text-slate-500">Showing {filteredStaffAccounts.length} {activeTab.toLowerCase()} accounts</span>
                <button onClick={loadDrivers} className="text-[#005c2b] font-bold flex items-center gap-1.5 hover:underline cursor-pointer">
                  <RefreshCw className="w-3.5 h-3.5" /> Sync DB
                </button>
              </div>

            </div>
          )}

          {activeTab === 'Administrators' && user?.is_super_admin && (
            <div className="space-y-6">
              <StaffCredentialNotice credential={staffCredential} onDismiss={() => setStaffCredential(null)} />
              <StaffProvisioningPanel allowedRoles={['admin']} onCreated={(credentials) => { setStaffCredential(credentials); loadAdministrators(); }} />

              <section className="overflow-hidden rounded-xl border border-border-subtle bg-white shadow-ambient">
                <div className="border-b border-border-subtle p-4">
                  <h2 className="text-sm font-extrabold text-slate-900">Administrator accounts</h2>
                  <p className="mt-1 text-xs text-slate-500">Account, verification and MFA status. Changes revoke existing sessions.</p>
                </div>
                <div className="overflow-x-auto">
                  <table className="w-full min-w-[700px] text-left text-xs">
                    <thead className="bg-slate-50 text-slate-500">
                      <tr><th className="p-3">Employee</th><th className="p-3">Status</th><th className="p-3">Verified</th><th className="p-3">Invitation</th><th className="p-3">MFA</th><th className="p-3">Action</th></tr>
                    </thead>
                    <tbody>
                      {administrators.map((account) => (
                        <tr key={account.id} className="border-t border-slate-100">
                          <td className="p-3"><strong>{account.full_name}</strong><span className="block text-slate-500">Official ID: {account.employee_id || 'Unavailable'}</span><span className="block text-slate-500">Login ID: {account.login_id || 'Unavailable'}</span></td>
                          <td className="p-3">{account.account_status}</td>
                          <td className="p-3">{account.is_verified ? 'Verified' : 'Pending'}</td>
                          <td className="p-3">
                            {account.invitation_status || 'not_invited'}
                            {account.invitation_status === 'pending' && account.invitation_expires_at && (
                              <span className="block text-slate-500">expires {new Date(account.invitation_expires_at).toLocaleString()}</span>
                            )}
                          </td>
                          <td className="p-3">{account.mfa_enabled ? 'Enrolled' : 'Required'}</td>
                          <td className="p-3">
                            {!account.is_super_admin && (
                              <div className="flex gap-2">
                                {account.account_status !== 'retired' && account.account_status !== 'deactivated' && <button onClick={async () => { if (!window.confirm(`Issue a new one-time password for ${account.full_name}? Existing sessions will be revoked.`)) return; try { setStaffCredential(await issueStaffTemporaryPassword(account.id)); loadAdministrators(); } catch (error) { setAdministratorError(error.response?.data?.detail || 'Temporary password could not be issued.'); } }}
                                  className="rounded border border-amber-300 px-2.5 py-1 font-bold text-amber-900">Reset password</button>}
                                {account.account_status === 'active' && <button onClick={() => handleAccountStatus(account, 'suspended')} className="rounded border border-red-200 px-2.5 py-1 font-bold text-red-700">Suspend</button>}
                                {account.account_status === 'suspended' && <button onClick={() => handleAccountStatus(account, 'active')} className="rounded border border-emerald-200 px-2.5 py-1 font-bold text-emerald-800">Reactivate</button>}
                                {account.account_status !== 'retired' && account.account_status !== 'deactivated' && <button onClick={() => handleAccountStatus(account, 'retired')} className="rounded border border-red-300 px-2.5 py-1 font-bold text-red-900">Retire</button>}
                              </div>
                            )}
                          </td>
                        </tr>
                      ))}
                      {administrators.length === 0 && <tr><td colSpan="6" className="p-5 text-center text-slate-500">No administrator records found.</td></tr>}
                    </tbody>
                  </table>
                </div>
              </section>

              <section className="rounded-xl border border-border-subtle bg-white p-4 shadow-ambient">
                <h2 className="text-sm font-extrabold text-slate-900">Security audit history</h2>
                <div className="mt-3 max-h-72 overflow-y-auto divide-y divide-slate-100">
                  {securityAuditEvents.map((event) => (
                    <div key={event.id} className="flex flex-wrap justify-between gap-2 py-2 text-xs">
                      <span className="font-semibold">{event.action} · {event.target_employee_id || 'system'}</span>
                      <time className="text-slate-500">{event.created_at ? new Date(event.created_at).toLocaleString() : ''}</time>
                    </div>
                  ))}
                  {securityAuditEvents.length === 0 && <p className="py-3 text-xs text-slate-500">No audit events recorded.</p>}
                </div>
              </section>
            </div>
          )}

          {/* 4. BINS VIEW */}
          {activeTab === 'Bins' && (
            <div className="space-y-6">
              
              {/* Bins Overview Cards — REAL API DATA */}
              <div className="grid grid-cols-1 md:grid-cols-2 xl:grid-cols-4 gap-6">
                <div className="bg-white border border-border-subtle rounded-xl p-5 shadow-ambient flex flex-col justify-between h-28 hover:shadow-md transition-shadow">
                  <span className="font-bold text-[11px] text-slate-400 uppercase tracking-wider">Total Bins</span>
                  <div className="flex justify-between items-baseline">
                    <span className="text-3xl font-bold">{binsData?.total_bins ?? '...'}</span>
                    <span className="text-[10px] text-[#005c2b] font-bold bg-[#b6edbb]/40 px-2 py-0.5 rounded-full">Avg {binsData?.avg_fill_level ?? 0}% full</span>
                  </div>
                </div>
                <div className="bg-white border border-border-subtle rounded-xl p-5 shadow-ambient flex flex-col justify-between h-28 border-t-4 border-t-status-urgent hover:shadow-md transition-shadow">
                  <span className="font-bold text-[11px] text-slate-400 uppercase tracking-wider">Critical (&ge;80%)</span>
                  <div className="flex justify-between items-baseline">
                    <span className="text-3xl font-bold">{binsData?.critical_bins ?? '...'}</span>
                    <span className="text-[10px] text-status-urgent font-bold bg-red-50 border border-red-200 px-2 py-0.5 rounded-full">Requires collection</span>
                  </div>
                </div>
                <div className="bg-white border border-border-subtle rounded-xl p-5 shadow-ambient flex flex-col justify-between h-28 border-t-4 border-t-status-pending hover:shadow-md transition-shadow">
                  <span className="font-bold text-[11px] text-slate-400 uppercase tracking-wider">Warning (60–79%)</span>
                  <div className="flex justify-between items-baseline">
                    <span className="text-3xl font-bold">{binsData?.warning_bins ?? '...'}</span>
                    <span className="text-[10px] text-status-pending font-bold bg-yellow-50 border border-yellow-200 px-2 py-0.5 rounded-full">Monitor closely</span>
                  </div>
                </div>
                <div className="bg-white border border-border-subtle rounded-xl p-5 shadow-ambient flex flex-col justify-between h-28 border-t-4 border-t-[#005c2b] hover:shadow-md transition-shadow">
                  <span className="font-bold text-[11px] text-slate-400 uppercase tracking-wider">Normal (&lt;60%)</span>
                  <div className="flex justify-between items-baseline">
                    <span className="text-3xl font-bold">{binsData?.normal_bins ?? '...'}</span>
                    <span className="text-[10px] text-[#005c2b] font-bold bg-[#b6edbb]/40 px-2 py-0.5 rounded-full">Operating normally</span>
                  </div>
                </div>
              </div>

              <div className="rounded-xl border border-border-subtle bg-white p-5 shadow-ambient">
                <h3 className="mb-4 text-sm font-bold">Bins requiring attention</h3>
                {binsError ? (
                  <p role="alert" className="text-sm font-semibold text-red-700">{binsError}</p>
                ) : !binsData ? (
                  <p className="text-sm font-medium text-slate-500">Loading bin telemetry…</p>
                ) : binsNeedingAttention.length ? (
                  <div className="space-y-3">
                    {binsNeedingAttention.map((bin) => (
                      <div key={bin.id} className="flex items-center justify-between gap-4 rounded-lg border border-border-subtle bg-slate-50 p-3">
                        <div>
                          <p className="text-xs font-bold">{bin.bin_code}</p>
                          <p className="mt-1 text-[10px] text-slate-500">{bin.location_name} · {bin.ward}</p>
                        </div>
                        <span className="rounded bg-yellow-50 px-2.5 py-1 text-xs font-bold text-status-pending">
                          {bin.fill_level_pct}% full
                        </span>
                      </div>
                    ))}
                  </div>
                ) : (
                  <p className="text-sm font-medium text-slate-500">No active bins require attention.</p>
                )}
              </div>

              {/* Bins Table assets list — REAL API DATA */}
              <div className="bg-white border border-border-subtle rounded-xl shadow-ambient overflow-hidden">
                <div className="p-5 border-b border-border-subtle flex flex-col sm:flex-row justify-between items-start sm:items-center gap-4 bg-slate-50">
                  <h3 className="font-bold text-sm">Bin Asset Roster</h3>
                  <div className="flex gap-2 w-full sm:w-auto">
                    <div className="relative w-full sm:w-60">
                      <Search className="w-4 h-4 text-slate-400 absolute left-3 top-2.5" />
                      <input
                        value={binSearch}
                        onChange={(e) => setBinSearch(e.target.value)}
                        className="w-full bg-white border border-border-subtle rounded-lg py-1.5 pl-9 pr-3 text-xs font-semibold focus:outline-none focus:border-[#005c2b]"
                        placeholder="Search bins..."
                        type="text"
                      />
                    </div>
                    <button onClick={loadBins} className="bg-white border border-border-subtle px-3 py-1.5 rounded-lg text-xs font-bold hover:bg-slate-100 flex items-center gap-1 cursor-pointer shadow-sm">
                      <RefreshCw className="w-3.5 h-3.5" />
                    </button>
                  </div>
                </div>

                <div className="overflow-x-auto">
                  <table className="w-full text-left text-xs font-semibold text-slate-600">
                    <thead>
                      <tr className="border-b border-border-subtle bg-slate-50 text-slate-400 font-bold uppercase text-[10px] tracking-wider">
                        <th className="py-3.5 px-6">Bin ID</th>
                        <th className="py-3.5 px-6">Location</th>
                        <th className="py-3.5 px-6">Ward</th>
                        <th className="py-3.5 px-6">Type</th>
                        <th className="py-3.5 px-6">Fill Level</th>
                        <th className="py-3.5 px-6">Status</th>
                      </tr>
                    </thead>
                    <tbody className="divide-y divide-border-subtle">
                      {(binsData?.bins || []).filter(b =>
                        b.bin_code.toLowerCase().includes(binSearch.toLowerCase()) ||
                        b.location_name.toLowerCase().includes(binSearch.toLowerCase()) ||
                        b.ward.toLowerCase().includes(binSearch.toLowerCase())
                      ).map((bin) => (
                        <tr key={bin.id} className="hover:bg-slate-50/50 transition-colors">
                          <td className="py-4 px-6 font-bold text-[#005c2b]">{bin.bin_code}</td>
                          <td className="py-4 px-6 text-slate-500">{bin.location_name}</td>
                          <td className="py-4 px-6 text-slate-500">{bin.ward}</td>
                          <td className="py-4 px-6">
                            <span className="px-2 py-0.5 rounded-full text-[10px] font-bold bg-slate-100 text-slate-600">{bin.bin_type}</span>
                          </td>
                          <td className="py-4 px-6 w-48">
                            <div className="flex items-center gap-2">
                              <div className="flex-1 h-2 bg-slate-100 rounded-full overflow-hidden">
                                <div className={`h-full rounded-full ${
                                  bin.fill_level_pct >= 80 ? 'bg-status-urgent' : (bin.fill_level_pct >= 60 ? 'bg-status-pending' : 'bg-success-whatsapp')
                                }`} style={{ width: `${bin.fill_level_pct}%` }}></div>
                              </div>
                              <span className={`font-bold ${
                                bin.fill_level_pct >= 80 ? 'text-status-urgent' : (bin.fill_level_pct >= 60 ? 'text-status-pending' : 'text-[#005c2b]')
                              }`}>{bin.fill_level_pct}%</span>
                            </div>
                          </td>
                          <td className="py-4 px-6">
                            <span className={`px-2.5 py-0.5 rounded-full text-[10px] font-bold border ${
                              bin.fill_level_pct >= 80 ? 'bg-red-50 text-status-urgent border-red-200' :
                              bin.fill_level_pct >= 60 ? 'bg-yellow-50 text-status-pending border-yellow-200' :
                              'bg-[#b6edbb]/30 text-[#005c2b] border-[#b6edbb]/50'
                            }`}>
                              {bin.fill_level_pct >= 80 ? 'Critical' : bin.fill_level_pct >= 60 ? 'Warning' : 'Normal'}
                            </span>
                          </td>
                        </tr>
                      ))}
                    </tbody>
                  </table>
                </div>

                <div className="px-6 py-4 border-t border-border-subtle bg-slate-50 flex justify-between items-center text-xs font-semibold">
                  <span className="text-slate-500">Showing {(binsData?.bins || []).length} bins from database</span>
                </div>
              </div>

            </div>
          )}

          {activeTab === 'Reports' && (
            <section className="space-y-5">
              <div className="rounded-xl border border-border-subtle bg-white p-6 shadow-ambient">
                <h3 className="text-xl font-bold">Complaint report</h3>
                <p className="mt-1 text-sm font-medium text-slate-600">
                  Export current complaint records from the municipal database.
                </p>
                <button
                  type="button"
                  onClick={handleExport}
                  disabled={exporting}
                  className="mt-4 inline-flex items-center gap-2 rounded-lg bg-[#005c2b] px-4 py-2.5 text-sm font-bold text-white disabled:opacity-60"
                >
                  <Download className="h-4 w-4" />
                  {exporting ? 'Exporting…' : 'Download complaint CSV'}
                </button>
                {exportError && <p role="alert" className="mt-3 text-sm font-semibold text-red-700">{exportError}</p>}
              </div>

              <div className="rounded-xl border border-border-subtle bg-white p-5 shadow-ambient">
                <h3 className="mb-4 text-sm font-bold">Current complaint metrics</h3>
                {dashboardError ? (
                  <p role="alert" className="text-sm font-semibold text-red-700">{dashboardError}</p>
                ) : dashboardLoading ? (
                  <p className="text-sm font-medium text-slate-500">Loading report data…</p>
                ) : !metrics ? (
                  <p className="text-sm font-medium text-slate-500">Complaint metrics are unavailable.</p>
                ) : (
                  <div className="grid grid-cols-1 gap-4 sm:grid-cols-3">
                    <p className="rounded-lg bg-slate-50 p-4 text-sm">
                      Total: <strong>{metrics.total_complaints}</strong>
                    </p>
                    <p className="rounded-lg bg-slate-50 p-4 text-sm">
                      Pending: <strong>{metrics.pending_complaints}</strong>
                    </p>
                    <p className="rounded-lg bg-slate-50 p-4 text-sm">
                      Completed: <strong>{metrics.completed_complaints}</strong>
                    </p>
                  </div>
                )}
              </div>
            </section>
          )}

          {/* 6. ANALYTICS VIEW */}
          {activeTab === 'Analytics' && (
            <div className="space-y-6">
              
              <div className="grid grid-cols-12 gap-6">
                <section className="col-span-12 rounded-xl border border-border-subtle bg-white p-5 shadow-ambient">
                  <h3 className="mb-5 text-sm font-bold">Monthly complaint activity</h3>
                  {analyticsError ? (
                    <p role="alert" className="text-sm font-semibold text-red-700">{analyticsError}</p>
                  ) : analyticsLoading ? (
                    <p className="text-sm font-medium text-slate-500">Loading analytics…</p>
                  ) : analyticsData?.monthly_trends?.length ? (
                    <div className="grid grid-cols-2 gap-4 sm:grid-cols-3 lg:grid-cols-6">
                      {analyticsData.monthly_trends.map((month) => {
                        const maxComplaints = Math.max(
                          ...analyticsData.monthly_trends.map((trend) => trend.complaints),
                          1
                        );
                        const height = Math.round((month.complaints / maxComplaints) * 100);
                        return (
                          <div key={`${month.month}-${month.complaints}`} className="flex flex-col items-center gap-2">
                            <span className="text-xs font-bold text-slate-700">{month.complaints}</span>
                            <div className="flex h-32 w-full items-end rounded bg-slate-50">
                              <div
                                className="w-full rounded bg-[#005c2b]"
                                style={{ height: `${height}%` }}
                                title={`${month.complaints} complaints`}
                              />
                            </div>
                            <span className="text-xs font-semibold text-slate-500">{month.month}</span>
                            <span className="text-[10px] text-slate-500">{month.resolved} resolved</span>
                          </div>
                        );
                      })}
                    </div>
                  ) : (
                    <p className="py-6 text-center text-sm font-medium text-slate-500">
                      No monthly complaint data is available yet.
                    </p>
                  )}
                </section>
              </div>

              <div className="grid grid-cols-1 gap-6 lg:grid-cols-2">
                <section className="rounded-xl border border-border-subtle bg-white p-5 shadow-ambient">
                  <h3 className="mb-4 text-sm font-bold">Complaint resolution by ward</h3>
                  {analyticsError ? (
                    <p role="alert" className="text-sm font-semibold text-red-700">{analyticsError}</p>
                  ) : analyticsLoading ? (
                    <p className="text-sm font-medium text-slate-500">Loading analytics…</p>
                  ) : analyticsData?.ward_breakdown?.length ? (
                    <div className="space-y-4">
                      {analyticsData.ward_breakdown.map((ward) => {
                        const pct = ward.total > 0 ? Math.round((ward.resolved / ward.total) * 100) : 0;
                        return (
                          <div key={ward.ward} className="flex items-center gap-4 text-xs font-semibold">
                            <span className="w-20 truncate text-slate-600">{ward.ward}</span>
                            <div className="h-2 flex-grow overflow-hidden rounded-full bg-slate-100">
                              <div className="h-full rounded-full bg-[#005c2b]" style={{ width: `${pct}%` }} />
                            </div>
                            <span className="w-20 text-right text-slate-900">{pct}% ({ward.total})</span>
                          </div>
                        );
                      })}
                    </div>
                  ) : (
                    <p className="py-6 text-center text-sm font-medium text-slate-500">
                      No ward complaint data is available yet.
                    </p>
                  )}
                </section>

                <section className="rounded-xl border border-border-subtle bg-white p-5 shadow-ambient">
                  <h3 className="mb-4 text-sm font-bold">Reported waste types</h3>
                  {analyticsError ? (
                    <p role="alert" className="text-sm font-semibold text-red-700">{analyticsError}</p>
                  ) : analyticsLoading ? (
                    <p className="text-sm font-medium text-slate-500">Loading analytics…</p>
                  ) : analyticsData?.top_waste_types?.length ? (
                    <ul className="space-y-3">
                      {analyticsData.top_waste_types.map(({ type, count }) => (
                        <li key={type} className="flex justify-between rounded bg-slate-50 px-3 py-2 text-sm">
                          <span className="font-medium text-slate-700">{type || 'Unspecified'}</span>
                          <strong>{count}</strong>
                        </li>
                      ))}
                    </ul>
                  ) : (
                    <p className="py-6 text-center text-sm font-medium text-slate-500">
                      No waste-type data is available yet.
                    </p>
                  )}
                </section>
              </div>

            </div>
          )}

          {/* 7. NOTIFICATIONS VIEW */}
          {activeTab === 'Notifications' && (
            <div className="space-y-6">
              
              <div className="grid grid-cols-12 gap-6">
                
                {/* Alert summary stats — REAL API DATA */}
                <div className="col-span-12 lg:col-span-4 bg-white border border-border-subtle rounded-xl p-5 shadow-ambient flex flex-col justify-between h-fit">
                  <h3 className="font-bold text-sm mb-4">Notification Summary</h3>
                  <div className="space-y-3 font-semibold text-xs">
                    
                    <div className="flex justify-between items-center p-3 rounded-lg bg-red-50 border border-red-100 text-status-urgent">
                      <div className="flex items-center gap-2">
                        <span className="material-symbols-outlined">error</span>
                        <span>Critical in-app records</span>
                      </div>
                      <span className="text-2xl font-bold">{notificationMetric(notifications.filter(n => n.notification_type === 'Critical').length)}</span>
                    </div>

                    <div className="flex justify-between items-center p-3 rounded-lg bg-yellow-50 border border-yellow-100 text-status-pending">
                      <div className="flex items-center gap-2">
                        <span className="material-symbols-outlined">warning</span>
                        <span>Warning records</span>
                      </div>
                      <span className="text-2xl font-bold">{notificationMetric(notifications.filter(n => n.notification_type === 'Warning').length)}</span>
                    </div>

                    <div className="flex justify-between items-center p-3 rounded-lg bg-slate-50 border border-border-subtle text-slate-600">
                      <div className="flex items-center gap-2">
                        <span className="material-symbols-outlined">info</span>
                        <span>Info Logs</span>
                      </div>
                      <span className="text-2xl font-bold">{notificationMetric(notifications.filter(n => n.notification_type === 'Info').length)}</span>
                    </div>

                    <div className="flex justify-between items-center p-3 rounded-lg bg-[#b6edbb]/20 border border-[#b6edbb] text-[#005c2b]">
                      <div className="flex items-center gap-2">
                        <span className="material-symbols-outlined">campaign</span>
                        <span>In-app announcements</span>
                      </div>
                        <span className="text-2xl font-bold">{notificationMetric(notifications.filter(n => n.is_broadcast).length)}</span>
                    </div>

                  </div>
                </div>

                {/* In-app announcement composer */}
                <div className="col-span-12 lg:col-span-8 bg-white border border-border-subtle rounded-xl p-5 shadow-ambient flex flex-col justify-between">
                  <h3 className="font-bold text-sm mb-4 flex items-center gap-1.5">
                    <span className="material-symbols-outlined text-[#005c2b]">campaign</span>
                    <span>In-app announcements</span>
                  </h3>
                  
                  <div className="space-y-4 text-xs font-semibold">
                    <p className="rounded-lg border border-blue-100 bg-blue-50 p-3 text-xs text-blue-900">Announcements are saved to the in-app notification feed and history. SMS and push delivery are not configured.</p>

                    <div>
                      <label className="block text-slate-500 mb-1">Announcement</label>
                      <textarea
                        value={broadcastContent}
                        onChange={(e) => setBroadcastContent(e.target.value)}
                        className="w-full border border-border-subtle rounded-lg py-2 px-3 focus:outline-none focus:border-[#005c2b] resize-none"
                        placeholder="Enter an in-app announcement..."
                        rows={3}
                        maxLength={4000}
                      />
                    </div>

                    <div className="flex justify-end gap-2">
                      <button
                        onClick={() => setBroadcastContent('')}
                        className="px-4 py-2 border border-border-subtle rounded-lg bg-white text-slate-600 hover:bg-slate-50 transition-colors cursor-pointer"
                      >
                        Cancel
                      </button>
                      <button
                        onClick={handleAddBroadcast}
                        disabled={sendingBroadcast || !broadcastContent.trim()}
                        className="px-4 py-2 bg-[#005c2b] text-white rounded-lg hover:bg-[#004a22] transition-colors flex items-center gap-1.5 shadow-sm cursor-pointer active:scale-98 disabled:opacity-50"
                      >
                        <Send className="w-3.5 h-3.5" />
                        <span>{sendingBroadcast ? 'Saving…' : 'Save in-app announcement'}</span>
                      </button>
                    </div>
                    {notificationsError && <p role="alert" className="text-xs text-red-700">{notificationsError}</p>}
                  </div>
                </div>

              </div>

              {/* Feed Card — REAL API DATA */}
              <div className="bg-white border border-border-subtle rounded-xl shadow-ambient overflow-hidden h-[450px] flex flex-col">
                <div className="p-4 border-b border-border-subtle bg-slate-50 flex justify-between items-center">
                  <h3 className="font-bold text-sm">In-app notification history</h3>
                  <div className="flex gap-1.5">
                    <button onClick={loadNotifications} className="px-2.5 py-1 bg-white border border-border-subtle rounded text-[10px] font-bold hover:bg-slate-50 cursor-pointer shadow-2xs flex items-center gap-1">
                      <RefreshCw className="w-3 h-3" />
                    </button>
                  </div>
                </div>

                <div className="flex-grow overflow-y-auto p-4 space-y-3.5 pr-1">
                  {notificationsLoading ? <p role="status" className="py-12 text-center text-sm text-slate-500">Loading in-app notifications…</p> : notificationsError ? <p role="alert" className="rounded-lg bg-red-50 p-3 text-sm text-red-700">{notificationsError}</p> : notifications.length === 0 ? (
                    <div className="text-center py-12 text-slate-400 font-semibold text-sm">No notifications yet.</div>
                  ) : notifications.map((notif) => {
                    const typeStyles = {
                      Critical: { bg: 'bg-red-50/70 border-red-150 text-[#ba1a1a]', iconBg: 'bg-[#ffdad6] text-[#93000a]' },
                      Warning: { bg: 'bg-yellow-50/70 border-yellow-150 text-status-pending', iconBg: 'bg-[#FEF3C7] text-status-pending' },
                      Info: { bg: 'bg-[#f1f3ff] border-border-subtle text-primary', iconBg: 'bg-secondary-container text-[#00210a]' },
                    };
                    const styles = typeStyles[notif.notification_type] || typeStyles.Info;
                    const timeAgo = new Date(notif.created_at).toLocaleDateString();
                    return (
                      <div key={notif.id} className={`flex gap-4 p-4 rounded-lg border ${styles.bg} transition-colors ${notif.is_read ? 'opacity-70' : ''}`}>
                        <div className={`flex-shrink-0 w-9 h-9 rounded-full ${styles.iconBg} flex items-center justify-center shadow-2xs`}>
                          <span className="material-symbols-outlined text-[20px]">{notif.icon}</span>
                        </div>
                        <div className="flex-1">
                          <div className="flex justify-between items-start mb-0.5">
                            <span className="text-[10px] font-bold uppercase tracking-wider">{notif.notification_type} {notif.is_broadcast ? '(Broadcast)' : 'Alert'}</span>
                            <span className="text-[10px] text-slate-400 font-semibold">{timeAgo}</span>
                          </div>
                          <h4 className="font-bold text-xs text-slate-900">{notif.title}</h4>
                          <p className="text-[11px] text-slate-500 mt-0.5">{notif.message}</p>
                          <p className="mt-1 text-[10px] text-slate-500">In-app record · Audience label: {notif.audience || 'unspecified'} · {notif.is_read ? 'Read' : 'Unread'}</p>
                        </div>
                        {!notif.is_read && <button type="button" disabled={notificationBusy === notif.id} onClick={() => handleMarkNotificationRead(notif.id)} className="self-start rounded border border-slate-200 bg-white px-2 py-1 text-[10px] font-bold disabled:opacity-50">{notificationBusy === notif.id ? 'Saving…' : 'Mark read'}</button>}
                      </div>
                    );
                  })}
                </div>
              </div>

            </div>
          )}

        </main>
      </div>

      {selectedComplaint && (
        <div className="fixed inset-0 z-[210] flex items-center justify-center bg-slate-950/60 p-4" onMouseDown={event => { if (event.target === event.currentTarget) setSelectedComplaint(null); }}>
          <section role="dialog" aria-modal="true" aria-labelledby="complaint-detail-title" className="max-h-[90vh] w-full max-w-3xl overflow-y-auto rounded-2xl bg-white p-5 shadow-2xl sm:p-7">
            <div className="mb-5 flex items-start justify-between gap-4">
              <div><h2 id="complaint-detail-title" className="text-lg font-extrabold">Complaint {selectedComplaint.id}</h2><p className="mt-1 text-sm text-slate-600">{selectedComplaint.ward || 'Ward unassigned'} · {selectedComplaint.location}</p></div>
              <button type="button" onClick={() => setSelectedComplaint(null)} aria-label="Close complaint details" className="rounded-lg p-2 hover:bg-slate-100"><X className="h-4 w-4" /></button>
            </div>
            {complaintDetailsLoading ? <p role="status" className="py-8 text-center text-sm text-slate-500">Loading complaint operations…</p> : complaintDetailsError ? <p role="alert" className="rounded-lg bg-red-50 p-3 text-sm text-red-700">{complaintDetailsError}</p> : complaintOperations && (
              <div className="space-y-5">
                <dl className="grid gap-3 rounded-xl bg-slate-50 p-4 text-sm sm:grid-cols-2">
                  <div><dt className="text-xs text-slate-500">Type</dt><dd className="font-semibold">{complaintOperations.complaint.type}</dd></div>
                  <div><dt className="text-xs text-slate-500">Complaint status</dt><dd className="font-semibold">{complaintOperations.complaint.status}</dd></div>
                  <div><dt className="text-xs text-slate-500">Assigned Driver</dt><dd className="font-semibold">{complaintOperations.complaint.assignedTo || 'Unassigned'}</dd></div>
                  <div><dt className="text-xs text-slate-500">Reported</dt><dd className="font-semibold">{complaintOperations.complaint.time ? new Date(complaintOperations.complaint.time).toLocaleString() : 'Unavailable'}</dd></div>
                  <div className="sm:col-span-2"><dt className="text-xs text-slate-500">Description</dt><dd className="whitespace-pre-wrap font-medium">{complaintOperations.complaint.description || 'No description supplied.'}</dd></div>
                </dl>
                <section className="rounded-xl border border-slate-200 p-4">
                  <h3 className="font-bold">Collection task and evidence</h3>
                  {!complaintOperations.task ? <p className="mt-2 text-sm text-slate-600">No task is assigned yet.</p> : <>
                    <p className="mt-2 text-sm text-slate-700">Task #{complaintOperations.task.id} · {complaintOperations.task.status}</p>
                    {complaintOperations.task.evidence?.length ? complaintOperations.task.evidence.map(item => <article key={item.id} className="mt-4 space-y-2 border-t pt-3">
                      <div className="grid gap-3 sm:grid-cols-2">
                        {item.before_image_url && <figure><img src={item.before_image_url} alt="Before collection evidence" className="max-h-56 w-full rounded-lg object-contain"/><figcaption className="text-xs text-slate-500">Before collection</figcaption></figure>}
                        {item.after_image_url && <figure><img src={item.after_image_url} alt="After collection evidence" className="max-h-56 w-full rounded-lg object-contain"/><figcaption className="text-xs text-slate-500">After collection</figcaption></figure>}
                      </div>
                      <p className="text-sm">Evidence: {item.status} · {item.notes || 'No collection notes.'}</p>
                      {item.rejection_reason && <p className="rounded bg-red-50 p-2 text-sm text-red-800">Rejection reason: {item.rejection_reason}</p>}
                    </article>) : <p className="mt-2 text-sm text-slate-600">No collection evidence has been submitted.</p>}
                    {complaintOperations.task.history?.length > 0 && <details className="mt-4"><summary className="cursor-pointer text-sm font-semibold">Task history ({complaintOperations.task.history.length})</summary><ol className="mt-2 space-y-1 text-xs text-slate-600">{complaintOperations.task.history.map((event, index) => <li key={`${event.event_type}-${index}`}>{new Date(event.created_at).toLocaleString()} · {event.event_type.replaceAll('_', ' ')} · {event.details || 'No additional details'}</li>)}</ol></details>}
                  </>}
                </section>
                {user?.role === 'admin' && complaintOperations.task && ['Pending Verification', 'Requires Rework', 'Completed'].includes(complaintOperations.task.status) && <button type="button" onClick={() => { setVerificationStatus(complaintOperations.task.status); setSelectedVerification(complaintOperations.task); setActiveTab('Task Verification'); setSelectedComplaint(null); }} className="rounded-lg bg-[#005c2b] px-4 py-2 text-sm font-bold text-white">Open task verification workflow</button>}
              </div>
            )}
          </section>
        </div>
      )}

      {/* Staff invitations are provisioned with the offline CLI; no token enters dashboard state. */}

      {accountDetails && <div className="fixed inset-0 z-50 flex items-center justify-center bg-slate-950/50 p-4"><section role="dialog" aria-modal="true" aria-labelledby="staff-account-history" className="max-h-[85vh] w-full max-w-2xl overflow-y-auto rounded-2xl bg-white p-5 shadow-xl"><div className="flex items-start justify-between gap-3"><div><h2 id="staff-account-history" className="text-lg font-bold">{accountDetails.full_name} · Account details</h2><p className="text-sm text-slate-500">{accountDetails.role} · {accountDetails.account_status}</p></div><button type="button" onClick={() => setAccountDetails(null)} aria-label="Close account details" className="rounded-lg p-2">×</button></div><dl className="mt-4 grid gap-3 rounded-xl bg-slate-50 p-4 text-sm sm:grid-cols-2"><div><dt className="text-xs text-slate-500">Official employee ID</dt><dd>{accountDetails.employee_id || 'Unavailable'}</dd></div><div><dt className="text-xs text-slate-500">Login ID</dt><dd>{accountDetails.login_id || 'Unavailable'}</dd></div><div><dt className="text-xs text-slate-500">Phone / email</dt><dd>{accountDetails.phone || 'Unavailable'} · {accountDetails.email || 'Unavailable'}</dd></div><div><dt className="text-xs text-slate-500">Ward</dt><dd>{accountDetails.ward || 'Unavailable'}</dd></div><div><dt className="text-xs text-slate-500">Verified / MFA</dt><dd>{accountDetails.is_verified ? 'Verified' : 'Unverified'} · {accountDetails.mfa_enabled ? 'Enrolled' : 'Not enrolled'}</dd></div></dl><h3 className="mt-5 font-bold">Account history</h3><div className="mt-2 space-y-2">{accountHistory.map(event => <article key={event.id} className="rounded-lg border border-slate-200 p-3 text-sm"><p className="font-semibold">{event.action} · {event.actor_employee_id || 'Actor unavailable'}</p><p>{event.details || 'Details unavailable'}</p><p className="text-xs text-slate-500">{event.created_at ? new Date(event.created_at).toLocaleString() : 'Unavailable'}</p></article>)}{!accountHistory.length && <p className="text-sm text-slate-500">No account history is recorded.</p>}</div></section></div>}

      <ProfileModal
        isOpen={showProfileModal}
        onClose={() => setShowProfileModal(false)}
        user={user}
        onProfileUpdated={handleProfileUpdated}
      />

    </div>
  );
};

export default AdminDashboardPage;
