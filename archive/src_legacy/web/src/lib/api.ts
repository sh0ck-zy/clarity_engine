/**
 * API Client for Match Intelligence Backend
 */

const API_BASE = '/api';

export interface Fixture {
    fixture_id: string;
    home_team: string;
    away_team: string;
    date: string;
    round: number | null;
    home_score: number | null;
    away_score: number | null;
    status: string | null;
}

export interface RoundSummary {
    round: number;
    fixtures_total: number;
    analyses_total: number;
    evaluations_total: number;
    accuracy: number | null;
}

export interface ContextCoverage {
    fixture_id: string;
    overall_score: number;
    sources: Array<{ name: string; status: string; details: string }>;
}

export interface Analysis {
    id: number;
    prompt_version: string;
    predicted_score: string | null;
    confidence: number | null;
    betting_recommendation: string | null;
    is_correct: boolean | null;
    full_json: Record<string, unknown>;
    created_at: string | null;
}

export interface Failure {
    fixture_id: string;
    home_team: string;
    away_team: string;
    predicted_score: string;
    actual_score: string;
    confidence: number;
    prompt_version: string;
    reasoning: string | null;
    context_used: Record<string, unknown> | null;
    reality_narrative: string | null;
}

export interface Prompt {
    key: string;
    name: string;
}

async function fetchJSON<T>(url: string, options?: RequestInit): Promise<T> {
    const response = await fetch(`${API_BASE}${url}`, {
        ...options,
        headers: {
            'Content-Type': 'application/json',
            ...options?.headers,
        },
    });

    if (!response.ok) {
        const error = await response.json().catch(() => ({ detail: 'Unknown error' }));
        throw new Error(error.detail || `HTTP ${response.status}`);
    }

    return response.json();
}

// Fixtures
export const getFixtures = (season = '2025-2026', round?: number) =>
    fetchJSON<Fixture[]>(`/fixtures?season=${season}${round ? `&round=${round}` : ''}`);

export const getRounds = (season = '2025-2026') =>
    fetchJSON<RoundSummary[]>(`/rounds?season=${season}`);

// Context
export const getContext = (fixtureId: string) =>
    fetchJSON<Record<string, unknown>>(`/context/${fixtureId}`);

export const getContextCoverage = (fixtureId: string) =>
    fetchJSON<ContextCoverage>(`/context/${fixtureId}/coverage`);

export const checkTimeTravel = (fixtureId: string) =>
    fetchJSON<{ is_safe: boolean; warnings: Array<{ severity: string; message: string }> }>(`/context/${fixtureId}/time-travel`);

// Analyses
export const runAnalysis = (fixtureId: string, promptVersion: string, forceRefresh = false) =>
    fetchJSON<Analysis>('/analyze', {
        method: 'POST',
        body: JSON.stringify({
            fixture_id: fixtureId,
            prompt_version: promptVersion,
            force_refresh: forceRefresh,
        }),
    });

export const getAnalyses = (fixtureId: string) =>
    fetchJSON<{ analyses: Analysis[] }>(`/analyses/${fixtureId}`);

// Evaluations
export const runEvaluation = (reportId: number, forceRefresh = false) =>
    fetchJSON<Record<string, unknown>>(`/evaluate/${reportId}?force_refresh=${forceRefresh}`, { method: 'POST' });

export const getEvaluations = (fixtureId: string) =>
    fetchJSON<{ evaluations: Array<Record<string, unknown>> }>(`/evaluations/${fixtureId}`);

// Failures
export const getFailures = (season = '2025-2026', promptVersion?: string) =>
    fetchJSON<Failure[]>(`/failures?season=${season}${promptVersion ? `&prompt_version=${promptVersion}` : ''}`);

// Prompts
export const getPrompts = () =>
    fetchJSON<{ prompts: Prompt[] }>('/prompts');

// Health
export const healthCheck = () =>
    fetchJSON<{ status: string; database: string }>('/health');
