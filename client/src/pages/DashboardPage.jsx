import React, { useState, useEffect } from 'react';
import { useNavigate } from 'react-router-dom';
import { fetchMyComplaints } from '../services/complaintService';
import { BACKEND_BASE_URL } from '../services/api';
import { getCurrentUser, logoutUser, updateUserProfile } from '../services/authService';
import ProfileModal from '../components/ProfileModal';
import ReportWasteModal from '../components/ReportWasteModal';
import InteractiveMap from '../components/InteractiveMap';
import { motion, AnimatePresence } from 'framer-motion';
import {
  LayoutDashboard,
  FileText,
  Search,
  Coins,
  Gift,
  User,
  HelpCircle,
  Settings,
  LogOut,
  Sparkles,
  Camera,
  Cpu,
  Truck,
  CheckCircle2,
  AlertCircle,
  MessageCircle,
  X,
  Plus,
  ArrowRight
} from 'lucide-react';

const DashboardPage = ({ initialTab = 'Dashboard' }) => {
  const navigate = useNavigate();
  const [activeTab, setActiveTab] = useState(initialTab);
  const [user, setUser] = useState(null);
  const [showWhatsAppModal, setShowWhatsAppModal] = useState(false);
  const [showReportModal, setShowReportModal] = useState(false);
  const [showProfileModal, setShowProfileModal] = useState(false);
  const [recentComplaints, setRecentComplaints] = useState([]);
  const [selectedComplaint, setSelectedComplaint] = useState(null);
  const [complaintFilter, setComplaintFilter] = useState('All');

  useEffect(() => {
    // Synchronize current user session with backend PostgreSQL database
    getCurrentUser().then((userData) => {
      if (userData) {
        setUser(userData);
      } else {
        const savedUser = localStorage.getItem('ecopulse_user');
        if (savedUser) {
          try {
            setUser(JSON.parse(savedUser));
          } catch (e) {
            setUser({ name: 'Priya Patil', email: 'priya@cityswap.io', role: 'citizen', ward: 'Ward 12', eco_coins: 150 });
          }
        }
      }
    });

    // Load complaints from backend API for logged-in user session
    fetchMyComplaints().then((data) => setRecentComplaints(data));
  }, []);

  const handleLogout = () => {
    logoutUser();
    navigate('/login');
  };

  const handleComplaintCreated = (newComplaint) => {
    setRecentComplaints((prev) => [newComplaint, ...prev]);
    // Refresh user eco coins
    getCurrentUser().then((u) => {
      if (u) setUser(u);
    });
  };

  const handleProfileUpdated = (updatedUser) => {
    setUser(updatedUser);
  };

  // Compute live real-time statistics
  const totalComplaintsCount = recentComplaints.length;
  const inProgressCount = recentComplaints.filter((c) => c.status === 'In Progress').length;
  const ecoCoinsCount = user?.eco_coins || 150;

  // How it works steps matching CITIZEN.png
  const steps = [
    {
      title: 'Report',
      description: 'Upload photo & location on WhatsApp',
      icon: Camera
    },
    {
      title: 'AI Verify',
      description: 'We verify & create complaint',
      icon: Cpu
    },
    {
      title: 'Assigned',
      description: 'Task assigned to driver or collector',
      icon: Truck
    },
    {
      title: 'Resolved',
      description: 'You get notified & earn EcoCoins',
      icon: CheckCircle2
    }
  ];

  // Sidebar navigation items matching CITIZEN.png
  const navItems = [
    { name: 'Dashboard', icon: LayoutDashboard, path: '/citizen' },
    { name: 'My Complaints', icon: FileText, path: '/citizen' },
    { name: 'Track Waste Truck', icon: Search, path: '/citizen' },
    { name: 'EcoCoins Rewards', icon: Coins, path: '/citizen' },
    { name: 'Redeem Coupons', icon: Gift, path: '/citizen' },
    { name: 'Profile Settings', icon: User, action: () => setShowProfileModal(true) },
    { name: 'Help & Support', icon: HelpCircle, action: () => setShowWhatsAppModal(true) },
    { name: 'Settings', icon: Settings, action: () => setShowProfileModal(true) },
  ];

  const getStatusBadgeClass = (status) => {
    if (status === 'In Progress') {
      return 'bg-yellow-100 text-yellow-800 border-yellow-300 font-extrabold whitespace-nowrap inline-flex items-center px-2.5 py-1 rounded-lg text-[11px] border shadow-2xs';
    }
    if (status === 'Pending') {
      return 'bg-red-100 text-red-800 border-red-300 font-extrabold whitespace-nowrap inline-flex items-center px-2.5 py-1 rounded-lg text-[11px] border shadow-2xs';
    }
    if (status === 'Completed') {
      return 'bg-emerald-100 text-emerald-800 border-emerald-300 font-extrabold whitespace-nowrap inline-flex items-center px-2.5 py-1 rounded-lg text-[11px] border shadow-2xs';
    }
    return 'bg-slate-100 text-slate-800 border-slate-300 font-extrabold whitespace-nowrap inline-flex items-center px-2.5 py-1 rounded-lg text-[11px] border shadow-2xs';
  };

  const [mobileMenuOpen, setMobileMenuOpen] = useState(false);

  return (
    <div className="min-h-screen bg-[#f6f9f7] font-sans selection:bg-[#02471f] selection:text-white flex text-slate-800">
      
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
              className="md:hidden fixed left-0 top-0 bottom-0 w-[280px] bg-primary text-white z-[110] flex flex-col py-6 shadow-2xl"
            >
              <div className="px-6 mb-6 flex items-center justify-between">
                <div>
                  <h1 className="text-lg font-headline-sm font-black text-white">EcoPulse AI</h1>
                  <p className="text-white/70 text-[10px] uppercase tracking-wider mt-0.5">Citizen Portal</p>
                </div>
                <button
                  onClick={() => setMobileMenuOpen(false)}
                  className="p-1.5 rounded-lg bg-white/10 text-white"
                >
                  <X className="w-4 h-4" />
                </button>
              </div>

              <div className="px-6 mb-6">
                <button
                  onClick={() => { setShowReportModal(true); setMobileMenuOpen(false); }}
                  className="w-full bg-[#a4f5b4] hover:bg-[#89d899] text-[#00210b] text-xs font-bold py-2.5 rounded-lg flex justify-center items-center gap-2"
                >
                  <Plus className="w-4 h-4" />
                  <span>Report Issue</span>
                </button>
              </div>

              <nav className="flex-1 space-y-1 overflow-y-auto">
                {navItems.map((item) => {
                  const Icon = item.icon;
                  const isActive = activeTab === item.name;
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
                      className={`w-full flex items-center gap-3 px-6 py-3 transition-all text-xs font-bold ${
                        isActive
                          ? 'bg-white/10 text-white border-l-4 border-[#a4f5b4]'
                          : 'text-white/70 hover:bg-white/5 hover:text-white'
                      }`}
                    >
                      <Icon className="w-4 h-4" />
                      <span>{item.name}</span>
                    </button>
                  );
                })}
              </nav>

              <div className="px-4 mt-auto pt-4 border-t border-white/10">
                <button
                  onClick={handleLogout}
                  className="w-full flex items-center gap-3 px-6 py-2.5 rounded-md text-white/70 font-medium hover:bg-white/5"
                >
                  <LogOut className="w-4 h-4" />
                  <span>Logout</span>
                </button>
              </div>
            </motion.div>
          </>
        )}
      </AnimatePresence>

      {/* ----------------------------------------------------------------- */}
      {/* LEFT SIDEBAR NAVIGATION MATCHING CITIZEN.PNG                     */}
      {/* ----------------------------------------------------------------- */}
      <aside className="w-[280px] bg-primary flex flex-col py-8 shrink-0 hidden md:flex min-h-screen text-white select-none">
        
        <div className="px-8 mb-8">
          <h1 className="text-xl font-headline-sm font-black text-white">EcoPulse AI</h1>
          <p className="text-white/70 text-[10px] uppercase tracking-wider mt-1">Citizen Portal</p>
        </div>

        {/* User Card */}
        <div
          onClick={() => setShowProfileModal(true)}
          className="px-8 mb-8 flex items-center gap-3 cursor-pointer hover:opacity-90"
        >
          <div className="w-10 h-10 rounded-full bg-white/20 overflow-hidden border border-white/30 flex items-center justify-center font-bold text-xs shrink-0 text-white">
            {user?.name ? user.name.charAt(0).toUpperCase() : 'P'}
          </div>
          <div className="flex flex-col">
            <span className="text-white text-xs font-bold">{user?.name || user?.full_name || 'Priya Patil'}</span>
            <span className="text-emerald-300 text-[10px] font-semibold">{user?.ward || 'Ward 12'} • Active Citizen</span>
          </div>
        </div>

        {/* Report New Issue CTA */}
        <div className="px-6 mb-6">
          <button
            onClick={() => setShowReportModal(true)}
            className="w-full bg-[#a4f5b4] hover:bg-[#89d899] text-[#00210b] text-xs font-bold py-3 rounded-lg flex justify-center items-center gap-2 cursor-pointer transition-colors shadow-sm"
          >
            <Plus className="w-4 h-4" />
            <span>Report New Issue</span>
          </button>
        </div>

        {/* Navigation Links */}
        <nav className="flex-1 space-y-1">
          {navItems.map((item) => {
            const Icon = item.icon;
            const isActive = activeTab === item.name;
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
                className={`w-full flex items-center gap-3 px-6 py-3 transition-all cursor-pointer text-xs font-bold ${
                  isActive
                    ? 'bg-white/10 text-white border-l-4 border-[#a4f5b4]'
                    : 'text-white/70 hover:bg-white/5 hover:text-white'
                }`}
              >
                <Icon className="w-4 h-4" />
                <span>{item.name}</span>
              </button>
            );
          })}
        </nav>

        {/* Logout Button */}
        <div className="px-4 mt-auto">
          <button
            onClick={handleLogout}
            className="w-full flex items-center gap-3 px-6 py-3 rounded-md text-white/70 font-medium hover:bg-white/5 hover:text-white transition-all duration-300 cursor-pointer"
          >
            <LogOut className="w-4 h-4" />
            <span>Logout</span>
          </button>
        </div>

      </aside>

      {/* ----------------------------------------------------------------- */}
      {/* MAIN DASHBOARD CONTENT                                            */}
      {/* ----------------------------------------------------------------- */}
      <div className="flex-1 flex flex-col min-w-0 min-h-screen">
        
        {/* Top Header Navbar */}
        <header className="h-16 bg-white border-b border-slate-200/90 px-4 sm:px-8 flex items-center justify-between sticky top-0 z-20">
          <div className="flex items-center gap-3">
            <button
              onClick={() => setMobileMenuOpen(true)}
              className="md:hidden p-2 rounded-lg bg-slate-100 text-slate-700 hover:bg-slate-200 cursor-pointer"
              aria-label="Open navigation menu"
            >
              <span className="material-symbols-outlined text-xl">menu</span>
            </button>
            <div>
              <h1 className="text-lg sm:text-xl font-black text-slate-900 tracking-tight">
                Citizen Dashboard
              </h1>
              <p className="text-[11px] font-semibold text-slate-500 hidden sm:block">
                Clean City • Ward 12 Municipal Portal
              </p>
            </div>
          </div>

          <div className="flex items-center gap-3">
            {/* Quick Action Button */}
            <button
              onClick={() => setShowReportModal(true)}
              className="inline-flex items-center gap-1.5 bg-[#02471f] hover:bg-[#003617] text-white px-3.5 py-2 rounded-xl text-xs font-extrabold shadow-xs transition-all cursor-pointer"
            >
              <Plus className="w-4 h-4" />
              <span>Report Issue</span>
            </button>

            {/* Profile Action */}
            <button
              onClick={() => setShowProfileModal(true)}
              className="p-2 rounded-xl bg-slate-100 hover:bg-slate-200 text-slate-700 transition-all cursor-pointer"
              title="Profile Settings"
            >
              <User className="w-4 h-4" />
            </button>
          </div>
        </header>

        {/* Dashboard Body Container */}
        <main className="p-4 sm:p-6 md:p-8 space-y-6 max-w-7xl w-full mx-auto">
          
          {activeTab === 'My Complaints' ? (
            <motion.div
              key="My Complaints"
              initial={{ opacity: 0, y: 15 }}
              animate={{ opacity: 1, y: 0 }}
              className="space-y-6"
            >
              <div className="flex flex-col md:flex-row md:items-center justify-between gap-4">
                <div>
                  <h2 className="text-2xl font-black text-slate-900">My Complaints</h2>
                  <p className="text-xs font-semibold text-slate-500 mt-1">
                    Track and manage your reported waste issues in real-time.
                  </p>
                </div>
                <button
                  onClick={() => setShowReportModal(true)}
                  className="px-4 py-2.5 bg-primary text-white text-xs font-bold rounded-xl shadow-sm hover:bg-primary-container transition-all"
                >
                  Report New Issue
                </button>
              </div>

              {/* Filters */}
              <div className="flex flex-wrap items-center gap-2">
                {['All', 'Pending', 'In Progress', 'Completed'].map(filter => (
                  <button
                    key={filter}
                    onClick={() => setComplaintFilter(filter)}
                    className={`px-4 py-2 rounded-full border text-xs font-bold transition-all cursor-pointer ${
                      complaintFilter === filter
                        ? 'border-primary text-primary bg-primary/5'
                        : 'border-slate-200 text-slate-600 bg-white hover:bg-slate-50'
                    }`}
                  >
                    {filter === 'All' ? 'All Complaints' : filter === 'Completed' ? 'Resolved' : filter}
                  </button>
                ))}
              </div>

              {/* Complaints Grid */}
              {recentComplaints.filter(c => complaintFilter === 'All' || c.status === complaintFilter).length === 0 ? (
                <div className="bg-white border border-slate-200 rounded-3xl p-12 text-center max-w-lg mx-auto">
                  <div className="w-12 h-12 bg-slate-50 text-slate-400 rounded-2xl flex items-center justify-center mx-auto mb-4 text-xl">
                    📁
                  </div>
                  <h3 className="text-base font-bold text-slate-900">No Complaints Found</h3>
                  <p className="text-xs text-slate-500 mt-1">You haven't reported any issues matching this status.</p>
                </div>
              ) : (
                <div className="grid grid-cols-1 lg:grid-cols-12 gap-6">
                  {/* High-priority active complaint */}
                  {(() => {
                    const filteredList = recentComplaints.filter(c => complaintFilter === 'All' || c.status === complaintFilter);
                    const mainComplaint = filteredList[0];
                    const otherComplaints = filteredList.slice(1);
                    return (
                      <>
                        <div 
                          onClick={() => setSelectedComplaint(mainComplaint)}
                          className="lg:col-span-8 bg-white border border-slate-200/90 rounded-2xl shadow-xs p-5 hover:border-primary/50 cursor-pointer transition-colors relative overflow-hidden group"
                        >
                          <div className="absolute top-0 right-0 w-32 h-32 bg-primary/5 rounded-bl-full -mr-16 -mt-16 group-hover:scale-110 transition-transform duration-500"></div>
                          <div className="flex justify-between items-start mb-4 relative z-10">
                            <div>
                              <div className="flex items-center gap-2 mb-1">
                                <span className="text-[10px] font-black text-slate-400">ID: {mainComplaint.id}</span>
                                <span className={getStatusBadgeClass(mainComplaint.status)}>{mainComplaint.status}</span>
                              </div>
                              <h3 className="text-lg font-black text-slate-900">{mainComplaint.title || mainComplaint.type}</h3>
                            </div>
                            <span className="text-slate-400 font-bold">→</span>
                          </div>
                          
                          <div className="grid grid-cols-1 md:grid-cols-2 gap-4 mb-4 relative z-10 text-xs font-semibold">
                            <div className="flex items-start gap-2.5">
                              <span className="text-primary text-base">📍</span>
                              <div>
                                <p className="text-slate-400 text-[10px]">Location</p>
                                <p className="text-slate-800">{mainComplaint.location}</p>
                              </div>
                            </div>
                            <div className="flex items-start gap-2.5">
                              <span className="text-primary text-base">♻️</span>
                              <div>
                                <p className="text-slate-400 text-[10px]">Waste Type</p>
                                <p className="text-slate-800">{mainComplaint.type}</p>
                              </div>
                            </div>
                          </div>

                          <div className="h-32 w-full rounded-lg overflow-hidden border border-slate-100 relative z-10 mb-4 bg-slate-50 flex items-center justify-center">
                            <span className="text-xs text-slate-400 font-bold select-none">🗺️ Live Interactive Map Snippet</span>
                          </div>

                          <div className="border-t border-slate-100 pt-4 flex justify-between items-center text-xs font-bold text-slate-500">
                            <span>Reported recently</span>
                            <span className="text-primary hover:underline inline-flex items-center gap-1">
                              View Timeline →
                            </span>
                          </div>
                        </div>

                        {/* Other standard complaints */}
                        <div className="lg:col-span-4 flex flex-col gap-4">
                          {otherComplaints.map(item => (
                            <div 
                              key={item.id} 
                              onClick={() => setSelectedComplaint(item)}
                              className="bg-white border border-slate-200/90 rounded-2xl p-5 hover:border-primary/50 cursor-pointer transition-colors flex flex-col justify-between animate-fadeIn"
                            >
                              <div className="flex justify-between items-start mb-3">
                                <div className="flex flex-col gap-1">
                                  <span className="text-[10px] font-black text-slate-400">ID: {item.id}</span>
                                  <h4 className="text-sm font-extrabold text-slate-900 leading-tight">{item.title || item.type}</h4>
                                </div>
                                <span className={getStatusBadgeClass(item.status)}>{item.status}</span>
                              </div>
                              <div className="space-y-1 text-xs font-semibold text-slate-600 mb-3">
                                <div className="flex items-center gap-1.5">
                                  <span>📍</span>
                                  <span className="truncate">{item.location}</span>
                                </div>
                                <div className="flex items-center gap-1.5">
                                  <span>♻️</span>
                                  <span className="truncate">{item.type}</span>
                                </div>
                              </div>
                              <div className="text-[10px] text-slate-400 font-bold">
                                Registered live
                              </div>
                            </div>
                          ))}
                        </div>
                      </>
                    );
                  })()}
                </div>
              )}
            </motion.div>
          ) : activeTab === 'Track Waste Truck' ? (
            <motion.div
              key="Track Waste Truck"
              initial={{ opacity: 0, y: 15 }}
              animate={{ opacity: 1, y: 0 }}
              className="space-y-6"
            >
              <div>
                <h2 className="text-2xl font-black text-slate-900">Track Waste Truck</h2>
                <p className="text-xs font-semibold text-slate-500 mt-1">
                  Live GPS mapping of waste collection vehicles in your ward.
                </p>
              </div>

              <div className="grid grid-cols-1 lg:grid-cols-12 gap-6">
                {/* Tracker Info Card */}
                <div className="lg:col-span-4 bg-white border border-slate-200/90 rounded-2xl p-5 flex flex-col gap-6 shadow-xs">
                  <div className="flex justify-between items-start">
                    <div>
                      <h3 className="text-lg font-black text-slate-900 mb-1">Unit #402</h3>
                      <p className="text-xs font-bold text-emerald-600 flex items-center gap-1.5">
                        <span className="w-2.5 h-2.5 rounded-full bg-emerald-500 animate-pulse"></span>
                        Active Route: Sector 7
                      </p>
                    </div>
                    <span className="px-2.5 py-1 bg-slate-100 border border-slate-200 text-slate-800 text-[10px] font-black rounded uppercase">
                      General Waste
                    </span>
                  </div>

                  <div className="grid grid-cols-2 gap-3">
                    <div className="bg-slate-50 rounded-xl p-3 border border-slate-100 text-center">
                      <p className="text-[10px] font-black text-slate-400 uppercase">Est. Arrival</p>
                      <p className="text-3xl font-black text-primary mt-1">14<span className="text-sm font-bold text-primary/70">min</span></p>
                    </div>
                    <div className="bg-slate-50 rounded-xl p-3 border border-slate-100 text-center">
                      <p className="text-[10px] font-black text-slate-400 uppercase">Distance Left</p>
                      <p className="text-3xl font-black text-primary mt-1">3.2<span className="text-sm font-bold text-primary/70">km</span></p>
                    </div>
                  </div>

                  <div className="space-y-3.5 border-t border-slate-100 pt-4 text-xs font-semibold">
                    <div className="flex items-start gap-2.5">
                      <span className="text-slate-400 text-sm">👤</span>
                      <div>
                        <p className="text-slate-400 text-[10px]">Crew Assigned</p>
                        <p className="text-slate-800">Ajay Patel (Driver) & Vikram Singh</p>
                      </div>
                    </div>
                    <div className="flex items-start gap-2.5">
                      <span className="text-slate-400 text-sm">📍</span>
                      <div>
                        <p className="text-slate-400 text-[10px]">Next Stop</p>
                        <p className="text-slate-800">Sector 7, Lane B</p>
                      </div>
                    </div>
                  </div>

                  <div className="flex items-center gap-2 border-t border-slate-100 pt-4 mt-auto">
                    <button className="flex-1 py-2.5 bg-emerald-50 hover:bg-emerald-100 text-emerald-800 border border-emerald-200 font-bold rounded-xl text-xs flex justify-center items-center gap-2">
                      📞 Call Crew
                    </button>
                    <button className="flex-1 py-2.5 bg-slate-100 hover:bg-slate-200 text-slate-700 font-bold rounded-xl text-xs flex justify-center items-center gap-2">
                      💬 Message
                    </button>
                  </div>
                </div>

                {/* Map Panel */}
                <div className="lg:col-span-8 h-[500px] rounded-2xl border border-slate-200 overflow-hidden relative shadow-xs bg-slate-100">
                  <InteractiveMap center={[18.5204, 73.8567]} zoom={14} driverLocation={[18.524, 73.852]} />
                </div>
              </div>
            </motion.div>
          ) : activeTab === 'EcoCoins Rewards' || activeTab === 'Redeem Coupons' ? (
            <motion.div
              key="EcoCoins Rewards"
              initial={{ opacity: 0, y: 15 }}
              animate={{ opacity: 1, y: 0 }}
              className="space-y-6"
            >
              <div>
                <h2 className="text-2xl font-black text-slate-900">EcoCoins Rewards</h2>
                <p className="text-xs font-semibold text-slate-500 mt-1">
                  Earn points by contributing to a cleaner city and redeem them for exclusive local benefits.
                </p>
              </div>

              {/* Balance Banner & Stats Grid */}
              <div className="grid grid-cols-1 lg:grid-cols-12 gap-6">
                <div className="lg:col-span-8 bg-white border border-slate-200/90 rounded-2xl p-5 relative overflow-hidden flex flex-col justify-between min-h-[220px] shadow-xs">
                  <div className="absolute -right-20 -top-20 w-64 h-64 bg-primary/5 rounded-full blur-3xl pointer-events-none"></div>
                  
                  <div className="relative z-10">
                    <span className="text-[10px] font-black text-slate-400 uppercase tracking-wider flex items-center gap-1.5">
                      🪙 Total Available Balance
                    </span>
                    <div className="mt-3 flex items-baseline gap-2">
                      <span className="text-5xl font-black text-primary tracking-tight">{ecoCoinsCount}</span>
                      <span className="text-base font-bold text-primary/70">EcoCoins</span>
                    </div>
                    <div className="mt-3 inline-flex items-center px-3 py-1 rounded-full bg-secondary-container text-on-secondary-container text-[10px] font-black">
                      📈 +350 points this month
                    </div>
                  </div>

                  <div className="relative z-10 mt-6 grid grid-cols-3 gap-4 border-t border-slate-100 pt-4 text-xs font-semibold text-slate-500">
                    <div>
                      <span className="block text-[10px] text-slate-400">Lifetime Earned</span>
                      <span className="font-black text-slate-800 text-sm">{ecoCoinsCount + 300}</span>
                    </div>
                    <div>
                      <span className="block text-[10px] text-slate-400">Complaints Resolved</span>
                      <span className="font-black text-slate-800 text-sm">{totalComplaintsCount}</span>
                    </div>
                    <div>
                      <span className="block text-[10px] text-slate-400">Next Tier</span>
                      <div className="flex items-center gap-2 mt-1">
                        <span className="font-black text-slate-800 text-sm">Gold</span>
                        <div className="flex-1 h-1.5 bg-slate-100 rounded-full overflow-hidden">
                          <div className="h-full bg-primary w-2/3 rounded-full"></div>
                        </div>
                      </div>
                    </div>
                  </div>
                </div>

                {/* Redeem CTA Box */}
                <div className="lg:col-span-4 bg-primary text-white rounded-2xl p-5 flex flex-col justify-between min-h-[220px] shadow-xs">
                  <div>
                    <h3 className="text-lg font-black mb-1.5">Ready to Redeem?</h3>
                    <p className="text-xs text-white/80 font-semibold leading-relaxed">
                      Explore active offers from local partners and city services to use your EcoCoins.
                    </p>
                  </div>
                  <div className="mt-4 bg-white/10 rounded-xl p-3 border border-white/20">
                    <span className="block text-[9px] text-white/60 uppercase font-black tracking-wide mb-1">Featured Offer</span>
                    <div className="flex items-center justify-between text-xs font-bold">
                      <span>20% Water Bill Discount</span>
                      <span className="bg-white text-primary px-1.5 py-0.5 rounded text-[10px] font-black">2,000 EC</span>
                    </div>
                  </div>
                </div>
              </div>

              {/* Coupons List */}
              <div className="space-y-4">
                <h3 className="text-base font-extrabold text-slate-900">Available Coupons & Benefits</h3>
                <div className="grid grid-cols-1 sm:grid-cols-2 lg:grid-cols-3 gap-5">
                  {[
                    { id: 1, title: '20% Water Bill Discount', cost: 2000, brand: 'Municipal Services', desc: 'Get 20% off on your quarterly water supply utility bill.' },
                    { id: 2, title: 'Free Bus Pass (10 Rides)', cost: 1000, brand: 'City Transport', desc: 'Valid for all city routes on smart electric buses.' },
                    { id: 3, title: 'Organic Compost Pack (5kg)', cost: 300, brand: 'Green City Labs', desc: '100% natural organic compost made from wet waste.' },
                    { id: 4, title: 'Reusable Canvas Tote Bag', cost: 100, brand: 'EcoPulse Store', desc: 'Durable, zero-waste cotton tote for shopping.' },
                    { id: 5, title: 'Free Parking Voucher (2 Hours)', cost: 500, brand: 'Smart Parking', desc: 'Valid at any municipal parking lot in central area.' }
                  ].map(coupon => {
                    const canAfford = ecoCoinsCount >= coupon.cost;
                    return (
                      <div 
                        key={coupon.id}
                        className="bg-white border border-slate-200/90 rounded-2xl p-5 flex flex-col justify-between shadow-2xs hover:border-primary/45 transition-colors"
                      >
                        <div>
                          <div className="flex justify-between items-start gap-2 mb-2">
                            <span className="text-[10px] font-black text-slate-400 uppercase tracking-wide">{coupon.brand}</span>
                            <span className="text-xs font-black text-primary bg-primary/5 px-2 py-0.5 rounded border border-primary/10">{coupon.cost} EC</span>
                          </div>
                          <h4 className="text-sm font-extrabold text-slate-900 mb-1">{coupon.title}</h4>
                          <p className="text-xs text-slate-500 font-semibold leading-relaxed mb-4">{coupon.desc}</p>
                        </div>
                        <button
                          disabled={!canAfford}
                          onClick={async () => {
                            if (user) {
                              const updatedCoins = user.eco_coins - coupon.cost;
                              try {
                                const updated = await updateUserProfile({ eco_coins: updatedCoins });
                                setUser(updated);
                                alert(`Successfully redeemed: ${coupon.title}! ${coupon.cost} EcoCoins deducted.`);
                              } catch (err) {
                                console.error('Failed to redeem coupon:', err);
                              }
                            }
                          }}
                          className={`w-full py-2.5 rounded-xl text-xs font-bold transition-all cursor-pointer ${
                            canAfford 
                              ? 'bg-primary text-white hover:bg-primary-container shadow-xs'
                              : 'bg-slate-100 text-slate-400 border border-slate-200 cursor-not-allowed'
                          }`}
                        >
                          {canAfford ? 'Redeem Coupon' : 'Insufficient Coins'}
                        </button>
                      </div>
                    );
                  })}
                </div>
              </div>
            </motion.div>
          ) : activeTab === 'Help & Support' ? (
            <motion.div
              key="Help & Support"
              initial={{ opacity: 0, y: 15 }}
              animate={{ opacity: 1, y: 0 }}
              className="space-y-6"
            >
              <div>
                <h2 className="text-2xl font-black text-slate-900">Help & Support</h2>
                <p className="text-xs font-semibold text-slate-500 mt-1">
                  Get instant support for waste management queries and chat with our AI agent.
                </p>
              </div>

              <div className="grid grid-cols-1 lg:grid-cols-12 gap-6">
                {/* Chatbot Banner */}
                <div className="lg:col-span-5 bg-white border border-slate-200/90 rounded-2xl p-5 flex flex-col justify-between items-center text-center shadow-xs">
                  <h3 className="text-base font-extrabold text-slate-900 mb-2 w-full text-left">AI Chat Support</h3>
                  
                  <div className="w-32 h-32 my-4 rounded-full bg-emerald-50 border border-emerald-100 flex items-center justify-center text-5xl select-none shadow-2xs">
                    💬
                  </div>

                  <p className="text-xs font-semibold text-slate-600 leading-relaxed max-w-xs mb-6">
                    Connect with our WhatsApp AI Chatbot to report issues, track trucks, or get instant civic answers.
                  </p>

                  <button
                    onClick={() => setShowWhatsAppModal(true)}
                    className="w-full py-3 bg-[#25D366] hover:bg-[#20ba59] text-white text-xs font-extrabold rounded-xl shadow-md flex justify-center items-center gap-2 cursor-pointer transition-all"
                  >
                    <span>💬 Chat on WhatsApp</span>
                  </button>
                </div>

                {/* FAQ List */}
                <div className="lg:col-span-7 bg-white border border-slate-200/90 rounded-2xl p-5 shadow-xs space-y-4">
                  <h3 className="text-base font-extrabold text-slate-900 mb-2">Frequently Asked Questions</h3>
                  <div className="divide-y divide-slate-100 space-y-3.5">
                    {[
                      { q: 'How do I earn EcoCoins?', a: 'You earn EcoCoins automatically whenever you report waste issues in the city that get verified and successfully resolved by the municipal collectors crew. Extra points are awarded for plastic sorting and hazardous waste alerts.' },
                      { q: 'How long does a complaint resolution take?', a: 'Standard complaints (like overflowing bins or missed garbage collection) are resolved within 12 to 24 hours. Urgent or hazardous waste complaints are given high priority and resolved within 4 to 6 hours.' },
                      { q: 'What is the ward limitation?', a: 'Your citizen portal allows reporting across any municipal ward. However, route updates, rewards collection packages, and community leaderboards are optimized for your registered ward area.' }
                    ].map((faq, idx) => (
                      <div key={idx} className="pt-3.5 first:pt-0">
                        <h4 className="text-sm font-extrabold text-slate-900 mb-1">{faq.q}</h4>
                        <p className="text-xs text-slate-500 font-semibold leading-relaxed">{faq.a}</p>
                      </div>
                    ))}
                  </div>
                </div>
              </div>
            </motion.div>
          ) : activeTab === 'Settings' ? (
            <motion.div
              key="Settings"
              initial={{ opacity: 0, y: 15 }}
              animate={{ opacity: 1, y: 0 }}
              className="space-y-6"
            >
              <div>
                <h2 className="text-2xl font-black text-slate-900">Portal Settings</h2>
                <p className="text-xs font-semibold text-slate-500 mt-1">
                  Update your civic registration profile details and ward preferences.
                </p>
              </div>

              <div className="max-w-2xl bg-white border border-slate-200/90 rounded-2xl p-6 shadow-xs">
                <form 
                  onSubmit={async (e) => {
                    e.preventDefault();
                    const formData = new FormData(e.target);
                    try {
                      const updated = await updateUserProfile({
                        full_name: formData.get('name'),
                        ward: formData.get('ward'),
                        phone: user?.phone || ""
                      });
                      setUser(updated);
                      alert('Profile settings updated successfully!');
                    } catch (err) {
                      console.error('Failed to update profile settings:', err);
                      alert('Failed to update profile settings.');
                    }
                  }}
                  className="space-y-4"
                >
                  <div>
                    <label className="block text-xs font-extrabold text-slate-600 mb-1.5 uppercase">Full Name</label>
                    <input 
                      type="text" 
                      name="name"
                      defaultValue={user?.name || user?.full_name || 'Priya Patil'}
                      required
                      className="w-full px-3.5 py-2.5 border border-slate-200 rounded-xl text-xs font-semibold focus:outline-none focus:border-primary"
                    />
                  </div>
                  <div>
                    <label className="block text-xs font-extrabold text-slate-600 mb-1.5 uppercase">Email Address</label>
                    <input 
                      type="email" 
                      name="email"
                      defaultValue={user?.email || 'priya@cityswap.io'}
                      required
                      className="w-full px-3.5 py-2.5 border border-slate-200 rounded-xl text-xs font-semibold focus:outline-none focus:border-primary"
                    />
                  </div>
                  <div>
                    <label className="block text-xs font-extrabold text-slate-600 mb-1.5 uppercase">Registered Ward</label>
                    <select 
                      name="ward"
                      defaultValue={user?.ward || 'Ward 12'}
                      className="w-full px-3.5 py-2.5 border border-slate-200 rounded-xl text-xs font-semibold bg-white focus:outline-none focus:border-primary"
                    >
                      <option value="Ward 12">Ward 12 - Central District</option>
                      <option value="Ward 14">Ward 14 - North District</option>
                      <option value="Ward 08">Ward 08 - South District</option>
                    </select>
                  </div>
                  <div className="pt-2 border-t border-slate-100 flex justify-end">
                    <button 
                      type="submit"
                      className="px-5 py-2.5 bg-primary text-white text-xs font-extrabold rounded-xl shadow-xs hover:bg-primary-container cursor-pointer transition-colors"
                    >
                      Save Changes
                    </button>
                  </div>
                </form>
              </div>
            </motion.div>
          ) : (
            <>
              {/* ----------------------------------------------------------- */}
              {/* ROW 1: 3 KPI STAT CARDS & RIGHT BANNER                      */}
              {/* ----------------------------------------------------------- */}
              <div className="grid grid-cols-1 lg:grid-cols-12 gap-5">
                
                {/* Left 3 Stat Cards (7 Cols) */}
                <div className="lg:col-span-7 space-y-5 flex flex-col justify-between">
                  
                  <div className="grid grid-cols-3 gap-4">
                    
                    {/* Stat 1: Total Complaints */}
                    <motion.div whileHover={{ y: -2 }} className="bg-white p-4 sm:p-5 rounded-2xl border border-slate-200/90 shadow-2xs">
                      <div className="text-xs font-bold text-slate-500">Total Complaints</div>
                      <div className="text-2xl sm:text-3xl font-black text-slate-900 mt-2">
                        {totalComplaintsCount}
                      </div>
                    </motion.div>

                    {/* Stat 2: In Progress */}
                    <motion.div whileHover={{ y: -2 }} className="bg-white p-4 sm:p-5 rounded-2xl border border-slate-200/90 shadow-2xs">
                      <div className="text-xs font-bold text-slate-500">In Progress</div>
                      <div className="text-2xl sm:text-3xl font-black text-slate-900 mt-2">
                        {inProgressCount}
                      </div>
                    </motion.div>

                    {/* Stat 3: EcoCoins */}
                    <motion.div whileHover={{ y: -2 }} className="bg-white p-4 sm:p-5 rounded-2xl border border-slate-200/90 shadow-2xs">
                      <div className="text-xs font-bold text-slate-500">EcoCoins</div>
                      <div className="flex items-center justify-between mt-2">
                        <span className="text-2xl sm:text-3xl font-black text-slate-900">
                          {ecoCoinsCount}
                        </span>
                        <div className="w-7 h-7 rounded-full bg-amber-400 text-amber-950 flex items-center justify-center font-bold text-xs shadow-xs border border-amber-300">
                          🪙
                        </div>
                      </div>
                    </motion.div>

                  </div>

                  {/* My Recent Complaints Panel Matching CITIZEN.png */}
                  <div className="bg-white p-5 rounded-2xl border border-slate-200/90 shadow-2xs flex-1 flex flex-col justify-between">
                    <div className="flex items-center justify-between mb-3">
                      <h3 className="text-base font-extrabold text-slate-900">My Recent Complaints</h3>
                      <button
                        onClick={() => setShowReportModal(true)}
                        className="text-xs font-bold text-[#02471f] hover:underline flex items-center gap-1 cursor-pointer"
                      >
                        <Plus className="w-3.5 h-3.5" />
                        <span>Add Complaint</span>
                      </button>
                    </div>

                    <div className="overflow-x-auto">
                      <table className="w-full text-left text-xs font-semibold text-slate-600">
                        <tbody className="divide-y divide-slate-100">
                          {recentComplaints.map((item) => (
                            <tr key={item.id} className="hover:bg-slate-50/80 transition-colors">
                              <td className="py-3 font-bold text-slate-900">{item.id}</td>
                              <td className="py-3 text-slate-700">{item.location}</td>
                              <td className="py-3 text-slate-700">{item.type}</td>
                              <td className="py-3">
                                <span className={getStatusBadgeClass(item.status)}>
                                  {item.status}
                                </span>
                              </td>
                            </tr>
                          ))}
                        </tbody>
                      </table>
                    </div>

                    <div className="pt-3 text-right">
                      <button
                        onClick={() => setActiveTab('My Complaints')}
                        className="text-xs font-bold text-[#02471f] hover:underline cursor-pointer"
                      >
                        View All
                      </button>
                    </div>
                  </div>

                </div>

                {/* Right Panel: Report New Waste Card (5 Cols) Matching CITIZEN.png */}
                <div className="lg:col-span-5 bg-white p-5 sm:p-6 rounded-2xl border border-slate-200/90 shadow-2xs flex flex-col items-center justify-between text-center">
                  
                  <h3 className="text-base font-extrabold text-slate-900 mb-2 w-full text-left">
                    Report New Waste
                  </h3>

                  {/* Recycling Illustration Image */}
                  <div className="w-full max-w-[240px] h-36 my-2 flex items-center justify-center overflow-hidden">
                    <img
                      src="/girl.png"
                      alt="Citizens Recycling Waste"
                      className="w-full h-full object-contain drop-shadow-md"
                    />
                  </div>

                  <p className="text-xs font-semibold text-slate-600 max-w-xs leading-relaxed my-2">
                    Help your city stay clean. Report waste in just a few seconds.
                  </p>

                  <div className="w-full space-y-2">
                    <button
                      onClick={() => setShowReportModal(true)}
                      className="w-full py-3 px-4 bg-[#02471f] hover:bg-[#003617] text-white text-xs sm:text-sm font-extrabold rounded-xl shadow-md hover:shadow-lg transition-all cursor-pointer flex items-center justify-center gap-2"
                    >
                      <Camera className="w-4 h-4" />
                      <span>Report Issue in App</span>
                    </button>

                    <button
                      onClick={() => setShowWhatsAppModal(true)}
                      className="w-full py-2.5 px-4 bg-emerald-50 hover:bg-emerald-100 text-[#02471f] border border-emerald-200 text-xs font-extrabold rounded-xl transition-all cursor-pointer flex items-center justify-center gap-2"
                    >
                      <MessageCircle className="w-4 h-4" />
                      <span>Report via WhatsApp</span>
                    </button>
                  </div>

                </div>

              </div>

              {/* ----------------------------------------------------------- */}
              {/* ROW 2: HOW IT WORKS (4 STEP CARDS MATCHING CITIZEN.PNG)     */}
              {/* ----------------------------------------------------------- */}
              <div className="bg-white p-5 sm:p-6 rounded-2xl border border-slate-200/90 shadow-2xs space-y-4">
                <h3 className="text-base font-extrabold text-slate-900">How It Works</h3>

                <div className="grid grid-cols-1 sm:grid-cols-2 lg:grid-cols-4 gap-4">
                  {steps.map((step, idx) => {
                    const IconComponent = step.icon;
                    return (
                      <div
                        key={step.title}
                        className="p-4 rounded-xl bg-slate-50/80 border border-slate-100 hover:border-emerald-200 transition-all flex items-start gap-3"
                      >
                        <div className="w-9 h-9 rounded-xl bg-[#02471f] text-white flex items-center justify-center font-bold shrink-0 shadow-xs">
                          <IconComponent className="w-4 h-4" />
                        </div>
                        <div>
                          <div className="text-xs font-extrabold text-slate-900">{step.title}</div>
                          <div className="text-[11px] font-semibold text-slate-500 leading-snug mt-0.5">
                            {step.description}
                          </div>
                        </div>
                      </div>
                    );
                  })}
                </div>
              </div>
            </>
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

      {/* Report Waste Modal */}
      <ReportWasteModal
        isOpen={showReportModal}
        onClose={() => setShowReportModal(false)}
        user={user}
        onComplaintCreated={handleComplaintCreated}
      />

      {/* Complaint Details Modal */}
      {selectedComplaint && (
        <div className="fixed inset-0 z-[100] flex items-center justify-center p-4 sm:p-6">
          {/* Backdrop */}
          <div 
            className="absolute inset-0 bg-slate-900/40 backdrop-blur-xs transition-opacity" 
            onClick={() => setSelectedComplaint(null)}
          ></div>
          
          {/* Modal Content */}
          <div className="relative bg-white rounded-2xl shadow-2xl w-full max-w-2xl max-h-[90vh] overflow-y-auto flex flex-col">
            <div className="sticky top-0 bg-white border-b border-slate-100 px-6 py-4 flex justify-between items-center z-10">
              <div>
                <h3 className="text-lg font-black text-slate-900">Complaint Details</h3>
                <p className="text-[10px] font-black text-slate-400">ID: {selectedComplaint.id}</p>
              </div>
              <button 
                className="text-slate-400 hover:text-slate-600 p-2 rounded-full hover:bg-slate-50 transition-colors" 
                onClick={() => setSelectedComplaint(null)}
              >
                <X className="w-5 h-5" />
              </button>
            </div>
            
            <div className="p-6 flex-1 space-y-6">
              <div>
                <h4 className="text-base font-black text-slate-900 mb-2">{selectedComplaint.title || selectedComplaint.type}</h4>
                <p className="text-xs text-slate-600 font-semibold leading-relaxed mb-4">
                  {selectedComplaint.description || 'No additional details provided. Waste has been reported at the location specified.'}
                </p>
                {selectedComplaint.image_url && (
                  <div className="flex gap-2">
                    <img 
                      alt="Evidence" 
                      className="w-24 h-24 object-cover rounded-xl border border-slate-200" 
                      src={selectedComplaint.image_url.startsWith('http') ? selectedComplaint.image_url : `${BACKEND_BASE_URL}${selectedComplaint.image_url}`} 
                    />
                  </div>
                )}
              </div>

              {/* Timeline */}
              <div>
                <h4 className="text-xs font-black text-slate-400 uppercase tracking-wider mb-4">Resolution Timeline</h4>
                <div className="relative border-l-2 border-slate-200 ml-3 space-y-6">
                  {/* Timeline Item 1 */}
                  {selectedComplaint.status === 'Completed' && (
                    <div className="relative pl-6">
                      <div className="absolute w-3.5 h-3.5 rounded-full bg-emerald-500 border-4 border-white -left-[8px] top-1"></div>
                      <div className="flex justify-between items-start mb-1 text-xs font-bold">
                        <h5 className="text-slate-900">Issue Resolved</h5>
                        <span className="text-slate-400 text-[10px]">Just now</span>
                      </div>
                      <p className="text-xs text-slate-500 font-semibold">The crew has cleared the waste and verified status.</p>
                    </div>
                  )}
                  {/* Timeline Item 2 */}
                  {(selectedComplaint.status === 'In Progress' || selectedComplaint.status === 'Completed') && (
                    <div className="relative pl-6">
                      <div className="absolute w-3.5 h-3.5 rounded-full bg-amber-500 border-4 border-white -left-[8px] top-1"></div>
                      <div className="flex justify-between items-start mb-1 text-xs font-bold">
                        <h5 className="text-slate-900">Crew Dispatched</h5>
                        <span className="text-slate-400 text-[10px]">Recent</span>
                      </div>
                      <p className="text-xs text-slate-500 font-semibold">A sanitation vehicle has been assigned to cleanup the site.</p>
                    </div>
                  )}
                  {/* Timeline Item 3 */}
                  <div className="relative pl-6">
                    <div className="absolute w-3.5 h-3.5 rounded-full bg-primary border-4 border-white -left-[8px] top-1"></div>
                    <div className="flex justify-between items-start mb-1 text-xs font-bold">
                      <h5 className="text-slate-900">Report Submitted</h5>
                      <span className="text-slate-400 text-[10px]">Registered</span>
                    </div>
                    <p className="text-xs text-slate-500 font-semibold">The initial alert was verified and logged into our smart system.</p>
                  </div>
                </div>
              </div>
            </div>

            <div className="sticky bottom-0 bg-slate-50 border-t border-slate-100 px-6 py-4 flex justify-end gap-3">
              <button 
                className="px-4 py-2 bg-white border border-slate-200 text-slate-700 rounded-xl text-xs font-bold hover:bg-slate-50 transition-colors" 
                onClick={() => setSelectedComplaint(null)}
              >
                Close
              </button>
            </div>
          </div>
        </div>
      )}

    </div>
  );
};

export default DashboardPage;
