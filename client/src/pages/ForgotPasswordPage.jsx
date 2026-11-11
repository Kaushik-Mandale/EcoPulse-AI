import React, { useState } from 'react';
import { Link } from 'react-router-dom';
import { ArrowLeft, Mail, KeyRound, CheckCircle2, ShieldAlert } from 'lucide-react';
import { resetPasswordRequest } from '../services/authService';

export default function ForgotPasswordPage() {
  const [identifier, setIdentifier] = useState('');
  const [role, setRole] = useState('citizen');
  const [isSubmitting, setIsSubmitting] = useState(false);
  const [success, setSuccess] = useState(false);
  const [errorMsg, setErrorMsg] = useState('');

  const handleSubmit = async (e) => {
    e.preventDefault();
    setIsSubmitting(true);
    setErrorMsg('');
    try {
      await resetPasswordRequest({ identifier, role });
      setSuccess(true);
    } catch (err) {
      setSuccess(true); // show generic secure response
    } finally {
      setIsSubmitting(false);
    }
  };

  return (
    <div className="min-h-screen bg-[#f8faf9] flex items-center justify-center p-4 font-sans text-slate-800">
      <div className="max-w-md w-full bg-white rounded-3xl p-6 sm:p-8 border border-slate-200 shadow-md">
        <Link to="/login" className="inline-flex items-center gap-1.5 text-xs font-bold text-slate-500 hover:text-[#005C2B] mb-4">
          <ArrowLeft className="w-4 h-4" /> Back to Login
        </Link>
        
        <div className="w-12 h-12 bg-emerald-100 text-[#005C2B] rounded-2xl flex items-center justify-center mb-3">
          <KeyRound className="w-6 h-6" />
        </div>

        <h2 className="text-2xl font-black text-slate-900">Reset Your Password</h2>
        <p className="text-xs text-slate-500 font-semibold mt-1">
          Enter your registered email or employee ID and we will send password reset instructions.
        </p>

        {success ? (
          <div className="mt-6 text-center space-y-4">
            <div className="w-12 h-12 bg-emerald-100 rounded-full flex items-center justify-center mx-auto text-emerald-600">
              <CheckCircle2 className="w-6 h-6" />
            </div>
            <p className="text-xs font-bold text-emerald-800 bg-emerald-50 p-3 rounded-xl border border-emerald-200">
              If an account exists for {identifier}, password reset instructions have been dispatched via SMS/Email.
            </p>
            <Link to="/login" className="inline-block text-xs font-extrabold bg-[#005C2B] text-white px-5 py-2.5 rounded-xl">
              Return to Login
            </Link>
          </div>
        ) : (
          <form onSubmit={handleSubmit} className="mt-6 space-y-4">
            <div>
              <label className="block text-xs font-bold text-slate-700 mb-1">Your Role</label>
              <select 
                value={role} 
                onChange={(e) => setRole(e.target.value)}
                className="w-full px-3.5 py-2.5 rounded-xl border border-slate-200 bg-slate-50 text-xs font-semibold focus:outline-none focus:border-[#005C2B]"
              >
                <option value="citizen">Citizen</option>
                <option value="driver">Driver</option>
                <option value="admin">Municipal Officer / Collector</option>
              </select>
            </div>
            <div>
              <label className="block text-xs font-bold text-slate-700 mb-1">Email / Mobile / Employee ID</label>
              <input 
                type="text" 
                required 
                value={identifier}
                onChange={(e) => setIdentifier(e.target.value)}
                placeholder="e.g. priya@ecopulse.ai or EMP-4512"
                className="w-full px-3.5 py-2.5 rounded-xl border border-slate-200 bg-slate-50 text-xs font-semibold focus:outline-none focus:border-[#005C2B]"
              />
            </div>
            <button
              type="submit"
              disabled={isSubmitting}
              className="w-full py-3 rounded-xl bg-[#005C2B] hover:bg-[#004a22] text-white font-extrabold text-xs transition-colors cursor-pointer"
            >
              {isSubmitting ? 'Sending Request...' : 'Send Reset Instructions'}
            </button>
          </form>
        )}
      </div>
    </div>
  );
}
