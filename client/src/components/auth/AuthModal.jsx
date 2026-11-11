import React, { useState, useEffect } from 'react';
import { motion, AnimatePresence } from 'framer-motion';
import { X } from 'lucide-react';
import LoginForm from './LoginForm';
import SignupForm from './SignupForm';
import ForgotPasswordModal from './ForgotPasswordModal';

const AuthModal = ({ isOpen, onClose, initialMode = 'login', onSuccess }) => {
  const [activeTab, setActiveTab] = useState(initialMode);
  const [isForgotPasswordOpen, setIsForgotPasswordOpen] = useState(false);

  useEffect(() => {
    setActiveTab(initialMode);
  }, [initialMode, isOpen]);

  // Handle escape key to close
  useEffect(() => {
    const handleKeyDown = (e) => {
      if (e.key === 'Escape' && isOpen && !isForgotPasswordOpen) {
        onClose();
      }
    };
    window.addEventListener('keydown', handleKeyDown);
    return () => window.removeEventListener('keydown', handleKeyDown);
  }, [isOpen, isForgotPasswordOpen, onClose]);

  if (!isOpen) return null;

  return (
    <AnimatePresence>
      <div className="fixed inset-0 z-50 flex items-center justify-center p-3 sm:p-6 overflow-y-auto">
        {/* Backdrop Overlay */}
        <motion.div
          initial={{ opacity: 0 }}
          animate={{ opacity: 1 }}
          exit={{ opacity: 0 }}
          onClick={onClose}
          className="fixed inset-0 bg-slate-900/65 backdrop-blur-md transition-opacity"
        />

        {/* Modal Floating Card */}
        <motion.div
          initial={{ opacity: 0, scale: 0.92, y: 30 }}
          animate={{ opacity: 1, scale: 1, y: 0 }}
          exit={{ opacity: 0, scale: 0.92, y: 30 }}
          transition={{ type: 'spring', damping: 26, stiffness: 320 }}
          className="relative w-full max-w-lg overflow-hidden rounded-[32px] bg-white/92 backdrop-blur-2xl border border-white/90 p-6 sm:p-8 md:p-9 shadow-[0_30px_70px_-15px_rgba(0,92,43,0.3)] z-10 text-gray-900"
        >
          {/* Top Decorative Ambient Glow */}
          <div className="absolute -top-24 -right-24 w-52 h-52 bg-[#005C2B]/15 rounded-full blur-2xl pointer-events-none" />
          <div className="absolute -bottom-24 -left-24 w-52 h-52 bg-sky-400/15 rounded-full blur-2xl pointer-events-none" />

          {/* Close Button */}
          <button
            onClick={onClose}
            className="absolute top-5 right-5 p-2 rounded-full text-gray-400 hover:text-gray-700 hover:bg-gray-100/80 transition-colors cursor-pointer z-20"
            aria-label="Close Auth Modal"
          >
            <X className="w-5 h-5" />
          </button>

          {/* Brand Header */}
          <div className="flex items-center gap-3 mb-6 pr-8">
            <div className="w-10 h-10 bg-[#005C2B] rounded-xl flex items-center justify-center text-white shadow-xs">
              <svg className="w-5 h-5 fill-current" viewBox="0 0 24 24">
                <path d="M20 8h-3V4H3c-1.1 0-2 .9-2 2v11h2c0 1.66 1.34 3 3 3s3-1.34 3-3h6c0 1.66 1.34 3 3 3s3-1.34 3-3h2v-5l-3-4zM6 18.5c-.83 0-1.5-.67-1.5-1.5s.67-1.5 1.5-1.5 1.5.67 1.5 1.5-.67 1.5-1.5 1.5zm13.5-9l1.96 2.5H17V9.5h2.5zm-1.5 9c-.83 0-1.5-.67-1.5-1.5s.67-1.5 1.5-1.5 1.5.67 1.5 1.5-.67 1.5-1.5 1.5z" />
              </svg>
            </div>
            <div>
              <div className="text-lg font-black text-gray-900 leading-tight">EcoPulse AI</div>
              <div className="text-[11px] font-semibold text-gray-500">Smart Civic & Sustainability Ecosystem</div>
            </div>
          </div>

          {/* Tab Switcher Header */}
          <div className="mb-6 p-1 bg-gray-100/90 rounded-2xl flex items-center border border-gray-200/80 relative">
            <button
              type="button"
              onClick={() => setActiveTab('login')}
              className={`relative flex-1 py-2 px-3 rounded-xl text-xs font-black transition-all cursor-pointer z-10 ${
                activeTab === 'login' ? 'text-[#005C2B]' : 'text-gray-600 hover:text-gray-900'
              }`}
            >
              {activeTab === 'login' && (
                <motion.div
                  layoutId="modal-tab-pill"
                  className="absolute inset-0 bg-white rounded-xl shadow-xs border border-emerald-100"
                  transition={{ type: 'spring', stiffness: 400, damping: 30 }}
                />
              )}
              <span className="relative z-10">Sign In</span>
            </button>

            <button
              type="button"
              onClick={() => setActiveTab('signup')}
              className={`relative flex-1 py-2 px-3 rounded-xl text-xs font-black transition-all cursor-pointer z-10 ${
                activeTab === 'signup' ? 'text-[#005C2B]' : 'text-gray-600 hover:text-gray-900'
              }`}
            >
              {activeTab === 'signup' && (
                <motion.div
                  layoutId="modal-tab-pill"
                  className="absolute inset-0 bg-white rounded-xl shadow-xs border border-emerald-100"
                  transition={{ type: 'spring', stiffness: 400, damping: 30 }}
                />
              )}
              <span className="relative z-10">Create Account</span>
            </button>
          </div>

          {/* Tab Content */}
          <AnimatePresence mode="wait">
            {activeTab === 'login' ? (
              <motion.div
                key="modal-login"
                initial={{ opacity: 0, x: -15 }}
                animate={{ opacity: 1, x: 0 }}
                exit={{ opacity: 0, x: 15 }}
                transition={{ duration: 0.2 }}
              >
                <LoginForm
                  onSwitchToSignup={() => setActiveTab('signup')}
                  onOpenForgotPassword={() => setIsForgotPasswordOpen(true)}
                  onRoleChange={(role) => setActiveRole(role)}
                  onSuccess={(data) => {
                    if (onSuccess) onSuccess(data);
                    onClose();
                  }}
                />
              </motion.div>
            ) : (
              <motion.div
                key="modal-signup"
                initial={{ opacity: 0, x: 15 }}
                animate={{ opacity: 1, x: 0 }}
                exit={{ opacity: 0, x: -15 }}
                transition={{ duration: 0.2 }}
              >
                <SignupForm
                  onSwitchToLogin={() => setActiveTab('login')}
                  onRoleChange={(role) => setActiveRole(role)}
                  onSuccess={(data) => {
                    if (onSuccess) onSuccess(data);
                    onClose();
                  }}
                />
              </motion.div>
            )}
          </AnimatePresence>
        </motion.div>

        {/* Nested Forgot Password Modal */}
        <ForgotPasswordModal
          isOpen={isForgotPasswordOpen}
          onClose={() => setIsForgotPasswordOpen(false)}
          onBackToLogin={() => setIsForgotPasswordOpen(false)}
        />
      </div>
    </AnimatePresence>
  );
};

export default AuthModal;
