import React, { useState } from 'react';
import { Link, useNavigate, useSearchParams } from 'react-router-dom';
import { AnimatePresence, motion } from 'framer-motion';
import { UserCheck, Truck, ShoppingBag, UserPlus, ShieldCheck } from 'lucide-react';
import CitizenPortalLogin from './CitizenPortalLogin';
import DriverPortalLogin from './DriverPortalLogin';
import CollectorPortalLogin from './CollectorPortalLogin';
import ForgotPasswordModal from './ForgotPasswordModal';

const ThreePortalLogins = ({ onSuccess }) => {
  const navigate = useNavigate();
  const [searchParams] = useSearchParams();
  const requestedPortal = searchParams.get('portal')?.toLowerCase();
  const requestedFieldRole = ['driver', 'collector'].includes(requestedPortal) ? requestedPortal : 'driver';
  const [activePortal, setActivePortal] = useState(['driver', 'collector'].includes(requestedPortal) ? 'field' : requestedPortal === 'admin' ? 'admin' : 'citizen');
  const [fieldRole, setFieldRole] = useState(requestedFieldRole);
  const [isForgotPasswordOpen, setIsForgotPasswordOpen] = useState(false);

  return (
    <div className="w-full px-2 sm:px-4">
      <div className="mx-auto mb-5 w-full max-w-md sm:max-w-lg">
        <div role="tablist" aria-label="Sign-in portal" className="grid w-full grid-cols-3 gap-1 rounded-2xl border border-slate-200/90 bg-white/95 p-1.5 shadow-md">
          <button type="button" role="tab" aria-selected={activePortal === 'citizen'} onClick={() => setActivePortal('citizen')} className={`flex items-center justify-center gap-1.5 rounded-xl px-2 py-2.5 text-xs font-black transition ${activePortal === 'citizen' ? 'bg-emerald-600 text-white' : 'text-slate-600 hover:bg-emerald-50'}`}><UserCheck size={16}/><span>Citizen</span></button>
          <button type="button" role="tab" aria-selected={activePortal === 'field'} onClick={() => setActivePortal('field')} className={`flex items-center justify-center gap-1.5 rounded-xl px-2 py-2.5 text-xs font-black transition ${activePortal === 'field' ? 'bg-[#005C2B] text-white' : 'text-slate-600 hover:bg-emerald-50'}`}><Truck size={16}/><span>Field Operations</span></button>
          <button type="button" role="tab" aria-selected={activePortal === 'admin'} onClick={() => setActivePortal('admin')} className={`flex items-center justify-center gap-1.5 rounded-xl px-2 py-2.5 text-xs font-black transition ${activePortal === 'admin' ? 'bg-orange-600 text-white' : 'text-slate-600 hover:bg-orange-50'}`}><ShieldCheck size={16}/><span>Admin</span></button>
        </div>

        <div className="mt-2 flex min-h-8 items-center justify-between gap-2 px-2 text-[11px] font-bold text-slate-500">
          {activePortal === 'citizen' ? <span>Citizen services and complaint reporting</span> : activePortal === 'field' ? <span>Employee sign-in · destination follows verified account role</span> : <span>Administrator accounts require MFA</span>}
          {activePortal === 'citizen' && <Link to="/signup" className="flex items-center gap-1 font-black text-[#005C2B] hover:underline"><UserPlus size={13}/>Create account</Link>}
        </div>
      </div>

      {activePortal === 'field' && <div role="tablist" aria-label="Field Operations sign-in method" className="mx-auto mb-3 grid max-w-md grid-cols-2 gap-2 rounded-xl border border-slate-200 bg-white p-1.5">
        <button type="button" role="tab" aria-selected={fieldRole === 'driver'} onClick={() => setFieldRole('driver')} className={`flex items-center justify-center gap-2 rounded-lg px-3 py-2 text-xs font-bold ${fieldRole === 'driver' ? 'bg-emerald-50 text-emerald-900' : 'text-slate-600 hover:bg-slate-50'}`}><Truck size={15}/>Driver</button>
        <button type="button" role="tab" aria-selected={fieldRole === 'collector'} onClick={() => setFieldRole('collector')} className={`flex items-center justify-center gap-2 rounded-lg px-3 py-2 text-xs font-bold ${fieldRole === 'collector' ? 'bg-emerald-50 text-emerald-900' : 'text-slate-600 hover:bg-slate-50'}`}><ShoppingBag size={15}/>Collector</button>
      </div>}

      <AnimatePresence mode="wait">
        <motion.div key={`${activePortal}-${fieldRole}`} initial={{ opacity: 0, y: 12 }} animate={{ opacity: 1, y: 0 }} exit={{ opacity: 0, y: -8 }} transition={{ duration: 0.2 }} className="mx-auto grid w-full max-w-md grid-cols-1 sm:max-w-lg">
          {activePortal === 'citizen' && <CitizenPortalLogin onSuccess={onSuccess} onSwitchToSignup={() => navigate('/signup')}/>}
          {activePortal === 'field' && fieldRole === 'driver' && <DriverPortalLogin onSuccess={onSuccess} onOpenForgotPassword={() => setIsForgotPasswordOpen(true)}/>}
          {activePortal === 'field' && fieldRole === 'collector' && <CollectorPortalLogin defaultRole="collector" restrictRole portalTitle="Field Operations Portal" onSuccess={onSuccess} onOpenForgotPassword={() => setIsForgotPasswordOpen(true)}/>}
          {activePortal === 'admin' && <CollectorPortalLogin defaultRole="admin" restrictRole portalTitle="Municipal Admin Portal" onSuccess={onSuccess} onOpenForgotPassword={() => setIsForgotPasswordOpen(true)}/>}
        </motion.div>
      </AnimatePresence>

      <ForgotPasswordModal isOpen={isForgotPasswordOpen} onClose={() => setIsForgotPasswordOpen(false)} onBackToLogin={() => setIsForgotPasswordOpen(false)}/>
    </div>
  );
};

export default ThreePortalLogins;
