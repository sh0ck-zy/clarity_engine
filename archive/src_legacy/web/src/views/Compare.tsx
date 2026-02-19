import { useState } from 'react'
import { useQuery } from '@tanstack/react-query'
import { getPrompts, getRounds } from '../lib/api'

interface PromptStats {
    total: number
    correct: number
    accuracy: number
    avgConfidence: number
}

export default function Compare() {
    const [promptA, setPromptA] = useState<string>('')
    const [promptB, setPromptB] = useState<string>('')

    const { data: prompts } = useQuery({
        queryKey: ['prompts'],
        queryFn: getPrompts,
    })

    const { data: rounds } = useQuery({
        queryKey: ['rounds'],
        queryFn: getRounds,
    })

    // Calculate mock stats for demo (in real app, fetch from backend)
    const getStatsForPrompt = (prompt: string): PromptStats => {
        // This would be a real API call in production
        const hash = prompt.split('').reduce((a, b) => { a = ((a << 5) - a) + b.charCodeAt(0); return a & a }, 0)
        return {
            total: 40 + Math.abs(hash % 20),
            correct: 25 + Math.abs(hash % 15),
            accuracy: 55 + Math.abs(hash % 20),
            avgConfidence: 60 + Math.abs(hash % 25),
        }
    }

    const statsA = promptA ? getStatsForPrompt(promptA) : null
    const statsB = promptB ? getStatsForPrompt(promptB) : null

    const canCompare = promptA && promptB && promptA !== promptB

    return (
        <div>
            <header className="page-header">
                <h1 className="page-title">⚖️ Compare</h1>
                <p className="page-subtitle">Head-to-head prompt comparison</p>
            </header>

            {/* Prompt Selectors */}
            <div className="grid grid-2" style={{ marginBottom: 'var(--space-xl)', gap: 'var(--space-lg)' }}>
                <div className="card">
                    <div className="card-header">
                        <h3 className="card-title">Prompt A</h3>
                    </div>
                    <select
                        value={promptA}
                        onChange={e => setPromptA(e.target.value)}
                    >
                        <option value="">Select prompt...</option>
                        {prompts?.prompts.map(p => (
                            <option key={p.key} value={p.key}>{p.key} - {p.name}</option>
                        ))}
                    </select>
                </div>

                <div className="card">
                    <div className="card-header">
                        <h3 className="card-title">Prompt B</h3>
                    </div>
                    <select
                        value={promptB}
                        onChange={e => setPromptB(e.target.value)}
                    >
                        <option value="">Select prompt...</option>
                        {prompts?.prompts.filter(p => p.key !== promptA).map(p => (
                            <option key={p.key} value={p.key}>{p.key} - {p.name}</option>
                        ))}
                    </select>
                </div>
            </div>

            {/* Comparison */}
            {canCompare && statsA && statsB ? (
                <>
                    {/* Head to head stats */}
                    <div className="card" style={{ marginBottom: 'var(--space-lg)' }}>
                        <div className="card-header">
                            <h3 className="card-title">Head to Head</h3>
                        </div>

                        <div className="grid grid-2" style={{ gap: 'var(--space-xl)', textAlign: 'center' }}>
                            {/* Prompt A */}
                            <div style={{
                                padding: 'var(--space-xl)',
                                background: statsA.accuracy > statsB.accuracy ? 'var(--success-soft)' : 'var(--bg-surface)',
                                borderRadius: 'var(--radius-lg)'
                            }}>
                                <div style={{ fontSize: '0.875rem', color: 'var(--text-muted)', marginBottom: 'var(--space-sm)' }}>
                                    {promptA}
                                </div>
                                <div style={{ fontSize: '3rem', fontWeight: 700 }}>
                                    {statsA.accuracy.toFixed(1)}%
                                </div>
                                <div style={{ color: 'var(--text-muted)' }}>
                                    {statsA.correct}/{statsA.total} correct
                                </div>
                            </div>

                            {/* Prompt B */}
                            <div style={{
                                padding: 'var(--space-xl)',
                                background: statsB.accuracy > statsA.accuracy ? 'var(--success-soft)' : 'var(--bg-surface)',
                                borderRadius: 'var(--radius-lg)'
                            }}>
                                <div style={{ fontSize: '0.875rem', color: 'var(--text-muted)', marginBottom: 'var(--space-sm)' }}>
                                    {promptB}
                                </div>
                                <div style={{ fontSize: '3rem', fontWeight: 700 }}>
                                    {statsB.accuracy.toFixed(1)}%
                                </div>
                                <div style={{ color: 'var(--text-muted)' }}>
                                    {statsB.correct}/{statsB.total} correct
                                </div>
                            </div>
                        </div>

                        {/* Winner */}
                        <div style={{
                            marginTop: 'var(--space-xl)',
                            padding: 'var(--space-lg)',
                            background: 'var(--accent-soft)',
                            borderRadius: 'var(--radius-md)',
                            textAlign: 'center'
                        }}>
                            {statsA.accuracy === statsB.accuracy ? (
                                <span style={{ fontSize: '1.25rem', fontWeight: 600 }}>🤝 It's a tie!</span>
                            ) : (
                                <span style={{ fontSize: '1.25rem', fontWeight: 600 }}>
                                    🏆 Winner: <strong>{statsA.accuracy > statsB.accuracy ? promptA : promptB}</strong>
                                    {' '}(+{Math.abs(statsA.accuracy - statsB.accuracy).toFixed(1)}%)
                                </span>
                            )}
                        </div>
                    </div>

                    {/* Detailed Metrics */}
                    <div className="card">
                        <div className="card-header">
                            <h3 className="card-title">Detailed Metrics</h3>
                        </div>
                        <div className="table-container">
                            <table>
                                <thead>
                                    <tr>
                                        <th>Metric</th>
                                        <th>{promptA}</th>
                                        <th>{promptB}</th>
                                        <th>Difference</th>
                                    </tr>
                                </thead>
                                <tbody>
                                    <tr>
                                        <td><strong>Accuracy</strong></td>
                                        <td>{statsA.accuracy.toFixed(1)}%</td>
                                        <td>{statsB.accuracy.toFixed(1)}%</td>
                                        <td style={{ color: statsA.accuracy > statsB.accuracy ? 'var(--success)' : statsA.accuracy < statsB.accuracy ? 'var(--danger)' : 'var(--text-muted)' }}>
                                            {statsA.accuracy > statsB.accuracy ? '+' : ''}{(statsA.accuracy - statsB.accuracy).toFixed(1)}%
                                        </td>
                                    </tr>
                                    <tr>
                                        <td><strong>Total Predictions</strong></td>
                                        <td>{statsA.total}</td>
                                        <td>{statsB.total}</td>
                                        <td>{statsA.total - statsB.total}</td>
                                    </tr>
                                    <tr>
                                        <td><strong>Correct Predictions</strong></td>
                                        <td>{statsA.correct}</td>
                                        <td>{statsB.correct}</td>
                                        <td>{statsA.correct - statsB.correct}</td>
                                    </tr>
                                    <tr>
                                        <td><strong>Avg Confidence</strong></td>
                                        <td>{statsA.avgConfidence.toFixed(1)}%</td>
                                        <td>{statsB.avgConfidence.toFixed(1)}%</td>
                                        <td>{(statsA.avgConfidence - statsB.avgConfidence).toFixed(1)}%</td>
                                    </tr>
                                </tbody>
                            </table>
                        </div>
                    </div>
                </>
            ) : (
                <div className="empty-state">
                    <div className="empty-state-icon">⚖️</div>
                    <p>Select two different prompts to compare their performance</p>
                </div>
            )}
        </div>
    )
}
