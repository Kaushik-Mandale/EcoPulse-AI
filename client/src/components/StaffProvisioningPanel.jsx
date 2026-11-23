import React, { useEffect, useState } from 'react';
import { createStaffAccount, fetchWardMunicipalities, fetchWards } from '../services/adminService';
import WardSelector from './WardSelector';

const roleLabels = { admin: 'Municipal Admin', driver: 'Driver', collector: 'Collector' };

export function StaffCredentialNotice({ credential, onDismiss }) {
  const [copyError, setCopyError] = useState('');
  if (!credential) return null;
  const copy = async () => {
    setCopyError('');
    try {
      await navigator.clipboard.writeText(`Login ID: ${credential.login_id}\nTemporary password: ${credential.temporary_password}`);
    } catch {
      setCopyError('Copy is unavailable in this browser. Select and copy the credentials manually.');
    }
  };
  return (
    <section role="status" className="rounded-2xl border border-amber-300 bg-amber-50 p-4 text-sm text-amber-950">
      <h3 className="font-bold">One-time credentials for {credential.full_name}</h3>
      <dl className="mt-3 grid gap-2 sm:grid-cols-2">
        <div><dt className="text-xs font-semibold uppercase">Login ID</dt><dd className="font-mono font-bold">{credential.login_id}</dd></div>
        <div><dt className="text-xs font-semibold uppercase">Temporary password</dt><dd className="font-mono font-bold">{credential.temporary_password}</dd></div>
      </dl>
      <p className="mt-3">Communicate these credentials manually through an approved secure channel. The account holder must rotate the temporary password; no message is sent by EcoPulse.</p>
      {credential.temporary_password_expires_at && <p className="mt-2 font-semibold">Temporary credential expires {new Date(credential.temporary_password_expires_at).toLocaleString()}.</p>}
      {copyError && <p role="alert" className="mt-2 text-xs font-semibold text-red-800">{copyError}</p>}
      <div className="mt-3 flex gap-2">
        <button type="button" onClick={copy} className="rounded-lg bg-amber-900 px-3 py-2 text-xs font-bold text-white">Copy credentials</button>
        <button type="button" onClick={onDismiss} className="rounded-lg border border-amber-400 px-3 py-2 text-xs font-bold">Dismiss</button>
      </div>
    </section>
  );
}

