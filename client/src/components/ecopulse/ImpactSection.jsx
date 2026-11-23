import React from 'react';

const ImpactSection = () => {
  return (
    <section id="impact" className="py-16 px-4 md:px-10 relative overflow-hidden">
      {/* Background Image (background_3.png) */}
      <div 
        className="absolute inset-0 z-0 bg-no-repeat bg-cover bg-center opacity-90 pointer-events-none"
        style={{ backgroundImage: `url('/background_3.png')` }}
      ></div>
      <div className="absolute inset-0 z-0 bg-white/80 backdrop-blur-[2px] pointer-events-none"></div>
      
      <div className="max-w-[1340px] mx-auto relative z-10">
        
        {/* Title */}
        <div className="text-center mb-10">
          <div className="inline-flex items-center gap-1.5 px-3 py-1 rounded-full bg-emerald-100/90 text-emerald-800 text-xs font-bold mb-3 border border-emerald-200">
            <span>Verified Operational Data</span>
          </div>
          <h2 className="text-2xl md:text-3xl lg:text-4xl font-extrabold text-[#101828] tracking-tight">
            Civic & Environmental Impact
          </h2>
          <p className="text-slate-600 text-sm font-semibold max-w-xl mx-auto mt-2">
            Performance indicators will be shown here when verified municipal data is available.
          </p>
        </div>

        <div className="max-w-3xl mx-auto rounded-3xl border border-slate-200 bg-white/95 p-8 text-center shadow-xs">
          <p className="text-sm font-semibold text-slate-600">
            No verified impact metrics have been published yet.
          </p>
        </div>

      </div>
    </section>
  );
};

export default ImpactSection;
