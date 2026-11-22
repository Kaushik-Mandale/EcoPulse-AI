import React, { useState, useEffect } from 'react';
import { useNavigate } from 'react-router-dom';
import {
  fetchDriverTasks,
  acceptDriverTask, startDriverTask, submitDriverEvidence, requestTaskVerification,
  fetchPerformanceData,
  fetchFuelLogs,
  addFuelEntry,
  fetchMessages,
  sendMessage
} from '../services/driverService';
import { getCurrentUser, logoutUser } from '../services/authService';
import ProfileModal from '../components/ProfileModal';
import FieldOperationsShell from '../components/field-operations/FieldOperationsShell';
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
  ChevronDown,
  MapPin,
  CheckCircle2,
  Clock,
  ArrowRight,
  Sparkles,
  Zap,
  Activity,
  AlertCircle,
} from 'lucide-react';

const DriverDashboardPage = () => {
  const navigate = useNavigate();
  const [activeTab, setActiveTab] = useState('Dashboard');
  const [driver, setDriver] = useState(null);
  const [showNavToast, setShowNavToast] = useState(false);
  const [showProfileModal, setShowProfileModal] = useState(false);
  const [dataLoading, setDataLoading] = useState(true);
  const [dataError, setDataError] = useState('');
  const [taskBusyId, setTaskBusyId] = useState(null);
  const [taskMessage, setTaskMessage] = useState('');
  const [evidenceDrafts, setEvidenceDrafts] = useState({});

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
    setDataLoading(true);
    setDataError('');
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
      setDataError('Unable to load driver data. Please retry.');
    } finally {
      setDataLoading(false);
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

  const handleLogout = async () => {
    await logoutUser();
    navigate('/login');
  };

  const handleStartNavigation = () => {
    setShowNavToast(true);
    setTimeout(() => setShowNavToast(false), 3500);
  };

  const runTaskAction = async (taskId, action) => {
    setTaskBusyId(taskId);
    setTaskMessage('');
    try {
      await action();
      await loadDriverData();
      setTaskMessage('Task updated successfully.');
    } catch (err) {
      setTaskMessage(err?.response?.data?.detail || 'Unable to update task. Please retry.');
    } finally {
      setTaskBusyId(null);
    }
  };

  const setEvidenceDraft = (taskId, key, value) => setEvidenceDrafts(prev => ({
    ...prev, [taskId]: { ...(prev[taskId] || {}), [key]: value }
  }));

  const uploadEvidence = async (taskId) => {
    const draft = evidenceDrafts[taskId] || {};
    if (!draft.afterPhoto) { setTaskMessage('Choose the required after-collection photo first.'); return; }
    await runTaskAction(taskId, async () => {
      await submitDriverEvidence(taskId, draft);
      setEvidenceDrafts(prev => ({ ...prev, [taskId]: { ...prev[taskId], afterPhoto: null, beforePhoto: null } }));
    });
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

  // Compute task progress from the currently loaded driver assignments.
  const totalStops = tasks.length;
  const completedStops = tasks.filter(t => t.status === 'Completed').length;
  const pendingStops = tasks.filter(t => t.status === 'Pending').length;
  const progressPercent = totalStops > 0 ? Math.round((completedStops / totalStops) * 100) : 0;

  // Sidebar navigation items matching DRIVER.png
  const navItems = [
    { name: 'Dashboard', icon: LayoutDashboard },
    { name: 'My Tasks', icon: ClipboardList },
    { name: 'Route & Navigation', icon: Navigation, action: handleStartNavigation },
    { name: 'My Performance', icon: TrendingUp },
    { name: 'Fuel Log', icon: Fuel },
    { name: 'Messages', icon: MessageSquare },
    { name: 'Profile Settings', icon: User, action: () => setShowProfileModal(true) },
    { name: 'Settings', icon: Settings, action: () => setShowProfileModal(true) },
  ];

  return (
    <FieldOperationsShell role="driver" identity={driver} items={navItems} activeItem={activeTab} onNavigate={setActiveTab} onRefresh={loadDriverData} onProfile={() => setShowProfileModal(true)} onLogout={handleLogout}>
      
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
            <span>Live turn-by-turn navigation is not available in this portal yet.</span>
          </motion.div>
        )}
      </AnimatePresence>

      {/* RIGHT MAIN CONTENT AREA MATCHING STITCH                           */}
      {/* ----------------------------------------------------------------- */}
      <div className="p-6 md:p-8 flex-1 flex flex-col min-h-0 bg-[#F9FAFB]">
          
          {/* Top Header Bar */}
          <div className="flex flex-col sm:flex-row items-start sm:items-center justify-between gap-4 bg-white p-4 sm:p-5 rounded-3xl border border-slate-200/90 shadow-2xs">
            <div>
              <h1 className="text-xl sm:text-2xl font-black text-slate-900 tracking-tight">
                Driver Tasks
              </h1>
              <p className="text-xs font-semibold text-slate-500 mt-0.5">
                Review assigned tasks and update their status.
              </p>
            </div>

            {/* Header Right Driver Card */}
            <div
              onClick={() => setShowProfileModal(true)}
              className="flex items-center gap-3 bg-white px-3.5 py-2 rounded-2xl border border-slate-200 shadow-2xs cursor-pointer hover:border-emerald-300 transition-all"
            >
              <div className="w-8 h-8 rounded-full bg-[#02471f] text-white flex items-center justify-center font-bold text-xs">
                {(driver?.name || driver?.full_name || 'D').charAt(0).toUpperCase()}
              </div>
              <div>
                <div className="text-xs font-extrabold text-slate-900">
                  {driver?.name || driver?.full_name || 'Driver'}
                </div>
                <div className="text-[10px] font-bold text-emerald-700">
                  {driver?.employee_id || 'Employee ID unavailable'}
                </div>
              </div>
            </div>
          </div>

          {/* Sub-View Navigation if not on Dashboard */}
          {dataLoading ? (
            <div role="status" className="rounded-2xl border border-slate-200 bg-white p-10 text-center text-sm font-semibold text-slate-600">
              Loading driver data…
            </div>
          ) : dataError ? (
            <div role="alert" className="rounded-2xl border border-red-200 bg-white p-10 text-center">
              <p className="text-sm font-semibold text-red-700">{dataError}</p>
              <button type="button" onClick={loadDriverData} className="mt-4 rounded-lg bg-primary px-4 py-2 text-sm font-bold text-white">
                Retry
              </button>
            </div>
          ) : activeTab === 'My Tasks' ? (
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
                    Accept assigned work, record collection evidence, and request Municipal Admin verification.
                  </p>
                </div>
                <button 
                  onClick={() => setActiveTab('Dashboard')}
                  className="px-4 py-2 bg-slate-100 hover:bg-slate-200 rounded-xl text-xs font-bold text-slate-700 transition-all cursor-pointer"
                >
                  ← Back to Main Dashboard
                </button>
              </div>

              {taskMessage && <p role="status" className="max-w-3xl rounded-lg bg-slate-50 p-3 text-sm text-slate-700">{taskMessage}</p>}
              <div className="space-y-3 max-w-3xl">
                {tasks.map((task) => (
                  <div
                    key={task.id}
                    className="p-4 rounded-2xl bg-slate-50 border border-slate-200/70 space-y-3"
                  >
                    <div className="flex items-center justify-between gap-3">
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
                    <div className="flex flex-wrap gap-2">
                      {task.status === 'Pending' && <button disabled={taskBusyId === task.id} onClick={() => runTaskAction(task.id, () => acceptDriverTask(task.id))} className="rounded-lg bg-primary px-3 py-2 text-xs font-bold text-white">Accept</button>}
                      {task.status === 'Accepted' && <button disabled={taskBusyId === task.id} onClick={() => runTaskAction(task.id, () => startDriverTask(task.id))} className="rounded-lg bg-primary px-3 py-2 text-xs font-bold text-white">Start collection</button>}
                    </div>
                    {['In Progress', 'Requires Rework'].includes(task.status) && <div className="grid gap-2 sm:grid-cols-2">
                      <label className="text-xs font-semibold text-slate-600">After photo (required)<input type="file" accept="image/jpeg,image/png,image/webp" onChange={e => setEvidenceDraft(task.id, 'afterPhoto', e.target.files?.[0])} className="mt-1 block w-full text-xs" /></label>
                      <label className="text-xs font-semibold text-slate-600">Before photo (optional)<input type="file" accept="image/jpeg,image/png,image/webp" onChange={e => setEvidenceDraft(task.id, 'beforePhoto', e.target.files?.[0])} className="mt-1 block w-full text-xs" /></label>
                      <textarea maxLength={4000} placeholder="Collection notes" value={evidenceDrafts[task.id]?.notes || ''} onChange={e => setEvidenceDraft(task.id, 'notes', e.target.value)} className="rounded-lg border p-2 text-sm sm:col-span-2" />
                      <button disabled={taskBusyId === task.id} onClick={() => uploadEvidence(task.id)} className="rounded-lg border border-primary px-3 py-2 text-xs font-bold text-primary">Save evidence</button>
                    </div>}
                    {task.status === 'Evidence Submitted' && <button disabled={taskBusyId === task.id} onClick={() => runTaskAction(task.id, () => requestTaskVerification(task.id))} className="rounded-lg bg-primary px-3 py-2 text-xs font-bold text-white">Submit for verification</button>}
                    {task.status === 'Pending Verification' && <p className="text-xs font-semibold text-amber-800">Evidence is awaiting Municipal Admin review.</p>}
                    {task.status === 'Requires Rework' && <p className="text-xs font-semibold text-red-700">Review feedback: {task.rejection_reason || 'Please submit updated evidence.'}</p>}
                  </div>
                ))}
                {!tasks.length && <p className="py-6 text-center text-sm text-slate-500">No tasks are assigned to your account.</p>}
              </div>
            </motion.div>
          ) : activeTab === 'Route & Navigation' ? (
            <motion.div
              key="Route & Navigation"
              initial={{ opacity: 0, y: 15 }}
              animate={{ opacity: 1, y: 0 }}
              className="space-y-6"
            >
              <div className="bg-white rounded-2xl border border-slate-200 p-5">
                <h2 className="text-lg font-extrabold text-slate-900">Assigned task locations</h2>
                <p className="mt-1 text-sm font-medium text-slate-600">
                  The map displays coordinates recorded with assigned tasks. Live driver position, traffic, and ETA are not available.
                </p>
                <div className="mt-4 h-[480px]">
                  <InteractiveMap zoom={14} tasks={tasks} height="100%" />
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
                  <p className="text-xs text-slate-500 mt-1">Performance metrics are shown only when recorded by the backend.</p>
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
                      {performance?.collection_efficiency_pct ?? 'Unavailable'}
                    </span>
                  </div>
                  <div>
                    <p className="text-[10px] font-bold text-slate-400 uppercase tracking-wider">Collection Efficiency</p>
                    <h3 className="text-3xl font-black text-slate-900 mt-1">{performance?.collection_efficiency ?? 'Unavailable'}</h3>
                  </div>
                </div>

                {/* Completed tasks */}
                <div className="bg-white border border-slate-200 rounded-xl p-5 shadow-xs flex flex-col justify-between min-h-[120px]">
                  <div className="flex justify-between items-start mb-2">
                    <div className="w-10 h-10 rounded-lg bg-slate-100 flex items-center justify-center text-amber-500">
                      <CheckCircle2 className="w-5 h-5" />
                    </div>
                  </div>
                  <div>
                    <p className="text-[10px] font-bold text-slate-400 uppercase tracking-wider">Tasks Completed</p>
                    <h3 className="text-3xl font-black text-slate-900 mt-1">{completedStops}</h3>
                  </div>
                </div>

                {/* Fuel Economy */}
                <div className="bg-white border border-slate-200 rounded-xl p-5 shadow-xs flex flex-col justify-between min-h-[120px]">
                  <div className="flex justify-between items-start mb-2">
                    <div className="w-10 h-10 rounded-lg bg-slate-100 flex items-center justify-center text-[#376941]">
                      <Fuel className="w-5 h-5" />
                    </div>
                    <span className="inline-flex items-center gap-1 text-[10px] font-bold text-red-600 bg-red-50 px-2 py-0.5 rounded-full">
                      {performance?.fuel_economy_pct ?? 'Unavailable'}
                    </span>
                  </div>
                  <div>
                    <p className="text-[10px] font-bold text-slate-400 uppercase tracking-wider">Fuel Economy</p>
                    <h3 className="text-3xl font-black text-slate-900 mt-1">{performance?.fuel_economy ?? 'Unavailable'}</h3>
                  </div>
                </div>

                {/* Safety Score */}
                <div className="bg-primary border border-primary-container rounded-xl p-5 shadow-xs flex flex-col justify-between min-h-[120px] text-white">
                  <div className="flex justify-between items-start mb-2">
                    <div className="w-10 h-10 rounded-lg bg-white/20 flex items-center justify-center text-white">
                      <CheckCircle2 className="w-5 h-5" />
                    </div>
                    <span className="inline-flex items-center gap-1 text-[10px] font-bold bg-white/20 px-2 py-0.5 rounded-full">
                      {performance?.safety_score_pct ?? 'Unavailable'}
                    </span>
                  </div>
                  <div>
                    <p className="text-[10px] font-bold text-emerald-300 uppercase tracking-wider">Safety Score</p>
                    <h3 className="text-3xl font-black mt-1">{performance?.safety_score ?? 'Unavailable'}</h3>
                  </div>
                </div>
              </div>

              {/* Data Section */}
              <div className="grid grid-cols-1 lg:grid-cols-12 gap-6">
                {/* Weekly Trends Chart */}
                <div className="lg:col-span-8 bg-white border border-slate-200 rounded-xl p-5 shadow-xs flex flex-col">
                  <div className="flex justify-between items-center mb-6">
                    <h3 className="text-sm font-bold text-slate-900">Weekly Performance Trends</h3>
                  </div>
                  
                  {/* Chart */}
                  {(performance?.weekly_trends || []).length ? (
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
                    {performance.weekly_trends.map((bar, idx) => (
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
                  ) : (
                    <div className="flex min-h-[220px] items-center justify-center text-sm font-medium text-slate-500">
                      No performance records are available.
                    </div>
                  )}

                </div>

                {/* Achievements & Leaderboard */}
                <div className="lg:col-span-4 flex flex-col gap-6">
                  {/* Achievements */}
                  <div className="bg-white border border-slate-200 rounded-xl p-5 shadow-xs">
                    <h3 className="text-xs font-bold text-slate-900 mb-4 uppercase tracking-wider">Recent Achievements</h3>
                    <div className="flex gap-4">
                      {(performance?.achievements || []).map((ach, idx) => (
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
                      {!(performance?.achievements || []).length && (
                        <p className="w-full py-4 text-center text-xs font-medium text-slate-500">No achievement records are available.</p>
                      )}
                    </div>
                  </div>

                  {/* Leaderboard */}
                  <div className="bg-white border border-slate-200 rounded-xl p-5 shadow-xs flex-1">
                    <div className="flex justify-between items-center mb-4">
                      <h3 className="text-xs font-bold text-slate-900 uppercase tracking-wider">Leaderboard</h3>
                    </div>
                    <div className="space-y-3">
                      {(performance?.leaderboard || []).map((entry, idx) => (
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
                      {!(performance?.leaderboard || []).length && (
                        <p className="py-4 text-center text-xs font-medium text-slate-500">Leaderboard data is unavailable.</p>
                      )}
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
                    <h3 className="text-3xl font-black text-slate-900">
                      {fuelSummary?.current_fuel_level == null ? 'Unavailable' : `${fuelSummary.current_fuel_level}%`}
                    </h3>
                    <div className="w-full bg-slate-100 rounded-full h-2 mt-3">
                      <div className="bg-primary h-2 rounded-full" style={{ width: `${fuelSummary?.current_fuel_level ?? 0}%` }}></div>
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
                    <h3 className="text-3xl font-black text-slate-900">
                      {fuelSummary?.avg_consumption == null ? 'Unavailable' : `${fuelSummary.avg_consumption} km/L`}
                    </h3>
                  </div>
                </div>

                {/* Spent Month */}
                <div className="bg-white border border-slate-200 rounded-xl p-5 shadow-xs flex flex-col justify-between min-h-[120px]">
                  <div className="flex items-center justify-between mb-4">
                    <h3 className="text-[10px] font-bold text-slate-400 uppercase tracking-wider">Spent (Month)</h3>
                    <Zap className="w-4 h-4 text-amber-500" />
                  </div>
                  <div>
                    <h3 className="text-3xl font-black text-slate-900">₹{(fuelSummary?.total_spent ?? 0).toLocaleString()}</h3>
                    <p className="text-[10px] font-bold text-slate-400 mt-2">Based on {(fuelSummary?.logs || []).length} recorded entries</p>
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
                  {(messagesOverview?.conversations || []).map((conv, idx) => (
                    <div key={idx} className={`p-3 cursor-pointer ${conv.active ? 'bg-slate-50 border-l-4 border-[#005c2b]' : 'hover:bg-slate-50'}`}>
                      <div className="flex justify-between items-start mb-1 text-[10px] font-bold text-slate-400">
                        <span className="text-slate-900 font-extrabold flex items-center gap-1">{conv.name}</span>
                        <span>{conv.time}</span>
                      </div>
                      <p className="text-xs truncate text-slate-500 font-semibold">{conv.lastMessage}</p>
                    </div>
                  ))}
                  {!(messagesOverview?.conversations || []).length && (
                    <p className="p-5 text-center text-xs font-medium text-slate-500">No conversations are available.</p>
                  )}
                </div>
              </div>

              {/* Right Active Chat Pane */}
              <div className="flex-1 bg-white border border-slate-200 rounded-xl shadow-xs flex flex-col overflow-hidden">
                <div className="p-4 border-b border-slate-100 bg-slate-50/50 flex justify-between items-center">
                  <div>
                    <h2 className="text-xs font-extrabold text-slate-900 uppercase tracking-wider">
                      {messagesOverview?.conversations?.[0]?.name || 'No conversation selected'}
                    </h2>
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
                    {driver?.ward || 'Not assigned'}
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

              <div className="grid grid-cols-1 lg:grid-cols-12 gap-5">
                <div className="lg:col-span-7 rounded-2xl border border-slate-200 bg-white p-5">
                  <h3 className="mb-3 text-base font-extrabold text-slate-900">Assigned task locations</h3>
                  <InteractiveMap
                    zoom={13}
                    tasks={tasks}
                    height="320px"
                  />
                </div>
                <div className="lg:col-span-5 rounded-2xl border border-slate-200 bg-white p-5">
                  <div className="mb-3 flex items-center justify-between">
                    <h3 className="text-base font-extrabold text-slate-900">My Route Tasks</h3>
                    <span className="text-xs font-semibold text-slate-500">
                      Vehicle: {driver?.vehicle_assignment || 'Not assigned'}
                    </span>
                  </div>
                  <div className="max-h-[320px] space-y-2.5 overflow-y-auto">
                    {tasks.map((task) => (
                      <div key={task.id} className="flex items-center justify-between gap-3 rounded-xl border border-slate-200 bg-slate-50 p-3">
                        <div className="min-w-0">
                          <p className="truncate text-xs font-extrabold text-slate-800">{task.name}</p>
                          <p className="mt-1 text-[10px] font-semibold text-slate-500">Task #{task.id}</p>
                        </div>
                        <span className="shrink-0 text-[10px] font-bold text-slate-600">{task.status}</span>
                      </div>
                    ))}
                    {!tasks.length && <p className="py-6 text-center text-sm text-slate-500">No tasks are assigned to your account.</p>}
                  </div>
                  <p className="mt-3 text-xs font-medium text-slate-500">
                    Live driver position, traffic, and ETA are not available.
                  </p>
                </div>
              </div>
            </>
          )}

        </div>

      {/* Driver Profile Settings Modal */}
      <ProfileModal
        isOpen={showProfileModal}
        onClose={() => setShowProfileModal(false)}
        user={driver}
        onProfileUpdated={handleProfileUpdated}
      />

    </FieldOperationsShell>
  );
};

export default DriverDashboardPage;
