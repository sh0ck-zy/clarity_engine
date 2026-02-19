import { Routes, Route, NavLink, useLocation } from 'react-router-dom'
import { useQuery } from '@tanstack/react-query'
import { healthCheck } from './lib/api'

// Views
import Dashboard from './views/Dashboard'
import Lab from './views/Lab'
import Backtest from './views/Backtest'
import Failures from './views/Failures'
import Compare from './views/Compare'

function App() {
    const location = useLocation()

    const { data: health } = useQuery({
        queryKey: ['health'],
        queryFn: healthCheck,
        refetchInterval: 30000,
    })

    const navItems = [
        { path: '/', label: 'Dashboard', icon: '📊' },
        { path: '/lab', label: 'Lab', icon: '🧪' },
        { path: '/backtest', label: 'Backtest', icon: '🔄' },
        { path: '/failures', label: 'Failures', icon: '🚨' },
        { path: '/compare', label: 'Compare', icon: '⚖️' },
    ]

    return (
        <div className="app-layout">
            <aside className="sidebar">
                <div className="sidebar-logo">
                    ⚽ Clarity Engine
                </div>

                <nav className="sidebar-nav">
                    {navItems.map(item => (
                        <NavLink
                            key={item.path}
                            to={item.path}
                            className={({ isActive }) => `nav-link ${isActive ? 'active' : ''}`}
                        >
                            <span>{item.icon}</span>
                            <span>{item.label}</span>
                        </NavLink>
                    ))}
                </nav>

                <div style={{ marginTop: 'auto', fontSize: '0.75rem', color: 'var(--text-muted)' }}>
                    {health?.status === 'ok' ? '🟢 Connected' : '🔴 Disconnected'}
                </div>
            </aside>

            <main className="main-content">
                <Routes>
                    <Route path="/" element={<Dashboard />} />
                    <Route path="/lab" element={<Lab />} />
                    <Route path="/backtest" element={<Backtest />} />
                    <Route path="/failures" element={<Failures />} />
                    <Route path="/compare" element={<Compare />} />
                </Routes>
            </main>
        </div>
    )
}

export default App
