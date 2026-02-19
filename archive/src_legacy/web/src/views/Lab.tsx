import { useState } from 'react'
import { useQuery } from '@tanstack/react-query'
import { getPrompts, getFixtures, getContext, checkTimeTravel, runAnalysis } from '../lib/api'

interface SchemaConfig {
    include_identity: boolean
    include_form: boolean
    include_absences: boolean
    include_head_to_head: boolean
    include_schedule: boolean
    include_league_position: boolean
    include_odds: boolean
}

const DEFAULT_SCHEMA: SchemaConfig = {
    include_identity: true,
    include_form: true,
    include_absences: true,
    include_head_to_head: true,
    include_schedule: true,
    include_league_position: true,
    include_odds: true,
}

export default function Lab() {
    const [schema, setSchema] = useState<SchemaConfig>(DEFAULT_SCHEMA)
    const [selectedPrompt, setSelectedPrompt] = useState<string>('')
    const [selectedFixture, setSelectedFixture] = useState<string>('')
    const [analysisResult, setAnalysisResult] = useState<Record<string, unknown> | null>(null)
    const [isRunning, setIsRunning] = useState(false)

    const { data: prompts } = useQuery({
        queryKey: ['prompts'],
        queryFn: getPrompts,
    })

    const { data: fixtures } = useQuery({
        queryKey: ['fixtures'],
        queryFn: () => getFixtures('2025-2026', undefined),
    })

    const { data: context, refetch: refetchContext } = useQuery({
        queryKey: ['context', selectedFixture],
        queryFn: () => getContext(selectedFixture),
        enabled: !!selectedFixture,
    })

    const { data: timeTravelCheck } = useQuery({
        queryKey: ['timeTravel', selectedFixture],
        queryFn: () => checkTimeTravel(selectedFixture),
        enabled: !!selectedFixture,
    })

    const toggleField = (field: keyof SchemaConfig) => {
        setSchema(prev => ({ ...prev, [field]: !prev[field] }))
    }

    const handleRunAnalysis = async () => {
        if (!selectedFixture || !selectedPrompt) return

        setIsRunning(true)
        try {
            const result = await runAnalysis(selectedFixture, selectedPrompt, false)
            setAnalysisResult(result as Record<string, unknown>)
        } catch (error) {
            console.error('Analysis failed:', error)
        } finally {
            setIsRunning(false)
        }
    }

    const schemaFields: Array<{ key: keyof SchemaConfig; label: string; description: string }> = [
        { key: 'include_identity', label: 'Team Identity', description: 'Elo, xG, PPDA, Field Tilt' },
        { key: 'include_form', label: 'Team Form', description: 'Last 5 results, xG trend' },
        { key: 'include_absences', label: 'Absences', description: 'Injuries, suspensions' },
        { key: 'include_head_to_head', label: 'Head to Head', description: 'Historical H2H record' },
        { key: 'include_schedule', label: 'Schedule', description: 'Rest days, congestion' },
        { key: 'include_league_position', label: 'League Position', description: 'Current standing' },
        { key: 'include_odds', label: 'Market Odds', description: 'Pre-match 1X2 odds' },
    ]

    return (
        <div>
            <header className="page-header">
                <h1 className="page-title">🧪 Lab</h1>
                <p className="page-subtitle">Configure context schema and run quick tests</p>
            </header>

            <div className="grid grid-2" style={{ gap: 'var(--space-lg)' }}>
                {/* Left: Configuration */}
                <div>
                    {/* Schema Builder */}
                    <div className="card" style={{ marginBottom: 'var(--space-lg)' }}>
                        <div className="card-header">
                            <h3 className="card-title">Context Schema</h3>
                        </div>
                        <div style={{ display: 'flex', flexDirection: 'column', gap: 'var(--space-md)' }}>
                            {schemaFields.map(field => (
                                <div key={field.key} style={{
                                    display: 'flex',
                                    justifyContent: 'space-between',
                                    alignItems: 'center',
                                    padding: 'var(--space-sm) 0',
                                    borderBottom: '1px solid var(--border-subtle)'
                                }}>
                                    <div>
                                        <div style={{ fontWeight: 500 }}>{field.label}</div>
                                        <div style={{ fontSize: '0.75rem', color: 'var(--text-muted)' }}>{field.description}</div>
                                    </div>
                                    <label className="toggle">
                                        <input
                                            type="checkbox"
                                            checked={schema[field.key]}
                                            onChange={() => toggleField(field.key)}
                                        />
                                        <span className="toggle-slider" />
                                    </label>
                                </div>
                            ))}
                        </div>
                    </div>

                    {/* Prompt Selector */}
                    <div className="card" style={{ marginBottom: 'var(--space-lg)' }}>
                        <div className="card-header">
                            <h3 className="card-title">Prompt Version</h3>
                        </div>
                        <select
                            value={selectedPrompt}
                            onChange={e => setSelectedPrompt(e.target.value)}
                        >
                            <option value="">Select a prompt...</option>
                            {prompts?.prompts.map(p => (
                                <option key={p.key} value={p.key}>{p.key} - {p.name}</option>
                            ))}
                        </select>
                    </div>

                    {/* Fixture Selector */}
                    <div className="card">
                        <div className="card-header">
                            <h3 className="card-title">Test Fixture</h3>
                        </div>
                        <select
                            value={selectedFixture}
                            onChange={e => setSelectedFixture(e.target.value)}
                        >
                            <option value="">Select a fixture...</option>
                            {fixtures?.map(f => (
                                <option key={f.fixture_id} value={f.fixture_id}>
                                    {f.home_team} vs {f.away_team} (R{f.round})
                                </option>
                            ))}
                        </select>

                        {/* Time Travel Check */}
                        {timeTravelCheck && (
                            <div style={{ marginTop: 'var(--space-md)' }}>
                                {timeTravelCheck.is_safe ? (
                                    <span className="badge badge-success">✓ Time-Travel Safe</span>
                                ) : (
                                    <span className="badge badge-danger">⚠ Data Leak Warning</span>
                                )}
                            </div>
                        )}

                        {/* Run Button */}
                        <button
                            className="btn btn-primary"
                            style={{ width: '100%', marginTop: 'var(--space-lg)' }}
                            disabled={!selectedFixture || !selectedPrompt || isRunning}
                            onClick={handleRunAnalysis}
                        >
                            {isRunning ? 'Running...' : '▶ Run Analysis'}
                        </button>
                    </div>
                </div>

                {/* Right: Results */}
                <div>
                    {/* Context Preview */}
                    {context && (
                        <div className="card" style={{ marginBottom: 'var(--space-lg)' }}>
                            <div className="card-header">
                                <h3 className="card-title">Context Preview</h3>
                            </div>
                            <div className="json-viewer" style={{ maxHeight: '300px', overflow: 'auto' }}>
                                <pre>{JSON.stringify(context, null, 2)}</pre>
                            </div>
                        </div>
                    )}

                    {/* Analysis Result */}
                    {analysisResult && (
                        <div className="card">
                            <div className="card-header">
                                <h3 className="card-title">Analysis Result</h3>
                            </div>

                            <div className="grid grid-3" style={{ marginBottom: 'var(--space-lg)' }}>
                                <div className="metric">
                                    <span className="metric-value">{(analysisResult as any).predicted_score || '-'}</span>
                                    <span className="metric-label">Predicted Score</span>
                                </div>
                                <div className="metric">
                                    <span className="metric-value">{(analysisResult as any).confidence || '-'}%</span>
                                    <span className="metric-label">Confidence</span>
                                </div>
                                <div className="metric">
                                    <span className="metric-value">{(analysisResult as any).is_correct ? '✓' : '✗'}</span>
                                    <span className="metric-label">Correct</span>
                                </div>
                            </div>

                            {(analysisResult as any).betting_recommendation && (
                                <div style={{
                                    padding: 'var(--space-md)',
                                    background: 'var(--accent-soft)',
                                    borderRadius: 'var(--radius-md)',
                                    marginBottom: 'var(--space-md)'
                                }}>
                                    <strong>Tip:</strong> {(analysisResult as any).betting_recommendation}
                                </div>
                            )}

                            <div className="json-viewer" style={{ maxHeight: '400px', overflow: 'auto' }}>
                                <pre>{JSON.stringify((analysisResult as any).full_json, null, 2)}</pre>
                            </div>
                        </div>
                    )}

                    {!context && !analysisResult && (
                        <div className="empty-state">
                            <div className="empty-state-icon">🧪</div>
                            <p>Select a fixture to preview context and run analysis</p>
                        </div>
                    )}
                </div>
            </div>
        </div>
    )
}
