import React, { useState, useEffect } from 'react';
import { useNavigate } from 'react-router-dom';
import {
  fetchDriverTasks,
  updateDriverTaskStatus,
  fetchPerformanceData,
  fetchFuelLogs,
  addFuelEntry,
  fetchMessages,
  sendMessage
} from '../services/driverService';
import { getCurrentUser, logoutUser } from '../services/authService';
import ProfileModal from '../components/ProfileModal';
import InteractiveMap from '../components/InteractiveMap';
import { motion, AnimatePresence } from 'framer-motion';
import {
  LayoutDashboard,
  ClipboardList,
  Navigation,
  TrendingUp,
  Fuel,
  MessageSquare,
  User,
  Settings,
  LogOut,
  ChevronDown,
  MapPin,
  CheckCircle2,
  Clock,
  ArrowRight,
  Sparkles,
  Zap,
  Activity,
  AlertCircle,
  RefreshCw,
  X
} from 'lucide-react';

const DriverDashboardPage = () => {
  const navigate = useNavigate();
  const [activeTab, setActiveTab] = useState('Dashboard');
  const [driver, setDriver] = useState(null);
  const [isNavigating, setIsNavigating] = useState(false);
  const [showNavToast, setShowNavToast] = useState(false);
  const [showProfileModal, setShowProfileModal] = useState(false);

  const [tasks, setTasks] = useState([]);
  const [performance, setPerformance] = useState(null);
  const [fuelSummary, setFuelSummary] = useState(null);
  const [messagesOverview, setMessagesOverview] = useState(null);

  // Fuel form input state
  const [fuelOdometer, setFuelOdometer] = useState('');
  const [fuelLiters, setFuelLiters] = useState('');
  const [fuelCost, setFuelCost] = useState('');

  // Chat input state
  const [chatText, setChatText] = useState('');

  const loadDriverData = async () => {
    try {
      const [userSession, tList, perfData, fuelData, msgData] = await Promise.all([
        getCurrentUser(),
        fetchDriverTasks(),
        fetchPerformanceData(),
        fetchFuelLogs(),
        fetchMessages()
      ]);
      if (userSession) setDriver(userSession);
      setTasks(tList);
      setPerformance(perfData);
      setFuelSummary(fuelData);
      setMessagesOverview(msgData);
    } catch (err) {
      console.error('Error loading driver data:', err);
    }
  };

  useEffect(() => {
    getCurrentUser().then((userData) => {
      if (userData) {
        setDriver(userData);
      } else {
        navigate('/login', { replace: true });
      }
    });

    loadDriverData();
  }, []);

  const handleLogout = () => {
    logoutUser();
    navigate('/login');
  };

  const handleStartNavigation = () => {
    setIsNavigating(true);
    setShowNavToast(true);
    setTimeout(() => setShowNavToast(false), 3500);
  };

  const toggleTaskStatus = async (taskId) => {
    const currentTask = tasks.find(t => t.id === taskId);
    if (!currentTask) return;

    let newStatus = 'In Progress';
    if (currentTask.status === 'Pending') newStatus = 'In Progress';
    else if (currentTask.status === 'In Progress') newStatus = 'Completed';
    else newStatus = 'Pending';

    // Optimistically update UI
    setTasks(prevTasks =>
      prevTasks.map(task => {
        if (task.id === taskId) {
          const statusColor = newStatus === 'Pending' ? 'bg-amber-100 text-amber-800 border-amber-200' : 'bg-emerald-100 text-emerald-800 border-emerald-200';
          return { ...task, status: newStatus, statusColor };
        }
        return task;
      })
    );

    try {
      await updateDriverTaskStatus(taskId, newStatus);
      await loadDriverData();
    } catch (err) {
      console.error('Error updating task in PostgreSQL:', err);
    }
  };

  const handleFuelSubmit = async (e) => {
    e.preventDefault();
    if (!fuelOdometer || !fuelLiters || !fuelCost) return;
    try {
      await addFuelEntry(fuelOdometer, fuelLiters, fuelCost);
      setFuelOdometer('');
      setFuelLiters('');
      setFuelCost('');
      await loadDriverData();
      alert('Fuel entry saved successfully!');
    } catch (err) {
      console.error('Error adding fuel log:', err);
      alert('Failed to save fuel entry.');
    }
  };

  const handleSendMessage = async (e) => {
    e.preventDefault();
    if (!chatText.trim()) return;
    try {
      await sendMessage(chatText);
      setChatText('');
      await loadDriverData();
    } catch (err) {
      console.error('Error sending chat message:', err);
    }
  };

  const handleProfileUpdated = (updatedUser) => {
    setDriver(updatedUser);
  };

  // Compute live real-time driver telemetry from PostgreSQL tasks
  const totalStops = tasks.length;
  const completedStops = tasks.filter(t => t.status === 'Completed').length;
  const pendingStops = tasks.filter(t => t.status === 'Pending').length;
  const progressPercent = totalStops > 0 ? Math.round((completedStops / totalStops) * 100) : 0;

  // Driver GPS coordinates [lat, lng]
  const driverGPS = [18.524, 73.852];

  // Sidebar navigation items matching DRIVER.png
  const navItems = [
    { name: 'Dashboard', icon: LayoutDashboard },
    { name: 'My Tasks', icon: ClipboardList },
    { name: 'Route & Navigation', icon: Navigation, action: handleStartNavigation },
    { name: 'My Performance', icon: TrendingUp },
    { name: 'Fuel Log', icon: Fuel },
    { name: 'Messages', icon: MessageSquare, badge: 3 },
    { name: 'Profile Settings', icon: User, action: () => setShowProfileModal(true) },
    { name: 'Settings', icon: Settings, action: () => setShowProfileModal(true) },
  ];

  const [mobileMenuOpen, setMobileMenuOpen] = useState(false);

  return (
    <div className="min-h-screen bg-[#f9f9ff] font-sans text-[#141b2c] flex select-none">
      
      {/* Toast Alert for Navigation */}
      <AnimatePresence>
        {showNavToast && (
          <motion.div
            initial={{ opacity: 0, y: -20 }}
            animate={{ opacity: 1, y: 0 }}
            exit={{ opacity: 0, y: -20 }}
            className="fixed top-6 right-6 z-50 bg-[#005c2b] text-white px-5 py-3 rounded-2xl shadow-xl flex items-center gap-3 font-bold text-xs"
          >
            <Navigation className="w-5 h-5 fill-current animate-bounce" />
            <span>Turn-by-Turn GPS Navigation Started on Interactive OpenStreetMap!</span>
          </motion.div>
        )}
      </AnimatePresence>

      {/* Mobile Top Header */}
      <div className="md:hidden fixed top-0 left-0 right-0 h-16 bg-primary text-white flex items-center justify-between px-4 z-[100] shadow-md">
        <div className="flex items-center gap-2.5">
          <button
            onClick={() => setMobileMenuOpen(!mobileMenuOpen)}
            className="p-2 rounded-lg bg-white/10 hover:bg-white/20 text-white cursor-pointer"
            aria-label="Toggle menu"
          >
            <span className="material-symbols-outlined text-xl">{mobileMenuOpen ? 'close' : 'menu'}</span>
          </button>
          <span className="font-extrabold text-sm tracking-tight">Driver Portal</span>
        </div>
        <div className="flex items-center gap-2">
          <button
            onClick={loadDriverData}
            className="p-2 rounded-lg bg-white/10 text-white cursor-pointer"
            title="Refresh Data"
          >
            <RefreshCw className="w-4 h-4" />
          </button>
          <div
            onClick={() => setShowProfileModal(true)}
            className="w-8 h-8 rounded-full bg-white/20 flex items-center justify-center font-black text-xs cursor-pointer"
          >
            {driver?.name ? driver.name.charAt(0).toUpperCase() : 'R'}
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
              className="md:hidden fixed left-0 top-0 bottom-0 w-[280px] bg-primary text-white z-[110] flex flex-col py-6 shadow-2xl"
            >
              <div className="px-6 mb-6 flex items-center justify-between">
                <div>
                  <h1 className="text-base font-bold text-white leading-none">City Swap</h1>
                  <p className="text-[10px] font-medium text-white/70 mt-1">Driver Portal</p>
                </div>
                <button
                  onClick={() => setMobileMenuOpen(false)}
                  className="p-1.5 rounded-lg bg-white/10 text-white"
                >
                  <X className="w-4 h-4" />
                </button>
              </div>

              <div className="flex-1 flex flex-col gap-1 overflow-y-auto">
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
                      className={`mx-4 py-3 px-4 flex items-center justify-between rounded-lg cursor-pointer ${
                        isActive
                          ? 'bg-white/15 text-white font-bold'
                          : 'text-white/70 hover:text-white hover:bg-white/10'
                      }`}
                    >
                      <div className="flex items-center gap-3">
                        <Icon className="w-4 h-4" />
                        <span className="text-xs font-semibold">{item.name}</span>
                      </div>
                      {item.badge && (
                        <span className="bg-red-500 text-white text-[10px] px-1.5 py-0.5 rounded-full font-black">
                          {item.badge}
                        </span>
                      )}
                    </button>
                  );
                })}
              </div>

              <div className="mt-auto px-4 pt-4 border-t border-white/10 space-y-2">
                <button
                  onClick={handleLogout}
                  className="w-full py-2 bg-[#ba1a1a] hover:bg-red-700 text-white font-bold rounded-lg text-xs"
                >
                  Sign Out
                </button>
              </div>
            </motion.div>
          </>
        )}
      </AnimatePresence>

      {/* ----------------------------------------------------------------- */}
      {/* LEFT SIDEBAR NAVIGATION MATCHING STITCH DESIGN                    */}
      {/* ----------------------------------------------------------------- */}
      <nav className="w-[280px] h-screen fixed left-0 top-0 bg-primary text-white border-r border-[#EAECF0] shadow-lg flex flex-col py-6 z-20 hidden md:flex">
        
        <div className="px-6 mb-8 flex items-center gap-3">
          <div className="w-10 h-10 bg-white rounded-full flex items-center justify-center text-primary font-bold">
            <svg className="w-6 h-6 fill-current text-primary" viewBox="0 0 24 24">
              <path d="M12 2A10 10 0 0 0 2 12a9.9 9.9 0 0 0 2.25 6.33l-1.42 1.42a1 1 0 0 0 .71 1.71h5a1 1 0 0 0 1-1v-5a1 1 0 0 0-1.71-.71L6.44 16.14A8 8 0 1 1 12 20a1 1 0 0 0 0 2 10 10 0 0 0 10-10A10 10 0 0 0 12 2zm1 5h-2v6h5v-2h-3V7z"/>
            </svg>
          </div>
          <div>
            <h1 className="text-base font-bold text-white leading-none">City Swap</h1>
            <p className="text-[10px] font-medium text-white/70 mt-1">Driver Portal</p>
          </div>
        </div>

        {/* Navigation Links */}
        <div className="flex-1 flex flex-col gap-1 overflow-y-auto">
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
                className={`mx-4 py-3 px-4 flex items-center justify-between rounded-lg transition-colors cursor-pointer ${
                  isActive
                    ? 'bg-white/15 text-white font-bold'
                    : 'text-white/70 hover:text-white hover:bg-white/10'
                }`}
              >
                <div className="flex items-center gap-3">
                  <Icon className="w-4 h-4" />
                  <span className="text-xs font-semibold">{item.name}</span>
                </div>
                {item.badge && (
                  <span className="bg-red-500 text-white text-[10px] px-1.5 py-0.5 rounded-full font-black">
                    {item.badge}
                  </span>
                )}
              </button>
            );
          })}
        </div>

        {/* Footer Profile */}
        <div className="mt-auto px-4 pt-4 border-t border-white/10 space-y-3">
          <div
            onClick={() => setShowProfileModal(true)}
            className="flex items-center gap-3 p-3 bg-white/5 rounded-lg cursor-pointer hover:bg-white/10 transition-colors"
          >
            <div className="w-10 h-10 rounded-full bg-white/20 flex items-center justify-center font-bold text-xs shrink-0 text-white border border-white/20">
              {driver?.name ? driver.name.charAt(0).toUpperCase() : 'R'}
            </div>
            <div className="flex-1 min-w-0">
              <p className="text-xs font-bold text-white truncate">
                {driver?.name || driver?.full_name || 'Driver'}
              </p>
              <p className="text-[10px] font-semibold text-emerald-300 flex items-center gap-1">
                <span>EcoCoins: {driver?.eco_coins || 100}</span>
              </p>
            </div>
          </div>
          <button
            onClick={handleLogout}
            className="w-full py-2 bg-[#ba1a1a] hover:bg-red-700 text-white font-bold rounded-lg text-xs transition-colors cursor-pointer"
          >
            Sign Out
          </button>
        </div>
      </nav>

      {/* ----------------------------------------------------------------- */}
      {/* RIGHT MAIN CONTENT AREA MATCHING STITCH                           */}
      {/* ----------------------------------------------------------------- */}
      <main className="flex-1 ml-0 md:ml-[280px] w-full max-w-full flex flex-col min-h-screen pt-16 md:pt-0">
        
        {/* TopAppBar */}
        <header className="h-16 w-full flex items-center sticky top-0 z-10 bg-white border-b border-[#EAECF0]">
          <div className="flex justify-between items-center px-6 w-full">
            <h2 className="text-lg font-bold text-[#141b2c] tracking-tight">
              Driver Telematics &amp; Live GPS Mapping
            </h2>
            <div className="flex items-center gap-4">
              <button className="text-slate-500 hover:text-[#00421d] transition-colors focus:outline-none p-2 rounded-full hover:bg-slate-50 cursor-pointer">
                <svg className="w-5 h-5 fill-current" viewBox="0 0 24 24">
                  <path d="M12 22a2 2 0 0 0 2-2h-4a2 2 0 0 0 2 2zm6-6v-5c0-3.07-1.63-5.64-4.5-6.32V4a1.5 1.5 0 0 0-3 0v.68C7.64 5.36 6 7.92 6 11v5l-2 2v1h16v-1l-2-2z"/>
                </svg>
              </button>
              <div className="h-8 w-px bg-slate-200"></div>
              <div className="flex items-center gap-2">
                <span className="text-xs text-slate-500">Status:</span>
                <span className="inline-flex items-center gap-1.5 py-1 px-2.5 rounded-full text-[10px] font-bold bg-[#b6edbb]/40 text-[#005c2b]">
                  <span className="w-2 h-2 rounded-full bg-[#25D366]"></span>
                  On Duty
                </span>
              </div>
            </div>
          </div>
        </header>

        {/* Page Content */}
        <div className="p-6 md:p-8 flex-1 flex flex-col min-h-0 bg-[#F9FAFB]">
          
          {/* Top Header Bar */}
          <div className="flex flex-col sm:flex-row items-start sm:items-center justify-between gap-4 bg-white p-4 sm:p-5 rounded-3xl border border-slate-200/90 shadow-2xs">
            <div>
              <h1 className="text-xl sm:text-2xl font-black text-slate-900 tracking-tight">
                Driver Telematics & Live GPS Mapping
              </h1>
              <p className="text-xs font-semibold text-slate-500 mt-0.5">
                Built-in OpenStreetMap navigation with real-time citizen waste coordinates
              </p>
            </div>

            {/* Header Right Driver Card */}
            <div
              onClick={() => setShowProfileModal(true)}
              className="flex items-center gap-3 bg-white px-3.5 py-2 rounded-2xl border border-slate-200 shadow-2xs cursor-pointer hover:border-emerald-300 transition-all"
            >
              <div className="w-8 h-8 rounded-full bg-[#02471f] text-white flex items-center justify-center font-bold text-xs">
                {driver?.name ? driver.name.charAt(0).toUpperCase() : 'R'}
              </div>
              <div>
                <div className="text-xs font-extrabold text-slate-900">
                  {driver?.name || driver?.full_name || 'Driver'}
                </div>
                <div className="text-[10px] font-bold text-emerald-700">
                  ⚡ EcoCoins: {driver?.eco_coins || 100}
                </div>
              </div>
            </div>
          </div>

          {/* Sub-View Navigation if not on Dashboard */}
          {activeTab === 'My Tasks' ? (
            <motion.div
              key="My Tasks"
              initial={{ opacity: 0, y: 15 }}
              animate={{ opacity: 1, y: 0 }}
              className="bg-white rounded-3xl p-6 border border-slate-200/80 shadow-sm space-y-6"
            >
              <div className="flex flex-col sm:flex-row sm:items-center justify-between gap-4 pb-4 border-b border-slate-100">
                <div>
                  <h2 className="text-xl font-extrabold text-slate-900">My Task Queue</h2>
                  <p className="text-xs font-semibold text-slate-500 mt-1">
                    Route schedules and waste collection stops for today. Click a task to toggle status.
                  </p>
                </div>
                <button 
                  onClick={() => setActiveTab('Dashboard')}
                  className="px-4 py-2 bg-slate-100 hover:bg-slate-200 rounded-xl text-xs font-bold text-slate-700 transition-all cursor-pointer"
                >
                  ← Back to Main Dashboard
                </button>
              </div>

              <div className="space-y-3 max-w-3xl">
                {tasks.map((task) => (
                  <div
                    key={task.id}
                    onClick={() => toggleTaskStatus(task.id)}
                    className="p-4 rounded-2xl bg-slate-50 hover:bg-slate-100/90 border border-slate-200/70 flex items-center justify-between transition-all cursor-pointer group"
                  >
                    <div className="flex items-center gap-3">
                      <div className={`w-8 h-8 rounded-full flex items-center justify-center font-bold text-sm ${
                        task.status === 'Completed' ? 'bg-emerald-100 text-emerald-800' : 'bg-slate-200 text-slate-700'
                      }`}>
                        {task.status === 'Completed' ? '✓' : '!'}
                      </div>
                      <div>
                        <h4 className="text-xs font-black text-slate-900">{task.name}</h4>
                        <p className="text-[10px] text-slate-400 font-bold uppercase mt-0.5">Location Stop #{task.id}</p>
                      </div>
                    </div>
                    <span className={`px-2.5 py-0.5 rounded-lg text-[10px] font-black border ${task.statusColor}`}>
                      {task.status}
                    </span>
                  </div>
                ))}
              </div>
            </motion.div>
          ) : activeTab === 'Route & Navigation' ? (
            <motion.div
              key="Route & Navigation"
              initial={{ opacity: 0, y: 15 }}
              animate={{ opacity: 1, y: 0 }}
              className="space-y-6"
            >
              {/* Top Metrics Row */}
              <div className="grid grid-cols-2 md:grid-cols-4 gap-4">
                {/* Est. Completion */}
                <div className="bg-white rounded-2xl p-4 border border-slate-200 shadow-sm flex flex-col justify-between">
                  <p className="text-[10px] font-black text-slate-400 uppercase mb-2 tracking-wider">Est. Completion</p>
                  <div className="flex items-baseline gap-2">
                    <h3 className="text-2xl font-black text-slate-950">14:30</h3>
                    <span className="text-[10px] font-black text-primary bg-secondary-container/20 px-2 py-0.5 rounded-full">-15m</span>
                  </div>
                </div>
                {/* Distance Remaining */}
                <div className="bg-white rounded-2xl p-4 border border-slate-200 shadow-sm flex flex-col justify-between">
                  <p className="text-[10px] font-black text-slate-400 uppercase mb-2 tracking-wider">Distance Left</p>
                  <div className="flex items-baseline gap-2">
                    <h3 className="text-2xl font-black text-slate-950">12.4</h3>
                    <span className="text-xs font-bold text-slate-400">km</span>
                  </div>
                </div>
                {/* Traffic Status */}
                <div className="bg-white rounded-2xl p-4 border border-slate-200 shadow-sm flex flex-col justify-between">
                  <p className="text-[10px] font-black text-slate-400 uppercase mb-2 tracking-wider">Traffic Status</p>
                  <h3 className="text-base font-black text-amber-500 mt-2">Moderate</h3>
                </div>
                {/* Next Stop ETA */}
                <div className="bg-white rounded-2xl p-4 border border-slate-200 shadow-sm flex flex-col justify-between">
                  <p className="text-[10px] font-black text-slate-400 uppercase mb-2 tracking-wider">Next Stop ETA</p>
                  <div className="flex items-baseline gap-2">
                    <h3 className="text-2xl font-black text-slate-955">8</h3>
                    <span className="text-xs font-bold text-slate-400">mins</span>
                  </div>
                </div>
              </div>

              {/* Map and Route Side by Side */}
              <div className="grid grid-cols-1 lg:grid-cols-12 gap-6">
                <div className="lg:col-span-8 h-[480px] rounded-2xl border border-slate-200 overflow-hidden relative shadow-xs bg-slate-100">
                  <InteractiveMap center={[18.5204, 73.8567]} zoom={14} driverLocation={driverGPS} tasks={tasks} />
                </div>
                <div className="lg:col-span-4 bg-white border border-slate-200 rounded-2xl p-5 shadow-xs space-y-4">
                  <h3 className="text-sm font-extrabold text-slate-900">Current Navigation Details</h3>
                  <div className="space-y-3.5 text-xs font-semibold text-slate-600">
                    <div className="p-3 bg-slate-50 border border-slate-100 rounded-xl">
                      <p className="text-[10px] font-black text-slate-400 uppercase mb-1">Target Stop</p>
                      <p className="text-slate-900 font-extrabold">Sai Nagar Road</p>
                    </div>
                    <div className="p-3 bg-slate-50 border border-slate-100 rounded-xl">
                      <p className="text-[10px] font-black text-slate-400 uppercase mb-1">Instructions</p>
                      <p className="text-slate-900 font-extrabold">Turn left at Sai Chowk. Destination is 200m ahead.</p>
                    </div>
                  </div>
                </div>
              </div>
            </motion.div>
          ) : activeTab === 'My Performance' ? (
            <motion.div
              key="My Performance"
              initial={{ opacity: 0, y: 15 }}
              animate={{ opacity: 1, y: 0 }}
              className="space-y-6"
            >
              {/* Header */}
              <div className="flex justify-between items-end mb-6">
                <div>
                  <h1 className="text-xl font-bold text-slate-900">Performance Overview</h1>
                  <p className="text-xs text-slate-500 mt-1">Track your efficiency, earnings, and safety metrics for this week.</p>
                </div>
                <div className="flex items-center gap-2 bg-white border border-slate-200 rounded-lg p-1 shadow-sm">
                  <button className="px-4 py-1.5 text-xs font-semibold rounded text-slate-600 hover:bg-slate-50">Today</button>
                  <button className="px-4 py-1.5 text-xs font-bold rounded bg-[#005c2b] text-white shadow-xs">This Week</button>
                  <button className="px-4 py-1.5 text-xs font-semibold rounded text-slate-600 hover:bg-slate-50">Month</button>
                </div>
              </div>

              {/* Metrics Bento Grid */}
              <div className="grid grid-cols-1 md:grid-cols-2 lg:grid-cols-4 gap-6">
                {/* Collection Efficiency */}
                <div className="bg-white border border-slate-200 rounded-xl p-5 shadow-xs flex flex-col justify-between min-h-[120px]">
                  <div className="flex justify-between items-start mb-2">
                    <div className="w-10 h-10 rounded-lg bg-slate-100 flex items-center justify-center text-primary">
                      <TrendingUp className="w-5 h-5" />
                    </div>
                    <span className="inline-flex items-center gap-1 text-[10px] font-bold text-emerald-600 bg-emerald-50 px-2 py-0.5 rounded-full">
                      {performance?.collection_efficiency_pct || '+4.2%'}
                    </span>
                  </div>
                  <div>
                    <p className="text-[10px] font-bold text-slate-400 uppercase tracking-wider">Collection Efficiency</p>
                    <h3 className="text-3xl font-black text-slate-900 mt-1">{performance?.collection_efficiency || '94%'}</h3>
                  </div>
                </div>

                {/* EcoCoins */}
                <div className="bg-white border border-slate-200 rounded-xl p-5 shadow-xs flex flex-col justify-between min-h-[120px]">
                  <div className="flex justify-between items-start mb-2">
                    <div className="w-10 h-10 rounded-lg bg-slate-100 flex items-center justify-center text-amber-500">
                      <Zap className="w-5 h-5" />
                    </div>
                    <span className="inline-flex items-center gap-1 text-[10px] font-bold text-emerald-600 bg-emerald-50 px-2 py-0.5 rounded-full">
                      {performance?.eco_coins_earned || '120 earned'}
                    </span>
                  </div>
                  <div>
                    <p className="text-[10px] font-bold text-slate-400 uppercase tracking-wider">EcoCoins Balance</p>
                    <h3 className="text-3xl font-black text-slate-900 mt-1">{performance?.eco_coins_balance || (driver?.eco_coins || 1450)}</h3>
                  </div>
                </div>

                {/* Fuel Economy */}
                <div className="bg-white border border-slate-200 rounded-xl p-5 shadow-xs flex flex-col justify-between min-h-[120px]">
                  <div className="flex justify-between items-start mb-2">
                    <div className="w-10 h-10 rounded-lg bg-slate-100 flex items-center justify-center text-[#376941]">
                      <Fuel className="w-5 h-5" />
                    </div>
                    <span className="inline-flex items-center gap-1 text-[10px] font-bold text-red-600 bg-red-50 px-2 py-0.5 rounded-full">
                      {performance?.fuel_economy_pct || '-0.2 km/l'}
                    </span>
                  </div>
                  <div>
                    <p className="text-[10px] font-bold text-slate-400 uppercase tracking-wider">Fuel Economy</p>
                    <h3 className="text-3xl font-black text-slate-900 mt-1">{performance?.fuel_economy || '4.1 km/l'}</h3>
                  </div>
                </div>

                {/* Safety Score */}
                <div className="bg-primary border border-primary-container rounded-xl p-5 shadow-xs flex flex-col justify-between min-h-[120px] text-white">
                  <div className="flex justify-between items-start mb-2">
                    <div className="w-10 h-10 rounded-lg bg-white/20 flex items-center justify-center text-white">
                      <CheckCircle2 className="w-5 h-5" />
                    </div>
                    <span className="inline-flex items-center gap-1 text-[10px] font-bold bg-white/20 px-2 py-0.5 rounded-full">
                      {performance?.safety_score_pct || 'Top 5%'}
                    </span>
                  </div>
                  <div>
                    <p className="text-[10px] font-bold text-emerald-300 uppercase tracking-wider">Safety Score</p>
                    <h3 className="text-3xl font-black mt-1">{performance?.safety_score || '98/100'}</h3>
                  </div>
                </div>
              </div>

              {/* Data Section */}
              <div className="grid grid-cols-1 lg:grid-cols-12 gap-6">
                {/* Weekly Trends Chart */}
                <div className="lg:col-span-8 bg-white border border-slate-200 rounded-xl p-5 shadow-xs flex flex-col">
                  <div className="flex justify-between items-center mb-6">
                    <h3 className="text-sm font-bold text-slate-900">Weekly Performance Trends</h3>
                    <button className="text-xs font-bold text-primary flex items-center gap-1 hover:underline">
                      Detailed Report <ArrowRight className="w-3.5 h-3.5" />
                    </button>
                  </div>
                  
                  {/* Chart */}
                  <div className="flex-1 min-h-[220px] w-full relative flex items-end justify-between px-4 pb-8 pt-10 border-b border-l border-slate-200">
                    <div className="absolute left-[-35px] top-0 bottom-8 flex flex-col justify-between text-[9px] font-bold text-slate-400 items-end">
                      <span>100%</span>
                      <span>75%</span>
                      <span>50%</span>
                      <span>25%</span>
                      <span>0%</span>
                    </div>
                    <div className="absolute inset-0 border-t border-slate-100 top-[25%] left-0 right-0 z-0"></div>
                    <div className="absolute inset-0 border-t border-slate-100 top-[50%] left-0 right-0 z-0"></div>
                    <div className="absolute inset-0 border-t border-slate-100 top-[75%] left-0 right-0 z-0"></div>
                    
                    {/* Bars */}
                    {(performance?.weekly_trends || [
                      { day: 'Mon', h: '60%', active: false },
                      { day: 'Tue', h: '75%', active: false },
                      { day: 'Wed', h: '90%', active: true, value: '90%' },
                      { day: 'Thu', h: '65%', active: false },
                      { day: 'Fri', h: '80%', active: false },
                      { day: 'Sat', h: '45%', active: false },
                      { day: 'Sun', h: '30%', active: false },
                    ]).map((bar, idx) => (
                      <div
                        key={idx}
                        style={{ height: bar.h }}
                        className={`w-8 rounded-t-sm relative z-10 group cursor-pointer transition-colors ${
                          bar.active ? 'bg-primary shadow-[0_0_15px_rgba(0,92,43,0.3)]' : 'bg-slate-100 hover:bg-slate-200'
                        }`}
                      >
                        {bar.value && (
                          <div className="absolute -top-7 left-1/2 -translate-x-1/2 bg-slate-900 text-white text-[9px] py-1 px-1.5 rounded whitespace-nowrap z-20">
                            {bar.value} Efficiency
                          </div>
                        )}
                        <div className={`absolute -bottom-6 left-1/2 -translate-x-1/2 text-[9px] font-bold ${bar.active ? 'text-primary font-black' : 'text-slate-400'}`}>
                          {bar.day}
                        </div>
                      </div>
                    ))}
                  </div>

                  <div className="mt-6 flex justify-center gap-6">
                    <div className="flex items-center gap-2">
                      <div className="w-3 h-3 rounded-full bg-[#005c2b]"></div>
                      <span className="text-[10px] font-bold text-slate-500">Collection Efficiency</span>
                    </div>
                    <div className="flex items-center gap-2">
                      <div className="w-3 h-3 rounded-full bg-slate-200"></div>
                      <span className="text-[10px] font-bold text-slate-500">Route Completion</span>
                    </div>
                  </div>
                </div>

                {/* Achievements & Leaderboard */}
                <div className="lg:col-span-4 flex flex-col gap-6">
                  {/* Achievements */}
                  <div className="bg-white border border-slate-200 rounded-xl p-5 shadow-xs">
                    <h3 className="text-xs font-bold text-slate-900 mb-4 uppercase tracking-wider">Recent Achievements</h3>
                    <div className="flex gap-4">
                      {(performance?.achievements || [
                        { title: 'Perfect Week', subtitle: '100% stop coverage', unlocked: true, icon: 'Sparkles' },
                        { title: 'Eco Driver Lvl 3', subtitle: 'Save 50L fuel', unlocked: true, icon: 'Activity' },
                        { title: '100k Club', subtitle: 'Drive 100,000 km', unlocked: false, icon: 'AlertCircle' }
                      ]).map((ach, idx) => (
                        <div key={idx} className={`flex flex-col items-center gap-2 w-1/3 text-center ${!ach.unlocked ? 'opacity-50 grayscale' : ''}`}>
                          <div className={`w-12 h-12 rounded-full border-2 flex items-center justify-center ${
                            ach.title === 'Perfect Week' ? 'bg-amber-50 border-amber-400 text-amber-500' :
                            ach.title === 'Eco Driver Lvl 3' ? 'bg-[#b6edbb]/40 border-emerald-400 text-[#005c2b]' :
                            'bg-slate-100 border-slate-300 text-slate-400'
                          }`}>
                            {ach.title === 'Perfect Week' ? <Sparkles className="w-5 h-5" /> :
                             ach.title === 'Eco Driver Lvl 3' ? <Activity className="w-5 h-5" /> :
                             <AlertCircle className="w-5 h-5" />}
                          </div>
                          <span className="text-[9px] font-bold text-slate-600 leading-tight">{ach.title}</span>
                        </div>
                      ))}
                    </div>
                  </div>

                  {/* Leaderboard */}
                  <div className="bg-white border border-slate-200 rounded-xl p-5 shadow-xs flex-1">
                    <div className="flex justify-between items-center mb-4">
                      <h3 className="text-xs font-bold text-slate-900 uppercase tracking-wider">Ward 12 Leaderboard</h3>
                      <span className="text-[10px] font-bold text-slate-400">Top 3</span>
                    </div>
                    <div className="space-y-3">
                      {(performance?.leaderboard || [
                        { rank: 1, initials: 'AS', name: 'Anita Sharma', points: 2100, is_you: false },
                        { rank: 2, initials: 'BB', name: driver?.full_name || driver?.name || 'Driver', points: driver?.eco_coins || 1450, is_you: true },
                        { rank: 3, initials: 'SJ', name: 'Suresh Joshi', points: 1220, is_you: false }
                      ]).map((entry, idx) => (
                        <div key={idx} className={`flex items-center gap-3 p-2 rounded-lg ${
                          entry.is_you ? 'bg-[#005c2b]/5 border border-[#005c2b]/20 relative' : 
                          entry.rank === 1 ? 'bg-amber-500/5 border border-amber-500/20' : 'hover:bg-slate-50'
                        }`}>
                          {entry.is_you && <div className="absolute -left-0.5 top-1/2 -translate-y-1/2 w-1 h-5 bg-[#005c2b] rounded-r"></div>}
                          <div className={`w-4 text-center font-extrabold text-xs ${
                            entry.rank === 1 ? 'text-amber-600' : 'text-slate-500'
                          }`}>{entry.rank}</div>
                          <div className="w-7 h-7 rounded-full bg-slate-200 flex items-center justify-center text-slate-500 font-bold text-xs">{entry.initials}</div>
                          <div className="flex-1 min-w-0">
                            <p className="text-xs font-bold text-slate-800 truncate">
                              {entry.name}
                              {entry.is_you && <span className="text-[8px] bg-[#005c2b] text-white px-1 py-0.2 rounded ml-1 font-normal">YOU</span>}
                            </p>
                          </div>
                          <span className="text-xs font-bold text-primary">{entry.points} pts</span>
                        </div>
                      ))}
                    </div>
                  </div>
                </div>
              </div>
            </motion.div>
          ) : activeTab === 'Fuel Log' ? (
            <motion.div
              key="Fuel Log"
              initial={{ opacity: 0, y: 15 }}
              animate={{ opacity: 1, y: 0 }}
              className="space-y-6"
            >
              {/* Header */}
              <div className="mb-6">
                <h1 className="text-xl font-bold text-slate-900 font-sans tracking-tight">Fuel Log Management</h1>
                <p className="text-xs text-slate-500 mt-1">Track fuel efficiency and compactor truck refills.</p>
              </div>

              {/* Metrics Row */}
              <div className="grid grid-cols-1 md:grid-cols-3 gap-6">
                {/* Current Fuel Level */}
                <div className="bg-white border border-slate-200 rounded-xl p-5 shadow-xs flex flex-col justify-between min-h-[120px]">
                  <div className="flex items-center justify-between mb-4">
                    <h3 className="text-[10px] font-bold text-slate-400 uppercase tracking-wider">Current Fuel Level</h3>
                    <Fuel className="w-4 h-4 text-primary" />
                  </div>
                  <div>
                    <h3 className="text-3xl font-black text-slate-900">{fuelSummary?.current_fuel_level || 62}%</h3>
                    <div className="w-full bg-slate-100 rounded-full h-2 mt-3">
                      <div className="bg-primary h-2 rounded-full" style={{ width: `${fuelSummary?.current_fuel_level || 62}%` }}></div>
                    </div>
                  </div>
                </div>

                {/* Average Consumption */}
                <div className="bg-white border border-slate-200 rounded-xl p-5 shadow-xs flex flex-col justify-between min-h-[120px]">
                  <div className="flex items-center justify-between mb-4">
                    <h3 className="text-[10px] font-bold text-slate-400 uppercase tracking-wider">Avg Consumption</h3>
                    <TrendingUp className="w-4 h-4 text-slate-400" />
                  </div>
                  <div>
                    <h3 className="text-3xl font-black text-slate-900">{fuelSummary?.avg_consumption || 3.8} <span className="text-xs text-slate-400 font-semibold">km/L</span></h3>
                    <p className="text-[10px] font-bold text-emerald-600 mt-2 flex items-center">
                      +0.2 km/L this week
                    </p>
                  </div>
                </div>

                {/* Spent Month */}
                <div className="bg-white border border-slate-200 rounded-xl p-5 shadow-xs flex flex-col justify-between min-h-[120px]">
                  <div className="flex items-center justify-between mb-4">
                    <h3 className="text-[10px] font-bold text-slate-400 uppercase tracking-wider">Spent (Month)</h3>
                    <Zap className="w-4 h-4 text-amber-500" />
                  </div>
                  <div>
                    <h3 className="text-3xl font-black text-slate-900">₹{(fuelSummary?.total_spent || 12450).toLocaleString()}</h3>
                    <p className="text-[10px] font-bold text-slate-400 mt-2">Based on {(fuelSummary?.logs || []).length || 3} refills</p>
                  </div>
                </div>
              </div>

              {/* Form & Table */}
              <div className="grid grid-cols-1 xl:grid-cols-12 gap-6">
                {/* Table */}
                <div className="xl:col-span-8 bg-white border border-slate-200 rounded-xl shadow-xs overflow-hidden flex flex-col">
                  <div className="p-4 border-b border-slate-100 flex justify-between items-center bg-slate-50/50">
                    <h3 className="text-xs font-bold text-slate-900 uppercase tracking-wider">Recent Fuel Logs</h3>
                    <button className="text-xs font-bold text-primary flex items-center gap-1 hover:underline">
                      Export
                    </button>
                  </div>
                  <div className="overflow-x-auto">
                    <table className="w-full text-left border-collapse">
                      <thead>
                        <tr className="bg-slate-50 border-b border-slate-100 text-slate-400 text-[10px] font-bold uppercase tracking-wider">
                          <th className="p-4">Date</th>
                          <th className="p-4">Odometer</th>
                          <th className="p-4">Liters</th>
                          <th className="p-4">Cost</th>
                          <th className="p-4 text-right">Receipt</th>
                        </tr>
                      </thead>
                      <tbody className="divide-y divide-slate-100 text-xs font-semibold text-slate-700">
                        {(fuelSummary?.logs || []).map((log) => (
                          <tr key={log.id} className="hover:bg-slate-50/50 transition-colors">
                            <td className="p-4">{new Date(log.created_at).toLocaleDateString(undefined, { month: 'short', day: 'numeric', year: 'numeric' })}</td>
                            <td className="p-4">{log.odometer.toLocaleString()} km</td>
                            <td className="p-4">{log.liters.toFixed(1)} L</td>
                            <td className="p-4 font-bold text-slate-900">₹{log.cost.toLocaleString()}</td>
                            <td className="p-4 text-right text-slate-400">📄</td>
                          </tr>
                        ))}
                        {(fuelSummary?.logs || []).length === 0 && (
                          <tr>
                            <td colSpan="5" className="p-4 text-center text-slate-400">No fuel entries logged yet.</td>
                          </tr>
                        )}
                      </tbody>
                    </table>
                  </div>
                </div>

                {/* Form */}
                <div className="xl:col-span-4 bg-white border border-slate-200 rounded-xl p-5 shadow-xs">
                  <h3 className="text-xs font-bold text-slate-900 uppercase tracking-wider mb-5 flex items-center gap-2">
                    Add Fuel Entry
                  </h3>
                  <form onSubmit={handleFuelSubmit} className="space-y-4 text-xs font-semibold">
                    <div>
                      <label className="block text-slate-500 mb-1">Odometer Reading (km)</label>
                      <input 
                        type="number" 
                        placeholder="e.g. 45300" 
                        required 
                        value={fuelOdometer}
                        onChange={(e) => setFuelOdometer(e.target.value)}
                        className="w-full px-3 py-2 border border-slate-200 rounded-xl focus:outline-none focus:border-primary" 
                      />
                    </div>
                    <div className="grid grid-cols-2 gap-4">
                      <div>
                        <label className="block text-slate-500 mb-1">Volume (Liters)</label>
                        <input 
                          type="number" 
                          placeholder="0.0" 
                          step="0.1" 
                          required 
                          value={fuelLiters}
                          onChange={(e) => setFuelLiters(e.target.value)}
                          className="w-full px-3 py-2 border border-slate-200 rounded-xl focus:outline-none focus:border-primary" 
                        />
                      </div>
                      <div>
                        <label className="block text-slate-500 mb-1">Total Cost</label>
                        <input 
                          type="number" 
                          placeholder="₹ 0.00" 
                          required 
                          value={fuelCost}
                          onChange={(e) => setFuelCost(e.target.value)}
                          className="w-full px-3 py-2 border border-slate-200 rounded-xl focus:outline-none focus:border-primary" 
                        />
                      </div>
                    </div>
                    <button type="submit" className="w-full py-2.5 bg-[#005c2b] text-white text-xs font-extrabold rounded-xl hover:bg-primary-container transition-all cursor-pointer">
                      Submit Log
                    </button>
                  </form>
                </div>
              </div>
            </motion.div>
          ) : activeTab === 'Messages' ? (
            <motion.div
              key="Messages"
              initial={{ opacity: 0, y: 15 }}
              animate={{ opacity: 1, y: 0 }}
              className="flex gap-6 h-[calc(100vh-12rem)] min-h-[480px] overflow-hidden"
            >
              {/* Left Thread List */}
              <div className="w-1/3 max-w-[320px] bg-white border border-slate-200 rounded-xl shadow-xs flex flex-col overflow-hidden">
                <div className="p-4 border-b border-slate-100 bg-slate-50/50 flex justify-between items-center">
                  <h2 className="text-xs font-bold text-slate-900 uppercase tracking-wider">Conversations</h2>
                </div>
                <div className="flex-1 overflow-y-auto divide-y divide-slate-100">
                  {(messagesOverview?.conversations || [
                    { name: 'Dispatch Center', lastMessage: 'Avoid Main St due to construction.', time: '10:42 AM', active: true, role: 'Dispatcher' },
                    { name: 'Fleet Maintenance', lastMessage: 'Reminder: Vehicle inspection due tomorrow.', time: '09:15 AM', active: false, role: 'Maintenance' },
                    { name: 'District Team Alpha', lastMessage: 'Good job on the route completion guys.', time: 'Yesterday', active: false, role: 'Team' }
                  ]).map((conv, idx) => (
                    <div key={idx} className={`p-3 cursor-pointer ${conv.active ? 'bg-slate-50 border-l-4 border-[#005c2b]' : 'hover:bg-slate-50'}`}>
                      <div className="flex justify-between items-start mb-1 text-[10px] font-bold text-slate-400">
                        <span className="text-slate-900 font-extrabold flex items-center gap-1">{conv.name}</span>
                        <span className={conv.name === 'Fleet Maintenance' ? 'text-[#005c2b] font-black' : ''}>{conv.time}</span>
                      </div>
                      <p className={`text-xs truncate ${conv.name === 'Fleet Maintenance' ? 'text-slate-900 font-bold' : 'text-slate-500 font-semibold'}`}>{conv.lastMessage}</p>
                    </div>
                  ))}
                </div>
              </div>

              {/* Right Active Chat Pane */}
              <div className="flex-1 bg-white border border-slate-200 rounded-xl shadow-xs flex flex-col overflow-hidden">
                <div className="p-4 border-b border-slate-100 bg-slate-50/50 flex justify-between items-center">
                  <div>
                    <h2 className="text-xs font-extrabold text-slate-900 uppercase tracking-wider">Dispatch Center</h2>
                    <p className="text-[9px] text-emerald-600 font-bold flex items-center gap-1 mt-0.5">
                      <span className="w-1.5 h-1.5 rounded-full bg-emerald-500 inline-block animate-pulse"></span> Online
                    </p>
                  </div>
                </div>
                
                {/* Chat History */}
                <div className="flex-1 overflow-y-auto p-4 bg-slate-50/50 space-y-4">
                  {(messagesOverview?.messages || []).map((msg) => {
                    const isSentByMe = msg.sender_role === 'Driver';
                    return (
                      <div key={msg.id} className={`flex ${isSentByMe ? 'justify-end ml-auto' : 'justify-start'} max-w-lg`}>
                        <div className={`p-3 rounded-2xl shadow-xs text-xs font-bold ${
                          isSentByMe ? 'bg-[#005c2b] text-white rounded-br-none' : 'bg-white border border-slate-100 text-slate-700 rounded-bl-none'
                        }`}>
                          {msg.body}
                        </div>
                      </div>
                    );
                  })}
                  {(messagesOverview?.messages || []).length === 0 && (
                    <div className="text-center text-slate-400 text-xs py-10">No messages yet in this conversation.</div>
                  )}
                </div>

                {/* Chat Input */}
                <div className="p-3 border-t border-slate-100 bg-white">
                  <form onSubmit={handleSendMessage} className="flex gap-2">
                    <input 
                      type="text" 
                      placeholder="Type a message..." 
                      required 
                      value={chatText}
                      onChange={(e) => setChatText(e.target.value)}
                      className="flex-1 px-4 py-2 border border-slate-200 rounded-xl text-xs font-semibold focus:outline-none focus:border-primary" 
                    />
                    <button type="submit" className="px-4 py-2 bg-primary text-white text-xs font-extrabold rounded-xl hover:bg-primary-container cursor-pointer transition-colors shadow-xs">
                      Send
                    </button>
                  </form>
                </div>
              </div>
            </motion.div>
          ) : (
            <>
              {/* ----------------------------------------------------------- */}
              {/* ROW 1: 5 KPI STAT CARDS BOUND TO POSTGRESQL                 */}
              {/* ----------------------------------------------------------- */}
              <div className="grid grid-cols-2 sm:grid-cols-3 lg:grid-cols-5 gap-4">
                
                {/* Stat 1: Today's Duty */}
                <motion.div whileHover={{ y: -2 }} className="bg-white p-4 sm:p-5 rounded-2xl border border-slate-200/90 shadow-2xs">
                  <div className="text-xs font-bold text-slate-500">Today's Duty</div>
                  <div className="text-xl sm:text-2xl font-black text-slate-900 mt-2">
                    {driver?.ward || 'Ward 12'}
                  </div>
                </motion.div>

                {/* Stat 2: Total Stops */}
                <motion.div whileHover={{ y: -2 }} className="bg-white p-4 sm:p-5 rounded-2xl border border-slate-200/90 shadow-2xs">
                  <div className="text-xs font-bold text-slate-500">Total Stops</div>
                  <div className="text-xl sm:text-2xl font-black text-slate-900 mt-2">{totalStops}</div>
                </motion.div>

                {/* Stat 3: Completed */}
                <motion.div whileHover={{ y: -2 }} className="bg-white p-4 sm:p-5 rounded-2xl border border-slate-200/90 shadow-2xs">
                  <div className="text-xs font-bold text-slate-500">Completed</div>
                  <div className="text-xl sm:text-2xl font-black text-slate-900 mt-2">{completedStops}</div>
                </motion.div>

                {/* Stat 4: Pending */}
                <motion.div whileHover={{ y: -2 }} className="bg-white p-4 sm:p-5 rounded-2xl border border-slate-200/90 shadow-2xs">
                  <div className="text-xs font-bold text-slate-500">Pending</div>
                  <div className="text-xl sm:text-2xl font-black text-slate-900 mt-2">{pendingStops}</div>
                </motion.div>

                {/* Stat 5: Progress */}
                <motion.div whileHover={{ y: -2 }} className="bg-white p-4 sm:p-5 rounded-2xl border border-slate-200/90 shadow-2xs col-span-2 sm:col-span-1">
                  <div className="text-xs font-bold text-slate-500">Progress</div>
                  <div className="text-xl sm:text-2xl font-black text-slate-900 mt-1 mb-2">
                    {progressPercent}%
                  </div>
                  <div className="w-full bg-slate-100 h-2 rounded-full overflow-hidden">
                    <motion.div 
                      initial={{ width: 0 }}
                      animate={{ width: `${progressPercent}%` }}
                      transition={{ duration: 1, ease: 'easeOut' }}
                      className="bg-[#02471f] h-full rounded-full"
                    />
                  </div>
                </motion.div>

              </div>

              {/* ----------------------------------------------------------- */}
              {/* ROW 2: BUILT-IN INTERACTIVE LEAFLET MAP & MY TASKS          */}
              {/* ----------------------------------------------------------- */}
              <div className="grid grid-cols-1 lg:grid-cols-12 gap-5">
                
                {/* Column 1: Built-in Interactive Leaflet OpenStreetMap (5 Cols) */}
                <div className="lg:col-span-5 bg-white p-5 rounded-2xl border border-slate-200/90 shadow-2xs flex flex-col justify-between">
                  <div className="flex items-center justify-between mb-3">
                    <h3 className="text-base font-extrabold text-slate-900">Today's Live OpenStreetMap Route</h3>
                    <button
                      onClick={handleStartNavigation}
                      className="bg-blue-600 hover:bg-blue-700 text-white font-black text-[11px] px-3.5 py-1.5 rounded-xl shadow-xs transition-all cursor-pointer flex items-center gap-1.5"
                    >
                      <Navigation className="w-3.5 h-3.5 fill-current" />
                      <span>Start GPS Navigation</span>
                    </button>
                  </div>

                  {/* Built-in Interactive Leaflet Map */}
                  <InteractiveMap
                    center={[18.5204, 73.8567]}
                    zoom={13}
                    driverLocation={driverGPS}
                    tasks={tasks}
                    onCompleteTask={(id) => toggleTaskStatus(id)}
                    height="280px"
                  />
                </div>

                {/* Column 2: Next Stop & My Vehicle Sub-Cards (3.5 Cols) */}
                <div className="lg:col-span-3 space-y-4 flex flex-col justify-between">
                  
                  {/* Next Stop Card */}
                  <div className="bg-white p-4 rounded-2xl border border-slate-200/90 shadow-2xs flex-1 flex flex-col justify-between">
                    <div className="text-xs font-extrabold text-slate-500 uppercase tracking-wider">Next Stop</div>
                    <div className="my-2">
                      <div className="text-sm font-black text-slate-900 leading-tight">
                        {tasks.find(t => t.status === 'In Progress')?.name || '2. Sai Nagar, Main Road'}
                      </div>
                      <div className="text-[11px] font-bold text-emerald-700 mt-1 flex items-center gap-1">
                        <Clock className="w-3 h-3" /> ETA: 8 mins (GPS Tracked)
                      </div>
                    </div>
                    <button
                      onClick={() => toggleTaskStatus(tasks.find(t => t.status === 'In Progress')?.id || 2)}
                      className="w-full py-2 bg-emerald-100 hover:bg-emerald-200 text-[#02471f] font-extrabold text-xs rounded-xl transition-all cursor-pointer"
                    >
                      Complete Next Stop
                    </button>
                  </div>

                  {/* My Vehicle Card */}
                  <div className="bg-white p-4 rounded-2xl border border-slate-200/90 shadow-2xs flex-1 flex flex-col justify-between">
                    <div className="text-xs font-extrabold text-slate-500 uppercase tracking-wider">My Vehicle</div>
                    <div className="my-2">
                      <div className="text-sm font-black text-slate-900">Compactor Truck #04</div>
                      <div className="text-[11px] font-bold text-slate-500 mt-0.5">Reg: MH12 AB 4567</div>
                    </div>
                    <div className="flex items-center justify-between text-xs font-bold text-emerald-700 bg-emerald-50 px-2.5 py-1.5 rounded-xl border border-emerald-100">
                      <span>Fuel Level</span>
                      <span className="font-extrabold">78% ⛽</span>
                    </div>
                  </div>

                </div>

                {/* Column 3: My Tasks Interactive Table (3.5 Cols) */}
                <div className="lg:col-span-4 bg-white p-5 rounded-2xl border border-slate-200/90 shadow-2xs flex flex-col justify-between">
                  <div className="flex items-center justify-between mb-3">
                    <h3 className="text-base font-extrabold text-slate-900">My Route Tasks</h3>
                    <span className="text-[10px] font-bold text-slate-500">Click to Toggle Status</span>
                  </div>

                  <div className="space-y-2.5 overflow-y-auto max-h-[220px] pr-1">
                    {tasks.map((task) => (
                      <div
                        key={task.id}
                        onClick={() => toggleTaskStatus(task.id)}
                        className="p-3 rounded-xl bg-slate-50 hover:bg-slate-100/90 border border-slate-200/70 flex items-center justify-between transition-all cursor-pointer group"
                      >
                        <div className="flex items-center gap-2.5 min-w-0">
                          <CheckCircle2 className={`w-4 h-4 shrink-0 ${task.status === 'Completed' ? 'text-emerald-600' : 'text-slate-400'}`} />
                          <span className="text-xs font-extrabold text-slate-800 truncate">
                            {task.name}
                          </span>
                        </div>
                        <span className={`px-2 py-0.5 rounded-lg text-[10px] font-black border shrink-0 ${task.statusColor}`}>
                          {task.status}
                        </span>
                      </div>
                    ))}
                  </div>

                  <div className="pt-3 text-xs font-semibold text-slate-500 text-center">
                    Status updates sync live to PostgreSQL database & map pins.
                  </div>
                </div>

              </div>
            </>
          )}

        </div>
      </main>

      {/* Driver Profile Settings Modal */}
      <ProfileModal
        isOpen={showProfileModal}
        onClose={() => setShowProfileModal(false)}
        user={driver}
        onProfileUpdated={handleProfileUpdated}
      />

    </div>
  );
};

export default DriverDashboardPage;
