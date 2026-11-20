import { type ReactNode, useState } from 'react';
import { Link, useLocation } from 'react-router-dom';
import {
  BarChart3,
  LayoutDashboard,
  Briefcase,
  FlaskConical,
  Moon,
  Sun,
  Menu,
  X,
  LineChart,
  Sparkles,
  Landmark,
  Search,
  Settings,
  Gavel,
  HeartPulse,
  Bot,
  BookMarked,
  Database,
  Radar,
  Terminal,
} from 'lucide-react';

const NAV_ITEMS = [
  { to: '/', label: 'Today', icon: LayoutDashboard },
  { to: '/rashifal', label: 'Rashifal', icon: Sparkles },
  { to: '/holdings', label: 'My holdings', icon: Briefcase },
  { to: '/market', label: 'Market overview', icon: LineChart },
  { to: '/symbols', label: 'Explore stocks', icon: BarChart3 },
];
const ADVANCED_ITEMS = [
  { to: '/prescription', label: 'Advanced advisor', icon: Sparkles },
  { to: '/signals', label: 'Strategy signals', icon: Radar },
  { to: '/portfolio', label: 'Paper portfolio', icon: Briefcase },
  { to: '/backtest', label: 'Backtest', icon: FlaskConical },
  { to: '/analytics', label: 'Analytics', icon: LineChart },
  { to: '/journal', label: 'Prediction journal', icon: BookMarked },
  { to: '/auction', label: 'Auction', icon: Gavel },
  { to: '/meroshare', label: 'MeroShare import', icon: Landmark },
  { to: '/research', label: 'Research', icon: Search },
  { to: '/data', label: 'Stored data', icon: Database },
  { to: '/ai', label: 'AI', icon: Bot },
  { to: '/operations', label: 'Operations', icon: Terminal },
  { to: '/health', label: 'Health', icon: HeartPulse },
  { to: '/settings', label: 'Settings', icon: Settings },
];

interface Props {
  children: ReactNode;
}

export function RootLayout({ children }: Props) {
  const location = useLocation();
  const [sidebarOpen, setSidebarOpen] = useState(false);
  const [dark, setDark] = useState(() => {
    if (typeof window !== 'undefined') {
      return localStorage.getItem('theme') === 'dark';
    }
    return false;
  });

  const toggleDark = () => {
    const next = !dark;
    setDark(next);
    document.documentElement.classList.toggle('dark', next);
    localStorage.setItem('theme', next ? 'dark' : 'light');
  };

  return (
    <div className="flex min-h-screen">
      {/* Mobile overlay */}
      {sidebarOpen && (
        <div
          className="fixed inset-0 z-20 bg-black/40 lg:hidden"
          onClick={() => setSidebarOpen(false)}
        />
      )}

      {/* Sidebar */}
      <aside
        className={`fixed inset-y-0 left-0 z-30 flex w-56 flex-col border-r border-border bg-surface transition-transform duration-200 lg:sticky lg:top-0 lg:h-screen lg:translate-x-0 ${
          sidebarOpen ? 'translate-x-0' : '-translate-x-full'
        }`}
      >
        <div className="flex h-16 items-center gap-3 border-b border-border px-6">
          <div className="flex h-8 w-8 items-center justify-center rounded-lg bg-nepse-600 text-white text-sm font-bold">
            N
          </div>
          <span className="text-base font-bold text-text-primary">NEPSE Trader</span>
        </div>

        <nav className="flex-1 space-y-1 overflow-y-auto p-4" aria-label="Main navigation">
          <p className="px-3 pt-5 pb-3 text-[9px] tracking-[0.16em] text-text-secondary">YOUR WORKSPACE</p>
          {NAV_ITEMS.map((item) => {
            const active = location.pathname === item.to;
            return (
              <Link
                key={item.to}
                to={item.to}
                onClick={() => setSidebarOpen(false)}
                className={`flex items-center gap-3 rounded-lg px-3 py-2.5 text-sm font-medium transition-all ${
                  active
                    ? 'bg-nepse-50 text-nepse-700 dark:bg-nepse-900/30 dark:text-nepse-400 shadow-sm'
                    : 'text-text-secondary hover:bg-surface-tertiary hover:text-text-primary'
                }`}
              >
                <item.icon className="h-4 w-4" />
                {item.label}
              </Link>
            );
          })}
          <details className="pt-7" open={ADVANCED_ITEMS.some(item => item.to === location.pathname) || undefined}>
            <summary className="cursor-pointer px-3 py-3 text-xs text-text-secondary">Research & tools</summary>
            {ADVANCED_ITEMS.map(item => <Link key={item.to} to={item.to} onClick={() => setSidebarOpen(false)} className={`flex items-center gap-3 rounded-lg px-3 py-2.5 text-xs ${location.pathname === item.to ? 'bg-nepse-50 text-nepse-700' : 'text-text-secondary hover:bg-surface-tertiary'}`}><item.icon size={14} />{item.label}</Link>)}
          </details>
        </nav>

        <div className="border-t border-border p-4">
          <button
            onClick={toggleDark}
            className="flex w-full items-center gap-3 rounded-lg px-3 py-2.5 text-sm font-medium text-text-secondary transition-colors hover:bg-surface-tertiary hover:text-text-primary"
          >
            {dark ? <Sun className="h-4 w-4" /> : <Moon className="h-4 w-4" />}
            {dark ? 'Light mode' : 'Dark mode'}
          </button>
        </div>
      </aside>

      {/* Main area */}
      <div className="flex flex-1 flex-col min-w-0">
        <header className="sticky top-0 z-10 flex h-16 items-center gap-4 border-b border-border bg-surface/80 px-4 backdrop-blur-sm lg:px-8">
          <button
            className="lg:hidden text-text-secondary hover:text-text-primary"
            aria-label={sidebarOpen ? 'Close navigation' : 'Open navigation'}
            onClick={() => setSidebarOpen(!sidebarOpen)}
          >
            {sidebarOpen ? <X className="h-5 w-5" /> : <Menu className="h-5 w-5" />}
          </button>
          <div className="flex items-center gap-2 text-xs text-text-tertiary">
            <LineChart className="h-3.5 w-3.5" />
            <span className="font-medium">{[...NAV_ITEMS, ...ADVANCED_ITEMS].find(item => item.to === location.pathname)?.label ?? 'Explore'}</span>
            <span className="rounded-full border border-nepse-200 bg-nepse-50 px-1.5 py-0.5 text-[10px] font-semibold text-nepse-600 dark:border-nepse-800 dark:bg-nepse-900/30 dark:text-nepse-400">BETA</span>
          </div>
          <div className="flex-1" />
          <span className="text-xs text-text-tertiary">
            {new Date().toLocaleDateString('en-NP', {
              year: 'numeric',
              month: 'short',
              day: 'numeric',
            })}
          </span>
        </header>

        <main className="page-enter flex-1 p-4 lg:p-8 xl:px-10">{children}</main>
      </div>
    </div>
  );
}
