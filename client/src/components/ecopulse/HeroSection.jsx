import React from 'react';
import { Link } from 'react-router-dom';
import { Smartphone, ShieldCheck, MapPin, Globe, Sparkles } from 'lucide-react';

const HeroSection = () => {
  return (
    <section className="relative overflow-hidden pt-8 pb-14 px-4 md:px-10 border-b border-gray-100 min-h-[620px]">
      
      {/* Seamless Horizontal Background (background_1.png) */}
      <div 
        className="absolute inset-0 z-0 bg-no-repeat bg-cover bg-center opacity-95 pointer-events-none"
        style={{ backgroundImage: `url('/background_1.png')` }}
      ></div>

      {/* Soft Gradient Mask for Left-to-Right Seamless Contrast */}
      <div className="absolute inset-0 z-0 bg-gradient-to-r from-white via-white/80 to-transparent pointer-events-none"></div>

      <div className="max-w-[1340px] mx-auto grid grid-cols-1 lg:grid-cols-12 gap-8 items-center relative z-10">
        
        {/* Left Column: Headline & CTAs */}
        <div className="lg:col-span-6 space-y-6 pt-2">
          
          {/* Top Pill Badge */}
          <div className="inline-flex items-center gap-2 bg-secondary-container/90 backdrop-blur-xs px-4 py-1.5 rounded-full text-xs font-bold text-primary tracking-wide border border-secondary-container">
            <span>AI-Powered</span>
            <span className="text-primary font-bold">•</span>
            <span>Smart</span>
            <span className="text-primary font-bold">•</span>
            <span>Sustainable</span>
          </div>

          {/* Hero Heading */}
          <h1 className="text-4xl md:text-5xl lg:text-[54px] font-black text-[#101828] leading-[1.12] tracking-tight">
            Building Cleaner, <br />
            Greener & Smarter Cities <br />
            with AI
          </h1>

          {/* Subtitle */}
          <p className="text-gray-700 text-sm md:text-[15px] leading-relaxed max-w-lg font-semibold">
            EcoPulse AI connects Citizens, Drivers, Collectors and Municipalities on one intelligent platform to make waste management efficient, transparent and sustainable. Piloting for 27 wards of Cities Municipal Corp.
          </p>

          {/* Action CTAs */}
          <div className="flex flex-wrap items-center gap-3 pt-2">
            
            {/* WhatsApp CTA */}
            <a 
              href="https://wa.me/?text=Hi%20EcoPulse%20AI%20Smart%20Waste%20Assistant" 
              target="_blank" 
              rel="noopener noreferrer"
              className="flex items-center gap-2.5 bg-primary hover:bg-primary-container text-white px-5 py-3 rounded-xl font-bold text-sm shadow-md transition-all cursor-pointer"
            >
              <svg className="w-5 h-5 fill-current" viewBox="0 0 24 24">
                <path d="M12.04 2c-5.46 0-9.91 4.45-9.91 9.91 0 1.75.46 3.45 1.32 4.95L2.05 22l5.25-1.38c1.45.79 3.08 1.21 4.74 1.21 5.46 0 9.91-4.45 9.91-9.91 0-2.65-1.03-5.14-2.9-7.01A9.84 9.84 0 0 0 12.04 2z"/>
              </svg>
              Chat with AI on WhatsApp
            </a>

            {/* Request Demo */}
            <Link 
              to="/demo" 
              className="flex items-center gap-2 bg-white/95 backdrop-blur-xs hover:bg-emerald-50 text-gray-800 hover:text-primary border border-gray-300 px-5 py-3 rounded-xl font-semibold text-sm shadow-2xs transition-all cursor-pointer"
            >
              <div className="w-5 h-5 rounded-full bg-primary flex items-center justify-center text-white text-[10px] font-bold">
                <Sparkles className="w-3 h-3" />
              </div>
              Launch Demo Sandbox
            </Link>

            {/* Live City GIS Map */}
            <Link 
              to="/map" 
              className="flex items-center gap-2 bg-white/95 backdrop-blur-xs hover:bg-gray-50 text-gray-800 border border-gray-300 px-5 py-3 rounded-xl font-semibold text-sm shadow-2xs transition-all cursor-pointer"
            >
              <div className="w-5 h-5 rounded-full bg-emerald-600 flex items-center justify-center text-white text-[10px] font-bold">
                <MapPin className="w-3 h-3" />
              </div>
              Live City GIS
            </Link>
          </div>

          {/* 4 Feature Points Bar with Lucide Icons */}
          <div className="pt-6 grid grid-cols-2 sm:grid-cols-4 gap-3 text-xs font-bold text-gray-800">
            <div className="flex items-center gap-2">
              <div className="w-7 h-7 rounded-lg bg-emerald-100 flex items-center justify-center text-emerald-700">
                <Smartphone className="w-4 h-4" />
              </div>
              <span>No App Required</span>
            </div>

            <div className="flex items-center gap-2">
              <div className="w-7 h-7 rounded-lg bg-emerald-100 flex items-center justify-center text-emerald-700">
                <ShieldCheck className="w-4 h-4" />
              </div>
              <span>AI Verified</span>
            </div>

            <div className="flex items-center gap-2">
              <div className="w-7 h-7 rounded-lg bg-emerald-100 flex items-center justify-center text-emerald-700">
                <MapPin className="w-4 h-4" />
              </div>
              <span>Real-time Tracking</span>
            </div>

            <div className="flex items-center gap-2">
              <div className="w-7 h-7 rounded-lg bg-emerald-100 flex items-center justify-center text-emerald-700">
                <Globe className="w-4 h-4" />
              </div>
              <span>Multi-lingual</span>
            </div>
          </div>

        </div>

        {/* Right Column: Seamlessly Blended Hero Visual */}
        <div className="lg:col-span-6 relative flex justify-center items-center">
          
          {/* Floating Circle Badge */}
          <div className="absolute -top-3 right-0 z-30 bg-white/95 backdrop-blur-xs border border-gray-200 shadow-md rounded-full w-32 h-32 p-3 flex flex-col items-center justify-center text-center">
            <span className="text-[10px] text-gray-500 font-medium">Piloting for</span>
            <span className="text-[12px] font-extrabold text-primary leading-tight">
              Cities Municipal <br /> Corp.
            </span>
          </div>

          {/* Seamless Illustration Image */}
          <div className="relative w-full max-w-[640px] flex items-center justify-center">
            <img
              src="/complete-right.png"
              alt="EcoPulse AI Smart Waste Truck and Smart City"
              className="w-full h-auto object-contain rounded-2xl drop-shadow-xl transition-all duration-300"
              style={{
                WebkitMaskImage: 'radial-gradient(circle at center, rgba(0,0,0,1) 85%, rgba(0,0,0,0.85) 95%, rgba(0,0,0,0) 100%)',
                maskImage: 'radial-gradient(circle at center, rgba(0,0,0,1) 85%, rgba(0,0,0,0.85) 95%, rgba(0,0,0,0) 100%)'
              }}
            />
          </div>

        </div>

      </div>
    </section>
  );
};

export default HeroSection;
