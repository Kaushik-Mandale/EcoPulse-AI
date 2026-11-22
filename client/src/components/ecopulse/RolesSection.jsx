import React from 'react';
import { useNavigate } from 'react-router-dom';

const RolesSection = () => {
  const navigate = useNavigate();

  const handlePortalClick = (role, targetRoute) => {
    const savedUser = localStorage.getItem('ecopulse_user');
    if (savedUser) {
      try {
        const user = JSON.parse(savedUser);
        if (user) {
          navigate(targetRoute);
          return;
        }
      } catch (e) {
        console.error('Error parsing session user:', e);
      }
    }
    // If not logged in, require login first
    navigate(`/login?portal=${role}`);
  };

  return (
    <section id="features" className="py-20 px-4 md:px-10 relative overflow-hidden bg-gradient-to-b from-[#eaf4fd] via-[#f2f8fe] to-white">
      {/* Seamless Continuous Sky Background with Soft White Clouds */}
      <div 
        className="absolute inset-0 z-0 bg-no-repeat bg-cover bg-center opacity-95 pointer-events-none"
        style={{ backgroundImage: `url('/seamless_sky_clouds.png')` }}
      ></div>
      {/* Atmospheric Soft Blue Gradient Overlay */}
      <div className="absolute inset-0 z-0 bg-gradient-to-b from-sky-100/30 via-white/10 to-white/60 pointer-events-none"></div>

      <div className="max-w-[1340px] mx-auto relative z-10">
        
        {/* Section Header */}
        <div className="text-center mb-12 flex items-center justify-center gap-2">
          <h2 className="text-2xl md:text-3xl lg:text-4xl font-extrabold text-[#101828] tracking-tight">
            One Platform. Three Civic Portals.
          </h2>
        </div>

        {/* 3 Role Cards Grid */}
        <div className="grid grid-cols-1 lg:grid-cols-3 gap-8">
          
          {/* Card 1: Citizen (featuring girl.png) */}
          <div className="bg-[#f0fbf4] border border-[#d2f3dc] rounded-3xl p-6 flex flex-col justify-between hover:shadow-md transition-all">
            <div>
              {/* Header Icon + Titles */}
              <div className="flex items-center gap-3 mb-4">
                <div className="w-10 h-10 rounded-xl bg-primary flex items-center justify-center text-white text-lg shadow-2xs">
                  👥
                </div>
                <div>
                  <h3 className="text-xl font-black text-gray-900 leading-tight">Citizen</h3>
                  <p className="text-xs font-semibold text-gray-500">Report • Track • Get Updates</p>
                </div>
              </div>

              {/* Checkpoint List */}
              <ul className="space-y-3 my-6 text-xs font-bold text-gray-700">
                <li className="flex items-center gap-2.5">
                  <span className="w-4 h-4 rounded-full bg-primary text-white text-[10px] flex items-center justify-center font-bold">✓</span>
                  <span>Report waste in seconds</span>
                </li>
                <li className="flex items-center gap-2.5">
                  <span className="w-4 h-4 rounded-full bg-primary text-white text-[10px] flex items-center justify-center font-bold">✓</span>
                  <span>Track complaint status</span>
                </li>
                <li className="flex items-center gap-2.5">
                  <span className="w-4 h-4 rounded-full bg-primary text-white text-[10px] flex items-center justify-center font-bold">✓</span>
                  <span>Use WhatsApp reporting</span>
                </li>
                <li className="flex items-center gap-2.5">
                  <span className="w-4 h-4 rounded-full bg-primary text-white text-[10px] flex items-center justify-center font-bold">✓</span>
                  <span>Manage your citizen profile</span>
                </li>
              </ul>
            </div>

            {/* Visual: girl.png */}
            <div className="mt-2">
              <div className="w-full mb-4 overflow-hidden rounded-2xl">
                <img
                  src="/girl.png"
                  alt="Citizen App & 3D Character Illustration"
                  className="w-full h-auto object-contain hover:scale-[1.02] transition-transform duration-300 drop-shadow-xs"
                />
              </div>

              <button 
                type="button"
                onClick={() => handlePortalClick('citizen', '/citizen')} 
                className="inline-flex items-center gap-1.5 text-xs font-extrabold text-primary hover:underline cursor-pointer"
              >
                Explore Citizen Portal →
              </button>
            </div>
          </div>

          {/* Card 2: Driver (featuring driver.png) */}
          <div className="bg-[#f0f7ff] border border-[#dbeafe] rounded-3xl p-6 flex flex-col justify-between hover:shadow-md transition-all">
            <div>
              {/* Header Icon + Titles */}
              <div className="flex items-center gap-3 mb-4">
                <div className="w-10 h-10 rounded-xl bg-blue-600 flex items-center justify-center text-white text-lg shadow-2xs">
                  🚚
                </div>
                <div>
                  <h3 className="text-xl font-black text-gray-900 leading-tight">Driver</h3>
                  <p className="text-xs font-semibold text-gray-500">View • Update • Complete</p>
                </div>
              </div>

              {/* Checkpoint List */}
              <ul className="space-y-3 my-6 text-xs font-bold text-gray-700">
                <li className="flex items-center gap-2.5">
                  <span className="w-4 h-4 rounded-full bg-blue-600 text-white text-[10px] flex items-center justify-center font-bold">✓</span>
                  <span>Get assigned tasks</span>
                </li>
                <li className="flex items-center gap-2.5">
                  <span className="w-4 h-4 rounded-full bg-blue-600 text-white text-[10px] flex items-center justify-center font-bold">✓</span>
                  <span>View assigned complaint details</span>
                </li>
                <li className="flex items-center gap-2.5">
                  <span className="w-4 h-4 rounded-full bg-blue-600 text-white text-[10px] flex items-center justify-center font-bold">✓</span>
                  <span>Update collection status</span>
                </li>
                <li className="flex items-center gap-2.5">
                  <span className="w-4 h-4 rounded-full bg-blue-600 text-white text-[10px] flex items-center justify-center font-bold">✓</span>
                  <span>Update task status</span>
                </li>
              </ul>
            </div>

            {/* Visual: driver.png */}
            <div className="mt-2">
              <div className="w-full mb-4 overflow-hidden rounded-2xl">
                <img
                  src="/driver.png"
                  alt="Driver App & 3D Character Illustration"
                  className="w-full h-auto object-contain hover:scale-[1.02] transition-transform duration-300 drop-shadow-xs"
                />
              </div>

              <button 
                type="button"
                onClick={() => handlePortalClick('driver', '/driver')} 
                className="inline-flex items-center gap-1.5 text-xs font-extrabold text-blue-600 hover:underline cursor-pointer"
              >
                Explore Driver Portal →
              </button>
            </div>
          </div>

          {/* Card 3: Collector (featuring admin.png) */}
          <div className="bg-[#f0fbf4] border border-[#d2f3dc] rounded-3xl p-6 flex flex-col justify-between hover:shadow-md transition-all">
            <div>
              {/* Header Icon + Titles */}
              <div className="flex items-center gap-3 mb-4">
                <div className="w-10 h-10 rounded-xl bg-primary flex items-center justify-center text-white text-lg shadow-2xs">
                  🛒
                </div>
                <div>
                  <h3 className="text-xl font-black text-gray-900 leading-tight">Admin</h3>
                  <p className="text-xs font-semibold text-gray-500">Monitor • Verify • Manage</p>
                </div>
              </div>

              {/* Checkpoint List */}
              <ul className="space-y-3 my-6 text-xs font-bold text-gray-700">
                <li className="flex items-center gap-2.5">
                  <span className="w-4 h-4 rounded-full bg-primary text-white text-[10px] flex items-center justify-center font-bold">✓</span>
                  <span>Review submitted complaints</span>
                </li>
                <li className="flex items-center gap-2.5">
                  <span className="w-4 h-4 rounded-full bg-primary text-white text-[10px] flex items-center justify-center font-bold">✓</span>
                  <span>Driver & asset management</span>
                </li>
                <li className="flex items-center gap-2.5">
                  <span className="w-4 h-4 rounded-full bg-primary text-white text-[10px] flex items-center justify-center font-bold">✓</span>
                  <span>Issue resolution & reports</span>
                </li>
                <li className="flex items-center gap-2.5">
                  <span className="w-4 h-4 rounded-full bg-primary text-white text-[10px] flex items-center justify-center font-bold">✓</span>
                  <span>Review available service metrics</span>
                </li>
              </ul>
            </div>

            {/* Visual: admin.png */}
            <div className="mt-2">
              <div className="w-full mb-4 overflow-hidden rounded-2xl">
                <img
                  src="/admin.png"
                  alt="Admin App & 3D Character Illustration"
                  className="w-full h-auto object-contain hover:scale-[1.02] transition-transform duration-300 drop-shadow-xs"
                />
              </div>

              <button 
                type="button"
                onClick={() => handlePortalClick('collector', '/admin')} 
                className="inline-flex items-center gap-1.5 text-xs font-extrabold text-primary hover:underline cursor-pointer"
              >
                Explore Admin Portal →
              </button>
            </div>
          </div>

        </div>

      </div>
    </section>
  );
};

export default RolesSection;
