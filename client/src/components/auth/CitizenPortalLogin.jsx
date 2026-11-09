import React, { useState, useEffect } from 'react';
import { motion, AnimatePresence } from 'framer-motion';
import { Phone, ShieldCheck, ChevronRight, CheckCircle2, ShieldAlert, Lock, Eye, EyeOff, Mail, Key, ArrowLeft, RefreshCw } from 'lucide-react';
import {
  loginUser,
  sendOtp,
  loginWithOtp,
  getOtpChallengeStatus,
  saveOtpSession,
  getStoredOtpSession,
  clearOtpSession
} from '../../services/authService';
import OtpInput from './OtpInput';

const CitizenPortalLogin = ({ onSuccess, onOpenForgotPassword, onSwitchToSignup }) => {
  const [loginMode, setLoginMode] = useState('otp'); // 'otp' (primary) | 'password' (fallback)
  const [mobileNumber, setMobileNumber] = useState('');
  const [otp, setOtp] = useState('');
  const [otpSent, setOtpSent] = useState(false);
  const [challengeId, setChallengeId] = useState(null);
  const [cooldown, setCooldown] = useState(0);
  const [timer, setTimer] = useState(300);

  // Password mode states
  const [identifier, setIdentifier] = useState('');
  const [password, setPassword] = useState('');
  const [showPassword, setShowPassword] = useState(false);
  const [rememberMe, setRememberMe] = useState(true);

  // Request status
  const [isSubmitting, setIsSubmitting] = useState(false);
  const [authSuccess, setAuthSuccess] = useState(false);
  const [errorMsg, setErrorMsg] = useState('');
  const [infoMsg, setInfoMsg] = useState('');

  // Restore active verification session on page load / refresh
  useEffect(() => {
    const restoreSession = async () => {
      const session = getStoredOtpSession('login');
      if (!session || !session.challenge_id) return;

      if (session.phone) setMobileNumber(session.phone);

      try {
        const status = await getOtpChallengeStatus(session.challenge_id);
        if (status.valid && status.seconds_remaining > 0) {
          setChallengeId(session.challenge_id);
          setOtpSent(true);
          setLoginMode('otp');
          setTimer(status.seconds_remaining);
          setCooldown(status.cooldown_remaining);
          setInfoMsg(`Verification session restored for +91 ******${(session.phone || '').slice(-4)}`);
        } else {
          clearOtpSession('login');
          if (status.expired) {
            setErrorMsg('Your previous verification code has expired. Please request a new code.');
          } else if (status.consumed) {
            setErrorMsg('Your previous verification session was already completed.');
          }
        }
      } catch (err) {
        clearOtpSession('login');
      }
    };

    restoreSession();
  }, []);

  // Cooldown countdown timer
  useEffect(() => {
    let interval = null;
    if (cooldown > 0) {
      interval = setInterval(() => {
        setCooldown((prev) => (prev > 1 ? prev - 1 : 0));
      }, 1000);
    }
    return () => clearInterval(interval);
  }, [cooldown]);

  // Expiration timer
  useEffect(() => {
    let interval = null;
    if (otpSent && timer > 0) {
      interval = setInterval(() => {
        setTimer((prev) => (prev > 1 ? prev - 1 : 0));
      }, 1000);
    }
    return () => clearInterval(interval);
  }, [otpSent, timer]);

  const cleanPhone = (val) => val.replace(/\D/g, '').slice(0, 10);

  const handleSendOtp = async () => {
    if (isSubmitting) return;
    const cleaned = cleanPhone(mobileNumber);
    if (!cleaned || cleaned.length !== 10) {
      setErrorMsg('Please enter a valid 10-digit Indian mobile number');
      return;
    }
    if (!/^[6-9]/.test(cleaned)) {
      setErrorMsg('Indian mobile numbers must start with 6, 7, 8, or 9');
      return;
    }

    setErrorMsg('');
    setInfoMsg('');
    setIsSubmitting(true);

    try {
      const res = await sendOtp({ phone: cleaned, purpose: 'login' });
      setChallengeId(res.challenge_id);
      saveOtpSession('login', {
        challenge_id: res.challenge_id,
        phone: cleaned
      });
      setOtpSent(true);
      setOtp('');
      setCooldown(res.cooldown_seconds || 60);
      setTimer(res.expires_in || 300);
      setInfoMsg(res.message || `OTP sent to +91 ******${cleaned.slice(-4)}`);
    } catch (err) {
      setErrorMsg(err.message || 'Failed to dispatch verification code. Please try again.');
    } finally {
      setIsSubmitting(false);
    }
  };

  const handleVerifyOtp = async (e) => {
    if (isSubmitting) return;
    if (e) e.preventDefault();
    if (!otp || otp.length !== 6) {
      setErrorMsg('Please enter the complete 6-digit verification code');
      return;
    }

    setErrorMsg('');
    setIsSubmitting(true);

    try {
      const cleaned = cleanPhone(mobileNumber);
      const res = await loginWithOtp({ phone: cleaned, otp, role: 'citizen', challengeId });
      clearOtpSession('login');
      setAuthSuccess(true);
      setTimeout(() => {
        if (onSuccess) {
          onSuccess(res?.user || { phone: cleaned, role: 'citizen' });
        }
      }, 600);
    } catch (err) {
      setErrorMsg(err.message || 'Invalid or expired OTP. Please try again.');
    } finally {
      setIsSubmitting(false);
    }
  };

  const handleChangeMobile = () => {
    clearOtpSession('login');
    setOtpSent(false);
    setOtp('');
    setChallengeId(null);
    setErrorMsg('');
    setInfoMsg('');
  };

  const handleSwitchMode = (mode) => {
    if (mode !== 'otp') {
      clearOtpSession('login');
      setOtpSent(false);
      setOtp('');
      setChallengeId(null);
    }
    setLoginMode(mode);
    setErrorMsg('');
    setInfoMsg('');
  };

  const handleSwitchToSignupSafe = () => {
    clearOtpSession('login');
    if (onSwitchToSignup) onSwitchToSignup();
  };

  const handlePasswordSubmit = async (e) => {
    e.preventDefault();
    setErrorMsg('');

    if (!identifier.trim()) {
      setErrorMsg('Please enter your email or mobile number');
      return;
    }
    if (!password) {
      setErrorMsg('Please enter your password');
      return;
    }

    setIsSubmitting(true);
    try {
      const res = await loginUser({
        email: identifier.trim(),
        password,
        role: 'citizen',
        rememberMe
      });
      setAuthSuccess(true);
      setTimeout(() => {
        if (onSuccess) {
          onSuccess(res?.user || { email: identifier, role: 'citizen' });
        }
      }, 600);
    } catch (err) {
      setErrorMsg(err.message || 'Authentication failed. Please verify your credentials.');
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
    <div className="bg-white rounded-[24px] sm:rounded-[28px] p-4 sm:p-6 shadow-xl border border-slate-200/90 relative overflow-hidden flex flex-col justify-between h-full hover:shadow-2xl transition-shadow duration-300">
      {/* Top Accent Line */}
      <div className="absolute top-0 inset-x-0 h-1.5 bg-[#16a34a]" />

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
            Dhule Civic Sandbox | <span className="text-[#16a34a]">स्वच्छता पोर्टल</span>
          </div>
          <div className="text-[10px] font-bold text-[#16a34a] mt-0.5">
            🌱 एकत्र येऊ, स्वच्छ धुळे घडवू. 🌱
          </div>
        </div>

        {/* Portal Title & Subtitle */}
        <div className="text-center mb-2.5">
          <h3 className="text-xl sm:text-2xl font-extrabold text-[#16a34a] tracking-tight">
            Citizen Portal
          </h3>
          <p className="text-[11px] sm:text-xs font-semibold text-slate-600 mt-0.5">
            Report waste, track status and earn rewards.
          </p>
        </div>

        {/* Hero Illustration */}
        <div className="relative w-full h-28 sm:h-32 rounded-2xl overflow-hidden border border-emerald-100 mb-3 bg-gradient-to-b from-[#eaf7ee] to-emerald-50 flex items-center justify-center shadow-2xs p-2">
          <img
            src="/ChatGPT Image Aug 5, 2026, 01_06_09 PM.png"
            alt="Citizen Portal Illustration"
            className="w-full h-full object-contain object-center drop-shadow-xs"
          />
        </div>

        {/* Auth Mode Toggle Pills */}
        <div className="flex rounded-xl bg-slate-100 p-1 mb-3 border border-slate-200">
          <button
            type="button"
            onClick={() => handleSwitchMode('otp')}
            className={`flex-1 py-1.5 text-xs font-extrabold rounded-lg transition-all flex items-center justify-center gap-1.5 cursor-pointer ${
              loginMode === 'otp'
                ? 'bg-white text-[#16a34a] shadow-xs'
                : 'text-slate-500 hover:text-slate-800'
            }`}
          >
            <Phone className="w-3.5 h-3.5" />
            <span>WhatsApp OTP</span>
          </button>

          <button
            type="button"
            onClick={() => handleSwitchMode('password')}
            className={`flex-1 py-1.5 text-xs font-extrabold rounded-lg transition-all flex items-center justify-center gap-1.5 cursor-pointer ${
              loginMode === 'password'
                ? 'bg-white text-[#16a34a] shadow-xs'
                : 'text-slate-500 hover:text-slate-800'
            }`}
          >
            <Key className="w-3.5 h-3.5" />
            <span>Password</span>
          </button>
        </div>

        {/* Feedback Messages */}
        <AnimatePresence>
          {errorMsg && (
            <motion.div
              initial={{ opacity: 0, y: -4 }}
              animate={{ opacity: 1, y: 0 }}
              exit={{ opacity: 0, y: -4 }}
              className="p-2.5 rounded-xl bg-red-50 border border-red-200 text-red-700 text-xs font-bold flex items-start gap-2 mb-2.5"
            >
              <ShieldAlert className="w-4 h-4 shrink-0 text-red-600 mt-0.5" />
              <div className="flex-1">
                <span>{errorMsg}</span>
                {errorMsg.toLowerCase().includes('sign up') && onSwitchToSignup && (
                  <button
                    type="button"
                    onClick={handleSwitchToSignupSafe}
                    className="block mt-1 font-black text-[#16a34a] underline cursor-pointer"
                  >
                    Click here to register your mobile number →
                  </button>
                )}
              </div>
            </motion.div>
          )}

          {infoMsg && !errorMsg && (
            <motion.div
              initial={{ opacity: 0, y: -4 }}
              animate={{ opacity: 1, y: 0 }}
              exit={{ opacity: 0, y: -4 }}
              className="p-2.5 rounded-xl bg-emerald-50 border border-emerald-200 text-emerald-800 text-xs font-bold flex items-center gap-2 mb-2.5"
            >
              <CheckCircle2 className="w-4 h-4 shrink-0 text-emerald-600" />
              <span>{infoMsg}</span>
            </motion.div>
          )}
        </AnimatePresence>

        {/* PRIMARY MODE: Mobile OTP Flow */}
        {loginMode === 'otp' ? (
          <div>
            {!otpSent ? (
              /* Step 1: Enter Mobile Number */
              <div className="space-y-3">
                <div>
                  <label className="block text-[11px] sm:text-xs font-bold text-slate-700 mb-1">
                    Registered Mobile Number
                  </label>
                  <div className="relative flex items-center border border-slate-300 rounded-xl bg-slate-50/80 focus-within:bg-white focus-within:border-[#16a34a] focus-within:ring-2 focus-within:ring-emerald-100 transition-all overflow-hidden">
                    <div className="pl-3 pr-2 py-2 sm:py-2.5 flex items-center gap-1.5 border-r border-slate-200 text-slate-700 font-bold text-xs shrink-0 select-none">
                      <span className="text-sm">🇮🇳</span>
                      <span>+91</span>
                    </div>
                    <input
                      type="tel"
                      inputMode="numeric"
                      value={mobileNumber}
                      onChange={(e) => setMobileNumber(cleanPhone(e.target.value))}
                      onKeyDown={(e) => {
                        if (e.key === 'Enter') {
                          e.preventDefault();
                          handleSendOtp();
                        }
                      }}
                      placeholder="98765 43210"
                      maxLength={10}
                      autoFocus
                      className="w-full px-3 py-2 sm:py-2.5 text-xs font-bold tracking-wide outline-none bg-transparent text-slate-900 placeholder:text-slate-400"
                    />
                  </div>
                  <p className="text-[10px] text-slate-500 font-medium mt-1">
                    We will send a 6-digit verification code via SMS.
                  </p>
                </div>

                <motion.button
                  whileHover={{ scale: 1.01 }}
                  whileTap={{ scale: 0.98 }}
                  type="button"
                  onClick={handleSendOtp}
                  disabled={isSubmitting || mobileNumber.length !== 10}
                  className="w-full py-2.5 sm:py-3 px-4 rounded-xl bg-[#16a34a] hover:bg-[#15803d] text-white font-extrabold text-xs sm:text-sm shadow-md transition-all flex items-center justify-center gap-2 cursor-pointer disabled:opacity-50 min-h-[42px]"
                >
                  {isSubmitting ? (
                    <div className="flex items-center gap-2">
                      <RefreshCw className="w-4 h-4 animate-spin" />
                      <span>Sending OTP...</span>
                    </div>
                  ) : (
                    <>
                      <span>Get WhatsApp Verification Code</span>
                      <ChevronRight className="w-4 h-4" />
                    </>
                  )}
                </motion.button>
              </div>
            ) : (
              /* Step 2: Enter & Verify 6-digit OTP */
              <form onSubmit={handleVerifyOtp} className="space-y-3">
                <div className="flex items-center justify-between text-xs">
                  <span className="text-slate-600 font-semibold">
                    Code sent via WhatsApp to <span className="font-extrabold text-slate-800">+91 ******{cleanPhone(mobileNumber).slice(-4)}</span>
                  </span>
                  <button
                    type="button"
                    onClick={handleChangeMobile}
                    className="text-[#16a34a] font-extrabold hover:underline flex items-center gap-1 cursor-pointer text-[11px]"
                  >
                    <ArrowLeft className="w-3 h-3" />
                    <span>Change</span>
                  </button>
                </div>

                <div>
                  <label className="block text-[11px] sm:text-xs font-bold text-slate-700 mb-1 text-center">
                    Enter 6-Digit Verification Code
                  </label>
                  <OtpInput
                    value={otp}
                    onChange={(val) => {
                      setOtp(val);
                      if (val.length === 6) {
                        setErrorMsg('');
                      }
                    }}
                    disabled={isSubmitting || authSuccess}
                  />
                  <div className="flex items-center justify-between text-[11px] text-slate-500 font-semibold mt-1">
                    <span>Code expires in: <strong className="text-slate-700">{formatTimer(timer)}</strong></span>
                    {cooldown > 0 ? (
                      <span className="text-slate-400 font-medium">Resend in {cooldown}s</span>
                    ) : (
                      <button
                        type="button"
                        onClick={handleSendOtp}
                        disabled={isSubmitting}
                        className="text-[#16a34a] font-extrabold hover:underline cursor-pointer"
                      >
                        Resend WhatsApp OTP
                      </button>
                    )}
                  </div>
                </div>

                <motion.button
                  whileHover={{ scale: 1.01 }}
                  whileTap={{ scale: 0.98 }}
                  type="submit"
                  disabled={isSubmitting || authSuccess || otp.length !== 6}
                  className="w-full py-2.5 sm:py-3 px-4 rounded-xl bg-[#16a34a] hover:bg-[#15803d] text-white font-extrabold text-xs sm:text-sm shadow-md transition-all flex items-center justify-center gap-2 cursor-pointer disabled:opacity-50 min-h-[42px]"
                >
                  {authSuccess ? (
                    <span className="flex items-center gap-1.5 text-white">
                      <CheckCircle2 className="w-4 h-4 text-emerald-200" />
                      Verified! Redirecting...
                    </span>
                  ) : isSubmitting ? (
                    <div className="flex items-center gap-2">
                      <RefreshCw className="w-4 h-4 animate-spin" />
                      <span>Verifying Code...</span>
                    </div>
                  ) : (
                    <>
                      <ShieldCheck className="w-4 h-4" />
                      <span>Verify & Sign In</span>
                    </>
                  )}
                </motion.button>
              </form>
            )}
          </div>
        ) : (
          /* FALLBACK MODE: Email / Mobile + Password */
          <form onSubmit={handlePasswordSubmit} className="space-y-2.5 sm:space-y-3">
            <div>
              <label className="block text-[11px] sm:text-xs font-bold text-slate-700 mb-1">
                Email or Mobile Number
              </label>
              <div className="relative flex items-center border border-slate-300 rounded-xl bg-slate-50/80 focus-within:bg-white focus-within:border-[#16a34a] focus-within:ring-2 focus-within:ring-emerald-100 transition-all overflow-hidden">
                <div className="pl-3.5 text-slate-400">
                  <Mail className="w-4 h-4" />
                </div>
                <input
                  type="text"
                  value={identifier}
                  onChange={(e) => setIdentifier(e.target.value)}
                  placeholder="Enter email or mobile number"
                  className="w-full pl-2.5 pr-4 py-2 sm:py-2.5 text-xs font-semibold outline-none bg-transparent text-slate-800 placeholder:text-slate-400"
                />
              </div>
            </div>

            <div>
              <label className="block text-[11px] sm:text-xs font-bold text-slate-700 mb-1">
                Password
              </label>
              <div className="relative flex items-center border border-slate-300 rounded-xl bg-slate-50/80 focus-within:bg-white focus-within:border-[#16a34a] focus-within:ring-2 focus-within:ring-emerald-100 transition-all">
                <div className="pl-3.5 text-slate-400">
                  <Lock className="w-4 h-4" />
                </div>
                <input
                  type={showPassword ? 'text' : 'password'}
                  value={password}
                  onChange={(e) => setPassword(e.target.value)}
                  placeholder="Enter your password"
                  className="w-full pl-2.5 pr-10 py-2 sm:py-2.5 text-xs font-semibold outline-none bg-transparent text-slate-800 placeholder:text-slate-400"
                />
                <button
                  type="button"
                  onClick={() => setShowPassword(!showPassword)}
                  className="absolute right-3 text-slate-400 hover:text-slate-600 cursor-pointer"
                >
                  {showPassword ? <EyeOff className="w-4 h-4" /> : <Eye className="w-4 h-4" />}
                </button>
              </div>
            </div>

            <div className="flex items-center justify-between text-[11px] sm:text-xs pt-0.5">
              <label className="flex items-center gap-1.5 cursor-pointer font-bold text-slate-600 select-none">
                <input
                  type="checkbox"
                  checked={rememberMe}
                  onChange={(e) => setRememberMe(e.target.checked)}
                  className="w-3.5 h-3.5 rounded border-slate-300 text-[#16a34a] focus:ring-emerald-200 accent-[#16a34a] cursor-pointer"
                />
                <span>Remember me</span>
              </label>

              <button
                type="button"
                onClick={onOpenForgotPassword}
                className="font-bold text-[#16a34a] hover:underline cursor-pointer"
              >
                Forgot Password?
              </button>
            </div>

            <motion.button
              whileHover={{ scale: 1.01 }}
              whileTap={{ scale: 0.98 }}
              type="submit"
              disabled={isSubmitting || authSuccess}
              className="w-full py-2.5 sm:py-3 px-4 rounded-xl bg-[#16a34a] hover:bg-[#15803d] text-white font-extrabold text-xs sm:text-sm shadow-md transition-all flex items-center justify-center gap-2 cursor-pointer mt-2 disabled:opacity-80 min-h-[42px]"
            >
              {authSuccess ? (
                <span className="flex items-center gap-1.5 text-white">
                  <CheckCircle2 className="w-4 h-4 text-emerald-200" />
                  Signed In!
                </span>
              ) : isSubmitting ? (
                <span>Authenticating...</span>
              ) : (
                <>
                  <span>Sign In with Password</span>
                  <ChevronRight className="w-4 h-4" />
                </>
              )}
            </motion.button>
          </form>
        )}

        {/* WhatsApp Assistant Link */}
        <div className="mt-3 sm:mt-3.5">
          <a
            href="https://wa.me/?text=Hi%20EcoPulse%20AI%20Assistant"
            target="_blank"
            rel="noopener noreferrer"
            className="w-full p-2.5 sm:p-3 rounded-2xl bg-[#f0fdf4] border border-emerald-200/80 hover:bg-emerald-100/60 flex items-center justify-between transition-all group"
          >
            <div className="flex items-center gap-2.5 sm:gap-3">
              <div className="w-7 sm:w-8 h-7 sm:h-8 rounded-full bg-[#25D366] text-white flex items-center justify-center shrink-0 shadow-xs">
                <svg className="w-3.5 sm:w-4 h-3.5 sm:h-4 fill-current" viewBox="0 0 24 24">
                  <path d="M.057 24l1.687-6.163c-1.041-1.804-1.588-3.849-1.587-5.946.003-6.556 5.338-11.891 11.893-11.891 3.181.001 6.167 1.24 8.413 3.488 2.245 2.248 3.481 5.236 3.48 8.414-.003 6.557-5.338 11.892-11.893 11.892-1.99-.001-3.951-.5-5.688-1.448l-6.305 1.654zm6.597-3.807c1.676.995 3.276 1.591 5.392 1.592 5.448 0 9.886-4.434 9.889-9.885.002-5.462-4.415-9.89-9.881-9.892-5.452 0-9.887 4.434-9.889 9.884-.001 2.225.651 3.891 1.746 5.634l-.999 3.648 3.742-.981zm11.387-5.464c-.074-.124-.272-.198-.57-.347-.297-.149-1.758-.868-2.031-.967-.272-.099-.47-.149-.669.149-.198.297-.768.967-.941 1.165-.173.198-.347.223-.644.074-.297-.149-1.255-.462-2.39-1.475-.883-.788-1.48-1.761-1.653-2.059-.173-.297-.018-.458.13-.606.134-.133.297-.347.446-.521.151-.172.2-.296.3-.495.099-.198.05-.372-.025-.521-.075-.148-.669-1.611-.916-2.206-.242-.579-.487-.501-.669-.51l-.57-.01c-.198 0-.52.074-.792.372s-1.04 1.016-1.04 2.479 1.065 2.876 1.213 3.074c.149.198 2.095 3.2 5.076 4.487.709.306 1.263.489 1.694.626.712.226 1.36.194 1.872.118.571-.085 1.758-.719 2.006-1.413.248-.695.248-1.29.173-1.414z" />
                </svg>
              </div>
              <div className="text-left">
                <div className="text-xs font-bold text-[#16a34a]">Need Help?</div>
                <div className="text-[10px] sm:text-[11px] font-semibold text-slate-600">Chat with WhatsApp AI Assistant</div>
              </div>
            </div>
            <ChevronRight className="w-4 h-4 text-[#16a34a] group-hover:translate-x-0.5 transition-transform shrink-0" />
          </a>
        </div>
      </div>

      {/* Municipal Branding Footer */}
      <div className="mt-4 pt-2 border-t border-emerald-100 flex items-center justify-between text-[10px] text-emerald-800/80 font-bold">
        <span>🏛️ Dhule Civic Sandbox</span>
        <span>DPDP Act 2023 Compliant</span>
      </div>
    </div>
  );
};

export default CitizenPortalLogin;
