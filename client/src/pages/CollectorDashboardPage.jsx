import React, { useCallback, useEffect, useMemo, useState } from 'react';
import { useNavigate } from 'react-router-dom';
import { Activity, AlertCircle, CheckCircle2, ClipboardList, Layers3, MapPin, ShieldCheck, UserRound, X } from 'lucide-react';
import { fetchAdminBins, fetchAdminComplaints, fetchAdminMetrics, fetchComplaintOperations, refreshBinTelemetry } from '../services/adminService';
import { getCurrentUser, logoutUser, updateUserProfile } from '../services/authService';
import { fetchCollectorTasks } from '../services/collectorService';
import FieldOperationsShell from '../components/field-operations/FieldOperationsShell';

const sections = [
  { id: 'Overview', label: 'Overview', icon: Activity },
  { id: 'Ward complaints', label: 'Ward complaints', icon: AlertCircle },
  { id: 'Collection tasks', label: 'Collection tasks', icon: ClipboardList },
  { id: 'Bin operations', label: 'Bin operations', icon: Layers3 },
  { id: 'Work history', label: 'Work history', icon: CheckCircle2 },
  { id: 'Profile', label: 'Profile', icon: UserRound },
];

const statusStyle = (status) => {
  if (status === 'Completed') return 'bg-emerald-50 text-emerald-800 border-emerald-200';
  if (status === 'Pending Verification' || status === 'Evidence Submitted') return 'bg-blue-50 text-blue-800 border-blue-200';
  if (status === 'Requires Rework') return 'bg-red-50 text-red-800 border-red-200';
  if (status === 'In Progress' || status === 'Accepted') return 'bg-amber-50 text-amber-800 border-amber-200';
  return 'bg-slate-50 text-slate-700 border-slate-200';
};

function StatusBadge({ children }) {
  return <span className={`inline-flex rounded-full border px-2.5 py-1 text-xs font-semibold ${statusStyle(children)}`}>{children || 'Unknown'}</span>;
}

