import React from 'react';
import { BrowserRouter as Router, Routes, Route, useNavigate, Navigate } from 'react-router-dom';
import Navbar from './components/ecopulse/Navbar';
import HeroSection from './components/ecopulse/HeroSection';
import RolesSection from './components/ecopulse/RolesSection';
import HowItWorksSection from './components/ecopulse/HowItWorksSection';
import ImpactSection from './components/ecopulse/ImpactSection';
import FooterSection from './components/ecopulse/FooterSection';
import LoginPage from './pages/LoginPage';
import SignupPage from './pages/SignupPage';
import DashboardPage from './pages/DashboardPage';
import AdminDashboardPage from './pages/AdminDashboardPage';
import SuperAdminDashboardPage from './pages/SuperAdminDashboardPage';
import FieldOperationsPage from './pages/FieldOperationsPage';
import ReportWastePage from './pages/ReportWastePage';
import TrackComplaintPage from './pages/TrackComplaintPage';
import InteractiveMapPage from './pages/InteractiveMapPage';
import EcoWalletPage from './pages/EcoWalletPage';
import HelpFaqPage from './pages/HelpFaqPage';
import ContactPage from './pages/ContactPage';
import LegalPage from './pages/LegalPage';
import ForgotPasswordPage from './pages/ForgotPasswordPage';
import OtpVerifyPage from './pages/OtpVerifyPage';
import InvitationActivationPage from './pages/InvitationActivationPage';
import NotificationsPage from './pages/NotificationsPage';
import NotFoundPage from './pages/NotFoundPage';
import SwapMarketplacePage from './pages/SwapMarketplacePage';
import ProtectedRoute from './components/auth/ProtectedRoute';
import { APP_ROUTE_PATHS } from './appRoutePaths';
import { Agentation } from 'agentation';
import './index.css';
import './App.css';

function LandingPage() {
  const navigate = useNavigate();

  const handleOpenLogin = () => {
    navigate('/login');
  };

  const handleOpenSignup = () => {
    navigate('/signup');
  };

  const handleAuthSuccess = (user) => {
    localStorage.setItem('ecopulse_user', JSON.stringify(user));
    const role = user?.role?.toLowerCase();
    if (role === 'driver') {
      navigate(APP_ROUTE_PATHS.fieldOperations);
    } else if (role === 'collector') {
      navigate(APP_ROUTE_PATHS.fieldOperations);
    } else if (role === 'admin') {
      navigate(user?.is_super_admin ? '/super-admin' : '/admin');
    } else if (role === 'citizen') {
      navigate('/citizen');
    } else navigate('/login', { replace: true });
  };

  return (
    <div className="min-h-screen bg-white text-gray-900 font-sans selection:bg-[#005C2B] selection:text-white relative overflow-x-hidden">
      {/* Main Page Header & Sections */}
      <Navbar onOpenLogin={handleOpenLogin} onOpenSignup={handleOpenSignup} />
      <main className="relative z-10">
        <HeroSection />
        <RolesSection />
        <HowItWorksSection />
        <ImpactSection />
      </main>
      <FooterSection />
    </div>
  );
}

