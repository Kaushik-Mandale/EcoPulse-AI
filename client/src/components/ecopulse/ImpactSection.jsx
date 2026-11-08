import React from 'react';
import { Target, Zap, Cpu, MessageSquare, Users, ShieldCheck } from 'lucide-react';

const ImpactSection = () => {
  const metrics = [
    {
      icon: Target,
      color: 'text-emerald-600',
      gradient: 'from-emerald-500/15 to-teal-500/25 border-emerald-300/50',
      stat: '95%',
      label: 'AI Detection Accuracy',
      subtext: 'Validated against municipal waste classifications',
    },
    {
      icon: Zap,
      color: 'text-amber-600',
      gradient: 'from-amber-500/15 to-orange-500/25 border-amber-300/50',
      stat: '<4 hrs',
      label: 'Resolution SLA Target',
      subtext: 'Ward-level automated driver dispatch',
    },
    {
      icon: Cpu,
      color: 'text-blue-600',
      gradient: 'from-blue-500/15 to-indigo-500/25 border-blue-300/50',
      stat: '40%',
      label: 'Reduction in Manual Work',
      subtext: 'Zero paperwork complaint tracking',
    },
    {
      icon: MessageSquare,
      color: 'text-emerald-600',
      gradient: 'from-emerald-500/15 to-green-500/25 border-emerald-300/50',
      stat: '24/7',
      label: 'Instant Citizen Support',
      subtext: 'Bilingual Marathi & English WhatsApp AI',
    },
    {
      icon: Users,
      color: 'text-purple-600',
      gradient: 'from-purple-500/15 to-violet-500/25 border-purple-300/50',
      stat: '27 Wards',
      label: 'Demonstration Scope',
      subtext: 'Demonstration ward coverage for civic evaluation',
    },
    {
      icon: ShieldCheck,
      color: 'text-cyan-600',
      gradient: 'from-cyan-500/15 to-blue-500/25 border-cyan-300/50',
      stat: '100%',
      label: 'Data Sovereignty & Security',
      subtext: 'Compliant with DPDP Act 2023 & SSL',
    },
  ];

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
            <span>Simulated Civic Benchmark Architecture</span>
          </div>
          <h2 className="text-2xl md:text-3xl lg:text-4xl font-extrabold text-[#101828] tracking-tight">
            Measurable Civic & Environmental Impact
          </h2>
          <p className="text-slate-600 text-sm font-semibold max-w-xl mx-auto mt-2">
            Target SLA benchmarks modeled for Tier-2/Tier-3 Indian municipal scenarios, evaluated against Dhule pilot models.
          </p>
        </div>

        {/* 6 Metrics Grid */}
        <div className="grid grid-cols-1 sm:grid-cols-2 lg:grid-cols-3 xl:grid-cols-6 gap-4">
          {metrics.map((item, idx) => {
            const IconComponent = item.icon;
            return (
              <div
                key={idx}
                className="bg-white/95 backdrop-blur-xs border border-secondary-container rounded-3xl p-5 text-center flex flex-col items-center justify-between shadow-xs hover:shadow-lg hover:border-primary/50 transition-all duration-300 transform hover:-translate-y-1 group"
              >
                {/* Icon Container */}
                <div className={`w-14 h-14 rounded-2xl bg-gradient-to-br ${item.gradient} border flex items-center justify-center mb-3 shadow-2xs group-hover:scale-110 transition-transform duration-300 select-none`}>
                  <IconComponent className={`w-7 h-7 ${item.color}`} />
                </div>
                <div>
                  <div className="text-2xl sm:text-3xl font-black text-gray-900 leading-none mb-1">
                    {item.stat}
                  </div>
                  <div className="text-xs font-black text-gray-800 leading-snug mb-1">
                    {item.label}
                  </div>
                  <div className="text-[10px] font-semibold text-gray-500 leading-tight">
                    {item.subtext}
                  </div>
                </div>
              </div>
            );
          })}
        </div>

      </div>
    </section>
  );
};

export default ImpactSection;
