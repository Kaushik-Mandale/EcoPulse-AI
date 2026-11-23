import React, { useEffect, useState } from 'react';
import { Link } from 'react-router-dom';
import {
  activateAdministratorAccount,
  activateCollectorAccount,
  activateDriverAccount,
  confirmMfaEnrollment,
  sendOtp,
  startMfaEnrollment,
  validateInvitation
} from '../services/authService';

const invitationMessages = {
  invalid: 'This invitation link is invalid. Ask the municipal administrator to issue a new invitation.',
  expired: 'This invitation has expired. Ask the municipal administrator to issue a new invitation.',
  revoked: 'This invitation has been revoked. Contact the municipal administrator for assistance.',
  used: 'This invitation has already been used. Sign in or contact the municipal administrator.'
};

const InvitationActivationPage = () => {
  const [invitationStatus, setInvitationStatus] = useState('loading');
  const [token, setToken] = useState('');
  const [role, setRole] = useState('');
  const [employeeId, setEmployeeId] = useState('');
  const [phone, setPhone] = useState('');
  const [otp, setOtp] = useState('');
  const [challengeId, setChallengeId] = useState('');
  const [password, setPassword] = useState('');
  const [otpSent, setOtpSent] = useState(false);
  const [adminActivated, setAdminActivated] = useState(false);
  const [mfaSecret, setMfaSecret] = useState('');
  const [mfaCode, setMfaCode] = useState('');
  const [complete, setComplete] = useState(false);
  const [busy, setBusy] = useState(false);
  const [errorMessage, setErrorMessage] = useState('');

  useEffect(() => {
    const handleInvitationLocation = () => {
      const invitationToken = new URLSearchParams(window.location.hash.slice(1)).get('token');
      window.history.replaceState(
        window.history.state,
        '',
        `${window.location.pathname}${window.location.search}`
      );
      setInvitationStatus('loading');
      setComplete(false);
      setAdminActivated(false);
      setMfaSecret('');
      setErrorMessage('');
      setToken('');
      setRole('');
      setEmployeeId('');

      if (!invitationToken) {
        setInvitationStatus('invalid');
        return;
      }

      setToken(invitationToken);
      validateInvitation(invitationToken)
        .then((result) => {
          setInvitationStatus(result.status);
          setRole(result.role || '');
          setEmployeeId(result.employee_id || '');
        })
        .catch((error) => {
          setInvitationStatus('invalid');
          setErrorMessage(error.message || 'The invitation could not be validated.');
        });
    };

    handleInvitationLocation();
    window.addEventListener('hashchange', handleInvitationLocation);
    return () => window.removeEventListener('hashchange', handleInvitationLocation);
  }, []);

  const handleSendOtp = async () => {
    setBusy(true);
    setErrorMessage('');
    try {
      const challenge = await sendOtp({ phone: phone.trim(), purpose: 'activation' });
      setChallengeId(challenge.challenge_id);
      setOtpSent(true);
    } catch (error) {
      setErrorMessage(error.message || 'A verification code could not be sent.');
    } finally {
      setBusy(false);
    }
  };

  const validatePassword = () => {
    const byteLength = new TextEncoder().encode(password).length;
    if (byteLength < 12 || byteLength > 72) {
      setErrorMessage('Choose a password between 12 and 72 UTF-8 bytes.');
      return false;
    }
    return true;
  };

  const handleDriverActivation = async (event) => {
    event.preventDefault();
    setErrorMessage('');
    if (!otpSent || !challengeId) {
      setErrorMessage('Verify the invited mobile number before activating the account.');
      return;
    }
    if (!validatePassword()) return;

    setBusy(true);
    try {
      await activateDriverAccount({
        token,
        phone: phone.trim(),
        otp: otp.trim(),
        challengeId,
        password
      });
      setComplete(true);
      setToken('');
      setPassword('');
      setOtp('');
    } catch (error) {
      setErrorMessage(error.message || 'The driver account could not be activated.');
    } finally {
      setBusy(false);
    }
  };

  const handleAdministratorActivation = async (event) => {
    event.preventDefault();
    setErrorMessage('');
    if (!validatePassword()) return;

    setBusy(true);
    try {
      if (!adminActivated) {
        if (role === 'collector') {
          await activateCollectorAccount({ token, password });
        } else {
          await activateAdministratorAccount({ token, password });
        }
        setAdminActivated(true);
      }
      const enrollment = await startMfaEnrollment({ employeeId, password });
      setMfaSecret(enrollment.secret);
    } catch (error) {
      setErrorMessage(error.message || 'Account activation or MFA setup could not be completed.');
    } finally {
      setBusy(false);
    }
  };

  const handleConfirmMfa = async (event) => {
    event.preventDefault();
    setErrorMessage('');
    if (!/^\d{6}$/.test(mfaCode)) {
      setErrorMessage('Enter the six-digit code from your authenticator app.');
      return;
    }

    setBusy(true);
    try {
      await confirmMfaEnrollment({ employeeId, password, code: mfaCode });
      setComplete(true);
      setToken('');
      setPassword('');
      setMfaSecret('');
      setMfaCode('');
    } catch (error) {
      setErrorMessage(error.message || 'The authenticator code could not be verified.');
    } finally {
      setBusy(false);
    }
  };

  const inputClass = 'mt-1 w-full rounded-lg border border-slate-300 px-3 py-2 text-sm';

  return (
    <main className="min-h-screen bg-slate-50 px-4 py-12">
      <section className="mx-auto max-w-lg rounded-2xl border border-slate-200 bg-white p-6 shadow-xl sm:p-8">
        <p className="text-sm font-extrabold text-emerald-800">EcoPulse AI</p>
        <h1 className="mt-2 text-2xl font-black text-slate-900">Municipal account activation</h1>

        {invitationStatus === 'loading' && (
          <p className="mt-5 text-sm text-slate-600">Validating your secure invitation…</p>
        )}

        {invitationStatus !== 'loading' && invitationStatus !== 'valid' && (
          <p role="alert" className="mt-5 rounded-lg bg-amber-50 p-4 text-sm font-semibold text-amber-900">
            {errorMessage || invitationMessages[invitationStatus] || invitationMessages.invalid}
          </p>
        )}

        {invitationStatus === 'valid' && complete && (
          <div className="mt-5 rounded-lg bg-emerald-50 p-4 text-sm font-semibold text-emerald-900">
            {role === 'driver'
              ? 'Your driver account is active. Sign in with your Employee ID and new password.'
              : role === 'collector'
                ? 'Your collector account is active and MFA is enrolled. Sign in with your Employee ID, password, and authenticator code.'
                : 'Your administrator account is active and MFA is enrolled. Sign in with your Employee ID, password, and authenticator code.'}
            <Link
              className="mt-3 inline-block font-bold underline"
              to={`/login?portal=${role === 'driver' ? 'driver' : 'collector'}`}
            >
              Continue to sign in
            </Link>
          </div>
        )}

        {invitationStatus === 'valid' && !complete && role === 'driver' && (
          <form onSubmit={handleDriverActivation} className="mt-5 space-y-4">
            {errorMessage && <p role="alert" className="rounded-lg bg-red-50 p-3 text-sm text-red-800">{errorMessage}</p>}
            <label className="block text-sm font-semibold text-slate-700">
              Invited mobile number
              <input
                className={inputClass}
                type="tel"
                autoComplete="tel"
                value={phone}
                onChange={(event) => setPhone(event.target.value)}
                required
              />
            </label>
            <button
              type="button"
              onClick={handleSendOtp}
              disabled={busy || !phone.trim()}
              className="rounded-lg bg-blue-700 px-4 py-2 text-sm font-bold text-white disabled:opacity-50"
            >
              {busy ? 'Please wait…' : otpSent ? 'Send another verification code' : 'Send verification code'}
            </button>
            {otpSent && (
              <>
                <label className="block text-sm font-semibold text-slate-700">
                  Verification code
                  <input
                    className={inputClass}
                    inputMode="numeric"
                    autoComplete="one-time-code"
                    value={otp}
                    onChange={(event) => setOtp(event.target.value.replace(/\D/g, '').slice(0, 6))}
                    required
                  />
                </label>
                <label className="block text-sm font-semibold text-slate-700">
                  Create password
                  <input
                    className={inputClass}
                    type="password"
                    autoComplete="new-password"
                    minLength={12}
                    value={password}
                    onChange={(event) => setPassword(event.target.value)}
                    required
                  />
                  <span className="mt-1 block text-xs font-normal text-slate-500">Use 12–72 UTF-8 bytes.</span>
                </label>
                <button
                  type="submit"
                  disabled={busy || !otp || !password}
                  className="w-full rounded-lg bg-emerald-800 px-4 py-3 text-sm font-bold text-white disabled:opacity-50"
                >
                  {busy ? 'Activating…' : 'Verify and activate account'}
                </button>
              </>
            )}
          </form>
        )}

        {invitationStatus === 'valid' && !complete && (role === 'admin' || role === 'collector') && (
          <div className="mt-5">
            {errorMessage && <p role="alert" className="mb-4 rounded-lg bg-red-50 p-3 text-sm text-red-800">{errorMessage}</p>}
            {!mfaSecret ? (
              <form onSubmit={handleAdministratorActivation} className="space-y-4">
                <label className="block text-sm font-semibold text-slate-700">
                  Authorized Employee ID
                  <input className={inputClass} value={employeeId} readOnly />
                </label>
                <label className="block text-sm font-semibold text-slate-700">
                  Create password
                  <input
                    className={inputClass}
                    type="password"
                    autoComplete="new-password"
                    minLength={12}
                    value={password}
                    onChange={(event) => setPassword(event.target.value)}
                    required
                  />
                  <span className="mt-1 block text-xs font-normal text-slate-500">Use 12–72 UTF-8 bytes.</span>
                </label>
                <button
                  type="submit"
                  disabled={busy || !password}
                  className="w-full rounded-lg bg-emerald-800 px-4 py-3 text-sm font-bold text-white disabled:opacity-50"
                >
                  {busy ? 'Starting secure setup…' : adminActivated ? 'Retry authenticator setup' : 'Activate and enroll MFA'}
                </button>
              </form>
            ) : (
              <form onSubmit={handleConfirmMfa} className="space-y-4">
                <p className="text-sm text-slate-700">
                  Add this key to your approved authenticator app. It is shown only during enrollment.
                </p>
                <code className="block break-all rounded-lg bg-slate-100 p-3 text-sm font-bold">{mfaSecret}</code>
                <label className="block text-sm font-semibold text-slate-700">
                  Authenticator code
                  <input
                    className={inputClass}
                    inputMode="numeric"
                    autoComplete="one-time-code"
                    value={mfaCode}
                    onChange={(event) => setMfaCode(event.target.value.replace(/\D/g, '').slice(0, 6))}
                    required
                  />
                </label>
                <button
                  type="submit"
                  disabled={busy || mfaCode.length !== 6}
                  className="w-full rounded-lg bg-emerald-800 px-4 py-3 text-sm font-bold text-white disabled:opacity-50"
                >
                  {busy ? 'Verifying…' : 'Confirm MFA enrollment'}
                </button>
              </form>
            )}
          </div>
        )}

        <Link className="mt-6 inline-block text-sm font-semibold text-slate-600 underline" to="/login">
          Return to sign in
        </Link>
      </section>
    </main>
  );
};

export default InvitationActivationPage;