function App() {
  return (
    <Router>
      <Routes>
        {/* Public Marketing & Core Information */}
        <Route path={APP_ROUTE_PATHS.home} element={<LandingPage />} />
        <Route path={APP_ROUTE_PATHS.login} element={<LoginPage />} />
        <Route path={APP_ROUTE_PATHS.signup} element={<SignupPage />} />

        {/* Public Civic Workflows */}
        <Route path={APP_ROUTE_PATHS.report} element={<ReportWastePage />} />
        <Route path={APP_ROUTE_PATHS.track} element={<TrackComplaintPage />} />
        <Route path={APP_ROUTE_PATHS.trackById} element={<TrackComplaintPage />} />
        <Route path={APP_ROUTE_PATHS.map} element={<InteractiveMapPage />} />
        <Route path={APP_ROUTE_PATHS.liveTracking} element={<InteractiveMapPage />} />
        <Route path={APP_ROUTE_PATHS.wallet} element={<EcoWalletPage />} />
        <Route path={APP_ROUTE_PATHS.rewards} element={<EcoWalletPage />} />
        <Route path={APP_ROUTE_PATHS.swaps} element={<SwapMarketplacePage />} />
        <Route path={APP_ROUTE_PATHS.items} element={<SwapMarketplacePage />} />
        <Route path={APP_ROUTE_PATHS.marketplace} element={<SwapMarketplacePage />} />

        {/* Knowledge, Support & Legal */}
        <Route path={APP_ROUTE_PATHS.help} element={<HelpFaqPage />} />
        <Route path={APP_ROUTE_PATHS.faq} element={<HelpFaqPage />} />
        <Route path={APP_ROUTE_PATHS.contact} element={<ContactPage />} />
        <Route path={APP_ROUTE_PATHS.privacy} element={<LegalPage />} />
        <Route path={APP_ROUTE_PATHS.terms} element={<LegalPage />} />
        <Route path={APP_ROUTE_PATHS.forgotPassword} element={<ForgotPasswordPage />} />
        <Route path={APP_ROUTE_PATHS.activate} element={<InvitationActivationPage />} />
        <Route path={APP_ROUTE_PATHS.otp} element={<OtpVerifyPage />} />
        <Route path={APP_ROUTE_PATHS.notifications} element={<NotificationsPage />} />

        {/* Citizen Portal Routes */}
        <Route
          path={APP_ROUTE_PATHS.citizen}
          element={
            <ProtectedRoute allowedRoles={['citizen', 'admin']}>
              <DashboardPage />
            </ProtectedRoute>
          }
        />
        <Route path={APP_ROUTE_PATHS.misspelledCitizenRedirect} element={<Navigate to={APP_ROUTE_PATHS.citizen} replace />} />
        <Route path={APP_ROUTE_PATHS.dashboardRedirect} element={<Navigate to={APP_ROUTE_PATHS.citizen} replace />} />
        <Route
          path={APP_ROUTE_PATHS.profile}
          element={
            <ProtectedRoute allowedRoles={['citizen', 'admin']}>
              <DashboardPage initialTab="Profile" />
            </ProtectedRoute>
          }
        />
        <Route
          path={APP_ROUTE_PATHS.settings}
          element={
            <ProtectedRoute allowedRoles={['citizen', 'admin']}>
              <DashboardPage initialTab="Settings" />
            </ProtectedRoute>
          }
        />

        {/* Municipal Admin Views */}
        <Route
          path={APP_ROUTE_PATHS.admin}
          element={
            <ProtectedRoute allowedRoles={['admin']}>
              <AdminDashboardPage />
            </ProtectedRoute>
          }
        />
        <Route
          path={APP_ROUTE_PATHS.superAdmin}
          element={
            <ProtectedRoute allowedRoles={['admin']} requireSuperAdmin>
              <SuperAdminDashboardPage />
            </ProtectedRoute>
          }
        />
        <Route
          path={APP_ROUTE_PATHS.analytics}
          element={
            <ProtectedRoute allowedRoles={['admin']}>
              <AdminDashboardPage initialTab="Analytics" />
            </ProtectedRoute>
          }
        />
        <Route
          path={APP_ROUTE_PATHS.users}
          element={
            <ProtectedRoute allowedRoles={['admin']}>
              <AdminDashboardPage initialTab="Drivers" />
            </ProtectedRoute>
          }
        />
        <Route
          path={APP_ROUTE_PATHS.complaints}
          element={
            <ProtectedRoute allowedRoles={['admin']}>
              <AdminDashboardPage initialTab="Complaints" />
            </ProtectedRoute>
          }
        />
        <Route
          path={APP_ROUTE_PATHS.vehicles}
          element={
            <ProtectedRoute allowedRoles={['admin']}>
              <AdminDashboardPage initialTab="Drivers" />
            </ProtectedRoute>
          }
        />
        <Route
          path={APP_ROUTE_PATHS.wards}
          element={
            <ProtectedRoute allowedRoles={['admin']}>
              <AdminDashboardPage initialTab="Smart Bins" />
            </ProtectedRoute>
          }
        />
        <Route
          path={APP_ROUTE_PATHS.reports}
          element={
            <ProtectedRoute allowedRoles={['admin']}>
              <AdminDashboardPage initialTab="Reports" />
            </ProtectedRoute>
          }
        />

        {/* Shared, server-role-selected Field Operations workspace */}
        <Route
          path={APP_ROUTE_PATHS.fieldOperations}
          element={
            <ProtectedRoute allowedRoles={['driver', 'collector']}>
              <FieldOperationsPage />
            </ProtectedRoute>
          }
        />
        {/* Legacy role URLs validate the session before redirecting to the shared portal. */}
        <Route
          path={APP_ROUTE_PATHS.driver}
          element={
            <ProtectedRoute allowedRoles={['driver']}>
              <Navigate to={APP_ROUTE_PATHS.fieldOperations} replace />
            </ProtectedRoute>
          }
        />
        <Route
          path={APP_ROUTE_PATHS.collector}
          element={
            <ProtectedRoute allowedRoles={['collector']}>
              <Navigate to={APP_ROUTE_PATHS.fieldOperations} replace />
            </ProtectedRoute>
          }
        />

        {/* Error Pages */}
        <Route path={APP_ROUTE_PATHS.notFoundPage} element={<NotFoundPage />} />
        <Route path={APP_ROUTE_PATHS.serverErrorPage} element={<NotFoundPage />} />
        <Route path={APP_ROUTE_PATHS.notFound} element={<NotFoundPage />} />
      </Routes>

      {/* Agentation Visual Feedback & Annotation Toolbar */}
      {import.meta.env.DEV && <Agentation />}
    </Router>
  );
}

export default App;
