import React from 'react';
import { LogOut, RefreshCw, UserRound } from 'lucide-react';

export default function FieldOperationsShell({
  role,
  identity,
  items,
  activeItem,
  onNavigate,
  onRefresh,
  onProfile,
  onLogout,
  children,
}) {
  const roleName = role === 'driver' ? 'Driver' : 'Collector';
  const name = identity?.name || identity?.full_name || roleName;
  const loginId = identity?.login_id || 'Login ID unavailable';
  const ward = identity?.ward || 'Ward not assigned';
  const selectItem = (item) => {
    if (item.action) item.action();
    else onNavigate(item.name);
  };

  const navItems = items.map((item) => {
    const Icon = item.icon;
    return (
      <button
        type="button"
        key={item.name}
        aria-current={activeItem === item.name ? 'page' : undefined}
        onClick={() => selectItem(item)}
        className={`flex shrink-0 items-center gap-3 rounded-xl px-3 py-3 text-left text-sm font-semibold transition-colors md:w-full ${activeItem === item.name ? 'bg-white/15 text-white' : 'text-emerald-100 hover:bg-white/10 hover:text-white'}`}
      >
        {Icon && <Icon size={17} aria-hidden="true" />}
        <span>{item.name}</span>
        {item.badge != null && <span className="ml-auto rounded-full bg-red-500 px-2 py-0.5 text-[10px] font-bold text-white">{item.badge}</span>}
      </button>
    );
  });

  return (
    <div className="min-h-screen bg-[#f4f8f5] text-slate-900 md:flex">
      <aside className="bg-[#003816] text-white md:fixed md:inset-y-0 md:flex md:w-72 md:flex-col">
        <div className="border-b border-white/10 px-5 py-5">
          <p className="text-lg font-extrabold">EcoPulse AI</p>
          <p className="mt-1 text-xs font-bold uppercase tracking-wide text-emerald-100">Field Operations Portal</p>
        </div>
        <div className="border-b border-white/10 px-5 py-4">
          <p className="truncate text-sm font-bold">{name}</p>
          <p className="mt-1 text-xs text-emerald-100">{loginId}</p>
          <p className="mt-1 text-xs text-emerald-100">{ward}</p>
          <span className="mt-3 inline-flex rounded-full bg-white/15 px-2.5 py-1 text-xs font-bold">{roleName}</span>
        </div>
        <nav aria-label={`${roleName} field operations`} className="flex gap-1 overflow-x-auto px-3 py-3 md:flex-1 md:flex-col md:overflow-y-auto">
          {navItems}
        </nav>
        <div className="hidden gap-2 border-t border-white/10 p-4 md:flex">
          <button type="button" onClick={onProfile} className="flex flex-1 items-center justify-center gap-2 rounded-lg bg-white/10 px-3 py-2 text-sm font-semibold hover:bg-white/15">
            <UserRound size={16} /> Profile
          </button>
          <button type="button" onClick={onLogout} className="flex items-center justify-center gap-2 rounded-lg bg-red-500/15 px-3 py-2 text-sm font-semibold text-red-100 hover:bg-red-500/25">
            <LogOut size={16} /><span>Sign out</span>
          </button>
        </div>
      </aside>

      <main className="min-w-0 flex-1 md:ml-72">
        <header className="sticky top-0 z-20 border-b border-slate-200 bg-white/95 px-4 py-3 backdrop-blur sm:px-6">
          <div className="flex flex-wrap items-center justify-between gap-3">
            <div className="min-w-0">
              <p className="text-xs font-bold uppercase tracking-[0.13em] text-emerald-800">Field Operations Portal</p>
              <p className="truncate text-sm font-semibold text-slate-800">{roleName} workspace · {ward}</p>
            </div>
            <div className="flex items-center gap-2">
              <button type="button" onClick={onRefresh} className="inline-flex items-center gap-2 rounded-lg border border-slate-200 px-3 py-2 text-sm font-semibold hover:bg-slate-50" aria-label="Refresh field operations data">
                <RefreshCw size={16} /><span className="hidden sm:inline">Refresh</span>
              </button>
              <button type="button" onClick={onProfile} className="inline-flex items-center gap-2 rounded-lg border border-slate-200 px-3 py-2 text-sm font-semibold hover:bg-slate-50">
                <UserRound size={16} /><span className="hidden sm:inline">Account</span>
              </button>
              <button type="button" onClick={onLogout} className="inline-flex items-center gap-2 rounded-lg border border-red-200 px-3 py-2 text-sm font-semibold text-red-700 hover:bg-red-50 md:hidden">
                <LogOut size={16} /><span>Sign out</span>
              </button>
            </div>
          </div>
        </header>
        {children}
      </main>
    </div>
  );
}
