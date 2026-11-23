import React, { useState } from 'react';
import { Link, useNavigate } from 'react-router-dom';
import { ArrowLeft, Smartphone, CheckCircle2, ShieldAlert } from 'lucide-react';

import { useLocation } from 'react-router-dom';
import api from '../services/api';

export default function OtpVerifyPage() {
  const navigate = useNavigate();
  const location = useLocation();
  const [otp, setOtp] = useState(['', '', '', '', '', '']);
  const [mobile] = useState(location.state?.phone || '');
  const [isSubmitting, setIsSubmitting] = useState(false);
  const [errorMsg, setErrorMsg] = useState('');

  const handleChange = (val, idx) => {
    const newOtp = [...otp];
    newOtp[idx] = val.replace(/\D/g, '').slice(-1);
    setOtp(newOtp);
    if (val && idx < 3) {
      document.getElementById(`otp-input-${idx + 1}`)?.focus();
    }
  };

  const handleVerify = async (e) => {
    e.preventDefault();
    setIsSubmitting(true);
    setErrorMsg('');
    const code = otp.join('');
    if (!mobile || code.length !== 6) {
      setErrorMsg('Enter the six-digit code sent to your registered mobile number.');
      setIsSubmitting(false);
      return;
    }
    try {
      const res = await api.post('/auth/verify-otp', {
        phone: mobile,
        otp: code,
        role: location.state?.role || 'citizen'
      });
      if (res.data?.access_token) {
        localStorage.setItem('ecopulse_token', res.data.access_token);
        localStorage.setItem('ecopulse_user', JSON.stringify(res.data.user));
        const role = res.data.user?.role?.toLowerCase();
        if (role === 'driver' || role === 'collector') navigate('/field-operations');
        else if (role === 'admin') navigate(res.data.user?.is_super_admin ? '/super-admin' : '/admin');
        else if (role === 'citizen') navigate('/citizen');
        else navigate('/login', { replace: true });
        return;
      }
      throw new Error('Verification did not return an authenticated session.');
    } catch (err) {
      setErrorMsg(err.response?.data?.detail || err.message || 'Verification failed. Request a new code and try again.');
    } finally {
      setIsSubmitting(false);
    }
  };

  return (
    <div className="min-h-screen bg-[#f8faf9] flex items-center justify-center p-4 font-sans text-slate-800">
      <div className="max-w-md w-full bg-white rounded-3xl p-6 sm:p-8 border border-slate-200 shadow-md text-center">
        <Link to="/login" className="inline-flex items-center gap-1.5 text-xs font-bold text-slate-500 hover:text-[#005C2B] mb-4">
          <ArrowLeft className="w-4 h-4" /> Back to Login
        </Link>
        <div className="w-12 h-12 bg-emerald-100 text-[#005C2B] rounded-2xl flex items-center justify-center mx-auto mb-3">
          <Smartphone className="w-6 h-6" />
        </div>
        <h2 className="text-2xl font-black text-slate-900">OTP Verification</h2>
        <p className="text-xs text-slate-500 font-semibold mt-1">
          {mobile ? <>Enter the six-digit code sent to <span className="font-bold text-slate-800">{mobile}</span></> : 'Open this page from the OTP sign-in flow to continue.'}
        </p>

        <form onSubmit={handleVerify} className="mt-6 space-y-4">
          <div className="flex justify-center gap-2.5">
            {otp.map((digit, idx) => (
              <input 
                key={idx}
                id={`otp-input-${idx}`}
                type="text" 
                maxLength="1"
                value={digit}
                onChange={(e) => handleChange(e.target.value, idx)}
                inputMode="numeric"
                className="w-12 h-14 text-center font-mono text-xl font-extrabold rounded-xl border border-slate-200 bg-slate-50 focus:outline-none focus:border-[#005C2B] focus:bg-white"
              />
            ))}
          </div>
          {errorMsg && <p role="alert" className="text-xs font-semibold text-red-700">{errorMsg}</p>}
          <button
            type="submit"
            disabled={isSubmitting}
            className="w-full py-3 rounded-xl bg-[#005C2B] hover:bg-[#004a22] text-white font-extrabold text-xs transition-colors cursor-pointer"
          >
            {isSubmitting ? 'Verifying OTP...' : 'Verify & Continue'}
          </button>
        </form>
      </div>
    </div>
  );
}
