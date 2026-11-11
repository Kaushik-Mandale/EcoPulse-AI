import React, { useState } from 'react';
import { motion, AnimatePresence } from 'framer-motion';
import { Mail, ArrowLeft, CheckCircle2, ShieldAlert, Sparkles, X } from 'lucide-react';
import { useForm } from 'react-hook-form';
import { zodResolver } from '@hookform/resolvers/zod';
import { z } from 'zod';
import { resetPasswordRequest } from '../../services/authService';

const forgotPasswordSchema = z.object({
  email: z.string().email('Please enter a valid email address'),
});

const ForgotPasswordModal = ({ isOpen, onClose, onBackToLogin }) => {
  const [isSubmitted, setIsSubmitted] = useState(false);

  const {
    register,
    handleSubmit,
    formState: { errors, isSubmitting },
    reset,
  } = useForm({
    resolver: zodResolver(forgotPasswordSchema),
  });

  const onSubmit = async (data) => {
    try {
      await resetPasswordRequest({ identifier: data.email, role: 'citizen' });
    } catch (err) {
      console.warn('Password reset fallback:', err);
    }
    setIsSubmitted(true);
  };

  const handleClose = () => {
    setIsSubmitted(false);
    reset();
    onClose();
  };

  if (!isOpen) return null;

  return (
    <AnimatePresence>
      <div className="fixed inset-0 z-50 flex items-center justify-center p-4 sm:p-6 overflow-y-auto">
        {/* Backdrop overlay */}
        <motion.div
          initial={{ opacity: 0 }}
          animate={{ opacity: 1 }}
          exit={{ opacity: 0 }}
          onClick={handleClose}
          className="fixed inset-0 bg-slate-900/60 backdrop-blur-md transition-opacity"
        />

        {/* Modal Floating Card */}
        <motion.div
          initial={{ opacity: 0, scale: 0.95, y: 20 }}
          animate={{ opacity: 1, scale: 1, y: 0 }}
          exit={{ opacity: 0, scale: 0.95, y: 20 }}
          transition={{ type: 'spring', damping: 25, stiffness: 300 }}
          className="relative w-full max-w-md overflow-hidden rounded-3xl bg-white/92 backdrop-blur-xl border border-emerald-100/80 p-6 sm:p-8 shadow-[0_25px_60px_-15px_rgba(0,92,43,0.25)] z-10 text-gray-900"
        >
          {/* Top Decorative Ambient Light */}
          <div className="absolute -top-24 -right-24 w-48 h-48 bg-[#005C2B]/15 rounded-full blur-2xl pointer-events-none" />

          {/* Close Button */}
          <button
            onClick={handleClose}
            className="absolute top-5 right-5 p-2 rounded-full text-gray-400 hover:text-gray-600 hover:bg-gray-100/80 transition-colors cursor-pointer"
            aria-label="Close Modal"
          >
            <X className="w-5 h-5" />
          </button>

          {!isSubmitted ? (
            <div>
              {/* Badge */}
              <div className="inline-flex items-center gap-1.5 bg-[#e2f4e8] px-3 py-1 rounded-full text-[11px] font-bold text-[#005C2B] mb-4 border border-[#c4ebcf]">
                <Sparkles className="w-3.5 h-3.5" />
                <span>Account Recovery</span>
              </div>

              {/* Title & Description */}
              <h3 className="text-2xl font-black text-gray-900 tracking-tight mb-2">
                Reset Password
              </h3>
              <p className="text-sm font-semibold text-gray-600 mb-6 leading-relaxed">
                Enter your registered email address and we'll send you instructions to safely reset your password.
              </p>

              {/* Reset Form */}
              <form onSubmit={handleSubmit(onSubmit)} className="space-y-4">
                <div>
                  <label className="block text-xs font-bold text-gray-800 uppercase tracking-wider mb-2">
                    Email Address
                  </label>
                  <div className="relative">
                    <div className="absolute inset-y-0 left-0 pl-3.5 flex items-center pointer-events-none text-gray-400">
                      <Mail className="w-4 h-4" />
                    </div>
                    <input
                      {...register('email')}
                      type="email"
                      placeholder="alex@ecopulse.ai"
                      className={`w-full pl-10 pr-4 py-3 rounded-xl border text-sm font-medium transition-all outline-none bg-white/90 ${
                        errors.email
                          ? 'border-red-400 focus:ring-4 focus:ring-red-100'
                          : 'border-gray-300 focus:border-[#005C2B] focus:ring-4 focus:ring-[#005C2B]/10'
                      }`}
                    />
                  </div>
                  {errors.email && (
                    <p className="mt-1.5 text-xs font-bold text-red-500 flex items-center gap-1">
                      <ShieldAlert className="w-3.5 h-3.5" />
                      {errors.email.message}
                    </p>
                  )}
                </div>

                {/* Submit Button */}
                <motion.button
                  whileHover={{ scale: 1.01 }}
                  whileTap={{ scale: 0.98 }}
                  type="submit"
                  disabled={isSubmitting}
                  className="w-full py-3.5 px-4 rounded-xl bg-gradient-to-r from-[#005C2B] to-[#007a33] text-white text-sm font-bold shadow-[0_10px_25px_-5px_rgba(0,92,43,0.35)] hover:from-[#004821] hover:to-[#005C2B] transition-all flex items-center justify-center gap-2 cursor-pointer disabled:opacity-70"
                >
                  {isSubmitting ? (
                    <div className="w-5 h-5 border-2 border-white border-t-transparent rounded-full animate-spin" />
                  ) : (
                    'Send Reset Link'
                  )}
                </motion.button>
              </form>

              {/* Back to Login Link */}
              <div className="mt-6 pt-4 border-t border-gray-100 text-center">
                <button
                  type="button"
                  onClick={onBackToLogin || handleClose}
                  className="inline-flex items-center gap-2 text-xs font-bold text-[#005C2B] hover:underline cursor-pointer"
                >
                  <ArrowLeft className="w-3.5 h-3.5" />
                  Back to Sign In
                </button>
              </div>
            </div>
          ) : (
            <motion.div
              initial={{ opacity: 0, scale: 0.9 }}
              animate={{ opacity: 1, scale: 1 }}
              className="text-center py-4 space-y-4"
            >
              <div className="w-16 h-16 bg-[#e2f4e8] rounded-full flex items-center justify-center text-[#005C2B] mx-auto shadow-xs border border-[#c4ebcf]">
                <CheckCircle2 className="w-8 h-8" />
              </div>
              <h3 className="text-xl font-black text-gray-900">Check Your Inbox</h3>
              <p className="text-xs font-semibold text-gray-600 leading-relaxed max-w-xs mx-auto">
                We've dispatched a password reset link to your email. Click the link to set up your new credentials.
              </p>

              <button
                onClick={handleClose}
                className="mt-4 px-6 py-2.5 bg-[#005C2B] text-white text-xs font-bold rounded-xl shadow-xs hover:bg-[#004821] transition-all cursor-pointer"
              >
                Done
              </button>
            </motion.div>
          )}
        </motion.div>
      </div>
    </AnimatePresence>
  );
};

export default ForgotPasswordModal;
