import React, { useState, useEffect, useRef } from 'react';
import { motion, AnimatePresence } from 'framer-motion';
import {
  User,
  Mail,
  Phone,
  ShieldCheck,
  CheckCircle2,
  ShieldAlert,
  ArrowRight,
  Sparkles,
  ArrowLeft,
  RefreshCw,
  Info,
  Copy,
  Check,
  MessageSquare,
  ExternalLink,
  Clock
} from 'lucide-react';
import {
  generateWhatsAppVerification,
  getWhatsAppVerificationStatus,
  saveOtpSession,
  getStoredOtpSession,
  clearOtpSession
} from '../../services/authService';

const SignupForm = ({ onSwitchToLogin, onRoleChange, onSuccess }) => {
  const [step, setStep] = useState('DETAILS'); // 'DETAILS' | 'VERIFY'
  const [fullName, setFullName] = useState('');
  const [phone, setPhone] = useState('');
  const [email, setEmail] = useState('');
  const [acceptTerms, setAcceptTerms] = useState(false);

  // Verification challenge state
  const [challengeId, setChallengeId] = useState(null);
  const [challengeSecret, setChallengeSecret] = useState('');
  const [verificationCode, setVerificationCode] = useState('');
  const [whatsappNumber, setWhatsappNumber] = useState('');
  const [timer, setTimer] = useState(300);
  const [cooldown, setCooldown] = useState(0);
  const [verificationStatus, setVerificationStatus] = useState('PENDING'); // PENDING | VERIFIED | EXPIRED | FAILED

  const [isSubmitting, setIsSubmitting] = useState(false);
  const [authSuccess, setAuthSuccess] = useState(false);
  const [serverError, setServerError] = useState('');
  const [infoMsg, setInfoMsg] = useState('');
  const [accountExists, setAccountExists] = useState(false);
  const [copied, setCopied] = useState(false);

  const pollIntervalRef = useRef(null);
  const timerIntervalRef = useRef(null);
  const isMountedRef = useRef(true);

  useEffect(() => {
    isMountedRef.current = true;
    return () => {
      isMountedRef.current = false;
      if (pollIntervalRef.current) clearInterval(pollIntervalRef.current);
      if (timerIntervalRef.current) clearInterval(timerIntervalRef.current);
    };
  }, []);

  // Restore active verification challenge on page refresh
  useEffect(() => {
    const restoreSession = async () => {
      const session = getStoredOtpSession('register');
      if (!session || !session.challenge_id) return;

      // Check if session has timed out beyond 5 minutes (300 seconds)
      const elapsed = Math.floor((Date.now() - (session.timestamp || 0)) / 1000);
      if (elapsed >= 300) {
        clearOtpSession('register');
        return;
      }

      if (session.draft?.fullName) setFullName(session.draft.fullName);
      if (session.draft?.email) setEmail(session.draft.email);
      if (session.phone) setPhone(session.phone);
      if (session.whatsapp_number) setWhatsappNumber(session.whatsapp_number);
      if (session.challenge_secret) setChallengeSecret(session.challenge_secret);
      setChallengeId(session.challenge_id);
      setAcceptTerms(true);

      try {
        const res = await getWhatsAppVerificationStatus(session.challenge_id, session.challenge_secret);
        if (!isMountedRef.current) return;

        if (res.status === 'VERIFIED') {
          setVerificationStatus('VERIFIED');
          setAuthSuccess(true);
          clearOtpSession('register');
          setTimeout(() => {
            if (onSuccess) onSuccess(res?.user);
          }, 800);
        } else if (res.status === 'PENDING' && res.seconds_remaining > 0) {
          setChallengeId(session.challenge_id);
          setChallengeSecret(session.challenge_secret);
          if (res.whatsapp_number) setWhatsappNumber(res.whatsapp_number);
          setStep('VERIFY');
          setTimer(res.seconds_remaining);
          setVerificationStatus('PENDING');
          setInfoMsg(`Verification in progress for +91 ******${(session.phone || '').slice(-4)}`);
        } else if (res.status === 'CONSUMED' || res.consumed) {
          clearOtpSession('register');
          setChallengeId(null);
          setChallengeSecret('');
          setStep('DETAILS');
          setServerError('This verification session has already been claimed. If you already registered, please sign in.');
        } else {
          clearOtpSession('register');
          setChallengeId(null);
          setChallengeSecret('');
          setStep('DETAILS');
          if (res.expired || res.status === 'EXPIRED') {
            setServerError('Your previous verification session has expired. Please enter your details to generate a new code.');
          } else {
            setServerError(res.message || 'Previous verification session is no longer active. Please generate a new code.');
          }
        }
      } catch (err) {
        clearOtpSession('register');
        setChallengeId(null);
        setChallengeSecret('');
        setStep('DETAILS');
        const msg = err.message || '';
        if (msg.includes('claimed') || msg.includes('409')) {
          setServerError('This verification session has already been claimed. If you already registered, please sign in.');
        } else if (msg.includes('403') || msg.includes('unauthorized')) {
          setServerError('Verification session authorization expired. Please generate a new code.');
        } else {
          setServerError('Previous verification session could not be resumed. Please generate a new code.');
        }
      }
    };

    restoreSession();
  }, [onSuccess]);

  // Expiration timer
  useEffect(() => {
    if (step === 'VERIFY' && timer > 0 && verificationStatus === 'PENDING') {
      timerIntervalRef.current = setInterval(() => {
        setTimer((prev) => {
          if (prev <= 1) {
            clearInterval(timerIntervalRef.current);
            setVerificationStatus('EXPIRED');
            clearOtpSession('register');
            return 0;
          }
          return prev - 1;
        });
      }, 1000);
    }
    return () => {
      if (timerIntervalRef.current) clearInterval(timerIntervalRef.current);
    };
  }, [step, timer, verificationStatus]);

  // Resend cooldown timer
  useEffect(() => {
    let interval = null;
    if (cooldown > 0) {
      interval = setInterval(() => {
        setCooldown((prev) => (prev > 1 ? prev - 1 : 0));
      }, 1000);
    }
    return () => clearInterval(interval);
  }, [cooldown]);

  // Background status polling when in VERIFY step
  useEffect(() => {
    if (step !== 'VERIFY' || !challengeId || verificationStatus !== 'PENDING') {
      if (pollIntervalRef.current) clearInterval(pollIntervalRef.current);
      return;
    }

    pollIntervalRef.current = setInterval(async () => {
      if (!isMountedRef.current) return;
      try {
        const res = await getWhatsAppVerificationStatus(challengeId, challengeSecret);
        if (!isMountedRef.current) return;

        if (res.status === 'VERIFIED') {
          clearInterval(pollIntervalRef.current);
          setVerificationStatus('VERIFIED');
          setAuthSuccess(true);
          clearOtpSession('register');
          setTimeout(() => {
            if (onSuccess) {
              onSuccess(res?.user || { full_name: fullName, phone: cleanPhone(phone), role: 'citizen' });
            }
          }, 900);
        } else if (res.status === 'EXPIRED') {
          clearInterval(pollIntervalRef.current);
          setVerificationStatus('EXPIRED');
          clearOtpSession('register');
          setServerError('Verification code expired. Please generate a new code.');
        } else if (res.status === 'CONSUMED') {
          clearInterval(pollIntervalRef.current);
          setVerificationStatus('CONSUMED');
          clearOtpSession('register');
          setServerError('This verification session has already been claimed. Please sign in instead.');
        } else if (res.status === 'FAILED') {
          clearInterval(pollIntervalRef.current);
          setVerificationStatus('FAILED');
          clearOtpSession('register');
          setServerError('Maximum verification attempts reached. Please generate a new code.');
        }
      } catch (err) {
        const errMsg = err.message || '';
        if (errMsg.includes('403') || errMsg.includes('unauthorized') || errMsg.includes('409') || errMsg.includes('claimed')) {
          clearInterval(pollIntervalRef.current);
          clearOtpSession('register');
          setVerificationStatus('FAILED');
          setServerError(errMsg);
        }
      }
    }, 2500);

    return () => {
      if (pollIntervalRef.current) clearInterval(pollIntervalRef.current);
    };
  }, [step, challengeId, challengeSecret, verificationStatus, fullName, phone, onSuccess]);

  const cleanPhone = (val) => val.replace(/\D/g, '').slice(0, 10);

  const handleRequestVerification = async (e) => {
    e.preventDefault();
    if (isSubmitting) return;
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
      const res = await generateWhatsAppVerification({
        fullName: fullName.trim(),
        phone: cleaned,
        email: email.trim() || null
      });

      setChallengeId(res.challenge_id);
      setChallengeSecret(res.challenge_secret || '');
      setVerificationCode(res.code);
      setWhatsappNumber(res.whatsapp_number);
      setTimer(res.expires_in || 300);
      setCooldown(res.cooldown_seconds || 60);
      setVerificationStatus('PENDING');

      // Save session without persisting OTP code to browser storage
      saveOtpSession('register', {
        challenge_id: res.challenge_id,
        challenge_secret: res.challenge_secret,
        phone: cleaned,
        whatsapp_number: res.whatsapp_number,
        draft: { fullName: fullName.trim(), email: email.trim() }
      });

      setStep('VERIFY');
      setInfoMsg(res.instructions || `Send VERIFY ${res.code} to our WhatsApp number`);
    } catch (err) {
      const msg = err.message || 'Failed to generate verification challenge';
      setServerError(msg);
      if (msg.toLowerCase().includes('already registered')) {
        setAccountExists(true);
      }
    } finally {
      setIsSubmitting(false);
    }
  };

  const handleRegenerateCode = async () => {
    if (cooldown > 0 || isSubmitting) return;
    setServerError('');
    setIsSubmitting(true);
    try {
      const cleaned = cleanPhone(phone);
      const res = await generateWhatsAppVerification({
        fullName: fullName.trim(),
        phone: cleaned,
        email: email.trim() || null
      });

      setChallengeId(res.challenge_id);
      setChallengeSecret(res.challenge_secret || '');
      setVerificationCode(res.code);
      setWhatsappNumber(res.whatsapp_number);
      setTimer(res.expires_in || 300);
      setCooldown(res.cooldown_seconds || 60);
      setVerificationStatus('PENDING');

      // Save session without persisting OTP code to browser storage
      saveOtpSession('register', {
        challenge_id: res.challenge_id,
        challenge_secret: res.challenge_secret,
        phone: cleaned,
        whatsapp_number: res.whatsapp_number,
        draft: { fullName: fullName.trim(), email: email.trim() }
      });

      setInfoMsg(`New code generated: VERIFY ${res.code}`);
    } catch (err) {
      setServerError(err.message || 'Failed to generate new code.');
    } finally {
      setIsSubmitting(false);
    }
  };

  const handleCopyMessage = () => {
    const textToCopy = `VERIFY ${verificationCode}`;
    navigator.clipboard.writeText(textToCopy);
    setCopied(true);
    setTimeout(() => setCopied(false), 2000);
  };

  const handleEditDetails = () => {
    clearOtpSession('register');
    if (pollIntervalRef.current) clearInterval(pollIntervalRef.current);
    if (timerIntervalRef.current) clearInterval(timerIntervalRef.current);
    setStep('DETAILS');
    setVerificationCode('');
    setServerError('');
    setInfoMsg('');
    setChallengeId(null);
    setChallengeSecret('');
    setVerificationStatus('PENDING');
  };

  const handleSwitchToLoginSafe = () => {
    clearOtpSession('register');
    if (onSwitchToLogin) onSwitchToLogin();
  };

  const formatTimer = (seconds) => {
    const mins = Math.floor(seconds / 60);
    const secs = seconds % 60;
    return `${mins}:${secs < 10 ? '0' : ''}${secs}`;
  };

  // WhatsApp deep link for 1-click message prefill
  const cleanBotPhone = (whatsappNumber || '').replace(/\D/g, '');
  const waDeepLink = `https://wa.me/${cleanBotPhone}?text=${encodeURIComponent(`VERIFY ${verificationCode}`)}`;

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
          {step === 'DETAILS' ? 'Create Citizen Account' : 'Verify via WhatsApp'}
        </h2>
        <p className="text-[11px] sm:text-xs font-semibold text-gray-600 mt-0.5 leading-relaxed">
          {step === 'DETAILS'
            ? 'Enter your name and mobile number. Email is optional.'
            : 'Send the verification code below to our official WhatsApp Business account.'}
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
        <form onSubmit={handleRequestVerification} className="space-y-3">
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
              You will verify your mobile number directly by sending a WhatsApp message.
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
                <span>Generating Verification Code...</span>
              </div>
            ) : (
              <div className="flex items-center gap-1.5">
                <span>Continue & Verify via WhatsApp</span>
                <ArrowRight className="w-3.5 h-3.5" />
              </div>
            )}
          </motion.button>
        </form>
      ) : (
        /* STEP 2: Website-Generated WhatsApp Verification Instructions */
        <div className="space-y-3">
          {/* Active Number & Edit Link */}
          <div className="flex items-center justify-between text-xs p-2 rounded-xl bg-emerald-50/60 border border-emerald-100">
            <div>
              <div className="text-[10px] text-gray-500 font-bold uppercase tracking-wider">Verifying Phone</div>
              <div className="font-extrabold text-gray-800 text-xs">+91 {cleanPhone(phone)}</div>
            </div>
            <button
              type="button"
              onClick={handleEditDetails}
              className="text-[#005C2B] font-extrabold text-xs hover:underline flex items-center gap-1 cursor-pointer"
            >
              <ArrowLeft className="w-3 h-3" />
              <span>Edit Details</span>
            </button>
          </div>

          {/* Verification Code Box */}
          {verificationCode ? (
            <div className="p-4 rounded-2xl bg-gradient-to-br from-emerald-50/80 via-white to-emerald-50/50 border border-emerald-200 text-center shadow-xs">
              <span className="text-[10px] font-bold text-[#005C2B] uppercase tracking-widest block mb-1">
                Your 6-Digit Verification Code
              </span>

              {/* Verification Code Digits */}
              <div className="text-3xl sm:text-4xl font-black text-gray-900 tracking-[0.2em] font-mono py-1 select-all">
                {verificationCode}
              </div>

              <p className="mt-2 text-xs font-medium text-gray-700 leading-snug">
                Send <strong className="font-mono bg-emerald-100/90 text-[#005C2B] px-1.5 py-0.5 rounded font-black">VERIFY {verificationCode}</strong> to our WhatsApp Business number:
              </p>

              <div className="mt-1.5 inline-flex items-center gap-1.5 bg-white px-3 py-1 rounded-full border border-gray-200 text-xs font-extrabold text-gray-900 shadow-2xs">
                <MessageSquare className="w-3.5 h-3.5 text-[#25D366]" />
                <span>{whatsappNumber}</span>
              </div>
            </div>
          ) : (
            <div className="p-4 rounded-2xl bg-amber-50/70 border border-amber-200 text-center shadow-xs">
              <span className="text-[10px] font-bold text-amber-800 uppercase tracking-widest block mb-1">
                Verification In Progress
              </span>
              <p className="text-xs font-medium text-amber-900 leading-snug">
                Active verification session for <strong>+91 {cleanPhone(phone)}</strong>
              </p>
              <p className="text-[11px] text-gray-600 mt-1.5 leading-relaxed">
                If you already sent your <strong>VERIFY</strong> message on WhatsApp, please wait while we confirm your account.
              </p>
              <div className="mt-3 flex items-center justify-center gap-2">
                <button
                  type="button"
                  onClick={handleRegenerateCode}
                  disabled={cooldown > 0 || isSubmitting}
                  className="py-1.5 px-3 rounded-xl bg-white hover:bg-amber-100 border border-amber-300 text-amber-900 text-xs font-bold transition-all flex items-center gap-1.5 shadow-2xs cursor-pointer"
                >
                  <RefreshCw className={`w-3 h-3 ${isSubmitting ? 'animate-spin' : ''}`} />
                  <span>{cooldown > 0 ? `Wait ${cooldown}s` : 'Generate New Verification Code'}</span>
                </button>
              </div>
            </div>
          )}

          {/* Action Buttons: 1-Click WhatsApp + Copy Code (shown when verificationCode is present) */}
          {verificationCode && (
            <div className="grid grid-cols-2 gap-2">
              <a
                href={waDeepLink}
                target="_blank"
                rel="noopener noreferrer"
                className="py-2.5 px-3 rounded-xl bg-[#25D366] hover:bg-[#20bd5a] text-white text-xs font-bold transition-all flex items-center justify-center gap-1.5 shadow-xs cursor-pointer"
              >
                <MessageSquare className="w-3.5 h-3.5" />
                <span>Open WhatsApp</span>
                <ExternalLink className="w-3 h-3 opacity-80" />
              </a>

              <button
                type="button"
                onClick={handleCopyMessage}
                className="py-2.5 px-3 rounded-xl bg-white hover:bg-gray-50 border border-gray-300 text-gray-800 text-xs font-bold transition-all flex items-center justify-center gap-1.5 shadow-2xs cursor-pointer"
              >
                {copied ? (
                  <>
                    <Check className="w-3.5 h-3.5 text-emerald-600" />
                    <span className="text-emerald-700">Copied!</span>
                  </>
                ) : (
                  <>
                    <Copy className="w-3.5 h-3.5 text-gray-500" />
                    <span>Copy Code</span>
                  </>
                )}
              </button>
            </div>
          )}

          {/* Live Status Indicator & Expiry Timer */}
          <div className="p-3 rounded-xl bg-slate-50 border border-slate-200 text-xs">
            {authSuccess || verificationStatus === 'VERIFIED' ? (
              <div className="flex items-center gap-2 text-emerald-700 font-extrabold justify-center py-1">
                <CheckCircle2 className="w-4 h-4 text-emerald-600 shrink-0" />
                <span>Verification Successful! Launching your portal...</span>
              </div>
            ) : verificationStatus === 'PENDING' ? (
              <div className="flex items-center justify-between">
                <div className="flex items-center gap-2 text-gray-700 font-bold">
                  <span className="relative flex h-2.5 w-2.5">
                    <span className="animate-ping absolute inline-flex h-full w-full rounded-full bg-emerald-400 opacity-75"></span>
                    <span className="relative inline-flex rounded-full h-2.5 w-2.5 bg-emerald-500"></span>
                  </span>
                  <span>Waiting for WhatsApp message...</span>
                </div>
                <div className="flex items-center gap-1 text-[11px] font-semibold text-gray-500">
                  <Clock className="w-3 h-3" />
                  <span>{formatTimer(timer)}</span>
                </div>
              </div>
            ) : (
              <div className="flex items-center justify-between">
                <span className="text-red-600 font-bold">Code Expired</span>
                <button
                  type="button"
                  onClick={handleRegenerateCode}
                  disabled={cooldown > 0 || isSubmitting}
                  className="text-[#005C2B] font-extrabold hover:underline text-xs cursor-pointer"
                >
                  {cooldown > 0 ? `Wait ${cooldown}s` : 'Generate New Code'}
                </button>
              </div>
            )}
          </div>

          {/* Step-by-Step Instructions */}
          <div className="text-[11px] text-gray-500 space-y-1 px-1">
            <div className="flex items-start gap-1.5">
              <span className="font-bold text-gray-700">1.</span>
              <span>Click <strong>Open WhatsApp</strong> or open WhatsApp on your phone (+91 {cleanPhone(phone)}).</span>
            </div>
            <div className="flex items-start gap-1.5">
              <span className="font-bold text-gray-700">2.</span>
              <span>Send the message <strong>VERIFY {verificationCode || '<code>'}</strong> to {whatsappNumber}.</span>
            </div>
            <div className="flex items-start gap-1.5">
              <span className="font-bold text-gray-700">3.</span>
              <span>Once received, your account will be activated here automatically!</span>
            </div>
          </div>
        </div>
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
            onClick={handleSwitchToLoginSafe}
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
