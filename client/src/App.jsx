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
import DriverDashboardPage from './pages/DriverDashboardPage';
import ReportWastePage from './pages/ReportWastePage';
import TrackComplaintPage from './pages/TrackComplaintPage';
import InteractiveMapPage from './pages/InteractiveMapPage';
import EcoWalletPage from './pages/EcoWalletPage';
import DemoPage from './pages/DemoPage';
import HelpFaqPage from './pages/HelpFaqPage';
import ContactPage from './pages/ContactPage';
import LegalPage from './pages/LegalPage';
import ForgotPasswordPage from './pages/ForgotPasswordPage';
import OtpVerifyPage from './pages/OtpVerifyPage';
import NotificationsPage from './pages/NotificationsPage';
import NotFoundPage from './pages/NotFoundPage';
import SwapMarketplacePage from './pages/SwapMarketplacePage';
import ProtectedRoute from './components/auth/ProtectedRoute';
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
    if (user?.role === 'driver') {
      navigate('/driver');
    } else if (user?.role === 'admin' || user?.role === 'collector') {
      navigate('/admin');
    } else {
      navigate('/citizen');
    }
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
        <Route path="/" element={<LandingPage />} />
        <Route path="/login" element={<LoginPage />} />
        <Route path="/signup" element={<SignupPage />} />
        <Route path="/demo" element={<DemoPage />} />

        {/* Public Civic Workflows */}
        <Route path="/report" element={<ReportWastePage />} />
        <Route path="/track" element={<TrackComplaintPage />} />
        <Route path="/track/:id" element={<TrackComplaintPage />} />
        <Route path="/map" element={<InteractiveMapPage />} />
        <Route path="/live-tracking" element={<InteractiveMapPage />} />
        <Route path="/wallet" element={<EcoWalletPage />} />
        <Route path="/rewards" element={<EcoWalletPage />} />
        <Route path="/swaps" element={<SwapMarketplacePage />} />
        <Route path="/items" element={<SwapMarketplacePage />} />
        <Route path="/marketplace" element={<SwapMarketplacePage />} />

        {/* Knowledge, Support & Legal */}
        <Route path="/help" element={<HelpFaqPage />} />
        <Route path="/faq" element={<HelpFaqPage />} />
        <Route path="/contact" element={<ContactPage />} />
        <Route path="/privacy" element={<LegalPage />} />
        <Route path="/terms" element={<LegalPage />} />
        <Route path="/forgot-password" element={<ForgotPasswordPage />} />
        <Route path="/otp" element={<OtpVerifyPage />} />
        <Route path="/notifications" element={<NotificationsPage />} />

        {/* Citizen Portal Routes */}
        <Route
          path="/citizen"
          element={
            <ProtectedRoute allowedRoles={['citizen', 'admin']}>
              <DashboardPage />
            </ProtectedRoute>
          }
        />
        <Route path="/citzen" element={<Navigate to="/citizen" replace />} />
        <Route path="/dashboard" element={<Navigate to="/citizen" replace />} />
        <Route
          path="/profile"
          element={
            <ProtectedRoute allowedRoles={['citizen', 'admin']}>
              <DashboardPage initialTab="Profile" />
            </ProtectedRoute>
          }
        />
        <Route
          path="/settings"
          element={
            <ProtectedRoute allowedRoles={['citizen', 'admin']}>
              <DashboardPage initialTab="Settings" />
            </ProtectedRoute>
          }
        />

        {/* Municipal Admin & Department Views */}
        <Route
          path="/admin"
          element={
            <ProtectedRoute allowedRoles={['admin', 'collector']}>
              <AdminDashboardPage />
            </ProtectedRoute>
          }
        />
        <Route path="/collector" element={<Navigate to="/admin" replace />} />
        <Route
          path="/analytics"
          element={
            <ProtectedRoute allowedRoles={['admin', 'collector']}>
              <AdminDashboardPage initialTab="Analytics" />
            </ProtectedRoute>
          }
        />
        <Route
          path="/users"
          element={
            <ProtectedRoute allowedRoles={['admin', 'collector']}>
              <AdminDashboardPage initialTab="Drivers" />
            </ProtectedRoute>
          }
        />
        <Route
          path="/complaints"
          element={
            <ProtectedRoute allowedRoles={['admin', 'collector']}>
              <AdminDashboardPage initialTab="Complaints" />
            </ProtectedRoute>
          }
        />
        <Route
          path="/vehicles"
          element={
            <ProtectedRoute allowedRoles={['admin', 'collector']}>
              <AdminDashboardPage initialTab="Drivers" />
            </ProtectedRoute>
          }
        />
        <Route
          path="/wards"
          element={
            <ProtectedRoute allowedRoles={['admin', 'collector']}>
              <AdminDashboardPage initialTab="Smart Bins" />
            </ProtectedRoute>
          }
        />
        <Route
          path="/reports"
          element={
            <ProtectedRoute allowedRoles={['admin', 'collector']}>
              <AdminDashboardPage initialTab="Reports" />
            </ProtectedRoute>
          }
        />

        {/* Driver Operations Portal */}
        <Route
          path="/driver"
          element={
            <ProtectedRoute allowedRoles={['driver', 'admin']}>
              <DriverDashboardPage />
            </ProtectedRoute>
          }
        />

        {/* Error Pages */}
        <Route path="/404" element={<NotFoundPage />} />
        <Route path="/500" element={<NotFoundPage />} />
        <Route path="*" element={<NotFoundPage />} />
      </Routes>

      {/* Agentation Visual Feedback & Annotation Toolbar */}
      {import.meta.env.DEV && <Agentation />}
    </Router>
  );
}

export default App;
