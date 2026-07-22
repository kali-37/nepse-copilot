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
} from 'lucide-react';

const NAV_ITEMS = [
  { to: '/', label: 'Dashboard', icon: LayoutDashboard },
  { to: '/symbols', label: 'Symbols', icon: BarChart3 },
  { to: '/portfolio', label: 'Portfolio', icon: Briefcase },
  { to: '/backtest', label: 'Backtest', icon: FlaskConical },
];

interface Props {
  children: ReactNode;
}

export function RootLayout({ children }: Props) {
  const location = useLocation();
  const [sidebarOpen, setSidebarOpen] = useState(false);
  const [dark, setDark] = useState(() => {
    if (typeof window !== 'undefined') {
      return localStorage.getItem('theme') === 'dark' ||
        (!localStorage.getItem('theme') && window.matchMedia('(prefers-color-scheme: dark)').matches);
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
        className={`fixed inset-y-0 left-0 z-30 flex w-64 flex-col border-r border-border bg-surface transition-transform duration-200 lg:static lg:translate-x-0 ${
          sidebarOpen ? 'translate-x-0' : '-translate-x-full'
        }`}
      >
        <div className="flex h-16 items-center gap-3 border-b border-border px-6">
          <div className="flex h-8 w-8 items-center justify-center rounded-lg bg-nepse-600 text-white text-sm font-bold">
            N
          </div>
          <span className="text-base font-bold text-text-primary">NEPSE Trader</span>
        </div>

        <nav className="flex-1 space-y-1 p-4">
          {NAV_ITEMS.map((item) => {
            const active = location.pathname === item.to;
            return (
              <Link
                key={item.to}
                to={item.to}
                onClick={() => setSidebarOpen(false)}
                className={`flex items-center gap-3 rounded-lg px-3 py-2.5 text-sm font-medium transition-colors ${
                  active
                    ? 'bg-nepse-50 text-nepse-700 dark:bg-nepse-900/30 dark:text-nepse-400'
                    : 'text-text-secondary hover:bg-surface-tertiary hover:text-text-primary'
                }`}
              >
                <item.icon className="h-4 w-4" />
                {item.label}
              </Link>
            );
          })}
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
            onClick={() => setSidebarOpen(true)}
          >
            {sidebarOpen ? <X className="h-5 w-5" /> : <Menu className="h-5 w-5" />}
          </button>
          <div className="flex items-center gap-2 text-xs text-text-tertiary">
            <LineChart className="h-3.5 w-3.5" />
            <span>NEPSE</span>
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

        <main className="flex-1 p-4 lg:p-8">{children}</main>
      </div>
    </div>
  );
}
