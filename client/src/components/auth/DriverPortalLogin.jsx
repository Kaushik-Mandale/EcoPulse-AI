import React, { useState } from 'react';
import { motion } from 'framer-motion';
import { User, Lock, Eye, EyeOff, ChevronRight, Headphones, CheckCircle2, ShieldAlert } from 'lucide-react';
import { loginUser } from '../../services/authService';
import api from '../../services/api';
import { isStrongOnboardingPassword, ONBOARDING_PASSWORD_REQUIREMENTS } from '../../utils/passwordStrength';

const DriverPortalLogin = ({ onSuccess, onOpenForgotPassword }) => {
  const [identifier, setIdentifier] = useState('');
  const [password, setPassword] = useState('');
  const [showPassword, setShowPassword] = useState(false);
  const [rememberMe, setRememberMe] = useState(true);
  const [isSubmitting, setIsSubmitting] = useState(false);
  const [authSuccess, setAuthSuccess] = useState(false);
  const [errorMsg, setErrorMsg] = useState('');
  const [phoneVerificationRequired, setPhoneVerificationRequired] = useState(false);
  const [phoneChallengeId, setPhoneChallengeId] = useState('');
  const [phoneOtp, setPhoneOtp] = useState('');
  const [rotationRequired, setRotationRequired] = useState(false);
  const [newPassword, setNewPassword] = useState('');
  const [confirmNewPassword, setConfirmNewPassword] = useState('');

  const handleSubmit = async (e) => {
    e.preventDefault();
    setErrorMsg('');

    if (!identifier.trim() || !password) {
      setErrorMsg('Employee ID and password are required');
      return;
    }

    setIsSubmitting(true);

    try {
      const result = await loginUser({ email: identifier.trim(), password, role: 'driver', rememberMe });
      if (!result?.user?.role) throw new Error('The authenticated account role could not be verified. Please sign in again.');
      setAuthSuccess(true);
      setTimeout(() => {
        if (onSuccess) {
          onSuccess(result.user);
        }
      }, 700);
    } catch (err) {
      if (err.code === 'PHONE_VERIFICATION_REQUIRED') {
        setPhoneVerificationRequired(true);
        setErrorMsg('Verify your registered mobile number before continuing.');
        return;
      }
      if (err.code === 'PASSWORD_CHANGE_REQUIRED') {
        setRotationRequired(true);
        setErrorMsg('Change your temporary password before continuing.');
        return;
      }
      if (err.code === 'TEMPORARY_CREDENTIAL_EXPIRED') {
        setErrorMsg('This temporary password has expired. Contact your municipal administrator for a reset.');
        return;
      }
      setErrorMsg(err.message || 'Invalid Employee ID/Credentials or Password');
    } finally {
      setIsSubmitting(false);
    }
  };

  const sendPhoneVerification = async () => {
    setErrorMsg('');
    setIsSubmitting(true);
    try {
      const { data } = await api.post('/auth/drivers/phone-verification/send', {
        login_id: identifier.trim(), password
      });
      setPhoneChallengeId(data.challenge_id);
      setErrorMsg('A verification code was sent to your registered mobile number.');
    } catch (error) {
      setErrorMsg(error.response?.data?.detail || 'Mobile verification could not be started.');
    } finally {
      setIsSubmitting(false);
    }
  };

  const confirmPhoneVerification = async () => {
    setErrorMsg('');
    setIsSubmitting(true);
    try {
      await api.post('/auth/drivers/phone-verification/confirm', {
        login_id: identifier.trim(), password, otp: phoneOtp, challenge_id: phoneChallengeId
      });
      setPhoneVerificationRequired(false);
      setPhoneChallengeId('');
      setPhoneOtp('');
      setErrorMsg('Mobile verified. Sign in again to rotate your temporary password.');
    } catch (error) {
      setErrorMsg(error.response?.data?.detail || 'Mobile verification failed or expired.');
    } finally {
      setIsSubmitting(false);
    }
  };

  const changeInitialPassword = async () => {
    setErrorMsg('');
    if (!isStrongOnboardingPassword(newPassword) || newPassword !== confirmNewPassword) {
      setErrorMsg('Choose a strong password that meets the requirements and confirm it.');
      return;
    }
    setIsSubmitting(true);
    try {
      await api.post('/auth/initial-password/change', {
        login_id: identifier.trim(), current_password: password, new_password: newPassword
      });
      setPassword(newPassword);
      setNewPassword('');
      setConfirmNewPassword('');
      setRotationRequired(false);
      setErrorMsg('Temporary password changed. Sign in to continue.');
    } catch (error) {
      setErrorMsg(error.response?.data?.detail || 'Password change could not be completed.');
    } finally {
      setIsSubmitting(false);
    }
  };

  return (
    <div className="bg-white rounded-[24px] sm:rounded-[28px] p-4 sm:p-6 shadow-xl border border-slate-200/90 relative overflow-hidden flex flex-col justify-between h-full hover:shadow-2xl transition-shadow duration-300">
      {/* Top Accent Line */}
      <div className="absolute top-0 inset-x-0 h-1.5 bg-[#2563eb]" />

      <div>
        {/* Logo Header */}
        <div className="text-center mb-2.5 sm:mb-3">
          <div className="flex items-center justify-center gap-1.5 sm:gap-2 mb-1">
            <div className="w-7 sm:w-8 h-7 sm:h-8 rounded-full bg-[#16a34a] text-white flex items-center justify-center p-1.5 shadow-xs">
              <svg className="w-full h-full fill-current" viewBox="0 0 24 24">
                <path d="M20 8h-3V4H3c-1.1 0-2 .9-2 2v11h2c0 1.66 1.34 3 3 3s3-1.34 3-3h6c0 1.66 1.34 3 3 3s3-1.34 3-3h2v-5l-3-4zM6 18.5c-.83 0-1.5-.67-1.5-1.5s.67-1.5 1.5-1.5 1.5.67 1.5 1.5-.67 1.5-1.5 1.5zm13.5-9l1.96 2.5H17V9.5h2.5zm-1.5 9c-.83 0-1.5-.67-1.5-1.5s.67-1.5 1.5-1.5 1.5.67 1.5 1.5-.67 1.5-1.5 1.5z" />
              </svg>
            </div>
            <span className="text-lg sm:text-xl font-black text-[#16a34a] tracking-tight">EcoPulse AI</span>
          </div>
          <div className="text-[11px] sm:text-xs font-bold text-slate-700 tracking-wide">
            EcoPulse AI | <span className="text-[#16a34a]">चालक</span>
          </div>
          <div className="text-[10px] font-bold text-[#16a34a] mt-0.5">
            🌱 एकत्र येऊ, स्वच्छ शहर घडवू. 🌱
          </div>
        </div>

        {/* Portal Title & Subtitle */}
        <div className="text-center mb-2.5">
          <h3 className="text-xl sm:text-2xl font-extrabold text-[#2563eb] tracking-tight">
            Field Operations Portal · Driver
          </h3>
          <p className="text-[11px] sm:text-xs font-semibold text-slate-600 mt-0.5">
            View your routes, tasks and complete your duty.
          </p>
        </div>

        {/* Hero Illustration */}
        <div className="relative w-full h-32 sm:h-36 rounded-2xl overflow-hidden border border-blue-100 mb-3 sm:mb-3.5 bg-gradient-to-b from-[#eff6ff] to-blue-50 flex items-center justify-center shadow-2xs p-2">
          <img
            src="/ChatGPT Image Aug 5, 2026, 01_06_02 PM.png"
            alt="Driver Portal Illustration"
            className="w-full h-full object-contain object-center drop-shadow-xs"
          />
        </div>

        {/* Form Fields */}
        <form onSubmit={handleSubmit} className="space-y-2.5 sm:space-y-3">
          {errorMsg && (
            <div className="p-2 rounded-xl bg-red-50 border border-red-200 text-red-700 text-xs font-bold flex items-center gap-1.5">
              <ShieldAlert className="w-4 h-4 shrink-0 text-red-600" />
              <span>{errorMsg}</span>
            </div>
          )}

          <div>
            <label className="block text-[11px] sm:text-xs font-bold text-slate-700 mb-1">Employee ID or Login ID</label>
            <div className="relative flex items-center border border-slate-300 rounded-xl bg-slate-50/80 focus-within:bg-white focus-within:border-[#2563eb] focus-within:ring-2 focus-within:ring-blue-100 transition-all">
              <div className="pl-3.5 text-slate-400"><User className="w-4 h-4" /></div>
              <input
                type="text"
                value={identifier}
                onChange={(e) => setIdentifier(e.target.value)}
                placeholder="Enter your municipal login ID"
                autoComplete="username"
                className="w-full pl-2.5 pr-4 py-2 sm:py-2.5 text-xs font-semibold outline-none bg-transparent text-slate-800 placeholder:text-slate-400"
              />
            </div>
          </div>

          {phoneVerificationRequired && (
            <div className="space-y-2 rounded-xl border border-blue-200 bg-blue-50 p-3">
              <p className="text-xs font-semibold text-blue-900">Step 2 of 2 · Verify the mobile number registered to this Driver account. Codes expire and can be used once.</p>
              {!phoneChallengeId ? <button type="button" onClick={sendPhoneVerification} disabled={isSubmitting}
                className="rounded-lg bg-blue-700 px-3 py-2 text-xs font-bold text-white disabled:opacity-50">{isSubmitting ? 'Sending…' : 'Send mobile verification code'}</button> : <>
                <input aria-label="Mobile verification code" inputMode="numeric" autoComplete="one-time-code" maxLength={6} value={phoneOtp}
                  onChange={(event) => setPhoneOtp(event.target.value.replace(/\D/g, ''))} placeholder="6-digit code"
                  className="w-full rounded-lg border border-slate-300 bg-white px-3 py-2 text-sm" />
                <button type="button" onClick={confirmPhoneVerification} disabled={isSubmitting || phoneOtp.length !== 6}
                  className="rounded-lg bg-blue-700 px-3 py-2 text-xs font-bold text-white disabled:opacity-50">{isSubmitting ? 'Verifying…' : 'Verify mobile'}</button>
                <button type="button" onClick={sendPhoneVerification} disabled={isSubmitting}
                  className="ml-2 rounded-lg border border-blue-300 px-3 py-2 text-xs font-bold text-blue-900 disabled:opacity-50">Request a new code</button>
              </>}
            </div>
          )}

          {rotationRequired && (
            <div className="space-y-2 rounded-xl border border-amber-200 bg-amber-50 p-3">
              <p className="text-xs font-semibold text-amber-900">Step 1 of 2 · Change your one-time password before mobile verification.</p>
              <input type="password" autoComplete="new-password" value={newPassword} onChange={(event) => setNewPassword(event.target.value)} placeholder="New password (12+ characters)" className="w-full rounded-lg border border-slate-300 bg-white px-3 py-2 text-sm" />
              <p className="text-[11px] text-amber-900">{ONBOARDING_PASSWORD_REQUIREMENTS}</p>
              <input type="password" autoComplete="new-password" value={confirmNewPassword} onChange={(event) => setConfirmNewPassword(event.target.value)} placeholder="Confirm new password" className="w-full rounded-lg border border-slate-300 bg-white px-3 py-2 text-sm" />
            </div>
          )}
          <div>
            <label className="block text-[11px] sm:text-xs font-bold text-slate-700 mb-1">Password</label>
            <div className="relative flex items-center border border-slate-300 rounded-xl bg-slate-50/80 focus-within:bg-white focus-within:border-[#2563eb] focus-within:ring-2 focus-within:ring-blue-100 transition-all">
              <div className="pl-3.5 text-slate-400"><Lock className="w-4 h-4" /></div>
              <input
                type={showPassword ? 'text' : 'password'}
                value={password}
                onChange={(e) => setPassword(e.target.value)}
                placeholder="Enter your password"
                autoComplete="current-password"
                className="w-full pl-2.5 pr-10 py-2 sm:py-2.5 text-xs font-semibold outline-none bg-transparent text-slate-800 placeholder:text-slate-400"
              />
              <button
                type="button"
                onClick={() => setShowPassword(!showPassword)}
                className="absolute right-3 text-slate-400 hover:text-slate-600 cursor-pointer"
                aria-label={showPassword ? 'Hide password' : 'Show password'}
              >
                {showPassword ? <EyeOff className="w-4 h-4" /> : <Eye className="w-4 h-4" />}
              </button>
            </div>
          </div>

          {/* Remember me and password recovery */}
          <div className="flex items-center justify-between text-[11px] sm:text-xs pt-0.5">
            <label className="flex items-center gap-1.5 cursor-pointer font-bold text-slate-600 select-none">
              <input
                type="checkbox"
                checked={rememberMe}
                onChange={(e) => setRememberMe(e.target.checked)}
                className="w-3.5 h-3.5 rounded border-slate-300 text-[#2563eb] focus:ring-blue-200 accent-[#2563eb] cursor-pointer"
              />
              <span>Remember me</span>
            </label>

            <button type="button" onClick={onOpenForgotPassword} className="font-bold text-[#2563eb] hover:underline cursor-pointer">
              Forgot Password?
            </button>
          </div>

          {/* Primary Submit Button */}
          <motion.button
            whileHover={{ scale: 1.01 }}
            whileTap={{ scale: 0.98 }}
            type={rotationRequired ? 'button' : 'submit'}
            onClick={rotationRequired ? changeInitialPassword : undefined}
            disabled={isSubmitting || authSuccess}
            className="w-full py-2.5 sm:py-3 px-4 rounded-xl bg-[#2563eb] hover:bg-[#1d4ed8] text-white font-extrabold text-xs sm:text-sm shadow-md transition-all flex items-center justify-center gap-2 cursor-pointer mt-2 disabled:opacity-80 min-h-[42px]"
          >
            {authSuccess ? (
              <span className="flex items-center gap-1.5 text-white">
                <CheckCircle2 className="w-4 h-4 text-blue-200" />
                Signed In!
              </span>
            ) : isSubmitting ? (
              <span>Authenticating...</span>
            ) : (
              <>
                <span>{rotationRequired ? 'Change temporary password' : 'Login'}</span>
                <ChevronRight className="w-4 h-4" />
              </>
            )}
          </motion.button>
        </form>

        {/* Need Help Support Card */}
        <div className="mt-3 sm:mt-3.5">
          <button
            type="button"
            onClick={() => alert('Driver Helpline: 1800-ECOPULSE-DRIVER')}
            className="w-full p-2.5 sm:p-3 rounded-2xl bg-[#eff6ff] border border-blue-200/80 hover:bg-blue-100/60 flex items-center justify-between transition-all group cursor-pointer"
          >
            <div className="flex items-center gap-2.5 sm:gap-3">
              <div className="w-7 sm:w-8 h-7 sm:h-8 rounded-full bg-[#2563eb] text-white flex items-center justify-center shrink-0 shadow-xs">
                <Headphones className="w-3.5 sm:w-4 h-3.5 sm:h-4" />
              </div>
              <div className="text-left">
                <div className="text-xs font-bold text-[#2563eb]">Need Help?</div>
                <div className="text-[10px] sm:text-[11px] font-semibold text-slate-600">Contact Support</div>
              </div>
            </div>
            <ChevronRight className="w-4 h-4 text-[#2563eb] group-hover:translate-x-0.5 transition-transform shrink-0" />
          </button>
        </div>
      </div>

      {/* Decorative Bottom Line */}
      <div className="mt-4 pt-2 border-t border-blue-100 flex items-center justify-between text-[10px] text-blue-800/70 font-bold">
        <span>🚛 Route Logistics</span>
        <span>EcoPulse AI 2026</span>
      </div>
    </div>
  );
};

export default DriverPortalLogin;
