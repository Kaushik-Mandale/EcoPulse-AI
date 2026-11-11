import React, { useState, useEffect } from 'react';
import { Link, useNavigate } from 'react-router-dom';
import { motion, AnimatePresence } from 'framer-motion';
import { ArrowLeft, Sparkles, Shield, Zap, Leaf, Recycle, Building2, Users, Star } from 'lucide-react';
import SignupForm from './SignupForm';
import ForgotPasswordModal from './ForgotPasswordModal';

const SplitAuthLayout = ({ mode = 'signup', onSuccessNavigation }) => {
  const navigate = useNavigate();
  const [activeTab, setActiveTab] = useState(mode); // 'signup'
  const [isForgotPasswordOpen, setIsForgotPasswordOpen] = useState(false);
  const [activeRole, setActiveRole] = useState('citizen'); // 'citizen' | 'driver' | 'collector' | 'admin'

  useEffect(() => {
    // If ever loaded with login mode, navigate immediately to canonical /login
    if (mode === 'login') {
      navigate('/login', { replace: true });
    }
  }, [mode, navigate]);

  // Illustration based on role selection
  const getRoleIllustration = () => {
    if (activeRole === 'driver') return '/driver.png';
    if (activeRole === 'collector') return '/admin.png';
    return '/complete-right.png';
  };

  return (
    <div className="relative min-h-screen lg:h-screen lg:max-h-screen w-full flex flex-col lg:flex-row overflow-y-auto lg:overflow-hidden bg-[#f4faf6] font-sans selection:bg-[#005C2B] selection:text-white">
      
      {/* Seamless Landing Page Background (/background_1.png) */}
      <div
        className="absolute inset-0 z-0 bg-no-repeat bg-cover bg-center opacity-95 pointer-events-none"
        style={{ backgroundImage: `url('/background_1.png')` }}
      />

      {/* Soft Gradient Overlay */}
      <div className="absolute inset-0 z-0 bg-gradient-to-br from-white/90 via-white/75 to-emerald-50/50 pointer-events-none" />

      {/* Animated Floating Ambient Orbs */}
      <motion.div
        animate={{
          scale: [1, 1.2, 1],
          opacity: [0.35, 0.55, 0.35],
        }}
        transition={{ duration: 10, repeat: Infinity, ease: 'easeInOut' }}
        className="absolute top-1/4 -left-20 w-72 sm:w-96 h-72 sm:h-96 bg-[#005C2B]/15 rounded-full blur-3xl pointer-events-none"
      />
      <motion.div
        animate={{
          scale: [1.2, 1, 1.2],
          opacity: [0.25, 0.45, 0.25],
        }}
        transition={{ duration: 12, repeat: Infinity, ease: 'easeInOut' }}
        className="absolute bottom-10 right-1/3 w-[350px] sm:w-[450px] h-[350px] sm:h-[450px] bg-amber-400/15 rounded-full blur-3xl pointer-events-none"
      />

      {/* ----------------------------------------------------------------- */}
      {/* LEFT SECTION (STORYTELLING – DESKTOP ONLY lg+)                    */}
      {/* ----------------------------------------------------------------- */}
      <div className="hidden lg:flex lg:w-[56%] xl:w-[58%] h-full relative z-10 flex-col justify-between p-6 xl:p-8 border-r border-emerald-100/70 bg-gradient-to-br from-white/80 via-white/55 to-emerald-50/40 backdrop-blur-md overflow-hidden">
        
        {/* Top Header Logo & Navigation */}
        <div className="flex items-center justify-between shrink-0">
          <Link to="/" className="flex items-center gap-2.5 group">
            <div className="w-[38px] h-[38px] bg-[#005C2B] rounded-xl flex items-center justify-center text-white shadow-xs group-hover:scale-105 transition-transform">
              <svg className="w-5 h-5 fill-current" viewBox="0 0 24 24">
                <path d="M20 8h-3V4H3c-1.1 0-2 .9-2 2v11h2c0 1.66 1.34 3 3 3s3-1.34 3-3h6c0 1.66 1.34 3 3 3s3-1.34 3-3h2v-5l-3-4zM6 18.5c-.83 0-1.5-.67-1.5-1.5s.67-1.5 1.5-1.5 1.5.67 1.5 1.5-.67 1.5-1.5 1.5zm13.5-9l1.96 2.5H17V9.5h2.5zm-1.5 9c-.83 0-1.5-.67-1.5-1.5s.67-1.5 1.5-1.5 1.5.67 1.5 1.5-.67 1.5-1.5 1.5z" />
              </svg>
            </div>
            <div>
              <div className="text-[19px] font-black text-gray-900 tracking-tight leading-none">
                EcoPulse AI
              </div>
              <div className="text-[10px] font-semibold text-gray-500 tracking-wide mt-0.5">
                Smart Civic & Sustainability Ecosystem
              </div>
            </div>
          </Link>

          <Link
            to="/"
            className="inline-flex items-center gap-1.5 bg-white/90 backdrop-blur-md px-3 py-1.5 rounded-xl text-xs font-bold text-gray-700 border border-gray-200/80 shadow-2xs hover:bg-white hover:text-[#005C2B] transition-all cursor-pointer"
          >
            <ArrowLeft className="w-3.5 h-3.5" />
            <span>Back to Home</span>
          </Link>
        </div>

        {/* Center Storytelling Hero */}
        <div className="my-auto space-y-3.5 relative max-w-xl py-2 shrink-1 overflow-hidden">
          
          {/* Top Pill Badge */}
          <motion.div
            initial={{ opacity: 0, y: -6 }}
            animate={{ opacity: 1, y: 0 }}
            className="inline-flex items-center gap-1.5 bg-[#e2f4e8]/90 backdrop-blur-xs px-3 py-1 rounded-full text-[11px] font-bold text-[#005C2B] tracking-wide border border-[#c4ebcf] shadow-2xs"
          >
            <Sparkles className="w-3 h-3" />
            <span>AI-POWERED</span>
            <span className="text-[#005C2B] font-bold">•</span>
            <span>CIRCULAR ECONOMY</span>
            <span className="text-[#005C2B] font-bold">•</span>
            <span>ZERO WASTE</span>
          </motion.div>

          {/* Hero Heading */}
          <div className="space-y-1.5">
            <h1 className="text-3xl xl:text-4xl font-black text-[#101828] leading-[1.12] tracking-tight">
              Building Smarter & <br />
              <span className="bg-gradient-to-r from-[#005C2B] via-emerald-600 to-teal-700 bg-clip-text text-transparent">
                Sustainable Cities
              </span> Together
            </h1>
            <p className="text-gray-700 text-xs xl:text-sm font-semibold leading-relaxed max-w-lg">
              EcoPulse AI connects Citizens, Drivers, Collectors, and Municipalities on one intelligent platform to make waste management efficient, transparent and sustainable.
            </p>
          </div>

          {/* Hero Illustration Container with Floating Badges */}
          <div className="relative w-full max-w-[480px] py-1 flex items-center justify-center">
            
            {/* Floating Badge 1 */}
            <motion.div
              animate={{ y: [0, -5, 0] }}
              transition={{ duration: 4, repeat: Infinity, ease: 'easeInOut' }}
              className="absolute -left-2 top-2 bg-white/95 backdrop-blur-md border border-emerald-100 p-2.5 rounded-xl shadow-lg flex items-center gap-2.5 z-30 max-w-[170px]"
            >
              <div className="w-7 h-7 rounded-lg bg-[#e2f4e8] text-[#005C2B] flex items-center justify-center font-bold shrink-0">
                <Zap className="w-4 h-4" />
              </div>
              <div>
                <div className="text-[10px] font-black text-gray-900">AI Route Sync</div>
                <div className="text-[8px] font-semibold text-gray-500">99.4% Efficiency</div>
              </div>
            </motion.div>

            {/* Floating Badge 2 */}
            <motion.div
              animate={{ y: [0, 5, 0] }}
              transition={{ duration: 5, repeat: Infinity, ease: 'easeInOut', delay: 1 }}
              className="absolute -right-2 bottom-4 bg-white/95 backdrop-blur-md border border-emerald-100 p-2.5 rounded-xl shadow-lg flex items-center gap-2.5 z-30 max-w-[175px]"
            >
              <div className="w-7 h-7 rounded-lg bg-amber-100 text-[#d9531e] flex items-center justify-center font-bold shrink-0">
                <Shield className="w-4 h-4" />
              </div>
              <div>
                <div className="text-[10px] font-black text-gray-900">Verified Proof</div>
                <div className="text-[8px] font-semibold text-gray-500">AI Photo Verification</div>
              </div>
            </motion.div>

            {/* Main Landing Illustration */}
            <motion.img
              key={activeRole}
              initial={{ scale: 0.96, opacity: 0 }}
              animate={{ scale: 1, opacity: 1 }}
              transition={{ duration: 0.3 }}
              src={getRoleIllustration()}
              alt="EcoPulse AI Smart City Infrastructure"
              className="w-full h-auto max-h-[190px] xl:max-h-[220px] object-contain rounded-xl drop-shadow-md"
            />
          </div>

          {/* 4 Feature Highlight Cards */}
          <div className="grid grid-cols-2 gap-2.5 pt-0.5">
            <div className="p-2.5 rounded-xl bg-white/85 border border-emerald-100/90 shadow-2xs flex items-start gap-2.5">
              <div className="w-7 h-7 rounded-lg bg-[#e2f4e8] text-[#005C2B] flex items-center justify-center shrink-0">
                <Leaf className="w-3.5 h-3.5" />
              </div>
              <div>
                <h4 className="text-[11px] font-black text-gray-900">Sustainable Communities</h4>
                <p className="text-[10px] font-semibold text-gray-500 leading-tight mt-0.5">
                  Minimize waste & track impact.
                </p>
              </div>
            </div>

            <div className="p-2.5 rounded-xl bg-white/85 border border-emerald-100/90 shadow-2xs flex items-start gap-2.5">
              <div className="w-7 h-7 rounded-lg bg-[#e2f4e8] text-[#005C2B] flex items-center justify-center shrink-0">
                <Recycle className="w-3.5 h-3.5" />
              </div>
              <div>
                <h4 className="text-[11px] font-black text-gray-900">Circular Economy</h4>
                <p className="text-[10px] font-semibold text-gray-500 leading-tight mt-0.5">
                  Turn scrap into eco-credits.
                </p>
              </div>
            </div>

            <div className="p-2.5 rounded-xl bg-white/85 border border-amber-100/90 shadow-2xs flex items-start gap-2.5">
              <div className="w-7 h-7 rounded-lg bg-amber-50 text-[#d9531e] flex items-center justify-center shrink-0">
                <Building2 className="w-3.5 h-3.5" />
              </div>
              <div>
                <h4 className="text-[11px] font-black text-gray-900">Smart City Ecosystem</h4>
                <p className="text-[10px] font-semibold text-gray-500 leading-tight mt-0.5">
                  AI route navigation for drivers.
                </p>
              </div>
            </div>

            <div className="p-2.5 rounded-xl bg-white/85 border border-emerald-100/90 shadow-2xs flex items-start gap-2.5">
              <div className="w-7 h-7 rounded-lg bg-[#e2f4e8] text-[#005C2B] flex items-center justify-center shrink-0">
                <Users className="w-3.5 h-3.5" />
              </div>
              <div>
                <h4 className="text-[11px] font-black text-gray-900">Community Impact</h4>
                <p className="text-[10px] font-semibold text-gray-500 leading-tight mt-0.5">
                  Real-time civic leaderboards & rewards.
                </p>
              </div>
            </div>
          </div>
        </div>

        {/* Bottom Trust Rating Bar */}
        <div className="pt-2 border-t border-emerald-100/80 flex items-center justify-between text-[11px] font-semibold text-gray-600 shrink-0">
          <div className="flex items-center gap-1.5">
            <div className="flex text-amber-400">
              {[1, 2, 3, 4, 5].map((star) => (
                <Star key={star} className="w-3.5 h-3.5 fill-current" />
              ))}
            </div>
            <span className="font-bold text-gray-900">4.9/5 Municipal Rating</span>
          </div>
          <span>© 2026 EcoPulse AI</span>
        </div>
      </div>

      {/* ----------------------------------------------------------------- */}
      {/* RIGHT SECTION (AUTH CARD)                                         */}
      {/* ----------------------------------------------------------------- */}
      <div className="w-full lg:w-[44%] xl:w-[42%] min-h-screen lg:h-full relative z-10 flex flex-col justify-between p-4 sm:p-5 lg:p-5 xl:p-6 overflow-y-auto">
        
        {/* Mobile Top Header */}
        <div className="flex lg:hidden items-center justify-between mb-3 shrink-0">
          <Link to="/" className="flex items-center gap-2">
            <div className="w-8 h-8 bg-[#005C2B] rounded-xl flex items-center justify-center text-white shadow-xs">
              <svg className="w-4 h-4 fill-current" viewBox="0 0 24 24">
                <path d="M20 8h-3V4H3c-1.1 0-2 .9-2 2v11h2c0 1.66 1.34 3 3 3s3-1.34 3-3h6c0 1.66 1.34 3 3 3s3-1.34 3-3h2v-5l-3-4zM6 18.5c-.83 0-1.5-.67-1.5-1.5s.67-1.5 1.5-1.5 1.5.67 1.5 1.5-.67 1.5-1.5 1.5zm13.5-9l1.96 2.5H17V9.5h2.5zm-1.5 9c-.83 0-1.5-.67-1.5-1.5s.67-1.5 1.5-1.5 1.5.67 1.5 1.5-.67 1.5-1.5 1.5z" />
              </svg>
            </div>
            <span className="text-base font-black text-gray-900">EcoPulse AI</span>
          </Link>

          <Link
            to="/"
            className="inline-flex items-center gap-1 text-xs font-bold text-gray-700 bg-white/90 px-2.5 py-1 rounded-lg border border-gray-200"
          >
            <ArrowLeft className="w-3 h-3" /> Home
          </Link>
        </div>

        {/* Centered Floating Glassmorphism Form Card */}
        <div className="my-auto w-full max-w-md sm:max-w-lg lg:max-w-md mx-auto">
          <motion.div
            initial={{ opacity: 0, y: 15, scale: 0.98 }}
            animate={{ opacity: 1, y: 0, scale: 1 }}
            transition={{ duration: 0.35, ease: [0.16, 1, 0.3, 1] }}
            className="bg-white rounded-[32px] p-5 sm:p-6 shadow-[0_20px_50px_-15px_rgba(217,83,30,0.15),0_10px_30px_rgba(0,0,0,0.04)] border border-slate-200/90 relative overflow-hidden"
          >
            {/* Top Accent Bar */}
            <div className="absolute top-0 inset-x-0 h-1.5 bg-gradient-to-r from-[#d9531e] via-amber-500 to-[#005C2B]" />

            {/* Registration Form (Citizen sign-in redirects to /login) */}
            <SignupForm
              onSwitchToLogin={() => navigate('/login')}
              onRoleChange={(role) => setActiveRole(role)}
              onSuccess={onSuccessNavigation}
            />
          </motion.div>
        </div>

        {/* Mobile & Right Footer */}
        <div className="pt-2 text-center text-[10px] font-semibold text-gray-500 shrink-0">
          © 2026 EcoPulse AI • Smart Civic & Sustainability Ecosystem
        </div>
      </div>

      {/* Forgot Password Modal */}
      <ForgotPasswordModal
        isOpen={isForgotPasswordOpen}
        onClose={() => setIsForgotPasswordOpen(false)}
        onBackToLogin={() => setIsForgotPasswordOpen(false)}
      />
    </div>
  );
};

export default SplitAuthLayout;
