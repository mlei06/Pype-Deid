import { NavLink, Outlet } from 'react-router-dom';
import {
  Blocks,
  Network,
  Play,
  BarChart3,
  Database,
  BookOpen,
  Rocket,
  Activity,
} from 'lucide-react';
import { clsx } from 'clsx';

const TABS = [
  { to: '/create', label: 'Create', icon: Blocks },
  { to: '/pipelines', label: 'Pipelines', icon: Network },
  { to: '/inference', label: 'Inference', icon: Play },
  { to: '/evaluate', label: 'Evaluate', icon: BarChart3 },
  { to: '/datasets', label: 'Datasets', icon: Database },
  { to: '/dictionaries', label: 'Dictionaries', icon: BookOpen },
  { to: '/deploy', label: 'Deploy', icon: Rocket },
  { to: '/audit', label: 'Audit', icon: Activity },
] as const;

export default function Shell() {
  return (
    <div className="flex h-screen flex-col bg-gray-50">
      <header className="flex h-12 shrink-0 items-center border-b border-gray-200 bg-white px-4">
        <span className="mr-8 text-sm font-semibold tracking-tight text-gray-900">
          Clinical De-ID Playground
        </span>
        <nav className="flex gap-1">
          {TABS.map(({ to, label, icon: Icon }) => (
            <NavLink
              key={to}
              to={to}
              className={({ isActive }) =>
                clsx(
                  'flex items-center gap-1.5 rounded-md px-3 py-1.5 text-sm font-medium transition-colors',
                  isActive
                    ? 'bg-gray-900 text-white'
                    : 'text-gray-600 hover:bg-gray-100 hover:text-gray-900',
                )
              }
            >
              <Icon size={15} />
              {label}
            </NavLink>
          ))}
        </nav>
      </header>
      <main className="flex-1 overflow-hidden">
        <Outlet />
      </main>
    </div>
  );
}
