import React, { useState } from 'react';
import { Link } from 'react-router-dom';
import { ArrowLeft, Send, Mail, Phone, MapPin, CheckCircle2, Building2 } from 'lucide-react';

export default function ContactPage() {
  const [submitted, setSubmitted] = useState(false);
  const [formData, setFormData] = useState({ name: '', organization: '', email: '', phone: '', message: '' });

  const handleSubmit = (e) => {
    e.preventDefault();
    setSubmitted(true);
  };

  return (
    <div className="min-h-screen bg-[#f8faf9] text-slate-800 font-sans selection:bg-[#005C2B] selection:text-white">
      <header className="bg-white border-b border-slate-200 sticky top-0 z-40">
        <div className="max-w-5xl mx-auto px-4 py-3.5 flex items-center justify-between">
          <div className="flex items-center gap-3">
            <Link to="/" className="w-9 h-9 rounded-xl bg-[#005C2B] text-white flex items-center justify-center hover:opacity-90 transition-opacity">
              <ArrowLeft className="w-5 h-5" />
            </Link>
            <div>
              <h1 className="text-lg font-black text-slate-900 tracking-tight leading-none">Municipal Partnership & Contact</h1>
              <p className="text-xs text-emerald-700 font-bold mt-0.5">EcoPulse AI Platform</p>
            </div>
          </div>
          <Link to="/" className="text-xs font-bold text-slate-600 hover:text-[#005C2B]">
            Back to Home
          </Link>
        </div>
      </header>

      <main className="max-w-4xl mx-auto px-4 py-8">
        <div className="grid grid-cols-1 md:grid-cols-12 gap-6">
          <div className="md:col-span-5 space-y-4">
            <div className="bg-white rounded-3xl p-6 border border-slate-200 shadow-xs space-y-4">
              <div className="w-12 h-12 rounded-2xl bg-emerald-100 text-[#005C2B] flex items-center justify-center">
                <Building2 className="w-6 h-6" />
              </div>
              <h2 className="text-2xl font-black text-slate-900">Partner with Us for Municipal Pilots</h2>
              <p className="text-xs text-slate-600 font-medium leading-relaxed">
                We are actively running municipal council pilots across Maharashtra. Schedule an evaluation demo or request pilot funding details.
              </p>

              <div className="space-y-3 pt-4 border-t border-slate-100 text-xs font-semibold text-slate-700">
                <div className="flex items-center gap-3">
                  <MapPin className="w-4 h-4 text-[#005C2B] shrink-0" />
                  <span>Dhule Urban Region Pilot, Maharashtra, India</span>
                </div>
                <div className="flex items-center gap-3">
                  <Phone className="w-4 h-4 text-[#005C2B] shrink-0" />
                  <a href="tel:+919876543210" className="hover:underline">+91 98765 43210</a>
                </div>
                <div className="flex items-center gap-3">
                  <Mail className="w-4 h-4 text-[#005C2B] shrink-0" />
                  <a href="mailto:pilot@ecopulse.ai" className="hover:underline">pilot@ecopulse.ai</a>
                </div>
              </div>
            </div>
          </div>

          <div className="md:col-span-7">
            {submitted ? (
              <div className="bg-white rounded-3xl p-8 border border-emerald-200 shadow-xs text-center space-y-4">
                <div className="w-14 h-14 bg-emerald-100 rounded-full flex items-center justify-center mx-auto text-emerald-600">
                  <CheckCircle2 className="w-8 h-8" />
                </div>
                <h3 className="text-2xl font-black text-slate-900">Inquiry Received</h3>
                <p className="text-xs text-slate-600 max-w-sm mx-auto font-medium">
                  Thank you! Our civic technology deployment team will reach out within 24 business hours with pilot documentation.
                </p>
                <button 
                  onClick={() => setSubmitted(false)}
                  className="bg-[#005C2B] text-white text-xs font-bold px-6 py-2.5 rounded-xl hover:bg-[#004a22] cursor-pointer"
                >
                  Send Another Message
                </button>
              </div>
            ) : (
              <form onSubmit={handleSubmit} className="bg-white rounded-3xl p-6 sm:p-8 border border-slate-200 shadow-xs space-y-4">
                <h3 className="text-lg font-black text-slate-900">Request Pilot Consultation</h3>
                <div>
                  <label className="block text-xs font-bold text-slate-700 mb-1">Your Name</label>
                  <input 
                    type="text" 
                    required 
                    value={formData.name}
                    onChange={(e) => setFormData(p => ({ ...p, name: e.target.value }))}
                    className="w-full px-3.5 py-2.5 rounded-xl border border-slate-200 bg-slate-50 text-sm font-semibold focus:outline-none focus:border-[#005C2B] focus:bg-white"
                  />
                </div>
                <div>
                  <label className="block text-xs font-bold text-slate-700 mb-1">Municipal Body / Organization</label>
                  <input 
                    type="text" 
                    placeholder="e.g. Municipal Council, NGO, Smart City Cell" 
                    value={formData.organization}
                    onChange={(e) => setFormData(p => ({ ...p, organization: e.target.value }))}
                    className="w-full px-3.5 py-2.5 rounded-xl border border-slate-200 bg-slate-50 text-sm font-semibold focus:outline-none focus:border-[#005C2B] focus:bg-white"
                  />
                </div>
                <div className="grid grid-cols-1 sm:grid-cols-2 gap-3">
                  <div>
                    <label className="block text-xs font-bold text-slate-700 mb-1">Email</label>
                    <input 
                      type="email" 
                      required 
                      value={formData.email}
                      onChange={(e) => setFormData(p => ({ ...p, email: e.target.value }))}
                      className="w-full px-3.5 py-2.5 rounded-xl border border-slate-200 bg-slate-50 text-sm font-semibold focus:outline-none focus:border-[#005C2B] focus:bg-white"
                    />
                  </div>
                  <div>
                    <label className="block text-xs font-bold text-slate-700 mb-1">Phone Number</label>
                    <input 
                      type="tel" 
                      value={formData.phone}
                      onChange={(e) => setFormData(p => ({ ...p, phone: e.target.value }))}
                      className="w-full px-3.5 py-2.5 rounded-xl border border-slate-200 bg-slate-50 text-sm font-semibold focus:outline-none focus:border-[#005C2B] focus:bg-white"
                    />
                  </div>
                </div>
                <div>
                  <label className="block text-xs font-bold text-slate-700 mb-1">Message / Requirements</label>
                  <textarea 
                    rows={3}
                    value={formData.message}
                    onChange={(e) => setFormData(p => ({ ...p, message: e.target.value }))}
                    placeholder="Tell us about your city population, ward count, or timeline..."
                    className="w-full px-3.5 py-2 rounded-xl border border-slate-200 bg-slate-50 text-sm font-semibold focus:outline-none focus:border-[#005C2B] focus:bg-white resize-none"
                  />
                </div>
                <button
                  type="submit"
                  className="w-full py-3 rounded-2xl bg-[#005C2B] hover:bg-[#004a22] text-white font-extrabold text-sm shadow-sm transition-all flex items-center justify-center gap-2 cursor-pointer"
                >
                  <Send className="w-4 h-4" /> Send Request
                </button>
              </form>
            )}
          </div>
        </div>
      </main>
    </div>
  );
}
