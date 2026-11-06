import React, { useState, useEffect, useRef } from 'react';
import { 
  MessageSquare, 
  CheckCircle2, 
  Copy, 
  Check, 
  AlertCircle, 
  ExternalLink, 
  RefreshCw, 
  Unlink, 
  Clock, 
  ShieldCheck, 
  Smartphone 
} from 'lucide-react';
import { generateLinkCode, getLinkStatus, unlinkWhatsApp } from '../services/whatsappLinkService';

const WhatsAppLinkCard = ({ user }) => {
  const [status, setStatus] = useState('NOT_LINKED'); // NOT_LINKED, GENERATING_CODE, CODE_GENERATED, CODE_EXPIRED, LINKED, ERROR
  const [linkData, setLinkData] = useState(null); // { code, expires_in, expires_at, bot_phone, instructions }
  const [linkStatus, setLinkStatus] = useState(null); // { is_linked, whatsapp_phone_masked, linked_at }
  const [timeLeft, setTimeLeft] = useState(0);
  const [copied, setCopied] = useState(false);
  const [errorMsg, setErrorMsg] = useState('');
  const [loading, setLoading] = useState(false);
  const [generating, setGenerating] = useState(false);
  const timerRef = useRef(null);
  const pollRef = useRef(null);
  const mountedRef = useRef(true);

  // Track mounted state to prevent setState after unmount
  useEffect(() => {
    mountedRef.current = true;
    return () => {
      mountedRef.current = false;
      if (timerRef.current) clearInterval(timerRef.current);
      if (pollRef.current) clearInterval(pollRef.current);
    };
  }, []);

  // Load initial WhatsApp link status from backend
  const checkStatus = async () => {
    try {
      const data = await getLinkStatus();
      if (!mountedRef.current) return;
      setLinkStatus(data);
      if (data.is_linked) {
        setStatus('LINKED');
        if (timerRef.current) clearInterval(timerRef.current);
        if (pollRef.current) clearInterval(pollRef.current);
      } else if (status === 'LINKED') {
        setStatus('NOT_LINKED');
      }
    } catch (err) {
      if (!mountedRef.current) return;
      // 401 is handled globally by api.js interceptor; show error for other failures
      if (err?.response?.status !== 401) {
        console.error('Failed to fetch WhatsApp link status:', err);
        setErrorMsg('Could not load link status. Please refresh the page.');
        setStatus('ERROR');
      }
    }
  };

  useEffect(() => {
    checkStatus();
  }, []);

  // Timer countdown + background polling — started once when CODE_GENERATED
  // Depends only on [status] to avoid restarting on every timeLeft tick
  useEffect(() => {
    if (status !== 'CODE_GENERATED') return;

    // Clear any previous intervals before starting new ones
    if (timerRef.current) clearInterval(timerRef.current);
    if (pollRef.current) clearInterval(pollRef.current);

    // Countdown timer
    timerRef.current = setInterval(() => {
      if (!mountedRef.current) return;
      setTimeLeft((prev) => {
        if (prev <= 1) {
          clearInterval(timerRef.current);
          if (mountedRef.current) setStatus('CODE_EXPIRED');
          return 0;
        }
        return prev - 1;
      });
    }, 1000);

    // Background poll every 5 s to detect successful linking
    pollRef.current = setInterval(async () => {
      if (!mountedRef.current) return;
      try {
        const res = await getLinkStatus();
        if (!mountedRef.current) return;
        if (res.is_linked) {
          setLinkStatus(res);
          setStatus('LINKED');
          clearInterval(pollRef.current);
          clearInterval(timerRef.current);
        }
      } catch (_) {
        // ignore transient poll errors
      }
    }, 5000);

    return () => {
      if (timerRef.current) clearInterval(timerRef.current);
      if (pollRef.current) clearInterval(pollRef.current);
    };
  }, [status]);

  const handleGenerate = async () => {
    if (generating) return; // prevent duplicate requests
    setGenerating(true);
    setStatus('GENERATING_CODE');
    setErrorMsg('');
    try {
      const res = await generateLinkCode();
      if (!mountedRef.current) return;
      // Backend returns both `link_code` and `code` for compatibility — prefer `code`
      const displayCode = res.code || res.link_code;
      setLinkData({ ...res, code: displayCode });
      setTimeLeft(res.expires_in || 600);
      setStatus('CODE_GENERATED');
    } catch (err) {
      if (!mountedRef.current) return;
      const detail = err.response?.data?.detail || err.message || 'Failed to generate link code';
      setErrorMsg(detail);
      setStatus('ERROR');
    } finally {
      if (mountedRef.current) setGenerating(false);
    }
  };

  const handleCopy = () => {
    if (!linkData?.code) return;
    const textToCopy = `LINK ${linkData.code}`;
    navigator.clipboard.writeText(textToCopy);
    setCopied(true);
    setTimeout(() => setCopied(false), 2500);
  };

  const handleUnlink = async () => {
    if (!window.confirm('Are you sure you want to disconnect your WhatsApp account? You will stop receiving updates on WhatsApp.')) {
      return;
    }
    setLoading(true);
    setErrorMsg('');
    try {
      await unlinkWhatsApp();
      setLinkStatus({ is_linked: false });
      setLinkData(null);
      setStatus('NOT_LINKED');
    } catch (err) {
      setErrorMsg(err.response?.data?.detail || err.message || 'Failed to unlink account');
    } finally {
      setLoading(false);
    }
  };

  const formatSeconds = (sec) => {
    const mins = Math.floor(sec / 60);
    const secs = sec % 60;
    return `${mins}:${secs < 10 ? '0' : ''}${secs}`;
  };

  const botNumberClean = (linkData?.bot_phone || '919876543210').replace(/[^0-9]/g, '');
  const waDirectUrl = linkData?.code 
    ? `https://wa.me/${botNumberClean}?text=${encodeURIComponent(`LINK ${linkData.code}`)}`
    : `https://wa.me/${botNumberClean}`;

  return (
    <div className="bg-white dark:bg-slate-800 rounded-2xl border border-slate-200 dark:border-slate-700 p-6 shadow-sm">
      <div className="flex items-start justify-between">
        <div className="flex items-center space-x-3">
          <div className="w-12 h-12 rounded-xl bg-emerald-50 dark:bg-emerald-950/40 text-emerald-600 dark:text-emerald-400 flex items-center justify-center">
            <MessageSquare className="w-6 h-6" />
          </div>
          <div>
            <h3 className="font-semibold text-lg text-slate-900 dark:text-white flex items-center gap-2">
              Connect WhatsApp
              {status === 'LINKED' && (
                <span className="inline-flex items-center px-2 py-0.5 rounded-full text-xs font-medium bg-emerald-100 text-emerald-800 dark:bg-emerald-900/40 dark:text-emerald-300">
                  <ShieldCheck className="w-3 h-3 mr-1" /> Linked
                </span>
              )}
            </h3>
            <p className="text-sm text-slate-500 dark:text-slate-400">
              EcoPulse AI · Dhule Municipal Waste Management
            </p>
          </div>
        </div>

        {status === 'LINKED' && (
          <button
            onClick={handleUnlink}
            disabled={loading}
            className="text-xs text-rose-600 hover:text-rose-700 dark:text-rose-400 font-medium flex items-center gap-1 border border-rose-200 dark:border-rose-900/50 px-2.5 py-1.5 rounded-lg hover:bg-rose-50 dark:hover:bg-rose-950/20 transition-colors"
          >
            <Unlink className="w-3.5 h-3.5" />
            {loading ? 'Disconnecting...' : 'Disconnect'}
          </button>
        )}
      </div>

      {/* Profile info */}
      <div className="mt-4 pt-4 border-t border-slate-100 dark:border-slate-700/60 flex flex-wrap gap-4 text-xs text-slate-600 dark:text-slate-400">
        <div className="flex items-center gap-1.5">
          <Smartphone className="w-3.5 h-3.5 text-slate-400" />
          <span>Registered Phone: <strong className="text-slate-800 dark:text-slate-200">{user?.phone || 'Not set'}</strong></span>
        </div>
        {linkStatus?.is_linked && linkStatus?.whatsapp_phone_masked && (
          <div className="flex items-center gap-1.5">
            <MessageSquare className="w-3.5 h-3.5 text-emerald-500" />
            <span>Linked WhatsApp: <strong className="text-emerald-700 dark:text-emerald-300">{linkStatus.whatsapp_phone_masked}</strong></span>
          </div>
        )}
      </div>

      {/* State: ERROR */}
      {status === 'ERROR' && (
        <div className="mt-4 p-3 bg-rose-50 dark:bg-rose-950/30 border border-rose-200 dark:border-rose-900/40 rounded-xl flex items-start gap-2.5 text-xs text-rose-700 dark:text-rose-300">
          <AlertCircle className="w-4 h-4 flex-shrink-0 mt-0.5" />
          <div className="flex-1">
            <p className="font-semibold">Unable to process request</p>
            <p className="mt-0.5">{errorMsg}</p>
            <button 
              onClick={() => setStatus('NOT_LINKED')} 
              className="mt-2 text-xs font-medium underline text-rose-800 dark:text-rose-200"
            >
              Try Again
            </button>
          </div>
        </div>
      )}

      {/* State: NOT_LINKED */}
      {status === 'NOT_LINKED' && (
        <div className="mt-4 space-y-3">
          <p className="text-sm text-slate-600 dark:text-slate-300">
            Link your WhatsApp number to report garbage accumulation directly through WhatsApp chat, track trucks, and earn EcoCoins.
          </p>
          <div className="bg-slate-50 dark:bg-slate-900/50 p-3 rounded-xl border border-slate-100 dark:border-slate-800 text-xs text-slate-500 space-y-1">
            <p className="font-medium text-slate-700 dark:text-slate-300">How flexible linking works:</p>
            <p>• Your WhatsApp number does not have to match your registration number.</p>
            <p>• A secure, one-time verification token links any WhatsApp device to this citizen profile.</p>
          </div>
          <button
            onClick={handleGenerate}
            className="w-full py-2.5 px-4 bg-emerald-600 hover:bg-emerald-700 text-white text-sm font-medium rounded-xl flex items-center justify-center gap-2 shadow-sm transition-colors"
          >
            <MessageSquare className="w-4 h-4" />
            Generate WhatsApp Linking Code
          </button>
        </div>
      )}

      {/* State: GENERATING_CODE */}
      {status === 'GENERATING_CODE' && (
        <div className="mt-6 py-8 flex flex-col items-center justify-center space-y-3">
          <RefreshCw className="w-8 h-8 text-emerald-600 animate-spin" />
          <p className="text-sm font-medium text-slate-600 dark:text-slate-300">Generating secure one-time linking token...</p>
        </div>
      )}

      {/* State: CODE_GENERATED */}
      {status === 'CODE_GENERATED' && linkData && (
        <div className="mt-4 space-y-4">
          <div className="bg-emerald-50 dark:bg-emerald-950/30 border border-emerald-200 dark:border-emerald-900/40 p-4 rounded-xl">
            <div className="flex items-center justify-between text-xs text-emerald-800 dark:text-emerald-300 font-medium mb-1.5">
              <span>Your One-Time Code</span>
              <span className="flex items-center gap-1 font-mono text-emerald-600 dark:text-emerald-400">
                <Clock className="w-3.5 h-3.5" /> Expires in {formatSeconds(timeLeft)}
              </span>
            </div>

            <div className="flex items-center gap-2 bg-white dark:bg-slate-900 border border-emerald-300 dark:border-emerald-800/60 rounded-lg p-2.5">
              <span className="font-mono text-base font-bold tracking-wider text-emerald-700 dark:text-emerald-400 flex-1 truncate">
                LINK {linkData.code}
              </span>
              <button
                onClick={handleCopy}
                className="px-3 py-1.5 bg-emerald-100 hover:bg-emerald-200 dark:bg-emerald-900/60 dark:hover:bg-emerald-800 text-emerald-800 dark:text-emerald-200 rounded-md text-xs font-medium flex items-center gap-1 transition-colors"
              >
                {copied ? <Check className="w-3.5 h-3.5 text-emerald-600" /> : <Copy className="w-3.5 h-3.5" />}
                {copied ? 'Copied' : 'Copy'}
              </button>
            </div>
          </div>

          <div className="space-y-2 text-xs text-slate-600 dark:text-slate-400">
            <p className="font-semibold text-slate-800 dark:text-slate-200">Next Steps:</p>
            <ol className="list-decimal list-inside space-y-1 pl-1">
              <li>Open WhatsApp on your mobile or desktop.</li>
              <li>Send the text <code className="bg-slate-100 dark:bg-slate-900 px-1 py-0.5 rounded text-emerald-600 font-mono">LINK {linkData.code}</code> to our municipal bot.</li>
              <li>You will receive an instant welcome message with the 9-option municipal service menu.</li>
            </ol>
          </div>

          <div className="flex gap-2">
            <a
              href={waDirectUrl}
              target="_blank"
              rel="noopener noreferrer"
              className="flex-1 py-2.5 px-4 bg-emerald-600 hover:bg-emerald-700 text-white text-sm font-medium rounded-xl flex items-center justify-center gap-2 shadow-sm transition-colors text-center"
            >
              <ExternalLink className="w-4 h-4" />
              Open in WhatsApp
            </a>
            <button
              onClick={checkStatus}
              title="Refresh status"
              className="p-2.5 border border-slate-200 dark:border-slate-700 hover:bg-slate-50 dark:hover:bg-slate-700 rounded-xl text-slate-600 dark:text-slate-300"
            >
              <RefreshCw className="w-4 h-4" />
            </button>
          </div>
        </div>
      )}

      {/* State: CODE_EXPIRED */}
      {status === 'CODE_EXPIRED' && (
        <div className="mt-4 p-4 bg-amber-50 dark:bg-amber-950/30 border border-amber-200 dark:border-amber-900/40 rounded-xl space-y-3">
          <div className="flex items-center gap-2 text-amber-800 dark:text-amber-300 text-xs font-semibold">
            <Clock className="w-4 h-4" />
            <span>Linking Code Expired</span>
          </div>
          <p className="text-xs text-slate-600 dark:text-slate-400">
            For security, one-time verification tokens expire after 10 minutes. Please generate a fresh token to link your account.
          </p>
          <button
            onClick={handleGenerate}
            className="w-full py-2 px-3 bg-amber-600 hover:bg-amber-700 text-white text-xs font-medium rounded-lg transition-colors"
          >
            Generate New Code
          </button>
        </div>
      )}

      {/* State: LINKED */}
      {status === 'LINKED' && (
        <div className="mt-4 space-y-3">
          <div className="p-3 bg-emerald-50 dark:bg-emerald-950/30 border border-emerald-200 dark:border-emerald-900/40 rounded-xl flex items-center gap-3">
            <CheckCircle2 className="w-5 h-5 text-emerald-600 dark:text-emerald-400 flex-shrink-0" />
            <div className="text-xs">
              <p className="font-semibold text-emerald-900 dark:text-emerald-200">WhatsApp Account Connected</p>
              <p className="text-emerald-700 dark:text-emerald-400 mt-0.5">
                Send photos directly to WhatsApp to report civic issues. All complaints will sync with this dashboard.
              </p>
            </div>
          </div>

          <div className="text-xs text-slate-500 dark:text-slate-400 flex items-center justify-between pt-1">
            <span>Linked on: {linkStatus?.linked_at ? new Date(linkStatus.linked_at).toLocaleDateString() : 'Active'}</span>
            <button
              onClick={checkStatus}
              className="text-slate-600 hover:text-slate-800 dark:text-slate-300 flex items-center gap-1 font-medium"
            >
              <RefreshCw className="w-3 h-3" /> Refresh
            </button>
          </div>
        </div>
      )}
    </div>
  );
};

export default WhatsAppLinkCard;

