import React from 'react';

const HowItWorksSection = () => {
  const steps = [
    {
      num: '1',
      icon: '📸',
      gradient: 'from-emerald-500/15 to-emerald-600/30',
      title: 'Report Waste',
      desc: 'Submit a waste report through the web portal or configured WhatsApp channel.',
    },
    {
      num: '2',
      icon: '🤖',
      gradient: 'from-blue-500/15 to-indigo-600/30',
      title: 'Add Report Details',
      desc: 'Provide the location, description, and any supporting photo.',
    },
    {
      num: '3',
      icon: '🚚',
      gradient: 'from-amber-500/15 to-orange-600/30',
      title: 'Municipal Review',
      desc: 'The submitted report is available for municipal handling.',
    },
    {
      num: '4',
      icon: '♻️',
      gradient: 'from-teal-500/15 to-emerald-600/30',
      title: 'Driver Task',
      desc: 'A driver task can be created when an eligible driver is assigned.',
    },
    {
      num: '5',
      icon: '🏆',
      gradient: 'from-yellow-500/15 to-amber-600/30',
      title: 'Status Updates',
      desc: 'Use the complaint reference to check its latest recorded status.',
    },
  ];

  return (
    <section id="how-it-works" className="py-16 px-4 md:px-10 relative overflow-hidden border-t border-b border-gray-100">
      {/* Background Image (background_3.png) for 3rd Section */}
      <div 
        className="absolute inset-0 z-0 bg-no-repeat bg-cover bg-center opacity-90 pointer-events-none"
        style={{ backgroundImage: `url('/background_3.png')` }}
      ></div>
      <div className="absolute inset-0 z-0 bg-white/80 backdrop-blur-[2px] pointer-events-none"></div>

      <div className="max-w-[1340px] mx-auto relative z-10">
        
        {/* Title */}
        <div className="text-center mb-14">
          <h2 className="text-2xl md:text-3xl lg:text-4xl font-extrabold text-[#101828] tracking-tight">
            How EcoPulse AI Works
          </h2>
        </div>

        {/* 5 Step Cards */}
        <div className="grid grid-cols-1 md:grid-cols-5 gap-5 relative">
          {steps.map((step, idx) => (
            <div key={idx} className="relative flex flex-col items-center group">
              
              {/* Step Card */}
              <div className="bg-white/95 backdrop-blur-md border border-gray-200/90 rounded-3xl p-6 w-full h-full flex flex-col items-center text-center shadow-md hover:shadow-xl hover:border-primary/50 transition-all duration-300 transform hover:-translate-y-1">
                
                {/* Number Badge */}
                <div className="w-8 h-8 rounded-full bg-primary text-white text-xs font-black flex items-center justify-center mb-4 shadow-xs">
                  {step.num}
                </div>

                {/* Big Prominent Icon Container (Larger & Crisp) */}
                <div className={`w-20 h-20 rounded-2xl bg-gradient-to-br ${step.gradient} border border-secondary-container/80 flex items-center justify-center text-4xl mb-4 shadow-sm group-hover:scale-110 transition-transform duration-300`}>
                  <span className="drop-shadow-sm select-none">{step.icon}</span>
                </div>

                {/* Title */}
                <h3 className="text-base font-black text-gray-900 mb-2">{step.title}</h3>

                {/* Desc */}
                <p className="text-xs text-gray-600 font-semibold leading-relaxed">{step.desc}</p>
              </div>

              {/* Connecting Arrow for desktop */}
              {idx < steps.length - 1 && (
                <div className="hidden md:flex absolute -right-3.5 top-1/2 -translate-y-1/2 z-20 w-7 h-7 rounded-full bg-white border border-gray-200 text-primary font-bold text-sm items-center justify-center shadow-sm">
                  ›
                </div>
              )}

            </div>
          ))}
        </div>

      </div>
    </section>
  );
};

export default HowItWorksSection;
