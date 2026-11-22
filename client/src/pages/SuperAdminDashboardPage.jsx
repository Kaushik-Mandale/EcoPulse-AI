import React, { useCallback, useEffect, useMemo, useState } from 'react';
import { useNavigate } from 'react-router-dom';
import { Activity, AlertTriangle, BarChart3, Building2, ClipboardList, Download, LogOut, RefreshCw, Search, Shield, ShieldCheck, UserRound, Users, X } from 'lucide-react';
import {
  downloadAdminExportCSV, fetchAdminAnalytics, fetchAdminComplaints, fetchAdminDrivers,
  fetchAdminMetrics, fetchAdministrators, fetchComplaintOperations,
  fetchGovernanceCitizenComplaints, fetchGovernanceCitizens, fetchGovernanceTasks,
  fetchSecurityAudit, issueStaffTemporaryPassword, updateAccountStatus,
  fetchAccountDetails, fetchAccountHistory,
  fetchWardMunicipalities, fetchWards, createWard, updateWard, createWardMunicipality,
} from '../services/adminService';
import { getCurrentUser, logoutUser } from '../services/authService';
import StaffProvisioningPanel, { StaffCredentialNotice } from '../components/StaffProvisioningPanel';

const tabs = [
  'Overview', 'Municipal Admin Management', 'Field Staff Management', 'Citizen Management',
  'Ward Management', 'Complaint Monitoring', 'Task Monitoring', 'Analytics & Reports',
  'Audit Logs', 'Security & Account Settings',
];
const taskStatuses = ['Pending', 'Accepted', 'In Progress', 'Evidence Submitted', 'Pending Verification', 'Requires Rework', 'Completed', 'Cancelled'];
const badgeClass = (value) => {
  const key = String(value || '').toLowerCase();
  if (['active', 'used', 'verified', 'enrolled', 'completed', 'approved', 'success', 'true'].includes(key)) return 'border-emerald-200 bg-emerald-50 text-emerald-800';
  if (['suspended', 'retired', 'deactivated', 'revoked', 'failed', 'rejected', 'cancelled'].includes(key)) return 'border-red-200 bg-red-50 text-red-800';
  if (['pending', 'expired', 'required', 'not_invited', 'in progress', 'requires rework'].includes(key)) return 'border-amber-200 bg-amber-50 text-amber-800';
  return 'border-slate-200 bg-slate-50 text-slate-700';
};
const dateValue = (value) => value ? new Date(value).toLocaleString() : 'Unavailable';
const label = (value) => String(value === 'deactivated' ? 'retired' : value || 'Unavailable').replaceAll('_', ' ');
const norm = (value) => String(value || '').trim().toLocaleLowerCase();

function Badge({ value }) {
  return <span className={`inline-flex rounded-full border px-2.5 py-1 text-xs font-semibold capitalize ${badgeClass(value)}`}>{label(value)}</span>;
}

function Empty({ children }) {
  return <p className="rounded-xl bg-white p-8 text-center text-sm text-slate-500">{children}</p>;
}

