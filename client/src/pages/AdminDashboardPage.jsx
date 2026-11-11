import React, { useState, useEffect } from 'react';
import { useNavigate } from 'react-router-dom';
import {
  fetchAdminMetrics, fetchAdminComplaints, assignDriverTask, downloadAdminExportCSV,
  fetchAdminDrivers, registerAdminDriver, toggleDriverStatus,
  fetchAdminBins, fetchAdminAnalytics,
  fetchAdminNotifications, sendAdminBroadcast, markNotificationRead
} from '../services/adminService';
import { getCurrentUser, logoutUser } from '../services/authService';
import ProfileModal from '../components/ProfileModal';
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
  Filter,
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
  const [user, setUser] = useState(null);
  const [showNotificationToast, setShowNotificationToast] = useState(false);
  const [showProfileModal, setShowProfileModal] = useState(false);
  const [dateRange, setDateRange] = useState('Oct 24, 2026');
  const [exporting, setExporting] = useState(false);
  const [assigningId, setAssigningId] = useState(null);

  const [metrics, setMetrics] = useState(null);
  const [recentComplaints, setRecentComplaints] = useState([]);

  // Real API data states
  const [drivers, setDrivers] = useState([]);
  const [binsData, setBinsData] = useState(null);
  const [analyticsData, setAnalyticsData] = useState(null);
  const [notifications, setNotifications] = useState([]);
  const [loadingDrivers, setLoadingDrivers] = useState(false);
  const [showRegisterDriverModal, setShowRegisterDriverModal] = useState(false);
  const [registerDriverForm, setRegisterDriverForm] = useState({ full_name: '', email: '', phone: '', employee_id: '', ward: 'Ward 12', password: 'Password123!' });
  const [registeringDriver, setRegisteringDriver] = useState(false);
  const [sendingBroadcast, setSendingBroadcast] = useState(false);

  // Custom states for sub-views inputs
  const [complaintSearch, setComplaintSearch] = useState('');
  const [driverSearch, setDriverSearch] = useState('');
  const [binSearch, setBinSearch] = useState('');
  
  const [reportDateRange, setReportDateRange] = useState('Last 7 Days');
  const [reportWard, setReportWard] = useState('All Wards');
  const [reportTonnage, setReportTonnage] = useState(true);
  const [reportFuel, setReportFuel] = useState(true);
  const [reportComplaints, setReportComplaints] = useState(false);
  const [reportGenerating, setReportGenerating] = useState(false);
  const [simulatedReports, setSimulatedReports] = useState([
    { name: 'Weekly Waste Audit - W42', category: 'Waste Tracking', desc: 'Tonnage by Ward, Landfill Diversion', date: 'Oct 24, 2026', time: '08:00 AM', status: 'Ready' },
    { name: 'Q3 Sustainability Impact', category: 'Environmental', desc: 'Emissions Reduced, Recycling Rates', date: 'Oct 01, 2026', time: '10:15 AM', status: 'Ready' },
    { name: 'Driver Efficiency - Sept 2026', category: 'Operations', desc: 'Route Completion, Idling Time, Fuel Use', date: 'Sep 30, 2026', time: '11:45 PM', status: 'Ready' }
  ]);
  const [broadcastAudience, setBroadcastAudience] = useState('All Drivers (Active Shift)');
  const [broadcastPriority, setBroadcastPriority] = useState('Standard (App Notification)');
  const [broadcastContent, setBroadcastContent] = useState('');

  const loadData = async () => {
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
    }
  };

  const loadDrivers = async () => {
    setLoadingDrivers(true);
    try {
      const data = await fetchAdminDrivers();
      setDrivers(data);
    } catch (err) {
      console.error('Error loading drivers:', err);
    } finally {
      setLoadingDrivers(false);
    }
  };

  const loadBins = async () => {
    try {
      const data = await fetchAdminBins();
      setBinsData(data);
    } catch (err) {
      console.error('Error loading bins:', err);
    }
  };

  const loadAnalytics = async () => {
    try {
      const data = await fetchAdminAnalytics();
      setAnalyticsData(data);
    } catch (err) {
      console.error('Error loading analytics:', err);
    }
  };

  const loadNotifications = async () => {
    try {
      const data = await fetchAdminNotifications();
      if (data && data.length > 0) setNotifications(data);
    } catch (err) {
      console.error('Error loading notifications:', err);
    }
  };

  useEffect(() => {
    getCurrentUser().then((userData) => {
      if (userData) {
        setUser(userData);
      } else {
        navigate('/login', { replace: true });
      }
    });
    // Load all dashboard data in parallel
    loadData();
    loadDrivers();
    loadBins();
    loadAnalytics();
    loadNotifications();
  }, []);

  const handleLogout = () => {
    logoutUser();
    navigate('/login');
  };

  const handleExport = async () => {
    setExporting(true);
    try {
      await downloadAdminExportCSV();
      setShowNotificationToast(true);
      setTimeout(() => setShowNotificationToast(false), 3500);
    } catch (err) {
      console.error('Error exporting CSV:', err);
    } finally {
      setExporting(false);
    }
  };

  const handleDriverAssignment = async (complaintDbId, driverName) => {
    setAssigningId(complaintDbId);
    try {
      await assignDriverTask(complaintDbId, driverName);
      await loadData();
    } catch (err) {
      console.error('Assignment error:', err);
    } finally {
      setAssigningId(null);
    }
  };

  const handleProfileUpdated = (updatedUser) => {
    setUser(updatedUser);
  };

  const handleAddReport = () => {
    if (reportGenerating) return;
    setReportGenerating(true);
    setTimeout(() => {
      setSimulatedReports((prev) => [
        {
          name: `Custom Audit - ${reportWard} (${reportDateRange})`,
          category: 'Custom Builder',
          desc: `${reportTonnage ? 'Waste Tonnage, ' : ''}${reportFuel ? 'Fuel Economy' : ''}`,
          date: 'Oct 24, 2026',
          time: 'Just Now',
          status: 'Ready'
        },
        ...prev
      ]);
      setReportGenerating(false);
    }, 2000);
  };

  const handleAddBroadcast = async () => {
    if (!broadcastContent.trim() || sendingBroadcast) return;
    setSendingBroadcast(true);
    try {
      await sendAdminBroadcast({
        title: 'Admin Broadcast',
        message: broadcastContent,
        audience: broadcastAudience,
        priority: broadcastPriority
      });
      setBroadcastContent('');
      // Refresh notifications list to show the new broadcast
      await loadNotifications();
      setShowNotificationToast(true);
      setTimeout(() => setShowNotificationToast(false), 3000);
    } catch (err) {
      console.error('Broadcast error:', err);
    } finally {
      setSendingBroadcast(false);
    }
  };

  const topWards = metrics?.top_wards || [
    { name: 'Ward 12', percent: 92 },
    { name: 'Ward 8', percent: 85 },
    { name: 'Ward 4', percent: 76 },
    { name: 'Ward 10', percent: 66 }
  ];

  // Derive available driver names from real DB data, with fallback
  const availableDrivers = drivers.length > 0
    ? drivers.filter(d => d.is_active).map(d => d.full_name)
    : ['Ramesh Yadav', 'Suresh Kumar', 'Ajay Patel', 'Vikram Singh'];

  const mapTasks = recentComplaints.map((c, i) => ({
    id: c.id,
    name: `${c.location} (${c.type})`,
    status: c.status,
    lat: 18.520 + (i * 0.006),
    lng: 73.850 + (i * 0.007)
  }));

  const pendingCount = metrics?.pending_complaints ?? recentComplaints.filter(c => c.status === 'Pending').length;
  const inProgressCount = metrics?.in_progress_complaints ?? recentComplaints.filter(c => c.status === 'In Progress').length;
  const completedCount = metrics?.completed_complaints ?? recentComplaints.filter(c => c.status === 'Completed').length;
  const totalComplaints = (metrics?.total_complaints ?? recentComplaints.length) || (pendingCount + inProgressCount + completedCount);

  const pendingPct = totalComplaints > 0 ? (pendingCount / totalComplaints) * 100 : 0;
  const inProgressPct = totalComplaints > 0 ? (inProgressCount / totalComplaints) * 100 : 0;
  const completedPct = totalComplaints > 0 ? (completedCount / totalComplaints) * 100 : 0;

  const sidebarNavItems = [
    { name: 'Dashboard', icon: 'dashboard' },
    { name: 'Complaints', icon: 'report_problem' },
    { name: 'Drivers', icon: 'local_shipping' },
    { name: 'Bins', icon: 'delete' },
    { name: 'Reports', icon: 'assessment' },
    { name: 'Analytics', icon: 'analytics' },
    { name: 'Notifications', icon: 'notifications', badge: 12 },
  ];

  const getPageHeaderTitle = () => {
    switch (activeTab) {
      case 'Dashboard':
        return 'Municipal Telemetry & OpenStreetMap GIS';
      case 'Complaints':
        return 'Municipal Complaints Management';
      case 'Drivers':
        return 'Municipal Fleet & Driver Directory';
      case 'Bins':
        return 'Smart Bin Telemetry & Inventory';
      case 'Reports':
        return 'Municipal Compliance & Sustainability Reports';
      case 'Analytics':
        return 'Predictive Analytics & Performance Insights';
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
            <span>Complaints Report Exported and Downloaded Successfully!</span>
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
            {activeTab === 'Dashboard' && (
              <button
                onClick={handleExport}
                disabled={exporting}
                className="bg-[#005c2b] text-white px-4 py-2 rounded-lg font-semibold text-xs hover:bg-[#004a22] hover:shadow-sm transition-all flex items-center gap-2 shadow-xs cursor-pointer active:scale-98"
              >
                <Download className="w-3.5 h-3.5" />
                <span>{exporting ? 'Exporting...' : 'Export Report'}</span>
              </button>
            )}

            {activeTab === 'Drivers' && (
              <button
                onClick={() => setShowProfileModal(true)}
                className="bg-[#005c2b] text-white px-4 py-2 rounded-lg font-semibold text-xs hover:bg-[#004a22] hover:shadow-sm transition-all flex items-center gap-2 shadow-xs cursor-pointer active:scale-98"
              >
                <Plus className="w-3.5 h-3.5" />
                <span>Register New Driver</span>
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
                    <span className="text-3xl font-bold tracking-tight text-slate-900">{totalComplaints}</span>
                    <div className="flex items-center text-[#005c2b] text-[11px] font-semibold mt-1">
                      <span className="material-symbols-outlined text-sm mr-1">trending_up</span>
                      <span>+12% this week</span>
                    </div>
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
                    <span className="text-3xl font-bold tracking-tight text-slate-900">{completedCount}</span>
                    <div className="flex items-center text-[#005c2b] text-[11px] font-semibold mt-1">
                      <span className="material-symbols-outlined text-sm mr-1">trending_up</span>
                      <span>+5% vs last month</span>
                    </div>
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
                    <span className="text-3xl font-bold tracking-tight text-slate-900">{inProgressCount}</span>
                    <div className="flex items-center text-status-pending text-[11px] font-semibold mt-1">
                      <span className="material-symbols-outlined text-sm mr-1">trending_flat</span>
                      <span>Steady</span>
                    </div>
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
                    <span className="text-3xl font-bold tracking-tight text-slate-900">{pendingCount}</span>
                    <div className="flex items-center text-status-urgent text-[11px] font-semibold mt-1">
                      <span className="material-symbols-outlined text-sm mr-1">trending_down</span>
                      <span>-2% vs last month</span>
                    </div>
                  </div>
                </div>

              </div>

              {/* Row 2: Map & Donut Chart */}
              <div className="grid grid-cols-1 xl:grid-cols-12 gap-6">
                
                {/* Telemetry Map */}
                <div className="xl:col-span-8 bg-white rounded-xl border border-border-subtle shadow-ambient flex flex-col overflow-hidden">
                  <div className="p-4 border-b border-border-subtle flex justify-between items-center bg-slate-50">
                    <h3 className="font-bold text-sm text-[#101828]">Municipal OpenStreetMap Telemetry</h3>
                    <span className="text-xs font-semibold text-emerald-700 bg-secondary-container/50 px-2.5 py-0.5 rounded-full border border-success-whatsapp/30">
                      {metrics?.active_trucks || 24} Active Driver Fleet
                    </span>
                  </div>
                  <div className="relative p-4 flex-1">
                    <InteractiveMap
                      center={[18.5204, 73.8567]}
                      zoom={13}
                      driverLocation={[18.524, 73.852]}
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
                      Live Telemetry
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
                        <span className="text-2xl font-bold leading-none">{totalComplaints}</span>
                        <span className="text-[9px] font-bold text-slate-400 uppercase mt-0.5">Total</span>
                      </div>
                    </div>

                    <div className="w-full grid grid-cols-3 gap-2 mt-4 text-[10px] font-semibold text-slate-600">
                      <div className="flex flex-col items-center p-1 bg-red-50 rounded border border-red-100">
                        <span className="text-status-urgent font-bold">Pending</span>
                        <span className="font-bold">{pendingCount} ({Math.round(pendingPct)}%)</span>
                      </div>
                      <div className="flex flex-col items-center p-1 bg-yellow-50 rounded border border-yellow-100">
                        <span className="text-status-pending font-bold">Progress</span>
                        <span className="font-bold">{inProgressCount} ({Math.round(inProgressPct)}%)</span>
                      </div>
                      <div className="flex flex-col items-center p-1 bg-emerald-50 rounded border border-[#a2ecd8]">
                        <span className="text-[#005c2b] font-bold">Resolved</span>
                        <span className="font-bold">{completedCount} ({Math.round(completedPct)}%)</span>
                      </div>
                    </div>
                  </div>

                  <div className="pt-2.5 border-t border-border-subtle flex items-center justify-between text-[10px] text-slate-400 font-semibold">
                    <span>⚡ Live Dynamic Diagnostics</span>
                    <span className="text-[#005c2b] font-bold">PostgreSQL Active</span>
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
                      {topWards.map((ward) => (
                        <div key={ward.name} className="flex items-center justify-between gap-3 text-xs font-semibold">
                          <span className="w-16 text-slate-500">{ward.name}</span>
                          <div className="flex-grow bg-slate-100 h-2.5 rounded-full overflow-hidden">
                            <div className="bg-[#005c2b] h-full rounded-full" style={{ width: `${ward.percent}%` }} />
                          </div>
                          <span className="w-10 text-right font-extrabold text-slate-900">{ward.percent}%</span>
                        </div>
                      ))}
                    </div>
                  </div>

                  <div className="mt-4 p-3 bg-emerald-50 border border-[#a2ecd8] rounded-xl flex items-center justify-between text-[11px] font-semibold text-[#005c2b]">
                    <span className="flex items-center gap-1.5">
                      <Sparkles className="w-3.5 h-3.5" />
                      <span>Average Ward Resolution Efficiency: 85%</span>
                    </span>
                    <span className="font-bold">Optimum</span>
                  </div>
                </div>

              </div>

            </div>
          )}

          {/* 2. COMPLAINTS VIEW */}
          {activeTab === 'Complaints' && (
            <div className="space-y-6">
              
              {/* Stats Grid */}
              <div className="grid grid-cols-1 md:grid-cols-2 xl:grid-cols-4 gap-6">
                <div className="bg-white border border-border-subtle border-l-4 border-l-[#005c2b] rounded-xl p-5 shadow-ambient flex flex-col justify-between h-28 hover:shadow-md transition-shadow">
                  <span className="font-bold text-[11px] text-slate-400 uppercase tracking-wider">Total Complaints</span>
                  <div className="flex justify-between items-baseline">
                    <span className="text-3xl font-bold">156</span>
                    <span className="text-[10px] text-[#005c2b] font-bold bg-[#b6edbb]/40 px-2 py-0.5 rounded-full">+12% this week</span>
                  </div>
                </div>
                <div className="bg-white border border-border-subtle border-l-4 border-l-success-whatsapp rounded-xl p-5 shadow-ambient flex flex-col justify-between h-28 hover:shadow-md transition-shadow">
                  <span className="font-bold text-[11px] text-slate-400 uppercase tracking-wider">Resolved</span>
                  <div className="flex justify-between items-baseline">
                    <span className="text-3xl font-bold">112</span>
                    <span className="text-[10px] text-[#005c2b] font-bold bg-[#b6edbb]/40 px-2 py-0.5 rounded-full">+5% vs last month</span>
                  </div>
                </div>
                <div className="bg-white border border-border-subtle border-l-4 border-l-status-pending rounded-xl p-5 shadow-ambient flex flex-col justify-between h-28 hover:shadow-md transition-shadow">
                  <span className="font-bold text-[11px] text-slate-400 uppercase tracking-wider">In Progress</span>
                  <div className="flex justify-between items-baseline">
                    <span className="text-3xl font-bold">28</span>
                    <span className="text-[10px] text-status-pending font-bold bg-yellow-50 px-2 py-0.5 rounded-full border border-yellow-200">Steady</span>
                  </div>
                </div>
                <div className="bg-white border border-border-subtle border-l-4 border-l-status-urgent rounded-xl p-5 shadow-ambient flex flex-col justify-between h-28 hover:shadow-md transition-shadow">
                  <span className="font-bold text-[11px] text-slate-400 uppercase tracking-wider">Overdue</span>
                  <div className="flex justify-between items-baseline">
                    <span className="text-3xl font-bold">16</span>
                    <span className="text-[10px] text-status-urgent font-bold bg-red-50 px-2 py-0.5 rounded-full border border-red-200">-2% vs last month</span>
                  </div>
                </div>
              </div>

              {/* Layout: Table + Activity Feed */}
              <div className="grid grid-cols-1 xl:grid-cols-12 gap-6">
                
                {/* Table card */}
                <div className="xl:col-span-8 bg-white border border-border-subtle rounded-xl shadow-ambient flex flex-col h-full min-h-[500px]">
                  <div className="p-4 border-b border-border-subtle flex flex-col sm:flex-row justify-between items-start sm:items-center gap-4 bg-slate-50">
                    <h3 className="font-bold text-sm">All Municipal Complaints</h3>
                    <div className="flex gap-2 w-full sm:w-auto">
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
                      <button className="bg-white border border-border-subtle px-3 py-1.5 rounded-lg text-xs font-bold hover:bg-slate-100 flex items-center cursor-pointer shadow-sm">
                        <Filter className="w-3.5 h-3.5" />
                      </button>
                    </div>
                  </div>

                  <div className="overflow-x-auto flex-1">
                    <table className="w-full text-left text-xs font-semibold text-slate-600">
                      <thead>
                        <tr className="border-b border-border-subtle bg-slate-50 text-slate-400 font-bold uppercase text-[10px] tracking-wider">
                          <th className="py-3 px-4">Tracking ID</th>
                          <th className="py-3 px-4">Citizen Name</th>
                          <th className="py-3 px-4">Type</th>
                          <th className="py-3 px-4">Date/Time</th>
                          <th className="py-3 px-4">Status</th>
                          <th className="py-3 px-4 text-right">Actions</th>
                        </tr>
                      </thead>
                      <tbody className="divide-y divide-border-subtle">
                        {recentComplaints
                          .filter(c => c.id.toLowerCase().includes(complaintSearch.toLowerCase()) || c.location.toLowerCase().includes(complaintSearch.toLowerCase()))
                          .map((item) => (
                            <tr key={item.id} className="hover:bg-slate-50/50 transition-colors">
                              <td className="py-3.5 px-4 font-bold text-slate-900">{item.id}</td>
                              <td className="py-3.5 px-4 text-slate-500">{item.citizen_name || 'Sarah Jenkins'}</td>
                              <td className="py-3.5 px-4">
                                <div className="flex items-center space-x-2">
                                  <span className={`w-2 h-2 rounded-full ${
                                    item.type.includes('Overflow') ? 'bg-status-urgent' : 'bg-secondary'
                                  }`}></span>
                                  <span>{item.type}</span>
                                </div>
                              </td>
                              <td className="py-3.5 px-4 text-slate-500">Oct 24, 09:15 AM</td>
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
                                <select
                                  value={item.assignedTo || 'Unassigned'}
                                  disabled={assigningId === item.db_id}
                                  onChange={(e) => handleDriverAssignment(item.db_id, e.target.value)}
                                  className="px-2.5 py-1 bg-slate-50 border border-slate-200 rounded-lg text-[10px] font-bold text-slate-800 focus:outline-none focus:border-[#005c2b] cursor-pointer"
                                >
                                  {(!item.assignedTo || item.assignedTo === 'Unassigned') && (
                                    <option value="Unassigned">Assign Driver...</option>
                                  )}
                                  {availableDrivers.map((driverName) => (
                                    <option key={driverName} value={driverName}>
                                      {driverName}
                                    </option>
                                  ))}
                                </select>
                              </td>
                            </tr>
                          ))}
                      </tbody>
                    </table>
                  </div>

                  <div className="p-4 border-t border-border-subtle flex justify-between items-center bg-slate-50 rounded-b-xl">
                    <span className="text-slate-500">Showing 1-4 of 156 entries</span>
                    <div className="flex gap-1">
                      <button className="p-1.5 border border-border-subtle rounded hover:bg-white text-slate-500 disabled:opacity-50" disabled>
                        <ChevronLeft className="w-3.5 h-3.5" />
                      </button>
                      <button className="px-3 py-1 rounded bg-[#005c2b] text-white font-bold">1</button>
                      <button className="px-3 py-1 rounded border border-border-subtle hover:bg-white">2</button>
                      <button className="px-3 py-1 rounded border border-border-subtle hover:bg-white">3</button>
                      <button className="p-1.5 border border-border-subtle rounded hover:bg-white text-slate-500">
                        <ChevronRight className="w-3.5 h-3.5" />
                      </button>
                    </div>
                  </div>
                </div>

                {/* Timeline activity list */}
                <div className="xl:col-span-4 bg-white border border-border-subtle rounded-xl shadow-ambient p-5 flex flex-col h-full min-h-[500px]">
                  <h3 className="font-semibold text-sm pb-2 border-b border-border-subtle mb-4">Recent Activity Timeline</h3>
                  <div className="relative flex-1">
                    <div className="absolute left-[15px] top-2 bottom-4 w-px bg-border-subtle" />
                    <div className="space-y-6 relative">
                      
                      <div className="flex items-start">
                        <div className="w-8 h-8 rounded-full bg-[#b6edbb]/40 flex items-center justify-center text-[#005c2b] border-2 border-white z-10 shadow-sm">
                          <Check className="w-4 h-4" />
                        </div>
                        <div className="ml-3 flex-grow">
                          <p className="text-xs font-bold text-slate-900">Complaint <span className="text-[#005c2b]">#CMP-1040</span> resolved</p>
                          <p className="text-[10px] text-slate-400 mt-0.5">By Driver Unit 4 • 10 mins ago</p>
                        </div>
                      </div>

                      <div className="flex items-start">
                        <div className="w-8 h-8 rounded-full bg-yellow-50 flex items-center justify-center text-status-pending border-2 border-white z-10 shadow-sm">
                          <Truck className="w-4 h-4" />
                        </div>
                        <div className="ml-3 flex-grow">
                          <p className="text-xs font-bold text-slate-900">Driver Dispatched</p>
                          <p className="text-[10px] text-slate-500 mt-0.5">Unit 7 assigned to complaint #CMP-1041 • 45 mins ago</p>
                        </div>
                      </div>

                      <div className="flex items-start">
                        <div className="w-8 h-8 rounded-full bg-red-50 flex items-center justify-center text-status-urgent border-2 border-white z-10 shadow-sm">
                          <AlertCircle className="w-4 h-4" />
                        </div>
                        <div className="ml-3 flex-grow">
                          <p className="text-xs font-bold text-slate-900">Urgent Complaint Logged</p>
                          <p className="text-[10px] text-slate-500 mt-0.5">New overflow complaint submitted in Ward 3 • 2 hours ago</p>
                        </div>
                      </div>

                    </div>
                  </div>
                  <button className="mt-4 w-full text-center py-2.5 text-[#005c2b] border border-border-subtle rounded-lg text-xs font-bold hover:bg-slate-50 transition-colors cursor-pointer">
                    View All Activity logs
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
                    <h3 className="text-white font-bold text-lg">Municipal Telemetry & OpenStreetMap GIS</h3>
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
                    <span className="text-3xl font-bold">{drivers.length || metrics?.total_drivers || 0}</span>
                    <span className="text-[10px] font-bold bg-[#b6edbb]/50 text-[#005c2b] px-2 py-0.5 rounded-full">registered</span>
                  </div>
                </div>
                <div className="bg-white border border-[#EAECF0] rounded-xl p-5 shadow-ambient border-t-4 border-t-[#005c2b] hover:shadow-md transition-shadow">
                  <p className="font-bold text-xs text-[#005c2b] uppercase tracking-wider mb-2 flex items-center gap-1.5">
                    <Truck className="w-4 h-4 text-[#005c2b]" />
                    <span>Active</span>
                  </p>
                  <div className="flex items-baseline gap-2">
                    <span className="text-3xl font-bold">{drivers.filter(d => d.is_active).length || metrics?.active_trucks || 0}</span>
                    <span className="text-xs text-slate-500 font-semibold">On Roster</span>
                  </div>
                </div>
                <div className="bg-white border border-[#EAECF0] rounded-xl p-5 shadow-ambient border-t-4 border-t-status-pending hover:shadow-md transition-shadow">
                  <p className="font-bold text-xs text-status-pending uppercase tracking-wider mb-2 flex items-center gap-1.5">
                    <Coffee className="w-4 h-4 text-status-pending" />
                    <span>Tasks Done</span>
                  </p>
                  <div className="flex items-baseline gap-2">
                    <span className="text-3xl font-bold">{drivers.reduce((sum, d) => sum + (d.tasks_completed || 0), 0)}</span>
                    <span className="text-xs text-slate-500 font-semibold">Total</span>
                  </div>
                </div>
                <div className="bg-white border border-[#EAECF0] rounded-xl p-5 shadow-ambient border-t-4 border-t-slate-400 hover:shadow-md transition-shadow">
                  <p className="font-bold text-xs text-slate-400 uppercase tracking-wider mb-2 flex items-center gap-1.5">
                    <Power className="w-4 h-4 text-slate-400" />
                    <span>Inactive</span>
                  </p>
                  <div className="flex items-baseline gap-2">
                    <span className="text-3xl font-bold">{drivers.filter(d => !d.is_active).length}</span>
                    <span className="text-xs text-slate-500 font-semibold">Deactivated</span>
                  </div>
                </div>
              </div>

              {/* Filter Toolbar */}
              <div className="flex flex-col sm:flex-row justify-between items-center gap-4">
                <div className="relative w-full sm:w-80">
                  <Search className="w-4 h-4 text-slate-400 absolute left-3 top-2.5" />
                  <input
                    value={driverSearch}
                    onChange={(e) => setDriverSearch(e.target.value)}
                    className="w-full bg-white border border-border-subtle rounded-lg py-1.5 pl-9 pr-3 text-xs font-semibold focus:outline-none focus:border-[#005c2b]"
                    placeholder="Search by name or vehicle ID..."
                    type="text"
                  />
                </div>
                <div className="flex gap-2 w-full sm:w-auto">
                  <button className="bg-white border border-border-subtle px-3 py-1.5 rounded-lg text-xs font-bold flex items-center gap-1 hover:bg-slate-50 shadow-sm cursor-pointer">
                    <Filter className="w-3.5 h-3.5" /> Filter
                  </button>
                </div>
              </div>

              {/* Driver Grid roster cards — REAL DB DATA */}
              {loadingDrivers ? (
                <div className="text-center py-12 text-slate-400 font-semibold text-sm">Loading drivers from database...</div>
              ) : drivers.length === 0 ? (
                <div className="text-center py-12 text-slate-400 font-semibold text-sm">No drivers found.</div>
              ) : (
              <div className="grid grid-cols-1 md:grid-cols-2 lg:grid-cols-3 gap-6">
                {drivers
                  .filter(d => d.full_name.toLowerCase().includes(driverSearch.toLowerCase()) || (d.employee_id || '').toLowerCase().includes(driverSearch.toLowerCase()) || (d.ward || '').toLowerCase().includes(driverSearch.toLowerCase()))
                  .map((driver) => (
                  <div key={driver.id} className="bg-white border border-border-subtle rounded-xl p-5 shadow-ambient relative group hover:shadow-md transition-all duration-300">
                    <div className="absolute top-4 right-4">
                      <span className={`px-2.5 py-0.5 rounded-full text-[10px] font-bold border flex items-center gap-1.5 ${
                        driver.is_active ? 'bg-[#b6edbb]/40 text-[#005c2b] border-[#b6edbb]' : 'bg-slate-100 text-slate-400 border-slate-200'
                      }`}>
                        <span className={`w-1.5 h-1.5 rounded-full ${driver.is_active ? 'bg-success-whatsapp' : 'bg-slate-400'}`}></span>
                        <span>{driver.is_active ? 'Active' : 'Inactive'}</span>
                      </span>
                    </div>

                    <div className="flex items-start gap-4 mb-4">
                      <div className="w-16 h-16 rounded-full border-2 border-[#b6edbb] bg-[#b6edbb]/20 flex items-center justify-center text-[#005c2b] font-bold text-xl shadow-sm shrink-0 transition-transform duration-300 group-hover:scale-105">
                        {driver.full_name.charAt(0)}
                      </div>
                      <div className="pt-1.5">
                        <h4 className="font-bold text-sm text-[#101828]">{driver.full_name}</h4>
                        <p className="text-[11px] text-slate-400 font-semibold flex items-center gap-1 mt-0.5">
                          <span className="material-symbols-outlined text-sm">badge</span> {driver.employee_id || 'No ID'}
                        </p>
                        <p className="text-[10px] text-slate-400 mt-0.5">{driver.email}</p>
                      </div>
                    </div>

                    <div className="grid grid-cols-2 gap-4 border-y border-border-subtle py-3 mb-4 text-xs font-semibold text-slate-500">
                      <div>
                        <span className="block text-[9px] uppercase tracking-wider text-slate-400">Ward</span>
                        <span className="text-slate-900 font-bold flex items-center gap-1 mt-0.5">
                          <span className="material-symbols-outlined text-sm text-[#005c2b]">location_on</span>
                          <span>{driver.ward || 'N/A'}</span>
                        </span>
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
                      <button
                        onClick={async () => {
                          await toggleDriverStatus(driver.id, !driver.is_active);
                          loadDrivers();
                        }}
                        className={`px-3 py-2.5 rounded-lg text-xs font-bold border transition-colors cursor-pointer ${
                          driver.is_active
                            ? 'bg-red-50 text-red-600 border-red-200 hover:bg-red-100'
                            : 'bg-[#b6edbb]/30 text-[#005c2b] border-[#b6edbb] hover:bg-[#b6edbb]/60'
                        }`}
                        title={driver.is_active ? 'Deactivate driver' : 'Activate driver'}
                      >
                        <Power className="w-3.5 h-3.5" />
                      </button>
                    </div>
                  </div>
                ))}
              </div>
              )}

              {/* Roster footer */}
              <div className="p-4 bg-white rounded-xl border border-border-subtle flex justify-between items-center shadow-ambient text-xs font-semibold">
                <span className="text-slate-500">Showing {drivers.length} registered drivers from database</span>
                <button onClick={loadDrivers} className="text-[#005c2b] font-bold flex items-center gap-1.5 hover:underline cursor-pointer">
                  <RefreshCw className="w-3.5 h-3.5" /> Sync DB
                </button>
              </div>

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

              {/* Map & Urgent Layout */}

              <div className="grid grid-cols-1 xl:grid-cols-12 gap-6">
                
                {/* Telemetry map */}
                <div className="xl:col-span-8 bg-white border border-border-subtle rounded-xl shadow-ambient flex flex-col overflow-hidden h-[380px]">
                  <div className="p-4 border-b border-border-subtle bg-slate-50 flex justify-between items-center">
                    <h3 className="font-bold text-sm">Real-Time OpenStreetMap Telemetry</h3>
                    <div className="flex gap-2">
                      <span className="inline-flex items-center gap-1.5 px-2 py-0.5 rounded-full bg-red-50 text-status-urgent text-[10px] font-bold border border-red-200">
                        <span className="w-1.5 h-1.5 rounded-full bg-status-urgent animate-pulse"></span> Full
                      </span>
                      <span className="inline-flex items-center gap-1.5 px-2 py-0.5 rounded-full bg-emerald-50 text-[#005c2b] text-[10px] font-bold border border-[#a2ecd8]">
                        <span className="w-1.5 h-1.5 rounded-full bg-success-whatsapp"></span> Empty
                      </span>
                    </div>
                  </div>
                  <div className="flex-1 relative bg-slate-100">
                    <InteractiveMap
                      center={[18.5204, 73.8567]}
                      zoom={13}
                      tasks={mapTasks}
                      height="100%"
                    />
                  </div>
                </div>

                {/* Urgent list */}
                <div className="xl:col-span-4 bg-white border border-border-subtle rounded-xl shadow-ambient p-5 flex flex-col h-[380px]">
                  <h3 className="font-semibold text-sm pb-2 border-b border-border-subtle mb-4">Urgent Collector Actions</h3>
                  <div className="flex-grow overflow-y-auto space-y-3 pr-1">
                    
                    <div className="p-3.5 border border-border-subtle rounded-lg bg-slate-50 hover:bg-slate-100 transition-colors flex justify-between items-center gap-2">
                      <div>
                        <span className="font-bold text-xs">BIN-092</span>
                        <p className="text-[10px] text-slate-500 truncate max-w-[150px] mt-0.5">Downtown Square - North</p>
                      </div>
                      <div className="text-right shrink-0">
                        <span className="block px-2.5 py-0.5 rounded bg-red-50 text-status-urgent font-bold text-[10px] border border-red-200">98% Full</span>
                        <button
                          onClick={() => setActiveTab('Complaints')}
                          className="mt-2 px-3 py-1 bg-[#005c2b] text-white text-[10px] font-bold rounded hover:bg-[#004a22] transition-colors cursor-pointer active:scale-95"
                        >
                          Dispatch
                        </button>
                      </div>
                    </div>

                    <div className="p-3.5 border border-border-subtle rounded-lg bg-slate-50 hover:bg-slate-100 transition-colors flex justify-between items-center gap-2">
                      <div>
                        <span className="font-bold text-xs">BIN-144</span>
                        <p className="text-[10px] text-slate-500 truncate max-w-[150px] mt-0.5">Westside Park Entrance</p>
                      </div>
                      <div className="text-right shrink-0">
                        <span className="block px-2.5 py-0.5 rounded bg-yellow-50 text-status-pending font-bold text-[10px] border border-yellow-200">Bat Low (15%)</span>
                        <button
                          onClick={() => setActiveTab('Notifications')}
                          className="mt-2 px-3 py-1 border border-border-subtle bg-white text-slate-700 text-[10px] font-bold rounded hover:bg-slate-50 transition-colors cursor-pointer active:scale-95"
                        >
                          Maint Alert
                        </button>
                      </div>
                    </div>

                  </div>
                </div>

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

          {/* 5. REPORTS VIEW */}
          {activeTab === 'Reports' && (
            <div className="space-y-6">
              
              <div className="bg-white border border-border-subtle rounded-xl p-6 shadow-ambient">
                <p className="text-xs font-bold text-slate-500 mb-1">Environmental & Compliance Audits</p>
                <h3 className="text-xl font-bold">Municipal Compliance & Sustainability Reports</h3>
              </div>

              <div className="grid grid-cols-12 gap-6">
                
                {/* Report Builder Form */}
                <div className="col-span-12 xl:col-span-4 bg-white border border-border-subtle rounded-xl p-5 shadow-ambient h-fit">
                  <h3 className="font-bold text-sm mb-5 flex items-center gap-2">
                    <span className="material-symbols-outlined text-[#005c2b]">tune</span>
                    <span>Custom Report Builder</span>
                  </h3>
                  <div className="space-y-4 text-xs font-semibold">
                    <div>
                      <label className="block text-slate-500 mb-1">Date Range Selection</label>
                      <select
                        value={reportDateRange}
                        onChange={(e) => setReportDateRange(e.target.value)}
                        className="w-full bg-white border border-border-subtle rounded-lg py-2.5 px-3 font-semibold focus:outline-none focus:border-[#005c2b]"
                      >
                        <option>Last 7 Days</option>
                        <option>Last 30 Days</option>
                        <option>This Quarter</option>
                        <option>Year to Date</option>
                        <option>Custom Range...</option>
                      </select>
                    </div>

                    <div>
                      <label className="block text-slate-500 mb-1">Ward Selection</label>
                      <select
                        value={reportWard}
                        onChange={(e) => setReportWard(e.target.value)}
                        className="w-full bg-white border border-border-subtle rounded-lg py-2.5 px-3 font-semibold focus:outline-none focus:border-[#005c2b]"
                      >
                        <option>All Wards</option>
                        <option>Ward 12 - Downtown</option>
                        <option>Ward 8 - Westside</option>
                        <option>Ward 4 - Residential</option>
                        <option>Ward 10 - Industrial</option>
                      </select>
                    </div>

                    <div>
                      <label className="block text-slate-500 mb-2">Check Data Types to Ingest</label>
                      <div className="space-y-2.5">
                        <label className="flex items-center gap-2 cursor-pointer">
                          <input
                            checked={reportTonnage}
                            onChange={(e) => setReportTonnage(e.target.checked)}
                            className="w-4 h-4 rounded text-[#005c2b] focus:ring-0 border-border-subtle"
                            type="checkbox"
                          />
                          <span>Waste Tonnage & Sorting</span>
                        </label>
                        <label className="flex items-center gap-2 cursor-pointer">
                          <input
                            checked={reportFuel}
                            onChange={(e) => setReportFuel(e.target.checked)}
                            className="w-4 h-4 rounded text-[#005c2b] focus:ring-0 border-border-subtle"
                            type="checkbox"
                          />
                          <span>Driver Fuel Logs & Mileage</span>
                        </label>
                        <label className="flex items-center gap-2 cursor-pointer">
                          <input
                            checked={reportComplaints}
                            onChange={(e) => setReportComplaints(e.target.checked)}
                            className="w-4 h-4 rounded text-[#005c2b] focus:ring-0 border-border-subtle"
                            type="checkbox"
                          />
                          <span>Citizen Complaint Escalation Logs</span>
                        </label>
                      </div>
                    </div>

                    <button
                      onClick={handleAddReport}
                      disabled={reportGenerating}
                      className="w-full bg-[#005c2b] hover:bg-[#004a22] text-white py-3 rounded-lg font-bold flex items-center justify-center gap-2 transition-all shadow-sm cursor-pointer disabled:opacity-85 active:scale-98"
                    >
                      <span className="material-symbols-outlined text-sm">magic_button</span>
                      <span>{reportGenerating ? 'Generating...' : 'Build Custom Audit Report'}</span>
                    </button>
                  </div>
                </div>

                {/* Generated Reports Table */}
                <div className="col-span-12 xl:col-span-8 bg-white border border-border-subtle rounded-xl shadow-ambient overflow-hidden">
                  <div className="p-4 border-b border-border-subtle bg-slate-50 flex justify-between items-center">
                    <h3 className="font-bold text-sm">Exportable Generated Archives</h3>
                    <span className="inline-flex items-center gap-1.5 px-2.5 py-0.5 rounded-full bg-yellow-50 text-status-pending text-[10px] font-bold border border-yellow-200">
                      <span className="w-1.5 h-1.5 rounded-full bg-status-pending"></span> Ready: {simulatedReports.length}
                    </span>
                  </div>

                  <div className="overflow-x-auto flex-grow">
                    <table className="w-full text-left text-xs font-semibold text-slate-600">
                      <thead>
                        <tr className="border-b border-border-subtle bg-slate-50 text-slate-400 font-bold uppercase text-[10px] tracking-wider">
                          <th className="py-3.5 px-6">Report Name</th>
                          <th className="py-3.5 px-6">Category</th>
                          <th className="py-3.5 px-6">Date Generated</th>
                          <th className="py-3.5 px-6 text-right">Actions</th>
                        </tr>
                      </thead>
                      <tbody className="divide-y divide-border-subtle">
                        {reportGenerating && (
                          <tr className="bg-yellow-50/40">
                            <td className="py-4 px-6" colSpan={4}>
                              <div className="flex items-center gap-3">
                                <RefreshCw className="w-5 h-5 text-status-pending animate-spin" />
                                <div>
                                  <div className="font-bold text-slate-900">Compiling database elements...</div>
                                  <p className="text-[10px] text-slate-400 mt-0.5">Please wait, estimated 2 mins remaining</p>
                                </div>
                              </div>
                            </td>
                          </tr>
                        )}
                        {simulatedReports.map((report, idx) => (
                          <tr key={idx} className="hover:bg-slate-50/50 transition-colors">
                            <td className="py-4 px-6">
                              <div className="flex items-center gap-3">
                                <div className="w-9 h-9 rounded-lg bg-slate-100 flex items-center justify-center text-[#005c2b] shrink-0">
                                  <span className="material-symbols-outlined text-[20px]">description</span>
                                </div>
                                <div>
                                  <div className="font-bold text-slate-900">{report.name}</div>
                                  <p className="text-[10px] text-slate-400 mt-0.5">{report.desc}</p>
                                </div>
                              </div>
                            </td>
                            <td className="py-4 px-6">
                              <span className="px-2 py-0.5 bg-slate-100 text-slate-500 rounded text-[10px] font-bold border border-border-subtle">
                                {report.category}
                              </span>
                            </td>
                            <td className="py-4 px-6 text-slate-500">
                              {report.date} <span className="text-[10px] opacity-70 ml-1">{report.time}</span>
                            </td>
                            <td className="py-4 px-6 text-right">
                              <div className="flex justify-end gap-1.5">
                                <button
                                  onClick={handleExport}
                                  className="p-1.5 text-slate-500 hover:text-[#005c2b] hover:bg-slate-100 rounded transition-colors cursor-pointer border border-transparent hover:border-border-subtle"
                                  title="Export PDF Document"
                                >
                                  <span className="material-symbols-outlined text-[18px]">picture_as_pdf</span>
                                </button>
                                <button
                                  onClick={handleExport}
                                  className="p-1.5 text-slate-500 hover:text-[#005c2b] hover:bg-slate-100 rounded transition-colors cursor-pointer border border-transparent hover:border-border-subtle"
                                  title="Export CSV Spreadsheet"
                                >
                                  <span className="material-symbols-outlined text-[18px]">table_view</span>
                                </button>
                              </div>
                            </td>
                          </tr>
                        ))}
                      </tbody>
                    </table>
                  </div>

                  <div className="px-6 py-4 border-t border-border-subtle bg-slate-50 flex justify-between items-center text-xs font-semibold text-slate-500">
                    <span>Showing 1 to {simulatedReports.length} of 24 records</span>
                    <div className="flex gap-1">
                      <button className="p-1.5 border border-border-subtle rounded hover:bg-white disabled:opacity-50" disabled>
                        <ChevronLeft className="w-3.5 h-3.5" />
                      </button>
                      <button className="px-3 py-1 rounded bg-[#005c2b] text-white font-bold">1</button>
                      <button className="px-3 py-1 rounded border border-border-subtle hover:bg-white">2</button>
                      <button className="p-1.5 border border-border-subtle rounded hover:bg-white">
                        <ChevronRight className="w-3.5 h-3.5" />
                      </button>
                    </div>
                  </div>
                </div>

              </div>

            </div>
          )}

          {/* 6. ANALYTICS VIEW */}
          {activeTab === 'Analytics' && (
            <div className="space-y-6">
              
              <div className="grid grid-cols-12 gap-6">
                
                {/* Waste generation line chart */}
                <div className="col-span-12 lg:col-span-8 bg-white border border-border-subtle rounded-xl p-5 shadow-ambient">
                  <div className="flex justify-between items-center mb-6">
                    <h3 className="font-bold text-sm">Waste Generation Analysis Trends</h3>
                    <span className="px-3 py-1 bg-slate-100 rounded-full font-bold text-[10px] text-slate-500 border border-border-subtle">
                      Monthly Tonnage
                    </span>
                  </div>

                  {/* High Quality Custom SVG Line Chart */}
                  <div className="h-64 w-full relative flex items-end">
                    <svg className="w-full h-full" viewBox="0 0 500 200" preserveAspectRatio="none">
                      {/* Grid Lines */}
                      <line x1="0" y1="50" x2="500" y2="50" stroke="#f1f5f9" strokeWidth="1" />
                      <line x1="0" y1="100" x2="500" y2="100" stroke="#f1f5f9" strokeWidth="1" />
                      <line x1="0" y1="150" x2="500" y2="150" stroke="#f1f5f9" strokeWidth="1" />
                      <line x1="0" y1="200" x2="500" y2="200" stroke="#e2e8f0" strokeWidth="1.5" />

                      {/* Organic waste filled curve */}
                      <path
                        d="M 10 160 Q 70 140 130 110 T 250 80 T 370 100 T 490 50 L 490 200 L 10 200 Z"
                        fill="rgba(0, 92, 43, 0.08)"
                      />
                      <path
                        d="M 10 160 Q 70 140 130 110 T 250 80 T 370 100 T 490 50"
                        fill="none"
                        stroke="#005c2b"
                        strokeWidth="2.5"
                      />

                      {/* Recyclables dashed line */}
                      <path
                        d="M 10 180 Q 70 160 130 150 T 250 120 T 370 90 T 490 70"
                        fill="none"
                        stroke="#F59E0B"
                        strokeWidth="2"
                        strokeDasharray="5,5"
                      />

                      {/* Data point dots */}
                      <circle cx="130" cy="110" r="4" fill="#005c2b" stroke="white" strokeWidth="1.5" />
                      <circle cx="250" cy="80" r="4" fill="#005c2b" stroke="white" strokeWidth="1.5" />
                      <circle cx="370" cy="100" r="4" fill="#005c2b" stroke="white" strokeWidth="1.5" />
                      <circle cx="490" cy="50" r="4" fill="#005c2b" stroke="white" strokeWidth="1.5" />
                    </svg>

                    {/* Chart Labels Overlay */}
                    <div className="absolute left-2 bottom-2 text-[9px] font-bold text-slate-400 flex gap-12">
                      <span>Jan</span>
                      <span>Mar</span>
                      <span>May</span>
                      <span>Jul</span>
                      <span>Aug</span>
                    </div>

                    <div className="absolute right-4 top-2 flex gap-4 text-[9px] font-bold">
                      <span className="flex items-center gap-1.5">
                        <span className="w-2.5 h-1 bg-[#005c2b]"></span>
                        <span>Organic Waste</span>
                      </span>
                      <span className="flex items-center gap-1.5">
                        <span className="w-2.5 h-1 bg-[#F59E0B] border-dashed border"></span>
                        <span>Recyclables</span>
                      </span>
                    </div>
                  </div>
                </div>

                {/* AI Observations Panel */}
                <div className="col-span-12 lg:col-span-4 bg-[#003816] text-white rounded-xl p-5 shadow-ambient relative overflow-hidden flex flex-col justify-between">
                  <div className="absolute inset-0 opacity-15 pointer-events-none bg-cover bg-center" style={{ backgroundImage: "url('https://lh3.googleusercontent.com/aida/AP1WRLsx8Y3kT3_RVi7TL0sPvWkeQ17n0t6FdoXG88omtcz8KGSwL_4prMJ6Npgg-LPtW-Sl2O0UpaCyyKp_JHsHlkdTIzAST9uQT8X_iG5T5YirHvPUJH8jZRRHNC8XWKXnxHBQm9ktrQE-LAS5y6A1odryIXPxbbTD3ugj3g3GIVHZ1hagZ_g9twT9tfbaKKyxii_r-04SMUcQpGIq02RssbHOeTm-5zYXPbfwzMZCXwLMOsQCfdunCWOjnw')" }}></div>
                  
                  <div className="relative z-10 space-y-4">
                    <div className="flex items-center gap-3">
                      <span className="material-symbols-outlined text-[#b8f0be] text-3xl font-bold">psychology</span>
                      <h3 className="font-bold text-sm">AI-Powered Insights</h3>
                    </div>
                    
                    <ul className="space-y-3.5 text-xs font-semibold text-white/95">
                      <li className="flex items-start gap-2 bg-white/10 p-2.5 rounded-lg border border-white/5 backdrop-blur-xs">
                        <TrendingUp className="w-4 h-4 text-red-400 shrink-0 mt-0.5" />
                        <p><strong>Ward 8</strong> plastics spiked 20% over 14 days, correlating with district festival schedules.</p>
                      </li>
                      <li className="flex items-start gap-2 bg-white/10 p-2.5 rounded-lg border border-white/5 backdrop-blur-xs">
                        <AlertCircle className="w-4 h-4 text-yellow-400 shrink-0 mt-0.5" />
                        <p>Route optimization detected in <strong>Sector North</strong>; potential 15% fuel efficiency savings.</p>
                      </li>
                    </ul>
                  </div>

                  <button
                    onClick={() => setActiveTab('Reports')}
                    className="relative z-10 w-full mt-4 py-2.5 bg-[#b8f0be] hover:bg-[#a2ecd8] text-[#003816] rounded-lg font-bold text-xs transition-colors cursor-pointer active:scale-98"
                  >
                    Generate Sustainability Summary
                  </button>
                </div>

              </div>

              {/* Bottom row metrics */}
              <div className="grid grid-cols-1 md:grid-cols-2 gap-6">
                
                {/* Ward Resolution Bars — REAL API DATA */}
                <div className="bg-white border border-border-subtle rounded-xl p-5 shadow-ambient">
                  <div className="flex justify-between items-center mb-5">
                    <h3 className="font-bold text-sm">Complaint Resolution by Ward</h3>
                    <span className="text-[10px] font-bold text-[#005c2b] bg-secondary-container px-2 py-0.5 rounded">Real Data</span>
                  </div>
                  <div className="space-y-4 font-semibold text-xs text-slate-500">
                    {(analyticsData?.ward_breakdown || []).map((ward) => {
                      const pct = ward.total > 0 ? Math.round((ward.resolved / ward.total) * 100) : 0;
                      return (
                        <div key={ward.ward} className="flex items-center gap-4">
                          <span className="w-16 truncate">{ward.ward}</span>
                          <div className="flex-grow bg-slate-100 h-2 rounded-full overflow-hidden">
                            <div className={`h-full rounded-full ${pct >= 70 ? 'bg-[#b6edbb]' : pct >= 40 ? 'bg-yellow-200' : 'bg-red-200'}`} style={{ width: `${pct}%` }}></div>
                          </div>
                          <span className="w-14 text-right text-slate-900 font-bold">{pct}% ({ward.total})</span>
                        </div>
                      );
                    })}
                    {!analyticsData && (
                      <div className="text-center py-6 text-slate-400">Loading analytics...</div>
                    )}
                  </div>
                </div>

                {/* Carbon footprint */}
                <div className="bg-white border border-border-subtle rounded-xl p-5 shadow-ambient flex flex-col justify-between">
                  <div>
                    <h3 className="font-bold text-sm">Fleet Carbon Footprint Index</h3>
                    <p className="text-[11px] text-slate-400 font-semibold mt-0.5">Estimated CO2 emissions vs baseline target</p>
                  </div>

                  <div className="flex items-center justify-center py-4 relative">
                    <div className="w-48 h-32 relative">
                      <svg className="w-full h-full" viewBox="0 0 36 36">
                        <path
                          className="text-slate-100 stroke-current"
                          strokeWidth="4"
                          fill="none"
                          d="M18 2.0845 a 15.9155 15.9155 0 0 1 0 31.831"
                          strokeDasharray="50, 100"
                          transform="rotate(180 18 18)"
                        />
                        <path
                          className="text-[#005c2b] stroke-current"
                          strokeWidth="4.5"
                          fill="none"
                          d="M18 2.0845 a 15.9155 15.9155 0 0 1 0 31.831"
                          strokeDasharray="42, 100"
                          transform="rotate(180 18 18)"
                        />
                      </svg>
                      <div className="absolute inset-0 flex flex-col items-center justify-end pb-2">
                        <span className="text-3xl font-bold">142</span>
                        <span className="text-[9px] font-bold text-slate-400">Tons CO2e</span>
                      </div>
                    </div>
                  </div>

                  <div className="p-3 bg-slate-50 border border-border-subtle rounded-lg flex justify-between items-center text-xs font-semibold">
                    <div>
                      <span className="block text-[9px] text-slate-400 uppercase">Target Goal</span>
                      <span className="text-slate-800 font-bold">150 Tons</span>
                    </div>
                    <div className="text-right">
                      <span className="block text-[9px] text-slate-400 uppercase">Status</span>
                      <span className="text-success-whatsapp font-bold flex items-center gap-0.5">
                        <span className="material-symbols-outlined text-xs">trending_down</span> -5.3%
                      </span>
                    </div>
                  </div>
                </div>

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
                        <span>Critical Alerts</span>
                      </div>
                      <span className="text-2xl font-bold">{notifications.filter(n => n.notification_type === 'Critical').length}</span>
                    </div>

                    <div className="flex justify-between items-center p-3 rounded-lg bg-yellow-50 border border-yellow-100 text-status-pending">
                      <div className="flex items-center gap-2">
                        <span className="material-symbols-outlined">warning</span>
                        <span>Warnings</span>
                      </div>
                      <span className="text-2xl font-bold">{notifications.filter(n => n.notification_type === 'Warning').length}</span>
                    </div>

                    <div className="flex justify-between items-center p-3 rounded-lg bg-slate-50 border border-border-subtle text-slate-600">
                      <div className="flex items-center gap-2">
                        <span className="material-symbols-outlined">info</span>
                        <span>Info Logs</span>
                      </div>
                      <span className="text-2xl font-bold">{notifications.filter(n => n.notification_type === 'Info').length}</span>
                    </div>

                    <div className="flex justify-between items-center p-3 rounded-lg bg-[#b6edbb]/20 border border-[#b6edbb] text-[#005c2b]">
                      <div className="flex items-center gap-2">
                        <span className="material-symbols-outlined">campaign</span>
                        <span>Broadcasts Sent</span>
                      </div>
                      <span className="text-2xl font-bold">{notifications.filter(n => n.is_broadcast).length}</span>
                    </div>

                  </div>
                </div>

                {/* Broadcast message composer */}
                <div className="col-span-12 lg:col-span-8 bg-white border border-border-subtle rounded-xl p-5 shadow-ambient flex flex-col justify-between">
                  <h3 className="font-bold text-sm mb-4 flex items-center gap-1.5">
                    <span className="material-symbols-outlined text-[#005c2b]">campaign</span>
                    <span>Broadcast Message dispatcher</span>
                  </h3>
                  
                  <div className="space-y-4 text-xs font-semibold">
                    <div className="grid grid-cols-2 gap-4">
                      <div>
                        <label className="block text-slate-500 mb-1">Target Audience</label>
                        <select
                          value={broadcastAudience}
                          onChange={(e) => setBroadcastAudience(e.target.value)}
                          className="w-full bg-white border border-border-subtle rounded-lg py-2 px-3 font-semibold focus:outline-none focus:border-[#005c2b]"
                        >
                          <option>All Drivers (Active Shift)</option>
                          <option>All Citizens</option>
                          <option>Ward A Personnel</option>
                          <option>Ward B Personnel</option>
                        </select>
                      </div>
                      <div>
                        <label className="block text-slate-500 mb-1">Alert Priority</label>
                        <select
                          value={broadcastPriority}
                          onChange={(e) => setBroadcastPriority(e.target.value)}
                          className="w-full bg-white border border-border-subtle rounded-lg py-2 px-3 font-semibold focus:outline-none focus:border-[#005c2b]"
                        >
                          <option>Standard (App Notification)</option>
                          <option>High (Push + SMS)</option>
                          <option>Emergency (Override Silent Mode)</option>
                        </select>
                      </div>
                    </div>

                    <div>
                      <label className="block text-slate-500 mb-1">Broadcast Content</label>
                      <textarea
                        value={broadcastContent}
                        onChange={(e) => setBroadcastContent(e.target.value)}
                        className="w-full border border-border-subtle rounded-lg py-2 px-3 focus:outline-none focus:border-[#005c2b] resize-none"
                        placeholder="Enter announcement text to broadcast..."
                        rows={3}
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
                        className="px-4 py-2 bg-[#005c2b] text-white rounded-lg hover:bg-[#004a22] transition-colors flex items-center gap-1.5 shadow-sm cursor-pointer active:scale-98"
                      >
                        <Send className="w-3.5 h-3.5" />
                        <span>Send Broadcast</span>
                      </button>
                    </div>
                  </div>
                </div>

              </div>

              {/* Feed Card — REAL API DATA */}
              <div className="bg-white border border-border-subtle rounded-xl shadow-ambient overflow-hidden h-[450px] flex flex-col">
                <div className="p-4 border-b border-border-subtle bg-slate-50 flex justify-between items-center">
                  <h3 className="font-bold text-sm">Real-time Notification Feed</h3>
                  <div className="flex gap-1.5">
                    <button onClick={loadNotifications} className="px-2.5 py-1 bg-white border border-border-subtle rounded text-[10px] font-bold hover:bg-slate-50 cursor-pointer shadow-2xs flex items-center gap-1">
                      <RefreshCw className="w-3 h-3" />
                    </button>
                    <button className="px-2.5 py-1 bg-white border border-border-subtle rounded text-[10px] font-bold hover:bg-slate-50 cursor-pointer shadow-2xs">All</button>
                    <button className="px-2.5 py-1 bg-red-50 text-status-urgent border border-red-150 rounded text-[10px] font-bold hover:bg-red-100 cursor-pointer shadow-2xs">Critical</button>
                    <button className="px-2.5 py-1 bg-yellow-50 text-status-pending border border-yellow-150 rounded text-[10px] font-bold hover:bg-yellow-100 cursor-pointer shadow-2xs">Warning</button>
                  </div>
                </div>

                <div className="flex-grow overflow-y-auto p-4 space-y-3.5 pr-1">
                  {notifications.length === 0 ? (
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
                      <div
                        key={notif.id}
                        className={`flex gap-4 p-4 rounded-lg border ${styles.bg} transition-colors hover:shadow-xs group cursor-pointer`}
                        onClick={() => markNotificationRead(notif.id)}
                      >
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
                        </div>
                      </div>
                    );
                  })}
                </div>
              </div>

            </div>
          )}

        </main>
      </div>

      {/* Profile Settings Modal */}
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
