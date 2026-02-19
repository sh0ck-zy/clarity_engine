import { useState, useEffect } from 'react'
import { useQuery } from '@tanstack/react-query'
import { getRounds, getFixtures, getPrompts, getContext, runAnalysis, type Fixture } from '../lib/api'

interface BacktestResult {
    fixture_id: string
    home_team: string
    away_team: string
    round: number
    status: 'success' | 'error' | 'pending'
    predicted_score?: string
    confidence?: number
    is_correct?: boolean
    error?: string
}

export default function Backtest() {
    const [selectedRounds, setSelectedRounds] = useState<number[]>([])
    const [selectedPrompt, setSelectedPrompt] = useState<string>('')
    const [results, setResults] = useState<BacktestResult[]>([])
    const [progress, setProgress] = useState(0)
    const [isRunning, setIsRunning] = useState(false)
    const [previewFixtureId, setPreviewFixtureId] = useState<string | null>(null)
    const [showContextJson, setShowContextJson] = useState(true) // Default ON

    const { data: rounds } = useQuery({
        queryKey: ['rounds'],
        queryFn: getRounds,
    })

    const { data: prompts } = useQuery({
        queryKey: ['prompts'],
        queryFn: getPrompts,
    })

    // Get rounds that have analyses (completed rounds with data)
    const completedRounds = rounds?.filter(r => r.analyses_total > 0) ?? []

    // Auto-select last 5 COMPLETED rounds (those with analyses) when rounds load
    useEffect(() => {
        if (rounds && rounds.length > 0 && selectedRounds.length === 0) {
            // Get rounds with analyses (completed), sorted descending, take first 5
            const withAnalyses = rounds
                .filter(r => r.analyses_total > 0)
                .sort((a, b) => b.round - a.round)
                .slice(0, 5)
                .map(r => r.round)

            if (withAnalyses.length > 0) {
                setSelectedRounds(withAnalyses)
            }
        }
    }, [rounds])

    // Fetch fixtures for all selected rounds
    const { data: allFixtures } = useQuery({
        queryKey: ['fixtures', 'multi', selectedRounds],
        queryFn: async () => {
            if (selectedRounds.length === 0) return []
            const allFix: Fixture[] = []
            for (const round of selectedRounds) {
                const fixtures = await getFixtures('2025-2026', round)
                allFix.push(...fixtures)
            }
            return allFix
        },
        enabled: selectedRounds.length > 0,
    })

    // Auto-select first fixture for preview when fixtures load
    useEffect(() => {
        if (allFixtures && allFixtures.length > 0 && !previewFixtureId) {
            setPreviewFixtureId(allFixtures[0].fixture_id)
        }
    }, [allFixtures])

    // Get context for preview
    const { data: previewContext, isLoading: contextLoading, error: contextError } = useQuery({
        queryKey: ['context', previewFixtureId],
        queryFn: () => getContext(previewFixtureId!),
        enabled: !!previewFixtureId && showContextJson,
        retry: false,
    })

    const toggleRound = (round: number) => {
        setSelectedRounds(prev =>
            prev.includes(round)
                ? prev.filter(r => r !== round)
                : [...prev, round].sort((a, b) => b - a)
        )
        setPreviewFixtureId(null) // Reset preview when rounds change
    }

    const selectCompletedRounds = (n: number) => {
        const completed = completedRounds
            .sort((a, b) => b.round - a.round)
            .slice(0, n)
            .map(r => r.round)
        setSelectedRounds(completed)
        setPreviewFixtureId(null)
    }

    const selectNone = () => {
        setSelectedRounds([])
        setPreviewFixtureId(null)
    }

    const totalFixtures = allFixtures?.length ?? 0

    const runBacktest = async () => {
        if (!allFixtures || !selectedPrompt) return

        setIsRunning(true)
        setResults([])
        setProgress(0)

        const newResults: BacktestResult[] = []

        for (let i = 0; i < allFixtures.length; i++) {
            const fixture = allFixtures[i]
            setProgress(((i + 1) / allFixtures.length) * 100)

            try {
                const result = await runAnalysis(fixture.fixture_id, selectedPrompt, false)
                newResults.push({
                    fixture_id: fixture.fixture_id,
                    home_team: fixture.home_team,
                    away_team: fixture.away_team,
                    round: fixture.round ?? 0,
                    status: 'success',
                    predicted_score: result.predicted_score ?? undefined,
                    confidence: result.confidence ?? undefined,
                    is_correct: result.is_correct ?? undefined,
                })
            } catch (error) {
                newResults.push({
                    fixture_id: fixture.fixture_id,
                    home_team: fixture.home_team,
                    away_team: fixture.away_team,
                    round: fixture.round ?? 0,
                    status: 'error',
                    error: error instanceof Error ? error.message : 'Unknown error',
                })
            }

            setResults([...newResults])
            await new Promise(r => setTimeout(r, 500))
        }

        setIsRunning(false)
    }

    const successCount = results.filter(r => r.status === 'success').length
    const correctCount = results.filter(r => r.is_correct === true).length
    const failCount = results.filter(r => r.is_correct === false).length

    return (
        <div>
            <header className="page-header">
                <h1 className="page-title">🔄 Backtest</h1>
                <p className="page-subtitle">Run batch analyses on completed rounds with time-travel safety</p>
            </header>

            {/* Stepper */}
            <div className="stepper">
                <div className={`step ${selectedRounds.length > 0 ? 'completed' : 'active'}`}>
                    1. Select Rounds
                </div>
                <div className={`step ${selectedPrompt ? 'completed' : selectedRounds.length > 0 ? 'active' : ''}`}>
                    2. Select Prompt
                </div>
                <div className={`step ${isRunning ? 'active' : results.length > 0 ? 'completed' : ''}`}>
                    3. Run Backtest
                </div>
                <div className={`step ${results.length > 0 && !isRunning ? 'active' : ''}`}>
                    4. Review Results
                </div>
            </div>

            <div className="grid grid-2" style={{ gap: 'var(--space-lg)' }}>
                {/* Left Column: Configuration */}
                <div>
                    {/* Round Selection */}
                    <div className="card" style={{ marginBottom: 'var(--space-lg)' }}>
                        <div className="card-header">
                            <h3 className="card-title">Completed Rounds ({selectedRounds.length} selected)</h3>
                            <div style={{ display: 'flex', gap: 'var(--space-sm)' }}>
                                <button className="btn btn-secondary" onClick={() => selectCompletedRounds(5)}>Last 5</button>
                                <button className="btn btn-secondary" onClick={() => selectCompletedRounds(completedRounds.length)}>All</button>
                                <button className="btn btn-secondary" onClick={selectNone}>None</button>
                            </div>
                        </div>

                        {completedRounds.length === 0 ? (
                            <div className="empty-state" style={{ padding: 'var(--space-md)' }}>
                                <p>No completed rounds with analyses found</p>
                            </div>
                        ) : (
                            <div style={{
                                display: 'grid',
                                gridTemplateColumns: 'repeat(auto-fill, minmax(140px, 1fr))',
                                gap: 'var(--space-sm)',
                                maxHeight: '200px',
                                overflowY: 'auto'
                            }}>
                                {completedRounds.sort((a, b) => b.round - a.round).map(r => (
                                    <label
                                        key={r.round}
                                        style={{
                                            display: 'flex',
                                            alignItems: 'center',
                                            gap: 'var(--space-sm)',
                                            padding: 'var(--space-sm)',
                                            background: selectedRounds.includes(r.round) ? 'var(--accent-soft)' : 'var(--bg-surface)',
                                            borderRadius: 'var(--radius-md)',
                                            cursor: 'pointer',
                                            border: selectedRounds.includes(r.round) ? '1px solid var(--accent)' : '1px solid var(--border-subtle)'
                                        }}
                                    >
                                        <input
                                            type="checkbox"
                                            checked={selectedRounds.includes(r.round)}
                                            onChange={() => toggleRound(r.round)}
                                            style={{ width: 'auto' }}
                                        />
                                        <span>R{r.round}</span>
                                        <span style={{ fontSize: '0.7rem', color: 'var(--text-muted)' }}>
                                            {r.analyses_total} analyses
                                        </span>
                                    </label>
                                ))}
                            </div>
                        )}
                    </div>

                    {/* Prompt Selection */}
                    <div className="card" style={{ marginBottom: 'var(--space-lg)' }}>
                        <div className="card-header">
                            <h3 className="card-title">Prompt</h3>
                        </div>
                        <select
                            value={selectedPrompt}
                            onChange={e => setSelectedPrompt(e.target.value)}
                        >
                            <option value="">Select prompt...</option>
                            {prompts?.prompts.map(p => (
                                <option key={p.key} value={p.key}>{p.key} - {p.name}</option>
                            ))}
                        </select>
                    </div>

                    {/* Run Button */}
                    <div className="card">
                        <div className="card-header">
                            <h3 className="card-title">Execute</h3>
                        </div>
                        <button
                            className="btn btn-primary"
                            style={{ width: '100%' }}
                            disabled={selectedRounds.length === 0 || !selectedPrompt || isRunning}
                            onClick={runBacktest}
                        >
                            {isRunning
                                ? `Running... ${progress.toFixed(0)}%`
                                : `Run Backtest (${totalFixtures} fixtures from ${selectedRounds.length} rounds)`
                            }
                        </button>

                        {isRunning && (
                            <div className="progress" style={{ marginTop: 'var(--space-md)' }}>
                                <div className="progress-fill" style={{ width: `${progress}%` }} />
                            </div>
                        )}
                    </div>
                </div>

                {/* Right Column: Context Preview */}
                <div>
                    <div className="card">
                        <div className="card-header">
                            <h3 className="card-title">📋 Context JSON Preview</h3>
                            <label className="toggle">
                                <input
                                    type="checkbox"
                                    checked={showContextJson}
                                    onChange={() => setShowContextJson(!showContextJson)}
                                />
                                <span className="toggle-slider" />
                            </label>
                        </div>

                        {showContextJson && (
                            <>
                                <select
                                    value={previewFixtureId ?? ''}
                                    onChange={e => setPreviewFixtureId(e.target.value || null)}
                                    style={{ marginBottom: 'var(--space-md)' }}
                                >
                                    <option value="">Select a fixture to preview...</option>
                                    {allFixtures?.map(f => (
                                        <option key={f.fixture_id} value={f.fixture_id}>
                                            R{f.round}: {f.home_team} vs {f.away_team}
                                        </option>
                                    ))}
                                </select>

                                {contextLoading && (
                                    <div className="loading"><div className="spinner" /></div>
                                )}

                                {contextError && (
                                    <div style={{
                                        padding: 'var(--space-md)',
                                        background: 'var(--danger-soft)',
                                        borderRadius: 'var(--radius-md)',
                                        color: 'var(--danger)'
                                    }}>
                                        Error loading context: {contextError instanceof Error ? contextError.message : 'Unknown error'}
                                    </div>
                                )}

                                {previewContext && !contextLoading && (
                                    <div className="json-viewer" style={{ maxHeight: '500px', overflow: 'auto' }}>
                                        <pre>{JSON.stringify(previewContext, null, 2)}</pre>
                                    </div>
                                )}

                                {!previewFixtureId && !previewContext && !contextLoading && (
                                    <div className="empty-state" style={{ padding: 'var(--space-lg)' }}>
                                        <p>Select a fixture above to see the context JSON</p>
                                    </div>
                                )}
                            </>
                        )}

                        {!showContextJson && (
                            <div className="empty-state" style={{ padding: 'var(--space-lg)' }}>
                                <p>Toggle on to preview context JSON</p>
                            </div>
                        )}
                    </div>
                </div>
            </div>

            {/* Results */}
            {results.length > 0 && (
                <div className="card" style={{ marginTop: 'var(--space-xl)' }}>
                    <div className="card-header">
                        <h3 className="card-title">Results</h3>
                        <div style={{ display: 'flex', gap: 'var(--space-md)' }}>
                            <span className="badge badge-success">✓ {correctCount} Correct</span>
                            <span className="badge badge-danger">✗ {failCount} Failed</span>
                            <span className="badge badge-neutral">{successCount}/{results.length} Complete</span>
                        </div>
                    </div>

                    {/* Accuracy */}
                    {successCount > 0 && (
                        <div style={{
                            padding: 'var(--space-lg)',
                            background: 'var(--bg-surface)',
                            borderRadius: 'var(--radius-md)',
                            marginBottom: 'var(--space-lg)',
                            textAlign: 'center'
                        }}>
                            <div style={{ fontSize: '2rem', fontWeight: 700 }}>
                                {successCount > 0 ? ((correctCount / successCount) * 100).toFixed(1) : 0}%
                            </div>
                            <div style={{ color: 'var(--text-muted)', fontSize: '0.875rem' }}>
                                Accuracy ({correctCount}/{successCount}) across {selectedRounds.length} rounds
                            </div>
                        </div>
                    )}

                    <div className="table-container">
                        <table>
                            <thead>
                                <tr>
                                    <th>Round</th>
                                    <th>Match</th>
                                    <th>Predicted</th>
                                    <th>Confidence</th>
                                    <th>Result</th>
                                </tr>
                            </thead>
                            <tbody>
                                {results.map(r => (
                                    <tr
                                        key={r.fixture_id}
                                        className={r.is_correct === false ? 'failure-row' : ''}
                                    >
                                        <td>R{r.round}</td>
                                        <td>{r.home_team} vs {r.away_team}</td>
                                        <td>{r.predicted_score || '-'}</td>
                                        <td>{r.confidence !== undefined ? `${r.confidence}%` : '-'}</td>
                                        <td>
                                            {r.status === 'error' ? (
                                                <span className="badge badge-danger">Error</span>
                                            ) : r.is_correct === true ? (
                                                <span className="badge badge-success">✓ Correct</span>
                                            ) : r.is_correct === false ? (
                                                <span className="badge badge-danger">✗ Wrong</span>
                                            ) : (
                                                <span className="badge badge-neutral">Pending</span>
                                            )}
                                        </td>
                                    </tr>
                                ))}
                            </tbody>
                        </table>
                    </div>
                </div>
            )}
        </div>
    )
}
