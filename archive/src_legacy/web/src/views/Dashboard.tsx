import { useQuery } from '@tanstack/react-query'
import { getRounds, getFailures } from '../lib/api'

export default function Dashboard() {
    const { data: rounds, isLoading: roundsLoading } = useQuery({
        queryKey: ['rounds'],
        queryFn: () => getRounds(),
    })

    const { data: failures, isLoading: failuresLoading } = useQuery({
        queryKey: ['failures'],
        queryFn: () => getFailures(),
    })

    const totalFixtures = rounds?.reduce((sum, r) => sum + r.fixtures_total, 0) ?? 0
    const totalAnalyses = rounds?.reduce((sum, r) => sum + r.analyses_total, 0) ?? 0
    const totalFailures = failures?.length ?? 0

    const avgAccuracy = rounds?.filter(r => r.accuracy !== null)
        .reduce((sum, r, _, arr) => sum + (r.accuracy! / arr.length), 0) ?? 0

    if (roundsLoading) {
        return <div className="loading"><div className="spinner" /></div>
    }

    return (
        <div>
            <header className="page-header">
                <h1 className="page-title">Match Intelligence</h1>
                <p className="page-subtitle">Backtesting platform for model development</p>
            </header>

            {/* Key Metrics */}
            <div className="grid grid-4" style={{ marginBottom: 'var(--space-xl)' }}>
                <div className="card">
                    <div className="metric">
                        <span className="metric-value">{totalFixtures}</span>
                        <span className="metric-label">Total Fixtures</span>
                    </div>
                </div>
                <div className="card">
                    <div className="metric">
                        <span className="metric-value">{totalAnalyses}</span>
                        <span className="metric-label">Analyses Run</span>
                    </div>
                </div>
                <div className="card">
                    <div className="metric">
                        <span className="metric-value">{avgAccuracy.toFixed(1)}%</span>
                        <span className="metric-label">Avg Accuracy</span>
                    </div>
                </div>
                <div className="card">
                    <div className="metric">
                        <span className="metric-value" style={{ color: 'var(--danger)' }}>{totalFailures}</span>
                        <span className="metric-label">Failed Predictions</span>
                    </div>
                </div>
            </div>

            {/* Rounds Table */}
            <div className="card">
                <div className="card-header">
                    <h3 className="card-title">Rounds Overview</h3>
                </div>
                <div className="table-container">
                    <table>
                        <thead>
                            <tr>
                                <th>Round</th>
                                <th>Fixtures</th>
                                <th>Analyses</th>
                                <th>Evaluations</th>
                                <th>Accuracy</th>
                                <th>Status</th>
                            </tr>
                        </thead>
                        <tbody>
                            {rounds?.map(round => {
                                const coverage = round.analyses_total / Math.max(round.fixtures_total, 1)
                                const status = coverage >= 1 ? 'complete' : coverage > 0 ? 'partial' : 'pending'

                                return (
                                    <tr key={round.round}>
                                        <td><strong>Round {round.round}</strong></td>
                                        <td>{round.fixtures_total}</td>
                                        <td>{round.analyses_total}</td>
                                        <td>{round.evaluations_total}</td>
                                        <td>{round.accuracy !== null ? `${round.accuracy.toFixed(1)}%` : '-'}</td>
                                        <td>
                                            <span className={`badge badge-${status === 'complete' ? 'success' : status === 'partial' ? 'warning' : 'neutral'}`}>
                                                {status}
                                            </span>
                                        </td>
                                    </tr>
                                )
                            })}
                        </tbody>
                    </table>
                </div>
            </div>

            {/* Recent Failures */}
            {!failuresLoading && failures && failures.length > 0 && (
                <div className="card" style={{ marginTop: 'var(--space-lg)' }}>
                    <div className="card-header">
                        <h3 className="card-title">🚨 Recent Failures</h3>
                        <a href="/failures" className="btn btn-secondary">View All</a>
                    </div>
                    <div className="table-container">
                        <table>
                            <thead>
                                <tr>
                                    <th>Match</th>
                                    <th>Predicted</th>
                                    <th>Actual</th>
                                    <th>Confidence</th>
                                    <th>Prompt</th>
                                </tr>
                            </thead>
                            <tbody>
                                {failures.slice(0, 5).map(f => (
                                    <tr key={f.fixture_id} className="failure-row">
                                        <td>{f.home_team} vs {f.away_team}</td>
                                        <td>{f.predicted_score}</td>
                                        <td>{f.actual_score}</td>
                                        <td>{f.confidence}%</td>
                                        <td><span className="badge badge-neutral">{f.prompt_version}</span></td>
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
