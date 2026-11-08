import React, { useState, useEffect } from 'react';
import { motion, AnimatePresence } from 'framer-motion';
import { User, Mail, Phone, ShieldCheck, CheckCircle2, ShieldAlert, ArrowRight, Sparkles, UserCheck, ArrowLeft, RefreshCw, Info } from 'lucide-react';
import { sendOtp, registerWithOtp } from '../../services/authService';
import OtpInput from './OtpInput';

const SignupForm = ({ onSwitchToLogin, onRoleChange, onSuccess }) => {
  const [step, setStep] = useState('DETAILS'); // 'DETAILS' | 'OTP'
  const [fullName, setFullName] = useState('');
  const [phone, setPhone] = useState('');
  const [email, setEmail] = useState('');
  const [acceptTerms, setAcceptTerms] = useState(false);
  const [otp, setOtp] = useState('');
  const [cooldown, setCooldown] = useState(0);
  const [timer, setTimer] = useState(300);

  const [isSubmitting, setIsSubmitting] = useState(false);
  const [authSuccess, setAuthSuccess] = useState(false);
  const [serverError, setServerError] = useState('');
  const [infoMsg, setInfoMsg] = useState('');
  const [accountExists, setAccountExists] = useState(false);

  // Cooldown timer
  useEffect(() => {
    let interval = null;
    if (cooldown > 0) {
      interval = setInterval(() => {
        setCooldown((prev) => (prev > 1 ? prev - 1 : 0));
      }, 1000);
    }
    return () => clearInterval(interval);
  }, [cooldown]);

  // Expiration countdown
  useEffect(() => {
    let interval = null;
    if (step === 'OTP' && timer > 0) {
      interval = setInterval(() => {
        setTimer((prev) => (prev > 1 ? prev - 1 : 0));
      }, 1000);
    }
    return () => clearInterval(interval);
  }, [step, timer]);

  const cleanPhone = (val) => val.replace(/\D/g, '').slice(0, 10);

  const handleRequestOtp = async (e) => {
    e.preventDefault();
    setServerError('');
    setInfoMsg('');
    setAccountExists(false);

    if (!fullName.trim() || fullName.trim().length < 2) {
      setServerError('Please enter your full name (minimum 2 characters)');
      return;
    }

    const cleaned = cleanPhone(phone);
    if (!cleaned || cleaned.length !== 10) {
      setServerError('Please enter a valid 10-digit Indian mobile number');
      return;
    }
    if (!/^[6-9]/.test(cleaned)) {
      setServerError('Indian mobile numbers must begin with 6, 7, 8, or 9');
      return;
    }

    if (email.trim() && !/^[^\s@]+@[^\s@]+\.[^\s@]+$/.test(email.trim())) {
      setServerError('Please enter a valid email address or leave it blank');
      return;
    }

    if (!acceptTerms) {
      setServerError('Please accept the Terms & Privacy policy to proceed');
      return;
    }

    setIsSubmitting(true);
    try {
      const res = await sendOtp({ phone: cleaned, purpose: 'register' });
      setStep('OTP');
      setOtp('');
      setCooldown(res.cooldown_seconds || 60);
      setTimer(res.expires_in || 300);
      setInfoMsg(res.message || `OTP dispatched to +91 ******${cleaned.slice(-4)}`);
    } catch (err) {
      const msg = err.message || 'Failed to dispatch verification code';
      setServerError(msg);
      if (msg.toLowerCase().includes('already registered')) {
        setAccountExists(true);
      }
    } finally {
      setIsSubmitting(false);
    }
  };

  const handleVerifyAndRegister = async (e) => {
    e.preventDefault();
    if (!otp || otp.length !== 6) {
      setServerError('Please enter the complete 6-digit verification code');
      return;
    }

    setServerError('');
    setIsSubmitting(true);

    try {
      const cleaned = cleanPhone(phone);
      const res = await registerWithOtp({
        fullName: fullName.trim(),
        phone: cleaned,
        email: email.trim() || null,
        otp
      });

      setAuthSuccess(true);
      setTimeout(() => {
        if (onSuccess) {
          onSuccess(res?.user || { full_name: fullName, phone: cleaned, role: 'citizen' });
        }
      }, 700);
    } catch (err) {
      setServerError(err.message || 'Registration failed. Please check the OTP code.');
    } finally {
      setIsSubmitting(false);
    }
  };

  const handleResendOtp = async () => {
    if (cooldown > 0 || isSubmitting) return;
    setServerError('');
    setIsSubmitting(true);
    try {
      const cleaned = cleanPhone(phone);
      const res = await sendOtp({ phone: cleaned, purpose: 'register' });
      setCooldown(res.cooldown_seconds || 60);
      setTimer(res.expires_in || 300);
      setInfoMsg(`New code sent to +91 ******${cleaned.slice(-4)}`);
    } catch (err) {
      setServerError(err.message || 'Failed to resend OTP.');
    } finally {
      setIsSubmitting(false);
    }
  };

  const formatTimer = (seconds) => {
    const mins = Math.floor(seconds / 60);
    const secs = seconds % 60;
    return `${mins}:${secs < 10 ? '0' : ''}${secs}`;
  };

  return (
    <div className="w-full text-gray-900">
      {/* Pill Badge */}
      <div className="flex justify-center sm:justify-start mb-2">
        <div className="inline-flex items-center gap-1.5 bg-[#e2f4e8]/90 backdrop-blur-xs px-3 py-1 rounded-full text-[11px] font-bold text-[#005C2B] tracking-wide border border-[#c4ebcf] shadow-2xs">
          <Sparkles className="w-3 h-3 text-[#005C2B]" />
          <span>EcoPulse AI Dhule</span>
          <span className="text-[#005C2B] font-bold">•</span>
          <span>Citizen Registration</span>
        </div>
      </div>

      {/* Form Heading & Subtitle */}
      <div className="text-center sm:text-left mb-3">
        <h2 className="text-xl sm:text-2xl font-black text-[#101828] tracking-tight leading-tight">
          {step === 'DETAILS' ? 'Create Citizen Account' : 'Verify Mobile Number'}
        </h2>
        <p className="text-[11px] sm:text-xs font-semibold text-gray-600 mt-0.5 leading-relaxed">
          {step === 'DETAILS'
            ? 'Enter your name and mobile number. Email is optional.'
            : `Enter the 6-digit OTP code sent to +91 ******${cleanPhone(phone).slice(-4)}`}
        </p>
      </div>

      {/* Server Error Alert */}
      <AnimatePresence>
        {serverError && (
          <motion.div
            initial={{ opacity: 0, height: 0 }}
            animate={{ opacity: 1, height: 'auto' }}
            exit={{ opacity: 0, height: 0 }}
            className="p-2.5 rounded-xl bg-red-50 border border-red-200 text-red-700 text-xs font-bold flex items-start gap-2 mb-3"
          >
            <ShieldAlert className="w-4 h-4 shrink-0 text-red-600 mt-0.5" />
            <div className="flex-1">
              <span>{serverError}</span>
              {accountExists && (
                <button
                  type="button"
                  onClick={onSwitchToLogin}
                  className="block mt-1 font-black text-[#005C2B] underline cursor-pointer"
                >
                  Click here to Sign In with this number →
                </button>
              )}
            </div>
          </motion.div>
        )}

        {infoMsg && !serverError && (
          <motion.div
            initial={{ opacity: 0, height: 0 }}
            animate={{ opacity: 1, height: 'auto' }}
            exit={{ opacity: 0, height: 0 }}
            className="p-2.5 rounded-xl bg-emerald-50 border border-emerald-200 text-emerald-800 text-xs font-bold flex items-center gap-2 mb-3"
          >
            <CheckCircle2 className="w-4 h-4 shrink-0 text-emerald-600" />
            <span>{infoMsg}</span>
          </motion.div>
        )}
      </AnimatePresence>

      {/* STEP 1: Personal Details */}
      {step === 'DETAILS' ? (
        <form onSubmit={handleRequestOtp} className="space-y-3">
          {/* Full Name (Required) */}
          <div>
            <label className="block text-[11px] font-bold text-gray-800 uppercase tracking-wider mb-1">
              Full Name <span className="text-red-500">*</span>
            </label>
            <div className="relative">
              <div className="absolute inset-y-0 left-0 pl-3 flex items-center pointer-events-none text-gray-400">
                <User className="w-3.5 h-3.5" />
              </div>
              <input
                type="text"
                value={fullName}
                onChange={(e) => setFullName(e.target.value)}
                placeholder="Priya Patil"
                required
                className="w-full pl-9 pr-3 py-2 rounded-xl border border-gray-300 focus:border-[#005C2B] focus:ring-2 focus:ring-[#005C2B]/10 text-xs font-medium transition-all outline-none bg-white/90"
              />
            </div>
          </div>

          {/* Mobile Phone Number (Required & Primary) */}
          <div>
            <label className="block text-[11px] font-bold text-gray-800 uppercase tracking-wider mb-1">
              Mobile Phone Number <span className="text-red-500">*</span>
            </label>
            <div className="relative flex items-center border border-gray-300 rounded-xl overflow-hidden bg-white/90 focus-within:border-[#005C2B] focus-within:ring-2 focus-within:ring-[#005C2B]/10 transition-all">
              <div className="pl-3 pr-2 py-2 flex items-center gap-1.5 border-r border-gray-200 text-gray-700 font-bold text-xs shrink-0 select-none">
                <span className="text-sm">🇮🇳</span>
                <span>+91</span>
              </div>
              <input
                type="tel"
                inputMode="numeric"
                value={phone}
                onChange={(e) => setPhone(cleanPhone(e.target.value))}
                placeholder="98765 43210"
                maxLength={10}
                required
                className="w-full px-3 py-2 text-xs font-bold tracking-wide outline-none bg-transparent text-gray-900"
              />
            </div>
            <p className="mt-0.5 text-[10px] text-gray-500 font-medium">
              We'll send an OTP to verify your ownership of this mobile number.
            </p>
          </div>

          {/* Email Address (Optional) */}
          <div>
            <div className="flex items-center justify-between mb-1">
              <label className="block text-[11px] font-bold text-gray-800 uppercase tracking-wider">
                Email Address
              </label>
              <span className="text-[10px] font-bold text-gray-400 uppercase tracking-wider">Optional</span>
            </div>
            <div className="relative">
              <div className="absolute inset-y-0 left-0 pl-3 flex items-center pointer-events-none text-gray-400">
                <Mail className="w-3.5 h-3.5" />
              </div>
              <input
                type="email"
                value={email}
                onChange={(e) => setEmail(e.target.value)}
                placeholder="citizen@dhule.gov.in (optional)"
                className="w-full pl-9 pr-3 py-2 rounded-xl border border-gray-300 focus:border-[#005C2B] focus:ring-2 focus:ring-[#005C2B]/10 text-xs font-medium transition-all outline-none bg-white/90"
              />
            </div>
          </div>

          {/* Terms & Privacy Checkbox */}
          <div className="pt-0.5">
            <label className="flex items-start gap-2 cursor-pointer text-xs font-bold text-gray-700 select-none">
              <input
                type="checkbox"
                checked={acceptTerms}
                onChange={(e) => setAcceptTerms(e.target.checked)}
                className="mt-0.5 w-3.5 h-3.5 rounded border-gray-300 text-[#005C2B] focus:ring-[#005C2B]/30 cursor-pointer accent-[#005C2B]"
              />
              <span className="leading-tight text-[11px] font-semibold text-gray-600">
                I agree to EcoPulse AI's{' '}
                <a href="#terms" className="text-[#005C2B] font-bold underline">Terms & Privacy Policy</a> (DPDP Act 2023).
              </span>
            </label>
          </div>

          {/* Submit Button */}
          <motion.button
            whileHover={{ scale: 1.01 }}
            whileTap={{ scale: 0.98 }}
            type="submit"
            disabled={isSubmitting || !fullName || phone.length !== 10 || !acceptTerms}
            className="w-full mt-2 py-2.5 px-4 rounded-xl bg-gradient-to-r from-[#005C2B] to-[#007a33] text-white text-xs font-bold shadow-xs hover:from-[#004821] hover:to-[#005C2B] transition-all flex items-center justify-center gap-2 cursor-pointer disabled:opacity-50 min-h-[42px]"
          >
            {isSubmitting ? (
              <div className="flex items-center gap-2">
                <RefreshCw className="w-3.5 h-3.5 animate-spin" />
                <span>Sending OTP...</span>
              </div>
            ) : (
              <div className="flex items-center gap-1.5">
                <span>Continue & Verify Mobile</span>
                <ArrowRight className="w-3.5 h-3.5" />
              </div>
            )}
          </motion.button>
        </form>
      ) : (
        /* STEP 2: OTP Verification & Completion */
        <form onSubmit={handleVerifyAndRegister} className="space-y-3">
          <div className="flex items-center justify-between text-xs p-2 rounded-xl bg-emerald-50/60 border border-emerald-100">
            <div>
              <div className="text-[10px] text-gray-500 font-bold uppercase tracking-wider">Verifying Phone</div>
              <div className="font-extrabold text-gray-800 text-xs">+91 {cleanPhone(phone)}</div>
            </div>
            <button
              type="button"
              onClick={() => {
                setStep('DETAILS');
                setOtp('');
                setServerError('');
              }}
              className="text-[#005C2B] font-extrabold text-xs hover:underline flex items-center gap-1 cursor-pointer"
            >
              <ArrowLeft className="w-3 h-3" />
              <span>Edit Details</span>
            </button>
          </div>

          <div>
            <label className="block text-[11px] font-bold text-gray-800 text-center mb-1">
              Enter 6-Digit Verification Code
            </label>
            <OtpInput
              value={otp}
              onChange={(val) => {
                setOtp(val);
                if (val.length === 6) setServerError('');
              }}
              disabled={isSubmitting || authSuccess}
            />
            <div className="flex items-center justify-between text-[11px] text-gray-500 font-semibold mt-1">
              <span>Code expires in: <strong className="text-gray-700">{formatTimer(timer)}</strong></span>
              {cooldown > 0 ? (
                <span className="text-gray-400">Resend in {cooldown}s</span>
              ) : (
                <button
                  type="button"
                  onClick={handleResendOtp}
                  disabled={isSubmitting}
                  className="text-[#005C2B] font-extrabold hover:underline cursor-pointer"
                >
                  Resend OTP
                </button>
              )}
            </div>
          </div>

          <motion.button
            whileHover={{ scale: 1.01 }}
            whileTap={{ scale: 0.98 }}
            type="submit"
            disabled={isSubmitting || authSuccess || otp.length !== 6}
            className="w-full mt-2 py-2.5 px-4 rounded-xl bg-gradient-to-r from-[#005C2B] to-[#007a33] text-white text-xs font-bold shadow-xs hover:from-[#004821] hover:to-[#005C2B] transition-all flex items-center justify-center gap-2 cursor-pointer disabled:opacity-50 min-h-[42px]"
          >
            {authSuccess ? (
              <div className="flex items-center gap-1.5 text-white font-black text-xs">
                <CheckCircle2 className="w-4 h-4 text-emerald-300" />
                <span>Account Created! Redirecting...</span>
              </div>
            ) : isSubmitting ? (
              <div className="flex items-center gap-2">
                <RefreshCw className="w-3.5 h-3.5 animate-spin" />
                <span>Creating Account...</span>
              </div>
            ) : (
              <div className="flex items-center gap-1.5">
                <ShieldCheck className="w-4 h-4" />
                <span>Verify & Complete Registration</span>
              </div>
            )}
          </motion.button>
        </form>
      )}

      {/* Driver/Admin Provisioning Notice */}
      <div className="mt-4 p-2.5 rounded-xl bg-slate-50 border border-slate-200/80 flex items-start gap-2 text-slate-600">
        <Info className="w-3.5 h-3.5 shrink-0 text-slate-400 mt-0.5" />
        <p className="text-[10px] font-medium leading-relaxed">
          Municipal staff (Drivers and Admins) accounts are provisioned by the Dhule Municipal Administration. Public registration is for Citizens only.
        </p>
      </div>

      {/* Switch Link to Login */}
      <div className="mt-3 pt-2 border-t border-gray-200/60 text-center">
        <p className="text-xs font-semibold text-gray-600">
          Already have an account?{' '}
          <button
            type="button"
            onClick={onSwitchToLogin}
            className="font-extrabold text-[#005C2B] hover:underline cursor-pointer ml-0.5"
          >
            Sign In Instead →
          </button>
        </p>
      </div>
    </div>
  );
};

export default SignupForm;
