import React, { useState } from 'react';
import { Link } from 'react-router-dom';
import { Menu, X, Camera, Search, MapPin, Building2, ChevronRight } from 'lucide-react';

const Navbar = ({ onOpenLogin, onOpenSignup }) => {
  const [mobileMenuOpen, setMobileMenuOpen] = useState(false);

  return (
    <nav className="w-full bg-white border-b border-gray-200 py-3 px-4 md:px-10 sticky top-0 z-50 shadow-2xs">
      <div className="max-w-[1340px] mx-auto flex items-center justify-between">
        
        {/* Brand Logo */}
        <Link to="/" className="flex items-center gap-3 cursor-pointer">
          <div className="w-[40px] h-[40px] bg-[#005C2B] rounded-xl flex items-center justify-center text-white shadow-xs">
            <svg className="w-6 h-6 fill-current" viewBox="0 0 24 24">
              <path d="M20 8h-3V4H3c-1.1 0-2 .9-2 2v11h2c0 1.66 1.34 3 3 3s3-1.34 3-3h6c0 1.66 1.34 3 3 3s3-1.34 3-3h2v-5l-3-4zM6 18.5c-.83 0-1.5-.67-1.5-1.5s.67-1.5 1.5-1.5 1.5.67 1.5 1.5-.67 1.5-1.5 1.5zm13.5-9l1.96 2.5H17V9.5h2.5zm-1.5 9c-.83 0-1.5-.67-1.5-1.5s.67-1.5 1.5-1.5 1.5.67 1.5 1.5-.67 1.5-1.5 1.5z"/>
            </svg>
          </div>
          <div>
            <div className="text-[20px] font-extrabold text-gray-900 tracking-tight leading-none">
              EcoPulse AI
            </div>
            <div className="text-[10px] font-bold text-emerald-700 tracking-wide mt-1">
              Smart Civic Waste Platform • Dhule Pilot
            </div>
          </div>
        </Link>

        {/* Desktop Navigation Links */}
        <div className="hidden lg:flex items-center gap-6 text-[13px] font-bold text-gray-700">
          <Link to="/" className="text-[#005C2B] font-extrabold hover:text-[#004a22]">
            Home
          </Link>
          <Link to="/report" className="hover:text-[#005C2B] flex items-center gap-1 transition-colors">
            <Camera className="w-3.5 h-3.5 text-emerald-600" /> Report Waste
          </Link>
          <Link to="/track" className="hover:text-[#005C2B] flex items-center gap-1 transition-colors">
            <Search className="w-3.5 h-3.5 text-emerald-600" /> Track Status
          </Link>
          <Link to="/map" className="hover:text-[#005C2B] flex items-center gap-1 transition-colors">
            <MapPin className="w-3.5 h-3.5 text-emerald-600" /> City GIS
          </Link>
          <Link to="/demo" className="text-amber-800 bg-amber-50 hover:bg-amber-100 border border-amber-200/80 px-2.5 py-1 rounded-lg flex items-center gap-1 transition-colors">
            <Building2 className="w-3.5 h-3.5 text-amber-600" /> Demo Sandbox
          </Link>
          <a href="#how-it-works" className="hover:text-[#005C2B] transition-colors">
            How It Works
          </a>
          <a href="#impact" className="hover:text-[#005C2B] transition-colors">
            Impact
          </a>
          <Link to="/help" className="hover:text-[#005C2B] transition-colors">
            FAQ
          </Link>
        </div>

        {/* Action Buttons & Mobile Hamburger */}
        <div className="flex items-center gap-2.5">
          <Link 
            to="/login"
            className="hidden sm:inline-flex px-4 py-2 rounded-xl border border-gray-300 text-gray-800 text-xs font-bold hover:bg-gray-50 hover:border-[#005C2B] hover:text-[#005C2B] transition-all cursor-pointer items-center justify-center"
          >
            Login
          </Link>
          <Link 
            to="/demo"
            className="px-4 py-2 rounded-xl bg-[#005C2B] text-white text-xs font-extrabold shadow-xs hover:bg-[#004a22] transition-all cursor-pointer inline-flex items-center justify-center gap-1"
          >
            <span>Explore Demo</span>
          </Link>

          {/* Mobile Menu Toggle */}
          <button
            onClick={() => setMobileMenuOpen(!mobileMenuOpen)}
            className="lg:hidden p-2 rounded-xl text-slate-600 hover:text-slate-900 hover:bg-slate-100 cursor-pointer"
            aria-label="Toggle navigation menu"
          >
            {mobileMenuOpen ? <X className="w-5 h-5" /> : <Menu className="w-5 h-5" />}
          </button>
        </div>

      </div>

      {/* Mobile Drawer Navigation */}
      {mobileMenuOpen && (
        <div className="lg:hidden mt-3 pt-3 border-t border-slate-100 space-y-2 px-2 pb-2 text-xs font-bold text-slate-800">
          <Link 
            to="/report" 
            onClick={() => setMobileMenuOpen(false)}
            className="flex items-center justify-between p-2.5 rounded-xl hover:bg-slate-50 text-[#005C2B]"
          >
            <span className="flex items-center gap-2"><Camera className="w-4 h-4" /> Report Waste Incident</span>
            <ChevronRight className="w-4 h-4" />
          </Link>
          <Link 
            to="/track" 
            onClick={() => setMobileMenuOpen(false)}
            className="flex items-center justify-between p-2.5 rounded-xl hover:bg-slate-50 text-slate-800"
          >
            <span className="flex items-center gap-2"><Search className="w-4 h-4" /> Track Existing Complaint</span>
            <ChevronRight className="w-4 h-4" />
          </Link>
          <Link 
            to="/map" 
            onClick={() => setMobileMenuOpen(false)}
            className="flex items-center justify-between p-2.5 rounded-xl hover:bg-slate-50 text-slate-800"
          >
            <span className="flex items-center gap-2"><MapPin className="w-4 h-4" /> City GIS & Live Fleet</span>
            <ChevronRight className="w-4 h-4" />
          </Link>
          <Link 
            to="/demo" 
            onClick={() => setMobileMenuOpen(false)}
            className="flex items-center justify-between p-2.5 rounded-xl bg-amber-50 text-amber-900 border border-amber-200"
          >
            <span className="flex items-center gap-2"><Building2 className="w-4 h-4 text-amber-700" /> Municipal Demo Sandbox</span>
            <ChevronRight className="w-4 h-4" />
          </Link>
          <Link 
            to="/wallet" 
            onClick={() => setMobileMenuOpen(false)}
            className="flex items-center justify-between p-2.5 rounded-xl hover:bg-slate-50 text-slate-800"
          >
            <span>⭐ EcoCoin Rewards Wallet</span>
            <ChevronRight className="w-4 h-4" />
          </Link>
          <Link 
            to="/help" 
            onClick={() => setMobileMenuOpen(false)}
            className="flex items-center justify-between p-2.5 rounded-xl hover:bg-slate-50 text-slate-800"
          >
            <span>❓ Knowledge Base & FAQ</span>
            <ChevronRight className="w-4 h-4" />
          </Link>
          <div className="pt-2 border-t border-slate-100 flex gap-2">
            <Link 
              to="/login"
              onClick={() => setMobileMenuOpen(false)}
              className="flex-1 py-2 text-center rounded-xl border border-slate-300 font-extrabold text-slate-800"
            >
              Portal Login
            </Link>
            <Link 
              to="/signup"
              onClick={() => setMobileMenuOpen(false)}
              className="flex-1 py-2 text-center rounded-xl bg-[#005C2B] text-white font-extrabold"
            >
              Sign Up
            </Link>
          </div>
        </div>
      )}
    </nav>
  );
};

export default Navbar;
