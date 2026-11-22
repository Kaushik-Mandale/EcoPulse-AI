import React, { useMemo, useState } from 'react';

/** Registry-backed ward picker. The form submits only the selected database ID. */
export default function WardSelector({ wards = [], value, onChange, required = true, disabled = false, loading = false, label = 'Assigned ward' }) {
  const [search, setSearch] = useState('');
  const options = useMemo(() => wards.filter(ward =>
    `${ward.ward_number} ${ward.display_name} ${ward.locality_description || ''}`.toLowerCase().includes(search.trim().toLowerCase())
  ), [wards, search]);
  return (
    <div className="text-xs font-semibold text-slate-700">
      <label htmlFor="registry-ward-search">{label}</label>
      <input id="registry-ward-search" type="search" value={search} onChange={event => setSearch(event.target.value)} placeholder="Search ward number or name" disabled={disabled || loading} className="mt-1 w-full rounded-lg border border-slate-300 p-2 text-sm font-normal" />
      <select required={required} value={value || ''} onChange={event => onChange(event.target.value ? Number(event.target.value) : '')} disabled={disabled || loading || wards.length === 0} aria-label={label} className="mt-2 w-full rounded-lg border border-slate-300 bg-white p-2 text-sm font-normal">
        <option value="">{loading ? 'Loading wards…' : wards.length ? 'Select a ward' : 'No active wards available'}</option>
        {options.map(ward => <option key={ward.id} value={ward.id}>Ward {ward.ward_number} — {ward.display_name}{ward.locality_description ? ` · ${ward.locality_description}` : ''}</option>)}
      </select>
    </div>
  );
}
