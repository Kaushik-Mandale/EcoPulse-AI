import React, { useEffect, useState } from 'react';
import { Link } from 'react-router-dom';
import { AlertTriangle, ArrowLeft, MapPin, Trash2 } from 'lucide-react';
import api from '../services/api';
import InteractiveMap from '../components/InteractiveMap';

export default function InteractiveMapPage() {
  const [complaints, setComplaints] = useState([]);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState('');

  useEffect(() => {
    let active = true;

    api.get('/complaints')
      .then(({ data }) => {
        if (!Array.isArray(data)) {
          throw new Error('The complaints response was not a list.');
        }
        if (active) setComplaints(data);
      })
      .catch((requestError) => {
        console.error('Unable to load reported complaint locations.', requestError);
        if (active) setError('Reported locations could not be loaded. Please try again later.');
      })
      .finally(() => {
        if (active) setLoading(false);
      });

    return () => {
      active = false;
    };
  }, []);

  const mappedComplaints = complaints.filter((complaint) =>
    Number.isFinite(complaint.latitude) && Number.isFinite(complaint.longitude)
  );
  const mapTasks = mappedComplaints.map((complaint) => ({
    id: complaint.id,
    name: complaint.type,
    location_name: complaint.location,
    status: complaint.status,
    latitude: complaint.latitude,
    longitude: complaint.longitude,
  }));

  return (
    <div className="min-h-screen bg-[#f8faf9] text-slate-800 font-sans selection:bg-[#005C2B] selection:text-white flex flex-col">
      <header className="bg-white border-b border-slate-200 sticky top-0 z-40">
        <div className="max-w-7xl mx-auto px-4 py-3.5 flex items-center justify-between">
          <div className="flex items-center gap-3">
            <Link to="/" className="w-9 h-9 rounded-xl bg-[#005C2B] text-white flex items-center justify-center hover:opacity-90 transition-opacity" aria-label="Back to home">
              <ArrowLeft className="w-5 h-5" />
            </Link>
            <div>
              <h1 className="text-lg font-black text-slate-900 tracking-tight leading-none">Reported Waste Locations</h1>
              <p className="text-xs text-emerald-700 font-bold mt-0.5">Map markers reflect submitted reports with location data</p>
            </div>
          </div>
          <Link to="/report" className="text-xs font-bold bg-[#005C2B] text-white px-3.5 py-2 rounded-xl hover:bg-[#004a22] transition-colors">
            + Report Waste
          </Link>
        </div>
      </header>

      <main className="flex-1 max-w-7xl w-full mx-auto p-4 flex flex-col gap-4">
        {error && (
          <div role="alert" className="flex items-center gap-2 rounded-xl border border-red-200 bg-red-50 p-4 text-sm text-red-800">
            <AlertTriangle className="h-5 w-5 shrink-0" />
            <span>{error}</span>
          </div>
        )}

        <div className="grid grid-cols-1 sm:grid-cols-2 gap-3">
          <div className="bg-white p-3.5 rounded-2xl border border-slate-200 shadow-2xs flex items-center gap-3">
            <div className="w-10 h-10 rounded-xl bg-emerald-100 text-[#005C2B] flex items-center justify-center">
              <Trash2 className="w-5 h-5" />
            </div>
            <div>
              <span className="text-[11px] font-bold text-slate-400 uppercase">Reports returned by service</span>
              <p className="text-lg font-black text-slate-900">
                {loading ? 'Loading…' : error ? 'Unavailable' : complaints.length}
              </p>
            </div>
          </div>

          <div className="bg-white p-3.5 rounded-2xl border border-slate-200 shadow-2xs flex items-center gap-3">
            <div className="w-10 h-10 rounded-xl bg-blue-100 text-blue-700 flex items-center justify-center">
              <MapPin className="w-5 h-5" />
            </div>
            <div>
              <span className="text-[11px] font-bold text-slate-400 uppercase">Reports with location</span>
              <p className="text-lg font-black text-slate-900">
                {loading ? 'Loading…' : error ? 'Unavailable' : mappedComplaints.length}
              </p>
            </div>
          </div>
        </div>

        <div className="flex-1 min-h-[550px] bg-white rounded-3xl border border-slate-200 shadow-xs overflow-hidden p-1">
          {loading ? (
            <div className="flex h-full min-h-[540px] items-center justify-center text-sm font-medium text-slate-500" role="status">
              Loading reported locations…
            </div>
          ) : error ? (
            <div className="flex h-full min-h-[540px] flex-col items-center justify-center gap-2 p-6 text-center text-sm text-slate-600">
              <AlertTriangle className="h-6 w-6 text-red-500" />
              <p>The map is unavailable because report data could not be loaded.</p>
            </div>
          ) : mapTasks.length ? (
            <InteractiveMap tasks={mapTasks} height="540px" />
          ) : (
            <div className="flex h-full min-h-[540px] flex-col items-center justify-center gap-2 p-6 text-center text-sm text-slate-600">
              <MapPin className="h-6 w-6 text-slate-400" />
              <p>No submitted reports currently include map coordinates.</p>
            </div>
          )}
        </div>
      </main>
    </div>
  );
}
