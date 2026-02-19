import { useState } from 'react'
import { useQuery } from '@tanstack/react-query'
import { getFailures, getPrompts, getContext, type Failure } from '../lib/api'

export default function Failures() {
    const [selectedPrompt, setSelectedPrompt] = useState<string>('')
    const [expandedId, setExpandedId] = useState<string | null>(null)

    const { data: prompts } = useQuery({
        queryKey: ['prompts'],
        queryFn: getPrompts,
    })

    const { data: failures, isLoading } = useQuery({
        queryKey: ['failures', selectedPrompt],
        queryFn: () => getFailures('2025-2026', selectedPrompt || undefined),
    })

    const { data: expandedContext } = useQuery({
        queryKey: ['context', expandedId],
        queryFn: () => getContext(expandedId!),
        enabled: !!expandedId,
    })

    if (isLoading) {
        return <div className="loading"><div className="spinner" /></div>
    }

    const failureCount = failures?.length ?? 0

    // Group failures by prompt
    const byPrompt: Record<string, Failure[]> = {}
    failures?.forEach(f => {
        if (!byPrompt[f.prompt_version]) byPrompt[f.prompt_version] = []
        byPrompt[f.prompt_version].push(f)
    })

    return (
        <div>
            <header className="page-header">
                <h1 className="page-title">🚨 Failures</h1>
                <p className="page-subtitle">Deep dive into failed predictions</p>
            </header>

            {/* Summary */}
            <div className="grid grid-4" style={{ marginBottom: 'var(--space-xl)' }}>
                <div className="card">
                    <div className="metric">
                        <span className="metric-value" style={{ color: 'var(--danger)' }}>{failureCount}</span>
                        <span className="metric-label">Total Failures</span>
                    </div>
                </div>
                {Object.entries(byPrompt).slice(0, 3).map(([prompt, list]) => (
                    <div key={prompt} className="card">
                        <div className="metric">
                            <span className="metric-value">{list.length}</span>
                            <span className="metric-label">{prompt}</span>
                        </div>
                    </div>
                ))}
            </div>

            {/* Filter */}
            <div className="card" style={{ marginBottom: 'var(--space-lg)' }}>
                <div style={{ display: 'flex', gap: 'var(--space-md)', alignItems: 'center' }}>
                    <label style={{ margin: 0, whiteSpace: 'nowrap' }}>Filter by prompt:</label>
                    <select
                        value={selectedPrompt}
                        onChange={e => setSelectedPrompt(e.target.value)}
                        style={{ maxWidth: '300px' }}
                    >
                        <option value="">All prompts</option>
                        {prompts?.prompts.map(p => (
                            <option key={p.key} value={p.key}>{p.key} - {p.name}</option>
                        ))}
                    </select>
                </div>
            </div>

            {/* Failures Table */}
            <div className="card">
                <div className="card-header">
                    <h3 className="card-title">Failed Predictions</h3>
                </div>

                {failures && failures.length > 0 ? (
                    <div className="table-container">
                        <table>
                            <thead>
                                <tr>
                                    <th>Match</th>
                                    <th>Predicted</th>
                                    <th>Actual</th>
                                    <th>Confidence</th>
                                    <th>Prompt</th>
                                    <th>Actions</th>
                                </tr>
                            </thead>
                            <tbody>
                                {failures.map(f => (
                                    <>
                                        <tr key={f.fixture_id} className="failure-row">
                                            <td><strong>{f.home_team} vs {f.away_team}</strong></td>
                                            <td>{f.predicted_score}</td>
                                            <td style={{ color: 'var(--success)' }}>{f.actual_score}</td>
                                            <td>{f.confidence}%</td>
                                            <td><span className="badge badge-neutral">{f.prompt_version}</span></td>
                                            <td>
                                                <button
                                                    className="btn btn-secondary"
                                                    onClick={() => setExpandedId(expandedId === f.fixture_id ? null : f.fixture_id)}
                                                >
                                                    {expandedId === f.fixture_id ? 'Hide' : 'Deep Dive'}
                                                </button>
                                            </td>
                                        </tr>

                                        {/* Expanded Deep Dive */}
                                        {expandedId === f.fixture_id && (
                                            <tr>
                                                <td colSpan={6} style={{ padding: 'var(--space-lg)', background: 'var(--bg-surface)' }}>
                                                    <div className="grid grid-2" style={{ gap: 'var(--space-lg)' }}>
                                                        {/* Left: Analysis info */}
                                                        <div>
                                                            <h4 style={{ marginBottom: 'var(--space-md)' }}>📊 Model Reasoning</h4>
                                                            {f.reasoning ? (
                                                                <div style={{
                                                                    background: 'var(--bg-secondary)',
                                                                    padding: 'var(--space-md)',
                                                                    borderRadius: 'var(--radius-md)',
                                                                    fontSize: '0.875rem',
                                                                    lineHeight: 1.6
                                                                }}>
                                                                    {f.reasoning}
                                                                </div>
                                                            ) : (
                                                                <p style={{ color: 'var(--text-muted)' }}>No reasoning available</p>
                                                            )}

                                                            <h4 style={{ margin: 'var(--space-lg) 0 var(--space-md)' }}>⚽ Match Reality</h4>
                                                            {f.reality_narrative ? (
                                                                <div style={{
                                                                    background: 'var(--bg-secondary)',
                                                                    padding: 'var(--space-md)',
                                                                    borderRadius: 'var(--radius-md)',
                                                                    fontSize: '0.875rem',
                                                                    lineHeight: 1.6
                                                                }}>
                                                                    {f.reality_narrative}
                                                                </div>
                                                            ) : (
                                                                <p style={{ color: 'var(--text-muted)' }}>No reality narrative available</p>
                                                            )}
                                                        </div>

                                                        {/* Right: Context used */}
                                                        <div>
                                                            <h4 style={{ marginBottom: 'var(--space-md)' }}>📋 Context Used</h4>
                                                            <div className="json-viewer" style={{ maxHeight: '400px', overflow: 'auto' }}>
                                                                <pre>{JSON.stringify(expandedContext, null, 2)}</pre>
                                                            </div>
                                                        </div>
                                                    </div>
                                                </td>
                                            </tr>
                                        )}
                                    </>
                                ))}
                            </tbody>
                        </table>
                    </div>
                ) : (
                    <div className="empty-state">
                        <div className="empty-state-icon">🎉</div>
                        <p>No failures found! Your model is performing well.</p>
                    </div>
                )}
            </div>
        </div>
    )
}