export default function SuperAdminDashboardPage() {
  const navigate = useNavigate();
  const [tab, setTab] = useState('Overview');
  const [identity, setIdentity] = useState(null);
  const [admins, setAdmins] = useState([]);
  const [staff, setStaff] = useState([]);
  const [citizens, setCitizens] = useState([]);
  const [complaints, setComplaints] = useState([]);
  const [tasksData, setTasksData] = useState({ counts: {}, tasks: [], total: 0 });
  const [metrics, setMetrics] = useState(null);
  const [analytics, setAnalytics] = useState(null);
  const [events, setEvents] = useState([]);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState('');
  const [query, setQuery] = useState('');
  const [eventAction, setEventAction] = useState('all');
  const [staffRoleFilter, setStaffRoleFilter] = useState('all');
  const [staffWardFilter, setStaffWardFilter] = useState('all');
  const [staffStatusFilter, setStaffStatusFilter] = useState('all');
  const [adminStatusFilter, setAdminStatusFilter] = useState('all');
  const [complaintStatus, setComplaintStatus] = useState('all');
  const [complaintWard, setComplaintWard] = useState('all');
  const [taskStatus, setTaskStatus] = useState('all');
  const [busyId, setBusyId] = useState(null);
  const [message, setMessage] = useState('');
  const [staffCredential, setStaffCredential] = useState(null);
  const [selectedComplaint, setSelectedComplaint] = useState(null);
  const [selectedCitizen, setSelectedCitizen] = useState(null);
  const [selectedAccount, setSelectedAccount] = useState(null);
  const [accountHistory, setAccountHistory] = useState([]);
  const [citizenStatusFilter, setCitizenStatusFilter] = useState('all');
  const [citizenComplaints, setCitizenComplaints] = useState([]);
  const [citizenHistoryLoading, setCitizenHistoryLoading] = useState(false);
  const [municipalities, setMunicipalities] = useState([]);
  const [registryWards, setRegistryWards] = useState([]);
  const [wardMunicipalityId, setWardMunicipalityId] = useState('');
  const [wardSearch, setWardSearch] = useState('');
  const [wardStatusFilter, setWardStatusFilter] = useState('all');
  const [wardEdit, setWardEdit] = useState(null);
  const [wardForm, setWardForm] = useState({ ward_number: '', display_name: '', locality_description: '' });
  const [newMunicipality, setNewMunicipality] = useState({ code: '', name: '' });

  const loadData = useCallback(async () => {
    setLoading(true);
    setError('');
    try {
      const user = await getCurrentUser();
      if (!user) { navigate('/login', { replace: true }); return; }
      if (user.role?.toLowerCase() !== 'admin' || !user.is_super_admin) {
        navigate(user.role?.toLowerCase() === 'admin' ? '/admin' : '/login', { replace: true });
        return;
      }
      setIdentity(user);
      const [adminRows, staffRows, metricData, auditRows, citizenRows, complaintRows, taskRows, analyticsData, municipalityRows, wardRows] = await Promise.all([
        fetchAdministrators(), fetchAdminDrivers(), fetchAdminMetrics(), fetchSecurityAudit(250),
        fetchGovernanceCitizens(), fetchAdminComplaints(), fetchGovernanceTasks(), fetchAdminAnalytics(),
        fetchWardMunicipalities(), fetchWards(),
      ]);
      setAdmins(adminRows || []);
      setStaff(staffRows || []);
      setMetrics(metricData || null);
      setEvents(auditRows || []);
      setCitizens(citizenRows || []);
      setComplaints(complaintRows || []);
      setTasksData(taskRows || { counts: {}, tasks: [], total: 0 });
      setAnalytics(analyticsData || null);
      setMunicipalities(municipalityRows || []);
      setRegistryWards(wardRows || []);
      setWardMunicipalityId(previous => previous || String(municipalityRows?.[0]?.id || ''));
    } catch (loadError) {
      setError(loadError?.response?.data?.detail || 'Governance data could not be loaded. Refresh to retry.');
    } finally { setLoading(false); }
  }, [navigate]);

  useEffect(() => { loadData(); }, [loadData]);

  const adminStats = useMemo(() => ({
    total: admins.filter(account => !account.is_super_admin).length,
    active: admins.filter(account => account.account_status === 'active' && !account.is_super_admin).length,
    suspended: admins.filter(account => account.account_status === 'suspended' && !account.is_super_admin).length,
    pendingInvites: admins.filter(account => account.invitation_status === 'pending' && !account.is_super_admin).length,
    expiredInvites: admins.filter(account => account.invitation_status === 'expired' && !account.is_super_admin).length,
  }), [admins]);
  const wardOptions = useMemo(() => [...new Set([
    ...admins.map(account => account.ward), ...staff.map(account => account.ward),
    ...citizens.map(account => account.ward), ...complaints.map(complaint => complaint.ward),
  ].map(value => String(value || '').trim()).filter(Boolean))].sort((a, b) => a.localeCompare(b)), [admins, staff, citizens, complaints]);
  const statusMatches = (account, filter) => filter === 'all' || (filter === 'retired' ? ['retired', 'deactivated'].includes(account.account_status) : account.account_status === filter);
  const filteredAdmins = admins.filter(account => !account.is_super_admin && `${account.full_name} ${account.employee_id} ${account.login_id || ''} ${account.email || ''} ${account.phone || ''} ${account.ward || ''} ${account.account_status} ${account.invitation_status}`.toLowerCase().includes(query.toLowerCase()) && statusMatches(account, adminStatusFilter));
  const filteredStaff = staff.filter(account =>
    `${account.full_name} ${account.employee_id || ''} ${account.login_id || ''} ${account.phone || ''} ${account.role} ${account.ward || ''} ${account.account_status}`.toLowerCase().includes(query.toLowerCase())
    && (staffRoleFilter === 'all' || account.role === staffRoleFilter)
    && (staffWardFilter === 'all' || String(account.ward_id || '') === staffWardFilter)
    && statusMatches(account, staffStatusFilter));
  const filteredCitizens = citizens.filter(citizen => `${citizen.id} ${citizen.full_name} ${citizen.phone || ''} ${citizen.email || ''} ${citizen.login_id || ''} ${citizen.ward || ''}`.toLowerCase().includes(query.toLowerCase()) && statusMatches(citizen, citizenStatusFilter));
  const filteredComplaints = complaints.filter(complaint =>
    `${complaint.id} ${complaint.location} ${complaint.type} ${complaint.ward} ${complaint.assignedTo || ''}`.toLowerCase().includes(query.toLowerCase())
    && (complaintStatus === 'all' || complaint.status === complaintStatus)
    && (complaintWard === 'all' || complaint.ward === complaintWard));
  const filteredTasks = (tasksData.tasks || []).filter(task =>
    `${task.id} ${task.status} ${task.driver_name || ''} ${task.location_name || ''} ${task.complaint?.ward || ''} ${task.complaint?.tracking_number || ''}`.toLowerCase().includes(query.toLowerCase())
    && (taskStatus === 'all' || task.status === taskStatus));
  const filteredEvents = events.filter(event => `${event.actor_employee_id || ''} ${event.target_employee_id || ''} ${event.action} ${event.details || ''}`.toLowerCase().includes(query.toLowerCase()) && (eventAction === 'all' || event.action === eventAction));
  const filteredRegistryWards = registryWards.filter(ward =>
    (wardMunicipalityId === '' || String(ward.municipality_id) === wardMunicipalityId)
    && (wardStatusFilter === 'all' || (wardStatusFilter === 'active') === ward.is_active)
    && `${ward.ward_number} ${ward.display_name} ${ward.locality_description || ''} ${ward.municipality_name || ''}`.toLowerCase().includes(wardSearch.toLowerCase())
  );
  const actionOptions = [...new Set(events.map(event => event.action).filter(Boolean))].sort();
  const activeCount = [...admins.filter(a => !a.is_super_admin), ...staff, ...citizens].filter(account => account.account_status === 'active').length;
  const suspendedCount = [...admins.filter(a => !a.is_super_admin), ...staff, ...citizens].filter(account => account.account_status === 'suspended').length;
  const wardGroups = useMemo(() => {
    const groups = new Map();
    const add = (name, kind) => {
      const raw = String(name || '').trim();
      if (!raw) return;
      const key = norm(raw);
      if (!groups.has(key)) groups.set(key, { key, names: new Set(), admins: 0, staff: 0, citizens: 0, complaints: 0 });
      const group = groups.get(key);
      group.names.add(raw);
      if (kind === 'admin') group.admins += 1;
      if (kind === 'staff') group.staff += 1;
      if (kind === 'citizen') group.citizens += 1;
      if (kind === 'complaint') group.complaints += 1;
    };
    admins.filter(account => !account.is_super_admin).forEach(account => add(account.ward, 'admin'));
    staff.forEach(account => add(account.ward, 'staff'));
    citizens.forEach(account => add(account.ward, 'citizen'));
    complaints.forEach(complaint => add(complaint.ward, 'complaint'));
    return [...groups.values()].map(group => ({ ...group, names: [...group.names].sort() })).sort((a, b) => a.key.localeCompare(b.key));
  }, [admins, staff, citizens, complaints]);
  const invitationPending = admins.filter(account => !account.is_super_admin && account.invitation_status === 'pending').length + staff.filter(account => account.invitation_status === 'pending').length;
  const invitationExpired = admins.filter(account => !account.is_super_admin && account.invitation_status === 'expired').length + staff.filter(account => account.invitation_status === 'expired').length;

  const setAccountStatus = async (account, status) => {
    const verb = status === 'suspended' ? 'suspend' : status === 'retired' ? 'permanently retire' : 'reactivate';
    const reason = ['suspended', 'retired'].includes(status) ? window.prompt(`Reason to ${verb} ${account.full_name} (required):`) : '';
    if (['suspended', 'retired'].includes(status) && (!reason || reason.trim().length < 3)) return;
    const irreversible = status === 'retired' ? ' This is permanent and cannot be undone.' : '';
    if (!window.confirm(`${verb[0].toUpperCase()}${verb.slice(1)} ${account.full_name}? Existing sessions will be revoked.${irreversible}`)) return;
    setBusyId(account.id); setError(''); setMessage('');
    try {
      await updateAccountStatus(account.id, status, reason?.trim());
      setMessage(status === 'retired' ? `${account.full_name} was permanently retired.` : `${account.full_name} is now ${status}. Existing sessions were revoked.`);
      await loadData();
    } catch (actionError) { setError(actionError?.response?.data?.detail || 'Account status could not be changed.'); }
    finally { setBusyId(null); }
  };

  const viewAccountHistory = async (account) => {
    setError('');
    try {
      const [details, history] = await Promise.all([fetchAccountDetails(account.id), fetchAccountHistory(account.id)]);
      setSelectedAccount(details);
      setAccountHistory(history || []);
    } catch (requestError) { setError(requestError?.response?.data?.detail || 'Account history could not be loaded.'); }
  };

  const saveWard = async (event) => {
    event.preventDefault(); setError(''); setMessage('');
    try {
      const payload = { ...wardForm, ward_number: wardForm.ward_number.trim(), display_name: wardForm.display_name.trim(), locality_description: wardForm.locality_description.trim() || null };
      if (wardEdit) await updateWard(wardEdit.id, { ...payload, is_active: wardEdit.is_active });
      else await createWard({ ...payload, municipality_id: Number(wardMunicipalityId) });
      setWardEdit(null); setWardForm({ ward_number: '', display_name: '', locality_description: '' });
      setMessage(wardEdit ? 'Ward details updated.' : 'Ward created.'); await loadData();
    } catch (saveError) { setError(saveError?.response?.data?.detail || 'Ward could not be saved.'); }
  };

  const toggleWard = async (ward) => {
    const next = !ward.is_active;
    if (!window.confirm(`${next ? 'Activate' : 'Deactivate'} ${ward.display_name}? ${next ? '' : 'Existing staff and historical records will remain assigned; new assignments will be blocked.'}`)) return;
    try {
      await updateWard(ward.id, { ward_number: ward.ward_number, display_name: ward.display_name, locality_description: ward.locality_description, is_active: next });
      setMessage(`${ward.display_name} ${next ? 'activated' : 'deactivated'}.`); await loadData();
    } catch (saveError) { setError(saveError?.response?.data?.detail || 'Ward status could not be changed.'); }
  };

  const saveMunicipality = async (event) => {
    event.preventDefault();
    try {
      const created = await createWardMunicipality({ code: newMunicipality.code.trim(), name: newMunicipality.name.trim() });
      setNewMunicipality({ code: '', name: '' }); setWardMunicipalityId(String(created.id));
      setMessage(`${created.name} added to the municipality registry.`); await loadData();
    } catch (saveError) { setError(saveError?.response?.data?.detail || 'Municipality could not be created.'); }
  };

  const resetStaffPassword = async (account) => {
    if (!window.confirm(`Issue a new one-time password for ${account.full_name}? Existing sessions will be revoked.`)) return;
    setBusyId(account.id); setError(''); setMessage('');
    try {
      setStaffCredential(await issueStaffTemporaryPassword(account.id));
      setMessage('One-time credentials are displayed until dismissed. Communicate them manually and securely.');
      await loadData();
    } catch (actionError) { setError(actionError?.response?.data?.detail || 'Temporary password could not be issued.'); }
    finally { setBusyId(null); }
  };

  const viewComplaint = async (complaint) => {
    setError('');
    try { setSelectedComplaint(await fetchComplaintOperations(complaint.db_id)); }
    catch (loadError) { setError(loadError?.response?.data?.detail || 'Complaint details could not be loaded.'); }
  };
  const viewCitizenHistory = async (citizen) => {
    setSelectedCitizen(citizen);
    setCitizenComplaints([]);
    setCitizenHistoryLoading(true);
    setError('');
    try { setCitizenComplaints(await fetchGovernanceCitizenComplaints(citizen.id) || []); }
    catch (loadError) { setError(loadError?.response?.data?.detail || 'Citizen complaint history could not be loaded.'); }
    finally { setCitizenHistoryLoading(false); }
  };
  const exportCsv = async () => {
    setError(''); setMessage('');
    try { await downloadAdminExportCSV(); setMessage('Complaint report downloaded.'); }
    catch (downloadError) { setError(downloadError?.response?.data?.detail || 'Report could not be downloaded.'); }
  };
  const logout = async () => { await logoutUser(); navigate('/login', { replace: true }); };
  const metricCard = (title, value, note, Icon = Activity) => <article key={title} className="rounded-2xl border border-slate-200 bg-white p-5 shadow-sm"><div className="flex items-start justify-between gap-2"><div><p className="text-xs font-bold uppercase tracking-wide text-slate-500">{title}</p><p className="mt-2 text-3xl font-extrabold text-[#003816]">{loading ? '…' : value ?? 'Unavailable'}</p><p className="mt-1 text-xs text-slate-500">{note}</p></div><span className="rounded-xl bg-emerald-50 p-3 text-emerald-800"><Icon size={19}/></span></div></article>;
  const tableSearch = <label className="relative block min-w-56 flex-1"><Search className="absolute left-3 top-2.5 text-slate-400" size={16}/><input aria-label="Search governance records" value={query} onChange={event => setQuery(event.target.value)} placeholder="Search records" className="w-full rounded-xl border border-slate-300 py-2 pl-9 pr-3 text-sm"/></label>;
  const tabButton = (name) => <button type="button" key={name} aria-current={tab === name ? 'page' : undefined} onClick={() => { setTab(name); setQuery(''); }} className={`flex shrink-0 items-center gap-2 rounded-xl px-3 py-2.5 text-left text-sm font-semibold md:w-full ${tab === name ? 'bg-white/15 text-white' : 'text-emerald-100 hover:bg-white/10'}`}><ShieldCheck size={16}/>{name}</button>;
  const statusControl = (account) => account.account_status === 'retired' || account.account_status === 'deactivated'
    ? <div className="flex flex-wrap gap-2"><span className="rounded-lg bg-red-50 px-2.5 py-1.5 text-xs font-semibold text-red-800">Retired permanently</span><button type="button" onClick={() => viewAccountHistory(account)} className="rounded-lg border border-slate-200 px-2.5 py-1.5 text-xs font-semibold">Details / history</button></div>
    : <div className="flex flex-wrap gap-2">
      {account.account_status === 'active' && <button type="button" disabled={busyId === account.id} onClick={() => setAccountStatus(account, 'suspended')} className="rounded-lg border border-red-200 px-2.5 py-1.5 text-xs font-semibold text-red-700 disabled:opacity-50">Suspend</button>}
      {account.account_status === 'suspended' && <button type="button" disabled={busyId === account.id} onClick={() => setAccountStatus(account, 'active')} className="rounded-lg border border-emerald-200 px-2.5 py-1.5 text-xs font-semibold text-emerald-800 disabled:opacity-50">Reactivate</button>}
      <button type="button" disabled={busyId === account.id} onClick={() => setAccountStatus(account, 'retired')} className="rounded-lg border border-red-300 px-2.5 py-1.5 text-xs font-semibold text-red-900 disabled:opacity-50">Retire</button>
      <button type="button" onClick={() => viewAccountHistory(account)} className="rounded-lg border border-slate-200 px-2.5 py-1.5 text-xs font-semibold">Details / history</button>
    </div>;

  return <div className="min-h-screen bg-[#f4f8f5] text-slate-900 md:flex">
    <aside className="bg-[#003816] text-white md:fixed md:inset-y-0 md:flex md:w-72 md:flex-col">
      <div className="px-5 py-5"><p className="text-lg font-extrabold">EcoPulse AI</p><p className="text-xs text-emerald-100">Super Admin Command Center</p></div>
      <nav aria-label="Super Admin portal" className="flex gap-1 overflow-x-auto px-3 pb-3 md:flex-1 md:flex-col md:overflow-y-auto">{tabs.map(tabButton)}</nav>
      <div className="hidden border-t border-white/15 p-4 md:block"><p className="truncate text-sm font-semibold">{identity?.name || identity?.full_name || 'Super Admin'}</p><p className="mt-1 text-xs text-emerald-100">Governance access · MFA protected</p><button type="button" onClick={logout} className="mt-4 flex w-full items-center gap-2 rounded-lg bg-red-500/15 px-3 py-2 text-sm font-semibold text-red-100"><LogOut size={16}/>Sign out</button></div>
    </aside>
    <main className="min-w-0 flex-1 p-4 pb-10 sm:p-6 md:ml-72 md:p-8">
      <header className="mb-6 flex flex-wrap items-center justify-between gap-3"><div><p className="text-xs font-bold uppercase tracking-[0.16em] text-emerald-800">Governance and security</p><h1 className="mt-1 text-2xl font-extrabold">{tab}</h1><p className="mt-1 text-sm text-slate-600">Centralized view of persisted EcoPulse AI operations</p></div><div className="flex gap-2"><button type="button" onClick={loadData} disabled={loading} className="inline-flex items-center gap-2 rounded-xl border border-slate-200 bg-white px-3 py-2 text-sm font-semibold disabled:opacity-50"><RefreshCw size={16}/>Refresh</button><button type="button" onClick={logout} className="inline-flex items-center gap-2 rounded-xl border border-slate-200 bg-white px-3 py-2 text-sm font-semibold md:hidden"><LogOut size={16}/>Sign out</button></div></header>
      {error && <p role="alert" className="mb-4 rounded-xl border border-red-200 bg-red-50 p-4 text-sm text-red-800"><AlertTriangle className="mr-2 inline" size={17}/>{error}</p>}
      {message && <p role="status" className="mb-4 rounded-xl border border-emerald-200 bg-emerald-50 p-4 text-sm text-emerald-800">{message}</p>}
      {loading && <p role="status" className="mb-4 text-sm text-slate-500">Loading authorized governance records…</p>}
      <div className="mb-4"><StaffCredentialNotice credential={staffCredential} onDismiss={() => setStaffCredential(null)}/></div>

      {tab === 'Overview' && <div className="space-y-6">
        <div className="grid gap-4 sm:grid-cols-2 xl:grid-cols-4">
          {metricCard('Registered citizens', metrics?.total_citizens ?? citizens.length, 'Citizen directory records', UserRound)}
          {metricCard('Municipal Admins', adminStats.total, 'Excludes the current Super Admin account', Building2)}
          {metricCard('Drivers', staff.filter(account => account.role === 'driver').length, 'Staff directory records', Users)}
          {metricCard('Collectors', staff.filter(account => account.role === 'collector').length, 'Staff directory records', Users)}
          {metricCard('Active accounts', activeCount, 'Citizen, Municipal Admin and field staff records', Shield)}
          {metricCard('Suspended accounts', suspendedCount, 'Citizen, Municipal Admin and field staff records', Shield)}
          {metricCard('Total complaints', metrics?.total_complaints, 'Persisted complaint count from metrics API', ClipboardList)}
          {metricCard('Pending complaints', metrics?.pending_complaints, 'Persisted complaints with Pending status', ClipboardList)}
          {metricCard('Completed complaints', metrics?.completed_complaints, 'Persisted complaints with Completed status', ClipboardList)}
          {metricCard('Tasks awaiting verification', tasksData.counts?.['Pending Verification'] ?? 0, 'Persisted task lifecycle status count', Activity)}
          {metricCard('Completed collection tasks', tasksData.counts?.Completed ?? 0, 'Persisted task lifecycle status count', Activity)}
          {metricCard('Pending invitations', invitationPending, `${invitationExpired} expired invitations across staff accounts`, ShieldCheck)}
        </div>
        <div className="grid gap-5 xl:grid-cols-2">
          <section className="rounded-2xl border border-slate-200 bg-white p-5"><div className="flex items-center justify-between"><h2 className="font-bold">Recent complaints</h2><button type="button" onClick={() => setTab('Complaint Monitoring')} className="text-sm font-semibold text-emerald-800">Monitor complaints</button></div><div className="mt-4 space-y-3">{complaints.slice(0, 5).map(item => <div key={item.db_id} className="flex items-center justify-between gap-3 rounded-xl border border-slate-100 p-3"><div><p className="font-semibold">{item.id} · {item.type}</p><p className="text-xs text-slate-500">{item.ward} · {item.location}</p></div><Badge value={item.status}/></div>)}{!loading && complaints.length === 0 && <Empty>No complaints are recorded.</Empty>}</div></section>
          <section className="rounded-2xl border border-slate-200 bg-white p-5"><div className="flex items-center justify-between"><h2 className="font-bold">Recent governance activity</h2><button type="button" onClick={() => setTab('Audit Logs')} className="text-sm font-semibold text-emerald-800">Open audit logs</button></div><div className="mt-4 space-y-3">{events.slice(0, 5).map(event => <div key={event.id} className="rounded-xl border border-slate-100 p-3"><p className="font-semibold">{label(event.action)}</p><p className="mt-1 text-xs text-slate-500">{event.actor_employee_id || 'Actor unavailable'} → {event.target_employee_id || 'Target unavailable'} · {dateValue(event.created_at)}</p></div>)}{!loading && events.length === 0 && <Empty>No security events are recorded.</Empty>}</div></section>
        </div>
      </div>}

      {tab === 'Municipal Admin Management' && <section className="space-y-4">
        <StaffProvisioningPanel allowedRoles={['admin']} onCreated={async credential => { setStaffCredential(credential); await loadData(); }}/>
        <div className="flex flex-wrap items-center gap-3 rounded-2xl border border-slate-200 bg-white p-4">{tableSearch}<label className="text-xs font-semibold">Status<select aria-label="Filter Municipal Admins by status" value={adminStatusFilter} onChange={event => setAdminStatusFilter(event.target.value)} className="ml-2 rounded-lg border border-slate-300 p-2 text-sm"><option value="all">All statuses</option>{['active', 'pending', 'suspended', 'retired'].map(status => <option key={status}>{status}</option>)}</select></label><p className="max-w-xl rounded-lg border border-emerald-200 bg-emerald-50 p-3 text-xs text-emerald-900">The Super Admin assigns each Municipal Admin’s unique official employee ID. Initial credentials are shown once for secure manual delivery.</p></div>
        <div className="overflow-x-auto rounded-2xl border border-slate-200 bg-white"><table className="w-full min-w-[1050px] text-left text-sm"><thead className="bg-slate-50 text-xs uppercase text-slate-500"><tr>{['Account','Ward','Status','Verified','MFA','Invitation','Expires','Actions'].map(column => <th key={column} className="p-3">{column}</th>)}</tr></thead><tbody>{filteredAdmins.map(account => <tr key={account.id} className="border-t border-slate-100"><td className="p-3"><p className="font-bold">{account.full_name}</p><p className="text-xs text-slate-500">Official ID: {account.employee_id || 'Unavailable'} · Login ID: {account.login_id || 'Unavailable'}</p><p className="text-xs text-slate-500">{account.email || 'Email unavailable'} · {account.phone || 'Phone unavailable'}</p></td><td className="p-3">{account.ward || 'Unavailable'}</td><td className="p-3"><Badge value={account.account_status}/></td><td className="p-3"><Badge value={account.is_verified ? 'verified' : 'unverified'}/></td><td className="p-3"><Badge value={account.mfa_enabled ? 'enrolled' : 'required'}/></td><td className="p-3"><Badge value={account.invitation_status}/></td><td className="p-3">{dateValue(account.invitation_expires_at)}</td><td className="p-3"><div className="flex flex-wrap gap-2"><button type="button" disabled={busyId === account.id || ['retired', 'deactivated'].includes(account.account_status)} onClick={() => resetStaffPassword(account)} className="rounded-lg border border-amber-300 px-2.5 py-1.5 text-xs font-semibold text-amber-900 disabled:opacity-50">Reset credentials</button>{statusControl(account)}</div></td></tr>)}{!loading && filteredAdmins.length === 0 && <tr><td colSpan="8" className="p-8 text-center text-slate-500">No Municipal Admin accounts match this search.</td></tr>}</tbody></table></div>
        <p className="text-xs text-slate-500">Invitation reset and resend remain offline operator workflows. Passwords and token material are never listed.</p>
      </section>}

      {tab === 'Field Staff Management' && <section className="space-y-4">
        <StaffProvisioningPanel allowedRoles={['driver', 'collector']} onCreated={async credential => { setStaffCredential(credential); await loadData(); }}/>
        <div className="flex flex-wrap items-center gap-3 rounded-2xl border border-slate-200 bg-white p-4">{tableSearch}<label className="text-xs font-semibold">Role<select aria-label="Filter staff by role" value={staffRoleFilter} onChange={event => setStaffRoleFilter(event.target.value)} className="ml-2 rounded-lg border border-slate-300 p-2 text-sm"><option value="all">All roles</option><option value="driver">Driver</option><option value="collector">Collector</option></select></label><label className="text-xs font-semibold">Ward<select aria-label="Filter staff by ward" value={staffWardFilter} onChange={event => setStaffWardFilter(event.target.value)} className="ml-2 rounded-lg border border-slate-300 p-2 text-sm"><option value="all">All wards</option>{registryWards.map(ward => <option key={ward.id} value={String(ward.id)}>{ward.ward_number} — {ward.display_name}</option>)}</select></label><label className="text-xs font-semibold">Status<select aria-label="Filter staff by status" value={staffStatusFilter} onChange={event => setStaffStatusFilter(event.target.value)} className="ml-2 rounded-lg border border-slate-300 p-2 text-sm"><option value="all">All statuses</option>{['active', 'pending', 'suspended', 'retired'].map(status => <option key={status}>{status}</option>)}</select></label></div>
        <div className="overflow-x-auto rounded-2xl border border-slate-200 bg-white"><table className="w-full min-w-[1050px] text-left text-sm"><thead className="bg-slate-50 text-xs uppercase text-slate-500"><tr>{['Employee','Role','Ward','Status','Verified','MFA','Invitation','Actions'].map(column => <th key={column} className="p-3">{column}</th>)}</tr></thead><tbody>{filteredStaff.map(account => <tr key={account.id} className="border-t border-slate-100"><td className="p-3"><p className="font-bold">{account.full_name}</p><p className="text-xs text-slate-500">Login ID: {account.login_id || 'Unavailable'} · Official ID: {account.employee_id || 'Unavailable'}</p><p className="text-xs text-slate-500">{account.phone || 'Phone unavailable'}</p></td><td className="p-3 capitalize">{account.role}</td><td className="p-3">{account.ward || 'Unavailable'}</td><td className="p-3"><Badge value={account.account_status || (account.is_active ? 'active' : 'inactive')}/></td><td className="p-3"><Badge value={account.is_verified ? 'verified' : 'unverified'}/></td><td className="p-3"><Badge value={account.mfa_enabled ? 'enrolled' : account.role === 'collector' ? 'required' : 'phone verification'}/></td><td className="p-3"><Badge value={account.invitation_status}/></td><td className="p-3"><div className="flex flex-wrap gap-2"><button type="button" disabled={busyId === account.id || ['retired', 'deactivated'].includes(account.account_status)} onClick={() => resetStaffPassword(account)} className="rounded-lg border border-amber-300 px-2.5 py-1.5 text-xs font-semibold text-amber-900 disabled:opacity-50">Reset credentials</button>{statusControl(account)}</div></td></tr>)}{!loading && filteredStaff.length === 0 && <tr><td colSpan="8" className="p-8 text-center text-slate-500">No field staff match these filters.</td></tr>}</tbody></table></div>
      </section>}

      {tab === 'Citizen Management' && <section className="space-y-4">
        <div className="flex flex-wrap items-center gap-3 rounded-2xl border border-slate-200 bg-white p-4">{tableSearch}<label className="text-xs font-semibold">Status<select aria-label="Filter citizens by status" value={citizenStatusFilter} onChange={event => setCitizenStatusFilter(event.target.value)} className="ml-2 rounded-lg border border-slate-300 p-2 text-sm"><option value="all">All</option><option value="active">Active</option><option value="suspended">Suspended</option><option value="retired">Retired</option></select></label></div>
        <div className="overflow-x-auto rounded-2xl border border-slate-200 bg-white"><table className="w-full min-w-[850px] text-left text-sm"><thead className="bg-slate-50 text-xs uppercase text-slate-500"><tr>{['Citizen','Phone / email','Ward','Status','Verified','WhatsApp','Complaints','History'].map(column => <th key={column} className="p-3">{column}</th>)}</tr></thead><tbody>{filteredCitizens.map(citizen => <tr key={citizen.id} className="border-t border-slate-100"><td className="p-3"><p className="font-semibold">{citizen.full_name}</p><p className="text-xs text-slate-500">Account #{citizen.id} · {citizen.login_id || 'No login ID recorded'}</p></td><td className="p-3">{citizen.phone || 'Phone unavailable'}<p className="text-xs text-slate-500">{citizen.email || 'Email unavailable'}</p></td><td className="p-3">{citizen.ward || 'Unavailable'}</td><td className="p-3"><Badge value={citizen.account_status}/></td><td className="p-3"><Badge value={citizen.is_verified ? 'verified' : 'unverified'}/></td><td className="p-3"><Badge value={citizen.whatsapp_linked ? 'linked' : 'not linked'}/></td><td className="p-3">{citizen.complaint_count}</td><td className="p-3"><div className="flex flex-wrap gap-2">{statusControl(citizen)}<button type="button" onClick={() => viewCitizenHistory(citizen)} className="rounded-lg border border-slate-200 px-3 py-1.5 text-xs font-semibold">Complaints</button></div></td></tr>)}{!loading && filteredCitizens.length === 0 && <tr><td colSpan="8" className="p-8 text-center text-slate-500">No citizens match this search.</td></tr>}</tbody></table></div>
      </section>}

      {tab === 'Ward Management' && <section className="space-y-5">
        <div className="grid gap-4 xl:grid-cols-[1fr_1.2fr]">
          <form onSubmit={saveWard} className="space-y-3 rounded-2xl border border-slate-200 bg-white p-5">
            <h2 className="font-bold">{wardEdit ? 'Edit ward' : 'Create ward'}</h2>
            <label className="block text-xs font-semibold">Municipality<select required value={wardMunicipalityId} onChange={event => setWardMunicipalityId(event.target.value)} disabled={Boolean(wardEdit)} className="mt-1 w-full rounded-lg border border-slate-300 bg-white p-2 text-sm">{municipalities.map(municipality => <option key={municipality.id} value={municipality.id}>{municipality.name} ({municipality.code})</option>)}</select></label>
            <div className="grid gap-3 sm:grid-cols-2"><label className="text-xs font-semibold">Ward number/code<input required maxLength={30} value={wardForm.ward_number} onChange={event => setWardForm(form => ({ ...form, ward_number: event.target.value, display_name: wardEdit ? form.display_name : `Ward ${event.target.value}` }))} className="mt-1 w-full rounded-lg border border-slate-300 p-2 text-sm"/></label><label className="text-xs font-semibold">Display name<input required maxLength={120} value={wardForm.display_name} onChange={event => setWardForm(form => ({ ...form, display_name: event.target.value }))} className="mt-1 w-full rounded-lg border border-slate-300 p-2 text-sm"/></label></div>
            <label className="block text-xs font-semibold">Locality / area description (optional)<textarea maxLength={2000} value={wardForm.locality_description} onChange={event => setWardForm(form => ({ ...form, locality_description: event.target.value }))} className="mt-1 w-full rounded-lg border border-slate-300 p-2 text-sm"/></label>
            <div className="flex gap-2"><button disabled={!wardMunicipalityId} className="rounded-lg bg-emerald-800 px-4 py-2 text-sm font-bold text-white">{wardEdit ? 'Save ward' : 'Create ward'}</button>{wardEdit && <button type="button" onClick={() => { setWardEdit(null); setWardForm({ ward_number: '', display_name: '', locality_description: '' }); }} className="rounded-lg border px-4 py-2 text-sm">Cancel</button>}</div>
            <p className="text-xs text-slate-500">Ward number/code is unique within its municipality. Deactivation preserves assignments and history.</p>
          </form>
          <form onSubmit={saveMunicipality} className="space-y-3 rounded-2xl border border-slate-200 bg-white p-5"><h2 className="font-bold">Add municipality</h2><div className="grid gap-3 sm:grid-cols-2"><label className="text-xs font-semibold">Code<input required pattern="[A-Za-z0-9_-]+" value={newMunicipality.code} onChange={event => setNewMunicipality(value => ({ ...value, code: event.target.value }))} className="mt-1 w-full rounded-lg border border-slate-300 p-2 text-sm"/></label><label className="text-xs font-semibold">Name<input required minLength={2} value={newMunicipality.name} onChange={event => setNewMunicipality(value => ({ ...value, name: event.target.value }))} className="mt-1 w-full rounded-lg border border-slate-300 p-2 text-sm"/></label></div><button className="rounded-lg border border-emerald-700 px-4 py-2 text-sm font-bold text-emerald-900">Add municipality</button><p className="text-xs text-slate-500">No locality boundaries or ward descriptions are inferred.</p></form>
        </div>
        <div className="flex flex-wrap items-center gap-3 rounded-2xl border border-slate-200 bg-white p-4"><input aria-label="Search wards" value={wardSearch} onChange={event => setWardSearch(event.target.value)} placeholder="Search ward number, name or locality" className="min-w-56 flex-1 rounded-lg border border-slate-300 p-2 text-sm"/><label className="text-xs font-semibold">Municipality<select value={wardMunicipalityId} onChange={event => setWardMunicipalityId(event.target.value)} className="ml-2 rounded-lg border border-slate-300 bg-white p-2 text-sm">{municipalities.map(municipality => <option key={municipality.id} value={municipality.id}>{municipality.name}</option>)}</select></label><label className="text-xs font-semibold">Status<select value={wardStatusFilter} onChange={event => setWardStatusFilter(event.target.value)} className="ml-2 rounded-lg border border-slate-300 bg-white p-2 text-sm"><option value="all">All</option><option value="active">Active</option><option value="inactive">Inactive</option></select></label></div>
        <div className="overflow-x-auto rounded-2xl border border-slate-200 bg-white"><table className="w-full min-w-[900px] text-left text-sm"><thead className="bg-slate-50 text-xs uppercase text-slate-500"><tr>{['Ward','Locality description','Municipal Admins','Drivers','Collectors','Status','Assigned staff / actions'].map(column => <th key={column} className="p-3">{column}</th>)}</tr></thead><tbody>{filteredRegistryWards.map(ward => <tr key={ward.id} className="border-t border-slate-100 align-top"><td className="p-3 font-semibold">{ward.ward_number} · {ward.display_name}<p className="text-xs font-normal text-slate-500">{ward.municipality_name}</p></td><td className="p-3">{ward.locality_description || 'Not specified'}</td><td className="p-3">{ward.staff_counts?.admin ?? 0}</td><td className="p-3">{ward.staff_counts?.driver ?? 0}</td><td className="p-3">{ward.staff_counts?.collector ?? 0}</td><td className="p-3"><Badge value={ward.is_active ? 'active' : 'inactive'}/></td><td className="p-3"><details><summary className="cursor-pointer text-xs font-semibold">View {ward.assigned_staff?.length || 0} assigned</summary><ul className="my-2 space-y-1">{ward.assigned_staff?.map(account => <li key={account.id} className="text-xs">{account.full_name} · {label(account.role)} · {account.account_status}</li>)}</ul></details><div className="mt-2 flex gap-2"><button type="button" onClick={() => { setWardEdit(ward); setWardMunicipalityId(String(ward.municipality_id)); setWardForm({ ward_number: ward.ward_number, display_name: ward.display_name, locality_description: ward.locality_description || '' }); }} className="rounded border px-2 py-1 text-xs font-semibold">Edit</button><button type="button" onClick={() => toggleWard(ward)} className="rounded border px-2 py-1 text-xs font-semibold">{ward.is_active ? 'Deactivate' : 'Activate'}</button></div></td></tr>)}{!loading && filteredRegistryWards.length === 0 && <tr><td colSpan="7" className="p-8 text-center text-slate-500">No wards match these filters.</td></tr>}</tbody></table></div>
      </section>}

      {tab === 'Complaint Monitoring' && <section className="space-y-4"><div className="flex flex-wrap items-center gap-3 rounded-2xl border border-slate-200 bg-white p-4">{tableSearch}<label className="text-xs font-semibold">Status<select aria-label="Filter complaints by status" value={complaintStatus} onChange={event => setComplaintStatus(event.target.value)} className="ml-2 rounded-lg border border-slate-300 p-2 text-sm"><option value="all">All statuses</option>{['Pending', 'In Progress', 'Completed'].map(status => <option key={status}>{status}</option>)}</select></label><label className="text-xs font-semibold">Ward<select aria-label="Filter complaints by ward" value={complaintWard} onChange={event => setComplaintWard(event.target.value)} className="ml-2 rounded-lg border border-slate-300 p-2 text-sm"><option value="all">All wards</option>{wardOptions.map(ward => <option key={ward}>{ward}</option>)}</select></label><button type="button" onClick={exportCsv} className="inline-flex items-center gap-2 rounded-lg border border-slate-200 px-3 py-2 text-sm font-semibold"><Download size={15}/>Export CSV</button></div><div className="overflow-x-auto rounded-2xl border border-slate-200 bg-white"><table className="w-full min-w-[850px] text-left text-sm"><thead className="bg-slate-50 text-xs uppercase text-slate-500"><tr>{['Complaint','Ward','Location','Status','Assigned Driver','Submitted','Details'].map(column => <th key={column} className="p-3">{column}</th>)}</tr></thead><tbody>{filteredComplaints.map(item => <tr key={item.db_id} className="border-t border-slate-100"><td className="p-3 font-semibold">{item.id}<p className="text-xs font-normal text-slate-500">{item.type}</p></td><td className="p-3">{item.ward}</td><td className="p-3">{item.location}</td><td className="p-3"><Badge value={item.status}/></td><td className="p-3">{item.assignedTo || 'Unassigned'}</td><td className="p-3">{dateValue(item.created_at)}</td><td className="p-3"><button type="button" onClick={() => viewComplaint(item)} className="rounded-lg border border-slate-200 px-3 py-1.5 text-xs font-semibold">View lifecycle</button></td></tr>)}{!loading && filteredComplaints.length === 0 && <tr><td colSpan="7" className="p-8 text-center text-slate-500">No complaints match these filters.</td></tr>}</tbody></table></div><p className="text-xs text-slate-500">Monitoring is read-only. Assignment and completion remain in the existing Municipal Admin evidence workflow.</p></section>}

      {tab === 'Task Monitoring' && <section className="space-y-4"><div className="grid gap-3 sm:grid-cols-2 lg:grid-cols-4">{taskStatuses.map(status => <article key={status} className="rounded-xl border border-slate-200 bg-white p-4"><p className="text-xs font-bold uppercase text-slate-500">{status}</p><p className="mt-1 text-2xl font-extrabold text-[#003816]">{tasksData.counts?.[status] ?? 0}</p></article>)}</div><div className="flex flex-wrap items-center gap-3 rounded-2xl border border-slate-200 bg-white p-4">{tableSearch}<label className="text-xs font-semibold">Task status<select aria-label="Filter tasks by status" value={taskStatus} onChange={event => setTaskStatus(event.target.value)} className="ml-2 rounded-lg border border-slate-300 p-2 text-sm"><option value="all">All statuses</option>{taskStatuses.map(status => <option key={status}>{status}</option>)}</select></label><span className="text-xs text-slate-500">Showing {filteredTasks.length} of {tasksData.total || 0} tasks{tasksData.total > (tasksData.tasks || []).length ? ' (latest 500 loaded)' : ''}.</span></div><div className="space-y-3">{filteredTasks.map(task => <article key={task.id} className="rounded-2xl border border-slate-200 bg-white p-4"><div className="flex flex-wrap items-start justify-between gap-3"><div><h2 className="font-bold">Task #{task.id} · {task.driver_name || 'Driver unavailable'}</h2><p className="text-sm text-slate-600">{task.location_name} · {task.complaint?.ward || 'Ward unavailable'} · Complaint {task.complaint?.tracking_number || 'unlinked'}</p></div><Badge value={task.status}/></div><div className="mt-3 grid gap-3 sm:grid-cols-2"><p className="text-sm"><span className="text-slate-500">Evidence items:</span> {task.evidence?.length ?? 0}</p><p className="text-sm"><span className="text-slate-500">Latest rejection reason:</span> {task.evidence?.find(evidence => evidence.rejection_reason)?.rejection_reason || 'Unavailable'}</p></div>{task.evidence?.length > 0 && <div className="mt-3 flex flex-wrap gap-3">{task.evidence.map(evidence => <a key={evidence.id} href={evidence.after_image_url} target="_blank" rel="noreferrer" className="text-sm font-semibold text-emerald-800 underline">View evidence #{evidence.id}</a>)}</div>}<details className="mt-3"><summary className="cursor-pointer text-sm font-semibold text-emerald-800">Task history</summary><ol className="mt-2 space-y-2 border-l border-slate-200 pl-4">{(task.history || []).map((event, index) => <li key={`${event.event_type}-${index}`} className="text-sm"><span className="font-semibold">{label(event.event_type)}</span> · {event.from_status || 'Start'} → {event.to_status || 'Unavailable'} · {dateValue(event.created_at)}{event.details && <p className="text-xs text-slate-600">{event.details}</p>}</li>)}{!task.history?.length && <li className="text-xs text-slate-500">No task history is recorded.</li>}</ol></details></article>)}{!loading && filteredTasks.length === 0 && <Empty>No tasks match this filter.</Empty>}</div><p className="text-xs text-slate-500">Read-only monitoring. Evidence approval and rejection remain under the existing Municipal Admin workflow.</p></section>}

      {tab === 'Analytics & Reports' && <section className="space-y-5"><div className="flex justify-end"><button type="button" onClick={exportCsv} className="inline-flex items-center gap-2 rounded-xl border border-slate-200 bg-white px-3 py-2 text-sm font-semibold"><Download size={16}/>Download complaints CSV</button></div><div className="grid gap-4 sm:grid-cols-2 xl:grid-cols-4">{metricCard('Complaint resolution rate', analytics?.resolution_rate == null ? null : `${analytics.resolution_rate}%`, 'Calculated by the existing analytics service', BarChart3)}{metricCard('Active Drivers', analytics?.active_drivers, 'Persisted active Driver accounts', Users)}{metricCard('Total Drivers', analytics?.total_drivers, 'Persisted Driver accounts', Users)}{metricCard('Average response hours', analytics?.avg_response_hours, 'Unavailable when the analytics service has no value', Activity)}{metricCard('Citizen satisfaction', analytics?.citizen_satisfaction, 'Unavailable unless recorded by the backend', Activity)}{metricCard('Waste collected (tonnes)', analytics?.waste_collected_tonnes, 'Unavailable unless recorded by the backend', Activity)}{metricCard('Pending verification', tasksData.counts?.['Pending Verification'] ?? 0, 'Task lifecycle count', ClipboardList)}</div><div className="grid gap-5 xl:grid-cols-2"><section className="rounded-2xl border border-slate-200 bg-white p-5"><h2 className="mb-3 font-bold">Ward complaint summary</h2><div className="space-y-2">{analytics?.ward_breakdown?.map(row => <div key={row.ward} className="flex items-center justify-between border-b border-slate-100 py-2 text-sm"><span>{row.ward}</span><span>{row.total} total · {row.resolved} resolved · {row.pending} pending</span></div>)}{!loading && !analytics?.ward_breakdown?.length && <Empty>No ward analytics are available.</Empty>}</div></section><section className="rounded-2xl border border-slate-200 bg-white p-5"><h2 className="mb-3 font-bold">Monthly complaint trends</h2><div className="space-y-2">{analytics?.monthly_trends?.map(row => <div key={row.month} className="flex items-center justify-between border-b border-slate-100 py-2 text-sm"><span>{row.month}</span><span>{row.complaints} complaints · {row.resolved} resolved</span></div>)}{!loading && !analytics?.monthly_trends?.length && <Empty>No monthly trends are available.</Empty>}</div></section></div><p className="text-xs text-slate-500">Staff operational summaries are not provided by the current analytics API. Unavailable metrics are not estimated.</p></section>}

      {tab === 'Audit Logs' && <section className="space-y-4"><div className="flex flex-wrap items-center gap-3 rounded-2xl border border-slate-200 bg-white p-4">{tableSearch}<label className="sr-only" htmlFor="audit-action-filter">Filter audit action</label><select id="audit-action-filter" value={eventAction} onChange={event => setEventAction(event.target.value)} className="rounded-xl border border-slate-300 bg-white px-3 py-2 text-sm"><option value="all">All actions</option>{actionOptions.map(action => <option key={action} value={action}>{label(action)}</option>)}</select><span className="text-xs text-slate-500">Latest {events.length} of up to 250 events</span></div><div className="space-y-3">{filteredEvents.map(event => <article key={event.id} className="rounded-2xl border border-slate-200 bg-white p-4 shadow-sm"><div className="flex flex-wrap items-start justify-between gap-3"><div><h2 className="font-bold capitalize">{label(event.action)}</h2><p className="mt-1 text-xs text-slate-500">{dateValue(event.created_at)}</p></div><Badge value="Outcome unavailable"/></div><dl className="mt-4 grid gap-3 text-sm sm:grid-cols-3"><div><dt className="text-xs text-slate-500">Actor</dt><dd className="font-semibold">{event.actor_employee_id || 'Unavailable'}</dd></div><div><dt className="text-xs text-slate-500">Target account</dt><dd className="font-semibold">{event.target_employee_id || 'Unavailable'}</dd></div><div><dt className="text-xs text-slate-500">Recorded details</dt><dd className="break-words">{event.details || 'Unavailable'}</dd></div></dl></article>)}{!loading && filteredEvents.length === 0 && <Empty>No audit events match these filters.</Empty>}<p className="text-xs text-slate-500">Audit data comes from recorded immutable security events. The current event schema does not record success/failure outcomes.</p></div></section>}

      {tab === 'Security & Account Settings' && <section className="space-y-5"><div className="grid gap-4 sm:grid-cols-2"><article className="rounded-2xl border border-slate-200 bg-white p-5"><h2 className="font-bold">Signed-in Super Admin</h2><dl className="mt-4 space-y-3 text-sm"><div><dt className="text-xs text-slate-500">Name</dt><dd>{identity?.name || identity?.full_name || 'Unavailable'}</dd></div><div><dt className="text-xs text-slate-500">Official employee ID</dt><dd>{identity?.employee_id || 'Unavailable'}</dd></div><div><dt className="text-xs text-slate-500">Login ID</dt><dd>{identity?.login_id || 'Unavailable'}</dd></div><div><dt className="text-xs text-slate-500">Role</dt><dd>{identity?.role || 'Unavailable'} · Super Admin {identity?.is_super_admin ? 'enabled' : 'unavailable'}</dd></div><div><dt className="text-xs text-slate-500">Account status</dt><dd><Badge value={identity?.account_status || (identity?.is_active ? 'active' : 'Unavailable')}/></dd></div><div><dt className="text-xs text-slate-500">Authenticator MFA</dt><dd><Badge value={identity?.mfa_enabled ? 'enrolled' : 'Unavailable'}/></dd></div></dl></article><article className="rounded-2xl border border-slate-200 bg-white p-5"><h2 className="font-bold">Session security</h2><p className="mt-3 text-sm text-slate-600">Staff password resets and account status changes revoke existing sessions. This portal does not expose session tokens or provide a separate revoke-all operation.</p><button type="button" onClick={logout} className="mt-4 inline-flex items-center gap-2 rounded-lg border border-red-200 px-3 py-2 text-sm font-semibold text-red-700"><LogOut size={16}/>Sign out of this session</button></article></div><section className="rounded-2xl border border-slate-200 bg-white p-5"><h2 className="font-bold">Recent security events for this account</h2><div className="mt-3 space-y-2">{events.filter(event => event.actor_employee_id === identity?.employee_id || event.target_employee_id === identity?.employee_id).slice(0, 10).map(event => <div key={event.id} className="flex flex-wrap justify-between gap-2 border-b border-slate-100 py-2 text-sm"><span>{label(event.action)} · {event.details || 'Details unavailable'}</span><span className="text-xs text-slate-500">{dateValue(event.created_at)}</span></div>)}{!loading && events.filter(event => event.actor_employee_id === identity?.employee_id || event.target_employee_id === identity?.employee_id).length === 0 && <p className="text-sm text-slate-500">No matching account events are present in the latest audit page.</p>}</div></section></section>}
    </main>

    {selectedCitizen && <div className="fixed inset-0 z-50 flex items-center justify-center bg-slate-950/50 p-4" role="presentation" onMouseDown={event => { if (event.target === event.currentTarget) setSelectedCitizen(null); }}><section role="dialog" aria-modal="true" aria-labelledby="citizen-history-title" className="max-h-[85vh] w-full max-w-2xl overflow-y-auto rounded-2xl bg-white p-5 shadow-xl"><div className="flex items-start justify-between gap-3"><div><h2 id="citizen-history-title" className="text-lg font-bold">Citizen profile · {selectedCitizen.full_name}</h2><p className="text-sm text-slate-500">Profile and citizen-facing complaint history; no tracking credentials are shown.</p></div><button type="button" aria-label="Close citizen history" onClick={() => setSelectedCitizen(null)} className="rounded-lg p-2 hover:bg-slate-100"><X size={18}/></button></div><dl className="mt-4 grid gap-3 rounded-xl bg-slate-50 p-4 text-sm sm:grid-cols-2"><div><dt className="text-xs text-slate-500">Phone</dt><dd>{selectedCitizen.phone || 'Unavailable'}</dd></div><div><dt className="text-xs text-slate-500">Email</dt><dd>{selectedCitizen.email || 'Unavailable'}</dd></div><div><dt className="text-xs text-slate-500">Ward</dt><dd>{selectedCitizen.ward || 'Unavailable'}</dd></div><div><dt className="text-xs text-slate-500">Account status</dt><dd><Badge value={selectedCitizen.account_status}/></dd></div><div><dt className="text-xs text-slate-500">Verified / WhatsApp linked</dt><dd>{selectedCitizen.is_verified ? 'Verified' : 'Not verified'} · {selectedCitizen.whatsapp_linked ? 'Linked' : 'Not linked'}</dd></div><div><dt className="text-xs text-slate-500">Registered</dt><dd>{dateValue(selectedCitizen.created_at)}</dd></div></dl>{citizenHistoryLoading ? <p className="py-8 text-center text-sm text-slate-500">Loading complaint history…</p> : <div className="mt-4 space-y-3">{citizenComplaints.map(complaint => <article key={complaint.id} className="rounded-xl border border-slate-200 p-3"><div className="flex justify-between gap-3"><strong>{complaint.id} · {complaint.type}</strong><Badge value={complaint.status}/></div><p className="mt-1 text-sm">{complaint.location} · {complaint.ward}</p><p className="text-xs text-slate-500">{dateValue(complaint.created_at)} · Image attached: {complaint.has_image ? 'Yes' : 'No'}</p></article>)}{!citizenComplaints.length && <Empty>No complaint history is recorded.</Empty>}</div>}</section></div>}
    {selectedAccount && <div className="fixed inset-0 z-50 flex items-center justify-center bg-slate-950/50 p-4"><section role="dialog" aria-modal="true" aria-labelledby="account-history-title" className="max-h-[85vh] w-full max-w-2xl overflow-y-auto rounded-2xl bg-white p-5 shadow-xl"><div className="flex items-start justify-between"><div><h2 id="account-history-title" className="text-lg font-bold">{selectedAccount.full_name} · Account details</h2><p className="text-sm text-slate-500">{selectedAccount.role} · {selectedAccount.account_status}</p></div><button type="button" onClick={() => setSelectedAccount(null)} aria-label="Close account details" className="rounded-lg p-2 hover:bg-slate-100"><X size={18}/></button></div><dl className="mt-4 grid gap-3 rounded-xl bg-slate-50 p-4 text-sm sm:grid-cols-2"><div><dt className="text-xs text-slate-500">Official employee ID</dt><dd>{selectedAccount.employee_id || 'Unavailable'}</dd></div><div><dt className="text-xs text-slate-500">Login ID</dt><dd>{selectedAccount.login_id || 'Unavailable'}</dd></div><div><dt className="text-xs text-slate-500">Phone / email</dt><dd>{selectedAccount.phone || 'Unavailable'} · {selectedAccount.email || 'Unavailable'}</dd></div><div><dt className="text-xs text-slate-500">Ward</dt><dd>{selectedAccount.ward || 'Unavailable'}</dd></div><div><dt className="text-xs text-slate-500">Verified / MFA</dt><dd>{selectedAccount.is_verified ? 'Verified' : 'Unverified'} · {selectedAccount.mfa_enabled ? 'Enrolled' : 'Not enrolled'}</dd></div><div><dt className="text-xs text-slate-500">Created / activated</dt><dd>{dateValue(selectedAccount.created_at)} · {dateValue(selectedAccount.activated_at)}</dd></div></dl><h3 className="mt-5 font-bold">Account history</h3><div className="mt-2 space-y-2">{accountHistory.map(event => <article key={event.id} className="rounded-lg border border-slate-200 p-3 text-sm"><p className="font-semibold">{label(event.action)} · {event.actor_employee_id || 'Actor unavailable'}</p><p>{event.details || 'Details unavailable'}</p><p className="text-xs text-slate-500">{dateValue(event.created_at)}</p></article>)}{!accountHistory.length && <p className="text-sm text-slate-500">No account history is recorded.</p>}</div></section></div>}    {selectedComplaint && <div className="fixed inset-0 z-50 flex items-center justify-center bg-slate-950/50 p-4" role="presentation" onMouseDown={event => { if (event.target === event.currentTarget) setSelectedComplaint(null); }}><section role="dialog" aria-modal="true" aria-labelledby="complaint-detail-title" className="max-h-[85vh] w-full max-w-3xl overflow-y-auto rounded-2xl bg-white p-5 shadow-xl"><div className="flex items-start justify-between gap-3"><div><h2 id="complaint-detail-title" className="text-lg font-bold">Complaint lifecycle · {selectedComplaint.complaint?.id}</h2><p className="text-sm text-slate-500">Read-only operations details</p></div><button type="button" aria-label="Close complaint details" onClick={() => setSelectedComplaint(null)} className="rounded-lg p-2 hover:bg-slate-100"><X size={18}/></button></div><dl className="mt-4 grid gap-3 sm:grid-cols-2"><div><dt className="text-xs text-slate-500">Ward / status</dt><dd>{selectedComplaint.complaint?.ward || 'Unavailable'} · {selectedComplaint.complaint?.status || 'Unavailable'}</dd></div><div><dt className="text-xs text-slate-500">Assignment</dt><dd>{selectedComplaint.complaint?.assignedTo || 'Unassigned'}</dd></div><div><dt className="text-xs text-slate-500">Location</dt><dd>{selectedComplaint.complaint?.location || 'Unavailable'}</dd></div><div><dt className="text-xs text-slate-500">Description</dt><dd>{selectedComplaint.complaint?.description || 'Unavailable'}</dd></div></dl>{selectedComplaint.task ? <article className="mt-5 rounded-xl border border-slate-200 p-4"><div className="flex justify-between"><h3 className="font-bold">Task #{selectedComplaint.task.id}</h3><Badge value={selectedComplaint.task.status}/></div><p className="mt-2 text-sm">Driver: {selectedComplaint.task.driver_name || 'Unavailable'}</p><p className="mt-2 text-sm">Evidence items: {selectedComplaint.task.evidence?.length ?? 0}</p>{selectedComplaint.task.evidence?.map(evidence => evidence.rejection_reason && <p key={evidence.id} className="mt-2 rounded-lg bg-red-50 p-3 text-sm text-red-800">Rejection: {evidence.rejection_reason}</p>)}<details className="mt-3"><summary className="cursor-pointer text-sm font-semibold text-emerald-800">History</summary><div className="mt-2 space-y-2">{(selectedComplaint.task.history || []).map((event, index) => <p key={`${event.event_type}-${index}`} className="text-sm">{label(event.event_type)} · {event.from_status || 'Start'} → {event.to_status} · {dateValue(event.created_at)}</p>)}</div></details></article> : <p className="mt-4 rounded-xl bg-slate-50 p-4 text-sm text-slate-600">No task is linked to this complaint.</p>}</section></div>}
  </div>;
}
