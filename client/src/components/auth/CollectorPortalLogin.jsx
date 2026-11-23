import React, { useState } from 'react';
import { motion } from 'framer-motion';
import { User, Lock, Eye, EyeOff, ChevronRight, Headphones, CheckCircle2, ShieldAlert, Key } from 'lucide-react';
import { loginUser } from '../../services/authService';
import api from '../../services/api';
import { isStrongOnboardingPassword, ONBOARDING_PASSWORD_REQUIREMENTS } from '../../utils/passwordStrength';
import { createMfaQrDataUrl } from '../../utils/mfaQr';

const CollectorPortalLogin = ({ onSuccess, onOpenForgotPassword, defaultRole = 'admin', restrictRole = false, portalTitle = 'Admin Portal' }) => {
  const [identifier, setIdentifier] = useState('');
  const [password, setPassword] = useState('');
  const [requestedRole, setRequestedRole] = useState(defaultRole);
  const [showPassword, setShowPassword] = useState(false);
  const [mfaCode, setMfaCode] = useState('');
  const [rotationRequired, setRotationRequired] = useState(false);
  const [passwordRotated, setPasswordRotated] = useState(false);
  const [newPassword, setNewPassword] = useState('');
  const [confirmNewPassword, setConfirmNewPassword] = useState('');
  const [mfaSetupSecret, setMfaSetupSecret] = useState('');
  const [mfaSetupQr, setMfaSetupQr] = useState('');
  const [mfaSetupBusy, setMfaSetupBusy] = useState(false);
  const [rememberMe, setRememberMe] = useState(true);
  const [isSubmitting, setIsSubmitting] = useState(false);
  const [authSuccess, setAuthSuccess] = useState(false);
  const [errorMsg, setErrorMsg] = useState('');

  const startMfaEnrollment = async () => {
    if (!identifier.trim() || !password) {
      setErrorMsg('Enter your Employee ID or Super Admin Login ID and password to enroll MFA.');
      return;
    }
    setMfaSetupBusy(true);
    setErrorMsg('');
    try {
      const { data } = await api.post('/auth/mfa/enrollment/start', {
        employee_id: identifier.trim(), password
      });
      setMfaSetupSecret(data.secret);
      try {
        setMfaSetupQr(await createMfaQrDataUrl(data.otpauth_uri));
      } catch {
        setErrorMsg('QR display failed. Use the manual authenticator key below to continue.');
      }
    } catch (error) {
      const detail = error.response?.data?.detail;
      if (detail?.code === 'PASSWORD_CHANGE_REQUIRED') {
        setRotationRequired(true);
        setMfaCode('');
        setErrorMsg(detail.message || 'Change the initial password before setting up an authenticator.');
      } else if (detail?.code === 'TEMPORARY_CREDENTIAL_EXPIRED') {
        setErrorMsg(detail.message || 'This temporary password has expired. Contact your Super Admin for a reset.');
      } else {
        setErrorMsg(typeof detail === 'string' ? detail : detail?.message || 'MFA enrollment could not be started.');
      }
    } finally {
      setMfaSetupBusy(false);
    }
  };

  const confirmMfaEnrollment = async () => {
    setMfaSetupBusy(true);
    setErrorMsg('');
    try {
      await api.post('/auth/mfa/enrollment/confirm', {
        employee_id: identifier.trim(), password, code: mfaCode
      });
      setMfaSetupSecret('');
      setMfaSetupQr('');
      setMfaCode('');
      setErrorMsg('Authenticator setup complete. Sign in with a new code.');
    } catch (error) {
      if (error.response?.status === 410) {
        setMfaSetupSecret('');
        setMfaSetupQr('');
        setMfaCode('');
      }
      setErrorMsg(error.response?.data?.detail || 'Authenticator code could not be verified.');
    } finally {
      setMfaSetupBusy(false);
    }
  };

  const handleSubmit = async (e) => {
    e.preventDefault();
    setErrorMsg('');

    if (!identifier.trim() || !password) {
      setErrorMsg('Employee ID or Login ID and password are required');
      return;
    }

    setIsSubmitting(true);

    try {
      const result = await loginUser({
        email: identifier.trim(), password, role: requestedRole, mfa_code: mfaCode, rememberMe
      });
      if (!result?.user?.role) throw new Error('The authenticated account role could not be verified. Please sign in again.');
      setAuthSuccess(true);
      setTimeout(() => {
        if (onSuccess) {
          onSuccess(result.user);
        }
      }, 700);
    } catch (err) {
      if (err.code === 'PASSWORD_CHANGE_REQUIRED') {
        setRotationRequired(true);
        setMfaCode('');
        setErrorMsg('Change the initial password before continuing.');
        return;
      }
      if (err.code === 'TEMPORARY_CREDENTIAL_EXPIRED') {
        setErrorMsg('This temporary password has expired. Contact your Super Admin for a reset.');
        return;
      }
      setErrorMsg(err.message || 'Invalid Employee ID/Credentials or Password');
    } finally {
      setIsSubmitting(false);
    }
  };

  const handleInitialPasswordChange = async (e) => {
    e.preventDefault();
    setErrorMsg('');
    if (!isStrongOnboardingPassword(newPassword) || newPassword !== confirmNewPassword) {
      setErrorMsg('Choose a strong password that meets the requirements and confirm it.');
      return;
    }
    setMfaSetupBusy(true);
    try {
      await api.post('/auth/initial-password/change', {
        login_id: identifier.trim(), current_password: password, new_password: newPassword
      });
      setPassword(newPassword);
      setNewPassword('');
      setConfirmNewPassword('');
      setRotationRequired(false);
      setPasswordRotated(true);
      setErrorMsg('Initial password changed. Set up your authenticator before signing in.');
    } catch (error) {
      setErrorMsg(error.response?.data?.detail || 'Initial password change could not be completed.');
    } finally {
      setMfaSetupBusy(false);
    }
  };

  return (
    <div className="bg-white rounded-[24px] sm:rounded-[28px] p-4 sm:p-6 shadow-xl border border-slate-200/90 relative overflow-hidden flex flex-col justify-between h-full hover:shadow-2xl transition-shadow duration-300">
      {/* Top Accent Line */}
      <div className="absolute top-0 inset-x-0 h-1.5 bg-[#ea580c]" />

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
            EcoPulse AI | <span className="text-[#16a34a]">प्रशासक</span>
          </div>
          <div className="text-[10px] font-bold text-[#16a34a] mt-0.5">
            🌱 एकत्र येऊ, स्वच्छ शहर घडवू. 🌱
          </div>
        </div>

        {/* Portal Title & Subtitle */}
        <div className="text-center mb-2.5">
          <h3 className="text-xl sm:text-2xl font-extrabold text-[#ea580c] tracking-tight">
            {portalTitle}
          </h3>
          <p className="text-[11px] sm:text-xs font-semibold text-slate-600 mt-0.5">
            Municipal employee access requires an authorized account and MFA.
          </p>
        </div>

        {/* Hero Illustration */}
        <div className="relative w-full h-32 sm:h-36 rounded-2xl overflow-hidden border border-orange-100 mb-3 sm:mb-3.5 bg-gradient-to-b from-[#fff7ed] to-orange-50 flex items-center justify-center shadow-2xs p-2">
          <img
            src="/ChatGPT Image Aug 5, 2026, 01_05_55 PM.png"
            alt="Admin Portal Illustration"
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

          {!restrictRole && <div>
            <label className="block text-[11px] sm:text-xs font-bold text-slate-700 mb-1">Municipal account type</label>
            <select
              value={requestedRole}
              onChange={(e) => setRequestedRole(e.target.value)}
              className="w-full rounded-xl border border-slate-300 bg-slate-50/80 px-3 py-2 text-xs font-semibold text-slate-800 outline-none focus:border-[#ea580c]"
            >
              <option value="admin">Administrator</option>
              <option value="collector">Collector</option>
            </select>
          </div>}

          <div>
            <label className="block text-[11px] sm:text-xs font-bold text-slate-700 mb-1">Employee ID or Super Admin Login ID</label>
            <div className="relative flex items-center border border-slate-300 rounded-xl bg-slate-50/80 focus-within:bg-white focus-within:border-[#ea580c] focus-within:ring-2 focus-within:ring-orange-100 transition-all">
              <div className="pl-3.5 text-slate-400"><User className="w-4 h-4" /></div>
              <input
                type="text" value={identifier} onChange={(e) => setIdentifier(e.target.value)}
                placeholder="Enter Employee ID or Login ID" autoComplete="username"
                className="w-full pl-2.5 pr-4 py-2 sm:py-2.5 text-xs font-semibold outline-none bg-transparent text-slate-800 placeholder:text-slate-400"
              />
            </div>
          </div>
          <div>
            <label className="block text-[11px] sm:text-xs font-bold text-slate-700 mb-1">Password</label>
            <div className="relative flex items-center border border-slate-300 rounded-xl bg-slate-50/80 focus-within:bg-white focus-within:border-[#ea580c] focus-within:ring-2 focus-within:ring-orange-100 transition-all">
              <div className="pl-3.5 text-slate-400"><Lock className="w-4 h-4" /></div>
              <input
                type={showPassword ? 'text' : 'password'} value={password}
                onChange={(e) => setPassword(e.target.value)} placeholder="Enter your password"
                autoComplete="current-password"
                className="w-full pl-2.5 pr-10 py-2 sm:py-2.5 text-xs font-semibold outline-none bg-transparent text-slate-800 placeholder:text-slate-400"
              />
              <button type="button" onClick={() => setShowPassword(!showPassword)}
                className="absolute right-3 text-slate-400 hover:text-slate-600 cursor-pointer"
                aria-label={showPassword ? 'Hide password' : 'Show password'}>
                {showPassword ? <EyeOff className="w-4 h-4" /> : <Eye className="w-4 h-4" />}
              </button>
            </div>
          </div>
          {!rotationRequired && <div>
            {passwordRotated && <p className="mb-2 text-xs font-semibold text-orange-900">Step 2 of 2 · Complete authenticator enrollment, then sign in with a current code.</p>}
            <label className="block text-[11px] sm:text-xs font-bold text-slate-700 mb-1">Authenticator code</label>
            <input
              type="text" inputMode="numeric" pattern="[0-9]{6}" maxLength={6}
              value={mfaCode} onChange={(e) => setMfaCode(e.target.value.replace(/\D/g, ''))}
              placeholder="6-digit authenticator code" autoComplete="one-time-code"
              className="w-full border border-slate-300 rounded-xl bg-slate-50/80 px-3 py-2 sm:py-2.5 text-xs font-semibold outline-none focus:bg-white focus:border-[#ea580c] focus:ring-2 focus:ring-orange-100"
            />
            <p className="mt-1 text-[10px] text-slate-500">Municipal employee accounts are provisioned by authorized administrators.</p>
            {!mfaSetupSecret ? (
              <button type="button" onClick={startMfaEnrollment} disabled={mfaSetupBusy}
                className="mt-2 text-[11px] font-bold text-[#ea580c] hover:underline disabled:opacity-50">
                {mfaSetupBusy ? 'Starting…' : 'Set up authenticator'}
              </button>
            ) : (
              <div className="mt-2 space-y-2 rounded-lg border border-orange-200 bg-orange-50 p-3">
                <p className="text-[11px] text-orange-900">Scan this QR code in your authenticator app, or enter the manual key below. Then enter its current 6-digit code to confirm.</p>
                {mfaSetupQr && <img src={mfaSetupQr} alt="Authenticator enrollment QR code" className="mx-auto h-60 w-60 rounded-lg border border-orange-200 bg-white p-2" />}
                <code className="block break-all rounded bg-white p-2 text-xs font-bold">{mfaSetupSecret}</code>
                <button type="button" onClick={confirmMfaEnrollment} disabled={mfaSetupBusy || mfaCode.length !== 6}
                  className="rounded-lg bg-[#ea580c] px-3 py-2 text-xs font-bold text-white disabled:opacity-50">
                  Confirm authenticator
                </button>
              </div>
            )}
          </div>}

          {rotationRequired && (
            <div className="space-y-2 rounded-xl border border-amber-200 bg-amber-50 p-3">
              <p className="text-xs font-semibold text-amber-900">Step 1 of 2 · Rotate the one-time password before authenticator setup.</p>
              <input type="password" autoComplete="new-password" value={newPassword}
                onChange={(e) => setNewPassword(e.target.value)} placeholder="New password (12+ characters)"
                className="w-full border border-slate-300 rounded-xl bg-white px-3 py-2 text-xs" />
              <p className="text-[11px] text-amber-900">{ONBOARDING_PASSWORD_REQUIREMENTS}</p>
              <input type="password" autoComplete="new-password" value={confirmNewPassword}
                onChange={(e) => setConfirmNewPassword(e.target.value)} placeholder="Confirm new password"
                className="w-full border border-slate-300 rounded-xl bg-white px-3 py-2 text-xs" />
            </div>
          )}

          {/* Checkbox & Forgot Password / Resend OTP */}
          <div className="flex items-center justify-between text-[11px] sm:text-xs pt-0.5">
            <label className="flex items-center gap-1.5 cursor-pointer font-bold text-slate-600 select-none">
              <input
                type="checkbox"
                checked={rememberMe}
                onChange={(e) => setRememberMe(e.target.checked)}
                className="w-3.5 h-3.5 rounded border-slate-300 text-[#ea580c] focus:ring-orange-200 accent-[#ea580c] cursor-pointer"
              />
              <span>Remember me</span>
            </label>

            <button
                type="button"
                onClick={onOpenForgotPassword}
                className="font-bold text-[#ea580c] hover:underline cursor-pointer"
              >
                Forgot Password?
            </button>
          </div>

          {/* Primary Submit Button */}
          <motion.button
            whileHover={{ scale: 1.01 }}
            whileTap={{ scale: 0.98 }}
            type={rotationRequired ? 'button' : 'submit'}
            onClick={rotationRequired ? handleInitialPasswordChange : undefined}
            disabled={isSubmitting || authSuccess}
            className="w-full py-2.5 sm:py-3 px-4 rounded-xl bg-[#ea580c] hover:bg-[#c2410c] text-white font-extrabold text-xs sm:text-sm shadow-md transition-all flex items-center justify-center gap-2 cursor-pointer mt-2 disabled:opacity-80 min-h-[42px]"
          >
            {authSuccess ? (
              <span className="flex items-center gap-1.5 text-white">
                <CheckCircle2 className="w-4 h-4 text-orange-200" />
                Signed In!
              </span>
            ) : isSubmitting ? (
              <span>Authenticating...</span>
            ) : (
              <>
                <span>{rotationRequired ? 'Change initial password' : 'Login'}</span>
                <ChevronRight className="w-4 h-4" />
              </>
            )}
          </motion.button>
        </form>

        {/* Need Help Support Card */}
        <div className="mt-3 sm:mt-3.5">
          <button
            type="button"
            onClick={() => alert('Admin Helpline: 1800-ECOPULSE-ADMIN')}
            className="w-full p-2.5 sm:p-3 rounded-2xl bg-[#fff7ed] border border-orange-200/80 hover:bg-orange-100/60 flex items-center justify-between transition-all group cursor-pointer"
          >
            <div className="flex items-center gap-2.5 sm:gap-3">
              <div className="w-7 sm:w-8 h-7 sm:h-8 rounded-full bg-[#ea580c] text-white flex items-center justify-center shrink-0 shadow-xs">
                <Headphones className="w-3.5 sm:w-4 h-3.5 sm:h-4" />
              </div>
              <div className="text-left">
                <div className="text-xs font-bold text-[#ea580c]">Need Help?</div>
                <div className="text-[10px] sm:text-[11px] font-semibold text-slate-600">Contact Support</div>
              </div>
            </div>
            <ChevronRight className="w-4 h-4 text-[#ea580c] group-hover:translate-x-0.5 transition-transform shrink-0" />
          </button>
        </div>
      </div>

      {/* Decorative Bottom Line */}
      <div className="mt-4 pt-2 border-t border-orange-100 flex items-center justify-between text-[10px] text-orange-800/70 font-bold">
        <span>♻️ Field Operations</span>
        <span>EcoPulse AI 2026</span>
      </div>
    </div>
  );
};

export default CollectorPortalLogin;