export default function StaffProvisioningPanel({ allowedRoles, onCreated }) {
  const [role, setRole] = useState(allowedRoles[0] || 'driver');
  const [form, setForm] = useState({ full_name: '', phone: '', email: '', employee_id: '', ward_id: '', municipality_id: '' });
  const [municipalities, setMunicipalities] = useState([]);
  const [wards, setWards] = useState([]);
  const [wardsLoading, setWardsLoading] = useState(false);
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState('');

  useEffect(() => {
    let active = true;
    fetchWardMunicipalities().then(rows => {
      if (!active) return;
      const activeRows = (rows || []).filter(municipality => municipality.is_active);
      setMunicipalities(activeRows);
      if (!form.municipality_id && activeRows.length) setForm(previous => ({ ...previous, municipality_id: String(activeRows[0].id) }));
    }).catch(requestError => { if (active) setError(requestError?.response?.data?.detail || 'Municipalities could not be loaded.'); });
    return () => { active = false; };
  }, []);

  useEffect(() => {
    if (!form.municipality_id) { setWards([]); return undefined; }
    let active = true;
    setWardsLoading(true);
    fetchWards({ municipalityId: Number(form.municipality_id), active: true }).then(rows => {
      if (active) setWards(rows || []);
    }).catch(requestError => {
      if (active) { setWards([]); setError(requestError?.response?.data?.detail || 'Wards could not be loaded.'); }
    }).finally(() => { if (active) setWardsLoading(false); });
    return () => { active = false; };
  }, [form.municipality_id]);

  const update = (field) => (event) => setForm((previous) => ({ ...previous, [field]: event.target.value }));
  const submit = async (event) => {
    event.preventDefault();
    setError('');
    setBusy(true);
    try {
      const result = await createStaffAccount({
        full_name: form.full_name.trim(),
        phone: form.phone.trim(),
        email: form.email.trim() || null,
        role,
        ...(role === 'admin' ? { employee_id: form.employee_id.trim(), municipality_id: Number(form.municipality_id) }
          : { ward_id: Number(form.ward_id) }),
      });
      setForm(previous => ({ ...previous, full_name: '', phone: '', email: '', employee_id: '', ward_id: '' }));
      onCreated?.(result);
    } catch (requestError) {
      setError(requestError?.response?.data?.detail || 'Staff account could not be created.');
    } finally {
      setBusy(false);
    }
  };

  if (!allowedRoles.length) return null;
  return (
    <section className="rounded-2xl border border-slate-200 bg-white p-4 shadow-sm">
      <h2 className="text-base font-bold text-slate-900">Create staff account</h2>
      <p className="mt-1 text-xs text-slate-600">Login IDs are allocated by the server. Credentials appear once after successful creation.</p>
      {error && <p role="alert" className="mt-3 rounded-lg bg-red-50 p-3 text-sm text-red-700">{error}</p>}
      <form onSubmit={submit} className="mt-4 grid gap-3 sm:grid-cols-2 lg:grid-cols-3">
        {allowedRoles.length > 1 && <label className="text-xs font-semibold text-slate-700">Account role
          <select value={role} onChange={(event) => setRole(event.target.value)} className="mt-1 w-full rounded-lg border border-slate-300 bg-white p-2 text-sm">
            {allowedRoles.map((option) => <option key={option} value={option}>{roleLabels[option]}</option>)}
          </select>
        </label>}
        <label className="text-xs font-semibold text-slate-700">Full name
          <input required minLength={2} maxLength={120} value={form.full_name} onChange={update('full_name')} autoComplete="name" className="mt-1 w-full rounded-lg border border-slate-300 p-2 text-sm" />
        </label>
        <label className="text-xs font-semibold text-slate-700">Mobile number
          <input required type="tel" value={form.phone} onChange={update('phone')} autoComplete="tel" className="mt-1 w-full rounded-lg border border-slate-300 p-2 text-sm" />
        </label>
        <label className="text-xs font-semibold text-slate-700">Email (optional)
          <input type="email" value={form.email} onChange={update('email')} autoComplete="email" className="mt-1 w-full rounded-lg border border-slate-300 p-2 text-sm" />
        </label>
        {role === 'admin' && <label className="text-xs font-semibold text-slate-700">Official employee ID
          <input required value={form.employee_id} onChange={update('employee_id')} autoComplete="off" className="mt-1 w-full rounded-lg border border-slate-300 p-2 text-sm" />
          <span className="mt-1 block font-normal text-slate-500">The Super Admin assigns the employee’s official ID. It must be unique.</span>
        </label>}
        {role !== 'admin' && municipalities.length > 1 && <label className="text-xs font-semibold text-slate-700">Municipality
          <select required value={form.municipality_id} onChange={event => setForm(previous => ({ ...previous, municipality_id: event.target.value, ward_id: '' }))} className="mt-1 w-full rounded-lg border border-slate-300 bg-white p-2 text-sm">
            {municipalities.map(municipality => <option key={municipality.id} value={municipality.id}>{municipality.name}</option>)}
          </select>
        </label>}
        {role !== 'admin' && <WardSelector wards={wards} value={form.ward_id} onChange={value => setForm(previous => ({ ...previous, ward_id: value }))} loading={wardsLoading} />}
        {role === 'admin' && <label className="text-xs font-semibold text-slate-700">Municipality
          <select required value={form.municipality_id} onChange={update('municipality_id')} className="mt-1 w-full rounded-lg border border-slate-300 bg-white p-2 text-sm">
            {municipalities.map(municipality => <option key={municipality.id} value={municipality.id}>{municipality.name}</option>)}
          </select>
        </label>}
        <div className="flex items-end"><button type="submit" disabled={busy || wardsLoading || (role !== 'admin' && !form.ward_id)} className="w-full rounded-lg bg-emerald-800 px-4 py-2.5 text-sm font-bold text-white disabled:opacity-50">{busy ? 'Creating…' : `Create ${roleLabels[role]}`}</button></div>
      </form>
    </section>
  );
}
