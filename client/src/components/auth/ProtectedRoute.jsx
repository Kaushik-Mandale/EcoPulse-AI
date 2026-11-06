import React, { useState, useEffect } from 'react';
import { Navigate, useLocation } from 'react-router-dom';
import { getCurrentUser } from '../../services/authService';

/**
 * ProtectedRoute — secure, backend-validated route guard.
 *
 * Security model:
 * - On route transition and mount, validates the JWT against the backend (/api/auth/me).
 * - Never injects demo/mock users.
 * - On 401/403 or missing token, redirects to /login.
 * - Shows a neutral loading screen while validation is in-flight.
 * - Handles browser Back/Forward: pageshow event (persisted=true) re-validates cached pages.
 * - Handles multi-tab logout: storage event listener immediately revokes access if another tab logged out.
 * - Enforces role-based access control.
 */
const ProtectedRoute = ({ children, allowedRoles }) => {
  const location = useLocation();
  const [authState, setAuthState] = useState({
    status: 'loading', // 'loading' | 'authenticated' | 'unauthenticated'
    user: null,
  });

  const validate = async () => {
    setAuthState({ status: 'loading', user: null });
    const user = await getCurrentUser(); // calls /api/auth/me; returns null on 401/403/no token
    if (user) {
      setAuthState({ status: 'authenticated', user });
    } else {
      setAuthState({ status: 'unauthenticated', user: null });
    }
  };

  useEffect(() => {
    validate();

    // Re-validate when the browser restores this page from the back-forward cache
    // (pageshow fires with persisted=true for bfcache restorations).
    const handlePageShow = (e) => {
      if (e.persisted) {
        validate();
      }
    };

    // Multi-tab synchronization: if another tab logs out (removes ecopulse_token),
    // immediately invalidate this tab's state and redirect to login.
    const handleStorageChange = (e) => {
      if (e.key === 'ecopulse_token' && !e.newValue) {
        setAuthState({ status: 'unauthenticated', user: null });
      }
    };

    window.addEventListener('pageshow', handlePageShow);
    window.addEventListener('storage', handleStorageChange);

    return () => {
      window.removeEventListener('pageshow', handlePageShow);
      window.removeEventListener('storage', handleStorageChange);
    };
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [location.pathname]);

  // ── Loading ────────────────────────────────────────────────────────────────
  if (authState.status === 'loading') {
    return (
      <div className="min-h-screen bg-[#f6f9f7] flex items-center justify-center">
        <div className="flex flex-col items-center gap-4">
          <div className="w-10 h-10 border-4 border-emerald-600 border-t-transparent rounded-full animate-spin" />
          <p className="text-sm text-slate-500 font-medium">Verifying session…</p>
        </div>
      </div>
    );
  }

  // ── Unauthenticated ────────────────────────────────────────────────────────
  if (authState.status === 'unauthenticated') {
    // Preserve the intended destination so we can redirect after login
    return <Navigate to="/login" replace state={{ from: location }} />;
  }

  // ── Role-Based Access Control ──────────────────────────────────────────────
  if (allowedRoles && allowedRoles.length > 0) {
    const userRole = (authState.user.role || 'citizen').toLowerCase();
    const hasPermission = allowedRoles.some((r) => r.toLowerCase() === userRole);

    if (!hasPermission) {
      // Redirect to the user's authorized home — never expose a denied dashboard
      if (userRole === 'driver') return <Navigate to="/driver" replace />;
      if (userRole === 'admin' || userRole === 'collector') return <Navigate to="/admin" replace />;
      return <Navigate to="/citizen" replace />;
    }
  }

  // ── Authenticated + Authorized ─────────────────────────────────────────────
  return children;
};

export default ProtectedRoute;