function CollectorDashboardPage() {
  const navigate = useNavigate();
  const [section, setSection] = useState('Overview');
  const [collector, setCollector] = useState(null);
  const [tasks, setTasks] = useState([]);
  const [complaints, setComplaints] = useState([]);
  const [bins, setBins] = useState([]);
  const [metrics, setMetrics] = useState(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState('');
  const [taskFilter, setTaskFilter] = useState('All');
  const [complaintFilter, setComplaintFilter] = useState('All');
  const [search, setSearch] = useState('');
  const [selectedComplaint, setSelectedComplaint] = useState(null);
  const [complaintDetail, setComplaintDetail] = useState(null);
  const [detailLoading, setDetailLoading] = useState(false);
  const [detailError, setDetailError] = useState('');
  const [binDrafts, setBinDrafts] = useState({});
  const [binBusy, setBinBusy] = useState(null);
  const [binMessage, setBinMessage] = useState('');
  const [profileForm, setProfileForm] = useState({ full_name: '', phone: '' });
  const [profileBusy, setProfileBusy] = useState(false);
  const [profileMessage, setProfileMessage] = useState('');
  const [profileError, setProfileError] = useState('');

  const loadPortal = useCallback(async () => {
    setLoading(true);
    setError('');
    try {
      const identity = await getCurrentUser();
      if (!identity) {
        navigate('/login', { replace: true });
        return;
      }
      if (identity.role?.toLowerCase() !== 'collector') {
        navigate(identity.role?.toLowerCase() === 'driver' ? '/field-operations' : '/admin', { replace: true });
        return;
      }
      setCollector(identity);
      setProfileForm({ full_name: identity.name || '', phone: identity.phone || '' });
      if (!identity.ward?.trim()) {
        setTasks([]);
        setComplaints([]);
        setBins([]);
        setMetrics(null);
        setError('Your account has no assigned ward. Ward operational records are unavailable until an authorized administrator assigns one.');
        return;
      }
      const [taskRows, complaintRows, binSummary, dashboardMetrics] = await Promise.all([
        fetchCollectorTasks(), fetchAdminComplaints(), fetchAdminBins(), fetchAdminMetrics()
      ]);
      setTasks(taskRows || []);
      setComplaints(complaintRows || []);
      setBins(binSummary?.bins || []);
      setMetrics(dashboardMetrics || null);
    } catch (loadError) {
      setError(loadError?.response?.data?.detail || 'Unable to load ward operations. Please retry.');
    } finally {
      setLoading(false);
    }
  }, [navigate]);

  useEffect(() => { loadPortal(); }, [loadPortal]);

  const taskCounts = useMemo(() => ({
    pending: tasks.filter(task => task.status === 'Pending').length,
    active: tasks.filter(task => ['Accepted', 'In Progress'].includes(task.status)).length,
    review: tasks.filter(task => task.status === 'Pending Verification').length,
    completed: tasks.filter(task => task.status === 'Completed').length,
  }), [tasks]);

  const filteredTasks = tasks.filter(task =>
    (taskFilter === 'All' || task.status === taskFilter)
    && `${task.complaint?.tracking_number || ''} ${task.complaint?.location || ''} ${task.driver_name || ''}`.toLowerCase().includes(search.toLowerCase())
  );
  const filteredComplaints = complaints.filter(complaint =>
    (complaintFilter === 'All' || complaint.status === complaintFilter)
    && `${complaint.id || ''} ${complaint.location || ''} ${complaint.type || ''}`.toLowerCase().includes(search.toLowerCase())
  );

  const openComplaint = async (complaint) => {
    setSelectedComplaint(complaint);
    setComplaintDetail(null);
    setDetailError('');
    setDetailLoading(true);
    try {
      setComplaintDetail(await fetchComplaintOperations(complaint.db_id));
    } catch (requestError) {
      setDetailError(requestError?.response?.data?.detail || 'Unable to load complaint details.');
    } finally {
      setDetailLoading(false);
    }
  };

  const submitBinLevel = async (event, bin) => {
    event.preventDefault();
    const level = Number(binDrafts[bin.id] ?? bin.fill_level_pct);
    if (!Number.isInteger(level) || level < 0 || level > 100) {
      setBinMessage('Enter a whole-number fill level from 0 to 100%.');
      return;
    }
    if (level === 0 && !window.confirm('Record this bin as empty? The backend will record a collection timestamp.')) return;
    setBinBusy(bin.id);
    setBinMessage('');
    try {
      await refreshBinTelemetry(bin.id, level);
      setBinMessage(`Ward bin ${bin.bin_code} observation saved.`);
      await loadPortal();
    } catch (requestError) {
      setBinMessage(requestError?.response?.data?.detail || 'Bin level could not be saved.');
    } finally {
      setBinBusy(null);
    }
  };

  const submitProfile = async (event) => {
    event.preventDefault();
    setProfileBusy(true);
    setProfileMessage('');
    setProfileError('');
    try {
      const updated = await updateUserProfile({ full_name: profileForm.full_name.trim(), phone: profileForm.phone.trim() });
      const freshIdentity = await getCurrentUser();
      setCollector(freshIdentity || { ...collector, ...updated });
      setProfileForm({ full_name: updated.name || profileForm.full_name.trim(), phone: updated.phone || profileForm.phone.trim() });
      setProfileMessage('Profile details updated. Your ward assignment remains administrator-managed.');
    } catch (requestError) {
      setProfileError(requestError?.response?.data?.detail || requestError.message || 'Profile could not be updated.');
    } finally {
      setProfileBusy(false);
    }
  };

  const logout = async () => {
    await logoutUser();
    navigate('/login', { replace: true });
  };

  const taskCard = (task) => (
    <article key={task.id} className="rounded-2xl border border-slate-200 bg-white p-4 shadow-sm sm:p-5">
      <div className="flex flex-wrap items-start justify-between gap-3">
        <div><p className="text-xs font-semibold uppercase tracking-wide text-slate-500">Task #{task.id} · {task.complaint?.tracking_number || 'Ward operation'}</p><h3 className="mt-1 font-bold text-slate-900">{task.complaint?.waste_type || 'Collection'} at {task.complaint?.location || task.location_name}</h3></div>
        <StatusBadge>{task.status}</StatusBadge>
      </div>
      <div className="mt-3 grid gap-2 text-sm text-slate-600 sm:grid-cols-2">
        <p><span className="font-semibold text-slate-800">Ward:</span> {task.complaint?.ward || collector?.ward}</p>
        <p><span className="font-semibold text-slate-800">Assigned Driver:</span> {task.driver_name || 'Unassigned'}</p>
        <p><span className="font-semibold text-slate-800">Evidence:</span> {task.evidence_status || 'Not submitted'}</p>
        <p><span className="font-semibold text-slate-800">Last update:</span> {task.updated_at ? new Date(task.updated_at).toLocaleString() : 'Unavailable'}</p>
      </div>
      {task.complaint?.description && <p className="mt-3 text-sm text-slate-600">{task.complaint.description}</p>}
      {task.collection_notes && <p className="mt-2 rounded-lg bg-slate-50 p-3 text-sm text-slate-700">Driver collection notes: {task.collection_notes}</p>}
      {task.rejection_reason && <p className="mt-2 rounded-lg border border-red-200 bg-red-50 p-3 text-sm text-red-800"><strong>Latest evidence rejection:</strong> {task.rejection_reason}</p>}
      {task.complaint?.latitude != null && task.complaint?.longitude != null && <p className="mt-3 inline-flex items-center gap-1 text-xs text-slate-500"><MapPin size={14}/>{task.complaint.latitude}, {task.complaint.longitude}</p>}
    </article>
  );

  const metricCard = (label, value, note) => <article key={label} className="rounded-2xl border border-slate-200 bg-white p-5 shadow-sm"><p className="text-xs font-bold uppercase tracking-wide text-slate-500">{label}</p><p className="mt-2 text-3xl font-extrabold text-[#003816]">{loading ? '…' : error ? '—' : value}</p>{note && <p className="mt-1 text-xs text-slate-500">{note}</p>}</article>;

  return (
    <FieldOperationsShell
      role="collector"
      identity={collector}
      items={sections.map(({ id, icon }) => ({ name: id, icon }))}
      activeItem={section}
      onNavigate={setSection}
      onRefresh={loadPortal}
      onProfile={() => setSection('Profile')}
      onLogout={logout}
    >
      <div className="p-4 pb-10 sm:p-6 md:p-8">

        {error && <div role="alert" className="mb-5 flex items-start gap-3 rounded-xl border border-amber-200 bg-amber-50 p-4 text-sm text-amber-900"><ShieldCheck size={18} className="mt-0.5 shrink-0"/>{error}</div>}
        {loading && <p role="status" className="mb-5 text-sm text-slate-500">Loading your ward operations…</p>}

        {section === 'Overview' && <div className="space-y-6">
          <div className="grid gap-4 sm:grid-cols-2 xl:grid-cols-5">
            {metricCard('Assigned ward', collector?.ward || '—', 'From your authenticated profile')}
            {metricCard('Pending tasks', taskCounts.pending)}
            {metricCard('Active collections', taskCounts.active, 'Driver tasks in accepted or in-progress state')}
            {metricCard('Evidence awaiting review', taskCounts.review, 'Municipal Admin review queue')}
            {metricCard('Completed work', taskCounts.completed, 'Approved task records in your ward')}
          </div>
          <div className="grid gap-5 xl:grid-cols-2">
            <section className="rounded-2xl border border-slate-200 bg-white p-5 shadow-sm"><div className="flex items-center justify-between"><h2 className="font-bold">Recent ward collection tasks</h2><button type="button" onClick={() => setSection('Collection tasks')} className="text-sm font-semibold text-emerald-800">View all</button></div><div className="mt-4 space-y-3">{tasks.slice(0, 4).map(taskCard)}{!loading && !error && tasks.length === 0 && <p className="rounded-xl bg-slate-50 p-5 text-sm text-slate-600">No task records are available for this ward.</p>}</div></section>
            <section className="rounded-2xl border border-slate-200 bg-white p-5 shadow-sm"><div className="flex items-center justify-between"><h2 className="font-bold">Ward complaint queue</h2><button type="button" onClick={() => setSection('Ward complaints')} className="text-sm font-semibold text-emerald-800">View all</button></div><div className="mt-4 space-y-3">{complaints.slice(0, 5).map(complaint => <button type="button" key={complaint.db_id} onClick={() => openComplaint(complaint)} className="flex w-full items-start justify-between gap-3 rounded-xl border border-slate-100 p-3 text-left hover:bg-slate-50"><span><span className="block text-xs font-semibold text-slate-500">{complaint.id} · {complaint.ward}</span><span className="mt-1 block text-sm font-bold">{complaint.type} · {complaint.location}</span></span><StatusBadge>{complaint.status}</StatusBadge></button>)}{!loading && !error && complaints.length === 0 && <p className="rounded-xl bg-slate-50 p-5 text-sm text-slate-600">No complaint records are available for your ward.</p>}</div><p className="mt-4 text-xs text-slate-500">Ward metrics: {metrics ? `${metrics.total_complaints} complaints · ${metrics.active_trucks} active vehicles` : 'unavailable'}</p></section>
          </div>
        </div>}

        {section === 'Ward complaints' && <section className="space-y-4"><div className="flex flex-wrap gap-3 rounded-2xl border border-slate-200 bg-white p-4"><label className="sr-only" htmlFor="collector-complaint-search">Search ward complaints</label><input id="collector-complaint-search" value={search} onChange={event => setSearch(event.target.value)} placeholder="Search tracking ID, type or location" className="min-w-52 flex-1 rounded-lg border border-slate-300 px-3 py-2 text-sm"/><label className="sr-only" htmlFor="collector-complaint-status">Filter complaint status</label><select id="collector-complaint-status" value={complaintFilter} onChange={event => setComplaintFilter(event.target.value)} className="rounded-lg border border-slate-300 px-3 py-2 text-sm"><option>All</option>{['Pending', 'In Progress', 'Pending Verification', 'Completed'].map(status => <option key={status}>{status}</option>)}</select></div><div className="grid gap-3">{filteredComplaints.map(complaint => <article key={complaint.db_id} className="flex flex-wrap items-center justify-between gap-3 rounded-2xl border border-slate-200 bg-white p-4 shadow-sm"><div><p className="text-xs font-semibold text-slate-500">{complaint.id} · {complaint.ward}</p><h2 className="mt-1 font-bold">{complaint.type} · {complaint.location}</h2><p className="mt-1 text-xs text-slate-500">Reported {complaint.time ? new Date(complaint.time).toLocaleString() : 'date unavailable'}</p></div><div className="flex items-center gap-2"><StatusBadge>{complaint.status}</StatusBadge><button type="button" onClick={() => openComplaint(complaint)} className="rounded-lg border border-slate-200 px-3 py-2 text-sm font-semibold hover:bg-slate-50">Details</button></div></article>)}{!loading && !error && filteredComplaints.length === 0 && <p className="rounded-xl bg-white p-8 text-center text-sm text-slate-600">No complaints match this filter.</p>}</div></section>}

        {section === 'Collection tasks' && <div className="space-y-4"><p className="rounded-xl border border-blue-200 bg-blue-50 p-4 text-sm text-blue-900">This is a ward oversight view. Assigned Drivers accept and start their tasks and submit collection evidence. Municipal Admins review evidence; Collectors cannot advance or approve Driver tasks.</p><div className="flex flex-wrap gap-3 rounded-2xl border border-slate-200 bg-white p-4"><label className="sr-only" htmlFor="collector-task-search">Search collection tasks</label><input id="collector-task-search" value={search} onChange={event => setSearch(event.target.value)} placeholder="Search tracking ID, location or Driver" className="min-w-52 flex-1 rounded-lg border border-slate-300 px-3 py-2 text-sm"/><label className="sr-only" htmlFor="collector-task-status">Filter task status</label><select id="collector-task-status" value={taskFilter} onChange={event => setTaskFilter(event.target.value)} className="rounded-lg border border-slate-300 px-3 py-2 text-sm"><option>All</option>{['Pending', 'Accepted', 'In Progress', 'Evidence Submitted', 'Pending Verification', 'Requires Rework', 'Completed', 'Cancelled'].map(status => <option key={status}>{status}</option>)}</select></div><div className="grid gap-3">{filteredTasks.map(taskCard)}{!loading && !error && filteredTasks.length === 0 && <p className="rounded-xl bg-white p-8 text-center text-sm text-slate-600">No ward tasks match this filter.</p>}</div></div>}

        {section === 'Bin operations' && <section className="space-y-4"><p className="rounded-xl border border-blue-200 bg-blue-50 p-4 text-sm text-blue-900">Record an observed fill level for an active bin in your assigned ward. A zero level records a collection timestamp.</p>{binMessage && <p role="status" className="rounded-lg bg-slate-100 p-3 text-sm text-slate-700">{binMessage}</p>}<div className="grid gap-4 md:grid-cols-2 xl:grid-cols-3">{bins.filter(bin => bin.is_active).map(bin => <article key={bin.id} className="rounded-2xl border border-slate-200 bg-white p-5 shadow-sm"><div className="flex items-start justify-between gap-2"><div><p className="text-xs font-semibold uppercase text-slate-500">{bin.bin_code} · {bin.ward}</p><h2 className="mt-1 font-bold">{bin.location_name}</h2><p className="mt-1 text-sm text-slate-600">Current recorded level: {bin.fill_level_pct}%</p></div><span className="rounded-full bg-emerald-50 px-2.5 py-1 text-xs font-bold text-emerald-800">Active</span></div><form onSubmit={event => submitBinLevel(event, bin)} className="mt-4 flex items-end gap-2"><label className="flex-1 text-xs font-semibold text-slate-600">Observed fill level (%)<input type="number" min="0" max="100" step="1" required value={binDrafts[bin.id] ?? bin.fill_level_pct} onChange={event => setBinDrafts(state => ({ ...state, [bin.id]: event.target.value }))} className="mt-1 w-full rounded-lg border border-slate-300 px-3 py-2 text-sm"/></label><button type="submit" disabled={binBusy === bin.id} className="rounded-lg bg-[#005c2b] px-3 py-2 text-sm font-bold text-white disabled:opacity-50">{binBusy === bin.id ? 'Saving…' : 'Save level'}</button></form></article>)}{!loading && !error && bins.filter(bin => bin.is_active).length === 0 && <p className="rounded-xl bg-white p-8 text-sm text-slate-600">No active ward bins are available.</p>}</div></section>}

        {section === 'Work history' && <section className="space-y-4"><div className="flex flex-wrap gap-2"><label className="sr-only" htmlFor="collector-history-filter">Filter work history</label><select id="collector-history-filter" value={taskFilter} onChange={event => setTaskFilter(event.target.value)} className="rounded-lg border border-slate-300 bg-white px-3 py-2 text-sm"><option>All</option>{['Completed', 'Pending Verification', 'Requires Rework', 'Evidence Submitted', 'In Progress', 'Pending'].map(status => <option key={status}>{status}</option>)}</select><p className="self-center text-sm text-slate-600">History is shown from Driver task records in {collector?.ward || 'your ward'}.</p></div><div className="grid gap-3">{filteredTasks.map(taskCard)}{!loading && !error && filteredTasks.length === 0 && <p className="rounded-xl bg-white p-8 text-sm text-slate-600">No work history matches this filter.</p>}</div></section>}

        {section === 'Profile' && <section className="grid gap-5 lg:grid-cols-[1fr_1.2fr]"><article className="rounded-2xl border border-slate-200 bg-white p-5 shadow-sm"><h2 className="font-bold">Collector account</h2><dl className="mt-4 space-y-3 text-sm"><div><dt className="text-xs text-slate-500">Name</dt><dd className="font-semibold">{collector?.name || '—'}</dd></div><div><dt className="text-xs text-slate-500">Employee ID</dt><dd className="font-semibold">{collector?.employee_id || '—'}</dd></div><div><dt className="text-xs text-slate-500">Email</dt><dd className="font-semibold">{collector?.email || '—'}</dd></div><div><dt className="text-xs text-slate-500">Assigned ward</dt><dd className="font-semibold">{collector?.ward || 'Unassigned'}</dd></div><div><dt className="text-xs text-slate-500">Account status</dt><dd><StatusBadge>{collector?.account_status || (collector ? 'Active' : 'Unavailable')}</StatusBadge></dd></div></dl><p className="mt-4 text-xs text-slate-500">Ward assignments and account governance are administrator-managed.</p></article><form onSubmit={submitProfile} className="rounded-2xl border border-slate-200 bg-white p-5 shadow-sm"><h2 className="font-bold">Update contact details</h2><p className="mt-1 text-xs text-slate-500">Name and phone can be updated. Ward is read-only.</p>{profileError && <p role="alert" className="mt-3 rounded-lg bg-red-50 p-3 text-sm text-red-700">{profileError}</p>}{profileMessage && <p role="status" className="mt-3 rounded-lg bg-emerald-50 p-3 text-sm text-emerald-800">{profileMessage}</p>}<label className="mt-4 block text-sm font-semibold">Full name<input required minLength={2} maxLength={100} value={profileForm.full_name} onChange={event => setProfileForm(form => ({ ...form, full_name: event.target.value }))} className="mt-1 w-full rounded-lg border border-slate-300 px-3 py-2"/></label><label className="mt-3 block text-sm font-semibold">Phone<input type="tel" required value={profileForm.phone} onChange={event => setProfileForm(form => ({ ...form, phone: event.target.value }))} className="mt-1 w-full rounded-lg border border-slate-300 px-3 py-2"/></label><button type="submit" disabled={profileBusy} className="mt-4 rounded-lg bg-[#005c2b] px-4 py-2 text-sm font-bold text-white disabled:opacity-50">{profileBusy ? 'Saving…' : 'Save profile'}</button></form></section>}
      </div>
      {selectedComplaint && <div className="fixed inset-0 z-50 flex items-center justify-center bg-black/50 p-4" onMouseDown={event => { if (event.target === event.currentTarget) setSelectedComplaint(null); }}><section role="dialog" aria-modal="true" aria-labelledby="collector-complaint-title" className="max-h-[90vh] w-full max-w-2xl overflow-y-auto rounded-2xl bg-white p-5 shadow-2xl"><div className="flex justify-between gap-3"><div><h2 id="collector-complaint-title" className="text-lg font-bold">Complaint {selectedComplaint.id}</h2><p className="text-sm text-slate-600">{selectedComplaint.ward} · {selectedComplaint.location}</p></div><button type="button" aria-label="Close complaint detail" onClick={() => setSelectedComplaint(null)} className="rounded-lg p-2 hover:bg-slate-100"><X size={18}/></button></div>{detailLoading ? <p role="status" className="py-8 text-sm text-slate-500">Loading complaint details…</p> : detailError ? <p role="alert" className="mt-4 rounded-lg bg-red-50 p-3 text-sm text-red-700">{detailError}</p> : complaintDetail && <div className="mt-5 space-y-4"><div className="rounded-xl bg-slate-50 p-4 text-sm"><p><strong>Type:</strong> {complaintDetail.complaint.type}</p><p className="mt-1"><strong>Status:</strong> {complaintDetail.complaint.status}</p><p className="mt-1"><strong>Assignment:</strong> {complaintDetail.complaint.assignedTo || 'Unassigned'}</p><p className="mt-3 whitespace-pre-wrap">{complaintDetail.complaint.description || 'No description supplied.'}</p></div>{(() => { const task = tasks.find(row => row.complaint?.id === selectedComplaint.db_id); return task ? <div className="rounded-xl border border-slate-200 p-4"><p className="font-bold">Task #{task.id} · {task.status}</p><p className="mt-1 text-sm text-slate-600">Evidence: {task.evidence_status || 'Not submitted'}</p>{task.collection_notes && <p className="mt-2 text-sm">Driver notes: {task.collection_notes}</p>}{task.rejection_reason && <p className="mt-2 rounded-lg bg-red-50 p-3 text-sm text-red-800">Rework reason: {task.rejection_reason}</p>}</div> : <p className="rounded-xl bg-slate-50 p-4 text-sm text-slate-600">No collection task is assigned.</p>; })()}</div>}</section></div>}
    </FieldOperationsShell>
  );
}

export default CollectorDashboardPage;
