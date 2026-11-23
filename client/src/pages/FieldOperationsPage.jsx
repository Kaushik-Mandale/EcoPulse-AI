import React, { useEffect, useState } from 'react';
import { useNavigate } from 'react-router-dom';
import api from '../services/api';
import DriverDashboardPage from './DriverDashboardPage';
import CollectorDashboardPage from './CollectorDashboardPage';

export default function FieldOperationsPage() {
  const navigate = useNavigate();
  const [workspace, setWorkspace] = useState(null);

  useEffect(() => {
    let current = true;
    api.get('/auth/me').then(({ data: identity }) => {
      if (!current) return;
      const role = identity?.role?.toLowerCase();
      if (role === 'driver' || role === 'collector') setWorkspace(role);
      else if (role === 'admin') navigate(identity.is_super_admin ? '/super-admin' : '/admin', { replace: true });
      else if (role === 'citizen') navigate('/citizen', { replace: true });
      else navigate('/login', { replace: true });
    }).catch(() => {
      if (current) navigate('/login', { replace: true });
    });
    return () => { current = false; };
  }, [navigate]);

  if (workspace === 'driver') return <DriverDashboardPage />;
  if (workspace === 'collector') return <CollectorDashboardPage />;
  return <div className="flex min-h-screen items-center justify-center bg-[#f4f8f5] text-sm font-semibold text-slate-600" role="status">Loading verified field workspace…</div>;
}
