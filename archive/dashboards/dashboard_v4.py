"""
Dashboard v4 - Clarity Engine (Workflow & Transparency Overhaul)

Iterative workflow dashboard with 6 tabs:
1. RONDA - Round overview with data/analysis status
2. GERADOR - Batch generate analyses with prompt selection
3. DADOS - Data validation and time-travel safety
4. ANALISES - View analyses with full transparency (context + prompt)
5. AVALIADOR - Run and view evaluations with criteria transparency
6. COMPARADOR - Compare prompt versions with metrics

Usage:
    streamlit run src/dashboard_v4.py --server.port 8504
"""

import json
import sys
import time
from dataclasses import asdict
from datetime import date, datetime
from pathlib import Path
from typing import Optional, Dict, Any, List

import streamlit as st
import pandas as pd

PROJECT_ROOT = Path(__file__).resolve().parents[1]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.append(str(PROJECT_ROOT))

from src.database.config import get_connection
from src.analysis.data_validator import DataValidator, get_fixture_data_status
from src.analysis.prompt_comparator import PromptComparator
from src.analysis.performance_tracker import PerformanceTracker
from src.analysis.prompts import PROMPTS, load_prompt, PROMPTS_DIR
from src.jobs.batch_runner import BatchRunner

# Page config
st.set_page_config(
    page_title="Clarity Engine v4",
    page_icon="⚽",
    layout="wide",
    initial_sidebar_state="collapsed"
)

# Custom CSS
st.markdown("""
<style>
    :root {
        --ce-bg: #0b111a;
        --ce-panel: #111827;
        --ce-surface: #1f2937;
        --ce-border: #273244;
        --ce-text: #e2e8f0;
        --ce-muted: #94a3b8;
        --ce-accent: #14b8a6;
        --ce-accent-soft: rgba(20, 184, 166, 0.18);
        --ce-success: #22c55e;
        --ce-warning: #f59e0b;
        --ce-danger: #f87171;
        --ce-radius: 14px;
    }
    body, .stApp {
        background: var(--ce-bg);
        color: var(--ce-text);
    }
    .stApp {
        font-family: "Manrope", "Inter", system-ui, sans-serif;
    }
    h1, h2, h3, h4, h5 {
        letter-spacing: -0.01em;
        color: var(--ce-text);
    }
    p, li, span, label {
        color: var(--ce-text);
    }
    .stMarkdown p {
        font-size: 15px;
        line-height: 1.65;
        color: var(--ce-muted);
    }
    .stTabs [data-baseweb="tab-list"] {
        gap: 24px;
    }
    .stTabs [data-baseweb="tab"] {
        height: 50px;
        padding-left: 20px;
        padding-right: 20px;
        font-size: 16px;
        font-weight: 500;
        color: var(--ce-muted);
        border-radius: 999px;
        background: transparent;
        border: 1px solid transparent;
    }
    .stTabs [aria-selected="true"] {
        color: var(--ce-text);
        background: var(--ce-accent-soft);
        border-color: rgba(20, 184, 166, 0.35);
    }
    .block-container {
        padding-top: 2.25rem;
        padding-bottom: 3rem;
    }
    .stContainer, .stExpander, .stDataFrame, .stTable, .stAlert {
        background: var(--ce-panel);
        border-radius: var(--ce-radius);
        border: 1px solid var(--ce-border);
        padding: 1rem 1.25rem;
        box-shadow: 0 18px 30px rgba(5, 10, 18, 0.35);
    }
    .stExpander {
        padding: 0.5rem 1rem;
    }
    .stAlert {
        margin-top: 1rem;
    }
    .metric-card {
        background-color: var(--ce-surface);
        border-radius: var(--ce-radius);
        padding: 16px;
        margin: 8px 0;
        border: 1px solid var(--ce-border);
    }
    .status-complete { color: var(--ce-success); }
    .status-partial { color: var(--ce-warning); }
    .status-missing { color: var(--ce-danger); }
    .factor-bar {
        height: 12px;
        background-color: #1a2433;
        border-radius: 4px;
        overflow: hidden;
    }
    .factor-fill {
        height: 100%;
        background-color: var(--ce-accent);
        border-radius: 4px;
    }
    .stButton > button {
        border-radius: 12px;
        border: 1px solid rgba(20, 184, 166, 0.35);
        background: var(--ce-accent);
        color: #0f172a;
        padding: 0.55rem 1.1rem;
        font-weight: 600;
        letter-spacing: 0.01em;
        box-shadow: 0 12px 18px rgba(8, 17, 26, 0.4);
    }
    .stButton > button:hover {
        background: #2dd4bf;
        border-color: #2dd4bf;
        transform: translateY(-1px);
    }
    .stSelectbox div[data-baseweb="select"],
    .stTextInput input,
    .stTextArea textarea,
    .stNumberInput input {
        background: var(--ce-surface);
        color: var(--ce-text);
        border-radius: 10px;
        border: 1px solid var(--ce-border);
    }
    .stSelectbox svg,
    .stSelectbox span,
    .stTextInput label,
    .stNumberInput label {
        color: var(--ce-muted);
    }
    div[data-baseweb="popover"] {
        background: var(--ce-panel);
        border-radius: 12px;
        border: 1px solid var(--ce-border);
    }
    .stMetric {
        background: var(--ce-surface);
        border: 1px solid var(--ce-border);
        border-radius: 14px;
        padding: 0.85rem 1rem;
    }
    .stMetric [data-testid="stMetricLabel"] {
        color: var(--ce-muted);
        font-size: 0.85rem;
        text-transform: uppercase;
        letter-spacing: 0.08em;
    }
    .stMetric [data-testid="stMetricValue"] {
        color: var(--ce-text);
        font-weight: 600;
    }
    .stDataFrame table {
        font-size: 14px;
        line-height: 1.4;
    }
    .stDataFrame td {
        white-space: normal;
    }
    .stDataFrame thead th {
        background: #111827;
        color: var(--ce-muted);
        text-transform: uppercase;
        font-size: 12px;
        letter-spacing: 0.08em;
    }
    .stDataFrame tbody tr:nth-child(even) {
        background: rgba(148, 163, 184, 0.08);
    }
    hr {
        border-color: rgba(148, 163, 184, 0.2);
        margin: 1.5rem 0;
    }
    .ce-pill {
        display: inline-block;
        padding: 0.2rem 0.6rem;
        border-radius: 999px;
        font-size: 0.75rem;
        font-weight: 600;
        letter-spacing: 0.04em;
        text-transform: uppercase;
        background: rgba(20, 184, 166, 0.15);
        color: var(--ce-accent);
        border: 1px solid rgba(20, 184, 166, 0.35);
    }
    .ce-pill--muted {
        background: rgba(148, 163, 184, 0.15);
        border-color: rgba(148, 163, 184, 0.35);
        color: var(--ce-muted);
    }
    .ce-stepper button {
        background: transparent;
        border: 1px solid var(--ce-border);
        color: var(--ce-muted);
    }
</style>
""", unsafe_allow_html=True)


# ============================================================
# DATA LOADING FUNCTIONS
# ============================================================

@st.cache_data(ttl=60)
def get_fixtures_by_round(
    round_num: int,
    season: str = "2025-2026",
    league: Optional[str] = None
) -> pd.DataFrame:
    """Load fixtures for a specific round."""
    conn = get_connection()
    if not conn:
        return pd.DataFrame()

    league_filter = ""
    params = [season, round_num]
    if league:
        league_filter = "AND f.league = %s"
        params.append(league)

    query = """
        SELECT
            f.id as fixture_id,
            f.home_team,
            f.away_team,
            f.date,
            f.home_score,
            f.away_score,
            f.status
        FROM fixtures f
        WHERE f.season = %s AND f.round = %s
    """
    query += f" {league_filter} ORDER BY f.date, f.home_team"

    df = pd.read_sql(query, conn, params=params)
    conn.close()
    return df


@st.cache_data(ttl=60)
def get_analysis_status(fixture_ids: list) -> dict:
    """Get analysis status for fixtures."""
    conn = get_connection()
    if not conn or not fixture_ids:
        return {}

    cur = conn.cursor()
    placeholders = ",".join(["%s"] * len(fixture_ids))
    cur.execute(f"""
        SELECT
            fixture_id,
            prompt_version,
            is_correct,
            confidence
        FROM analysis_reports
        WHERE fixture_id IN ({placeholders})
    """, fixture_ids)

    status = {}
    for row in cur.fetchall():
        fid = row[0]
        if fid not in status:
            status[fid] = []
        status[fid].append({
            "prompt": row[1],
            "is_correct": row[2],
            "confidence": row[3]
        })

    conn.close()
    return status


@st.cache_data(ttl=60)
def get_max_round(season: str = "2025-2026", league: Optional[str] = None) -> int:
    """Get the maximum round number with data."""
    conn = get_connection()
    if not conn:
        return 1

    cur = conn.cursor()
    if league:
        cur.execute("""
            SELECT MAX(round) FROM fixtures
            WHERE season = %s AND league = %s AND round IS NOT NULL
        """, (season, league))
    else:
        cur.execute("""
            SELECT MAX(round) FROM fixtures
            WHERE season = %s AND round IS NOT NULL
        """, (season,))
    result = cur.fetchone()[0]
    conn.close()
    return result or 1


@st.cache_data(ttl=60)
def get_current_round(season: str = "2025-2026", league: Optional[str] = None) -> int:
    """Get the current round (most recent with played matches)."""
    conn = get_connection()
    if not conn:
        return 1

    cur = conn.cursor()
    if league:
        cur.execute("""
            SELECT MAX(round) FROM fixtures
            WHERE season = %s AND league = %s AND home_score IS NOT NULL
        """, (season, league))
    else:
        cur.execute("""
            SELECT MAX(round) FROM fixtures
            WHERE season = %s AND home_score IS NOT NULL
        """, (season,))
    result = cur.fetchone()[0]
    conn.close()
    return result or 1


@st.cache_data(ttl=60)
def get_all_fixtures(season: str = "2025-2026") -> list:
    """Get all fixtures for the season."""
    conn = get_connection()
    if not conn:
        return []

    cur = conn.cursor()
    cur.execute("""
        SELECT id, home_team, away_team, date, round
        FROM fixtures
        WHERE season = %s
        ORDER BY date DESC, home_team
    """, (season,))

    fixtures = []
    for row in cur.fetchall():
        fixtures.append({
            "id": row[0],
            "label": f"{row[1]} vs {row[2]} (R{row[4]})",
            "home_team": row[1],
            "away_team": row[2],
            "date": row[3],
            "round": row[4]
        })

    conn.close()
    return fixtures


@st.cache_data(ttl=60)
def get_league_overview() -> pd.DataFrame:
    """Get league-level summary stats."""
    conn = get_connection()
    if not conn:
        return pd.DataFrame()

    query = """
        SELECT
            f.league,
            f.season,
            COUNT(*) AS fixtures_total,
            COUNT(DISTINCT ar.id) AS analyses_total,
            COUNT(DISTINCT ae.id) AS evaluations_total
        FROM fixtures f
        LEFT JOIN analysis_reports ar ON ar.fixture_id = f.id
        LEFT JOIN analysis_evaluations ae ON ae.fixture_id = f.id
        GROUP BY f.league, f.season
        ORDER BY f.season DESC, f.league
    """
    df = pd.read_sql(query, conn)
    conn.close()
    return df


@st.cache_data(ttl=60)
def get_round_stats(league: str, season: str) -> pd.DataFrame:
    """Get round-level stats for a league + season."""
    conn = get_connection()
    if not conn:
        return pd.DataFrame()

    query = """
        SELECT
            f.round,
            COUNT(*) AS fixtures_total,
            COUNT(DISTINCT ar.id) AS analyses_total,
            COUNT(DISTINCT ae.id) AS evaluations_total,
            MAX(COALESCE(ae.created_at, ar.created_at, f.date)) AS last_update
        FROM fixtures f
        LEFT JOIN analysis_reports ar ON ar.fixture_id = f.id
        LEFT JOIN analysis_evaluations ae ON ae.fixture_id = f.id
        WHERE f.season = %s AND f.league = %s AND f.round IS NOT NULL
        GROUP BY f.round
        ORDER BY f.round DESC
    """
    df = pd.read_sql(query, conn, params=(season, league))
    conn.close()
    return df


@st.cache_data(ttl=60)
def get_round_top_prompt(league: str, season: str) -> dict:
    """Get the most used prompt per round."""
    conn = get_connection()
    if not conn:
        return {}

    query = """
        SELECT
            f.round,
            ar.prompt_version,
            COUNT(*) AS prompt_count
        FROM fixtures f
        JOIN analysis_reports ar ON ar.fixture_id = f.id
        WHERE f.season = %s AND f.league = %s AND f.round IS NOT NULL
        GROUP BY f.round, ar.prompt_version
    """
    df = pd.read_sql(query, conn, params=(season, league))
    conn.close()

    if df.empty:
        return {}

    top_prompt = {}
    for _, row in df.iterrows():
        round_num = int(row["round"])
        prompt = row["prompt_version"]
        count = row["prompt_count"]
        if round_num not in top_prompt or count > top_prompt[round_num]["count"]:
            top_prompt[round_num] = {"prompt": prompt, "count": count}

    return {r: data["prompt"] for r, data in top_prompt.items()}


@st.cache_data(ttl=60)
def get_round_metrics_table(league: str, season: str, round_num: int) -> pd.DataFrame:
    """Key metrics table for a specific round."""
    conn = get_connection()
    if not conn:
        return pd.DataFrame()

    query = """
        SELECT
            ar.prompt_version,
            COUNT(ar.id) AS analyses,
            AVG(CASE WHEN ar.is_correct THEN 1 ELSE 0 END) * 100 AS accuracy,
            AVG(CASE WHEN ae.score_accuracy THEN 1 ELSE 0 END) * 100 AS score_accuracy,
            AVG(CASE WHEN ae.tip_accuracy THEN 1 ELSE 0 END) * 100 AS tip_accuracy,
            AVG(ae.narrative_score) AS narrative_avg
        FROM analysis_reports ar
        JOIN fixtures f ON ar.fixture_id = f.id
        LEFT JOIN analysis_evaluations ae ON ae.report_id = ar.id
        WHERE f.season = %s AND f.league = %s AND f.round = %s
        GROUP BY ar.prompt_version
        ORDER BY analyses DESC
    """
    df = pd.read_sql(query, conn, params=(season, league, round_num))
    conn.close()
    return df


@st.cache_data(ttl=60)
def get_fixtures_without_analysis(
    round_num: int,
    prompt_version: str,
    season: str = "2025-2026",
    league: Optional[str] = None
) -> list:
    """Get fixtures in a round that don't have analysis for a specific prompt."""
    conn = get_connection()
    if not conn:
        return []

    league_filter = ""
    params = [prompt_version, season, round_num]
    if league:
        league_filter = "AND f.league = %s"
        params.append(league)

    query = """
        SELECT f.id, f.home_team, f.away_team
        FROM fixtures f
        LEFT JOIN analysis_reports ar ON f.id = ar.fixture_id AND ar.prompt_version = %s
        WHERE f.season = %s AND f.round = %s AND ar.id IS NULL
    """
    query += f" {league_filter} ORDER BY f.date"

    cur = conn.cursor()
    cur.execute(query, params)

    fixtures = []
    for row in cur.fetchall():
        fixtures.append({
            "id": row[0],
            "home_team": row[1],
            "away_team": row[2]
        })

    conn.close()
    return fixtures


@st.cache_data(ttl=60)
def get_unevaluated_analyses(season: str = "2025-2026", limit: int = 50) -> list:
    """Get analyses that have match reality but no evaluation."""
    conn = get_connection()
    if not conn:
        return []

    cur = conn.cursor()
    cur.execute("""
        SELECT ar.id, ar.fixture_id, ar.prompt_version, f.home_team, f.away_team, f.round, f.date
        FROM analysis_reports ar
        JOIN fixtures f ON ar.fixture_id = f.id
        JOIN match_reality mr ON f.id = mr.fixture_id
        LEFT JOIN analysis_evaluations ae ON ar.id = ae.report_id
        WHERE f.season = %s AND ae.report_id IS NULL
        ORDER BY f.date DESC
        LIMIT %s
    """, (season, limit))

    analyses = []
    for row in cur.fetchall():
        analyses.append({
            "report_id": row[0],
            "fixture_id": row[1],
            "prompt_version": row[2],
            "home_team": row[3],
            "away_team": row[4],
            "round": row[5],
            "date": row[6]
        })

    conn.close()
    return analyses


@st.cache_data(ttl=60)
def get_analysis_with_context(fixture_id: str) -> dict:
    """Get analysis report with full_json and context data."""
    conn = get_connection()
    if not conn:
        return {}

    cur = conn.cursor()
    cur.execute("""
        SELECT
            ar.id, ar.prompt_version, ar.predicted_score, ar.confidence,
            ar.betting_recommendation, ar.full_json, ar.created_at,
            f.home_team, f.away_team, f.date, f.home_score, f.away_score
        FROM analysis_reports ar
        JOIN fixtures f ON ar.fixture_id = f.id
        WHERE ar.fixture_id = %s
        ORDER BY ar.created_at DESC
    """, (fixture_id,))

    analyses = []
    for row in cur.fetchall():
        full_json = row[5]
        if isinstance(full_json, str):
            try:
                full_json = json.loads(full_json)
            except:
                full_json = {}
        analyses.append({
            "id": row[0],
            "prompt_version": row[1],
            "predicted_score": row[2],
            "confidence": row[3],
            "betting_recommendation": row[4],
            "full_json": full_json or {},
            "created_at": row[6],
            "home_team": row[7],
            "away_team": row[8],
            "date": row[9],
            "actual_home": row[10],
            "actual_away": row[11]
        })

    conn.close()
    return {"analyses": analyses}


@st.cache_data(ttl=60)
def get_evaluation_for_report(report_id: int) -> Optional[dict]:
    """Get evaluation for a specific analysis report."""
    conn = get_connection()
    if not conn:
        return None

    cur = conn.cursor()
    cur.execute("""
        SELECT
            narrative_score, narrative_feedback, narrative_critical_flags,
            score_accuracy, score_explanation,
            tip_accuracy, tip_explanation,
            evaluation_json
        FROM analysis_evaluations
        WHERE report_id = %s
    """, (report_id,))

    row = cur.fetchone()
    conn.close()

    if not row:
        return None

    critical_flags = row[2]
    if isinstance(critical_flags, str):
        try:
            critical_flags = json.loads(critical_flags)
        except:
            critical_flags = []

    return {
        "narrative_score": row[0],
        "narrative_feedback": row[1],
        "narrative_critical_flags": critical_flags or [],
        "score_accuracy": row[3],
        "score_explanation": row[4],
        "tip_accuracy": row[5],
        "tip_explanation": row[6],
        "evaluation_json": row[7] if isinstance(row[7], dict) else json.loads(row[7]) if row[7] else {}
    }


@st.cache_data(ttl=60)
def get_match_reality(fixture_id: str) -> Optional[dict]:
    """Get match reality data for a fixture."""
    conn = get_connection()
    if not conn:
        return None

    cur = conn.cursor()
    cur.execute("""
        SELECT
            score_home, score_away, narrative_summary, key_events,
            luck_factor, xg_home, xg_away, created_at
        FROM match_reality
        WHERE fixture_id = %s
        ORDER BY created_at DESC
        LIMIT 1
    """, (fixture_id,))

    row = cur.fetchone()
    conn.close()

    if not row:
        return None

    key_events = row[3]
    if isinstance(key_events, str):
        try:
            key_events = json.loads(key_events)
        except:
            key_events = []
    elif key_events is None:
        key_events = []

    return {
        "score_home": row[0],
        "score_away": row[1],
        "narrative_summary": row[2],
        "key_events": key_events,
        "luck_factor": row[4],
        "xg_home": row[5],
        "xg_away": row[6],
        "created_at": row[7]
    }


@st.cache_data(ttl=60)
def get_evaluation_summary(season: str = "2025-2026") -> pd.DataFrame:
    """Get evaluation summary by prompt version."""
    conn = get_connection()
    if not conn:
        return pd.DataFrame()

    query = """
        SELECT
            ar.prompt_version,
            COUNT(*) as evaluations,
            AVG(ae.narrative_score) as avg_narrative_score,
            COUNT(CASE WHEN ae.score_accuracy = TRUE THEN 1 END)::float
                / NULLIF(COUNT(ae.score_accuracy), 0) * 100 as score_accuracy,
            COUNT(CASE WHEN ae.tip_accuracy = TRUE THEN 1 END)::float
                / NULLIF(COUNT(ae.tip_accuracy), 0) * 100 as tip_accuracy
        FROM analysis_evaluations ae
        JOIN analysis_reports ar ON ae.report_id = ar.id
        JOIN fixtures f ON ae.fixture_id = f.id
        WHERE f.season = %s
        GROUP BY ar.prompt_version
        ORDER BY evaluations DESC
    """

    df = pd.read_sql(query, conn, params=(season,))
    conn.close()
    return df


@st.cache_data(ttl=60)
def get_prompt_comparison_data(prompt_a: str, prompt_b: str, season: str = "2025-2026") -> dict:
    """Get head-to-head comparison data for two prompts on same fixtures."""
    conn = get_connection()
    if not conn:
        return {}

    # Get fixtures with analyses from both prompts
    query = """
        SELECT
            ar_a.fixture_id,
            f.home_team, f.away_team, f.round,
            f.home_score, f.away_score,
            ar_a.predicted_score as pred_a, ar_a.confidence as conf_a, ar_a.is_correct as correct_a,
            ar_b.predicted_score as pred_b, ar_b.confidence as conf_b, ar_b.is_correct as correct_b,
            ae_a.narrative_score as narrative_a, ae_a.score_accuracy as score_acc_a, ae_a.tip_accuracy as tip_acc_a,
            ae_b.narrative_score as narrative_b, ae_b.score_accuracy as score_acc_b, ae_b.tip_accuracy as tip_acc_b
        FROM analysis_reports ar_a
        JOIN analysis_reports ar_b ON ar_a.fixture_id = ar_b.fixture_id
        JOIN fixtures f ON ar_a.fixture_id = f.id
        LEFT JOIN analysis_evaluations ae_a ON ae_a.report_id = ar_a.id
        LEFT JOIN analysis_evaluations ae_b ON ae_b.report_id = ar_b.id
        WHERE ar_a.prompt_version = %s
          AND ar_b.prompt_version = %s
          AND f.season = %s
          AND f.home_score IS NOT NULL
        ORDER BY f.date DESC
    """
    df = pd.read_sql(query, conn, params=(prompt_a, prompt_b, season))
    conn.close()

    if df.empty:
        return {"matches": [], "stats_a": {}, "stats_b": {}}

    matches = []
    a_wins = 0
    b_wins = 0
    ties = 0
    narrative_a_scores = []
    narrative_b_scores = []
    score_a_hits = 0
    score_b_hits = 0
    score_a_total = 0
    score_b_total = 0
    tip_a_hits = 0
    tip_b_hits = 0
    tip_a_total = 0
    tip_b_total = 0

    for _, row in df.iterrows():
        actual = f"{int(row['home_score'])}-{int(row['away_score'])}"

        # Determine winner
        a_correct = row['correct_a'] if pd.notna(row['correct_a']) else None
        b_correct = row['correct_b'] if pd.notna(row['correct_b']) else None

        if a_correct and not b_correct:
            winner = prompt_a
            a_wins += 1
        elif b_correct and not a_correct:
            winner = prompt_b
            b_wins += 1
        else:
            winner = "TIE"
            ties += 1

        if pd.notna(row["narrative_a"]):
            narrative_a_scores.append(float(row["narrative_a"]))
        if pd.notna(row["narrative_b"]):
            narrative_b_scores.append(float(row["narrative_b"]))

        if pd.notna(row["score_acc_a"]):
            score_a_total += 1
            if row["score_acc_a"]:
                score_a_hits += 1
        if pd.notna(row["score_acc_b"]):
            score_b_total += 1
            if row["score_acc_b"]:
                score_b_hits += 1

        if pd.notna(row["tip_acc_a"]):
            tip_a_total += 1
            if row["tip_acc_a"]:
                tip_a_hits += 1
        if pd.notna(row["tip_acc_b"]):
            tip_b_total += 1
            if row["tip_acc_b"]:
                tip_b_hits += 1

        matches.append({
            "fixture_id": row['fixture_id'],
            "match": f"{row['home_team']} vs {row['away_team']}",
            "round": row['round'],
            "actual": actual,
            "pred_a": row['pred_a'],
            "pred_b": row['pred_b'],
            "correct_a": a_correct,
            "correct_b": b_correct,
            "winner": winner
        })

    total = len(matches)
    stats_a = {
        "correct": sum(1 for m in matches if m['correct_a']),
        "total": total,
        "accuracy": sum(1 for m in matches if m['correct_a']) / total * 100 if total > 0 else 0,
        "avg_confidence": df["conf_a"].dropna().mean() if not df.empty else None,
        "avg_narrative": sum(narrative_a_scores) / len(narrative_a_scores) if narrative_a_scores else None,
        "score_accuracy": score_a_hits / score_a_total * 100 if score_a_total > 0 else None,
        "score_samples": score_a_total,
        "tip_accuracy": tip_a_hits / tip_a_total * 100 if tip_a_total > 0 else None,
        "tip_samples": tip_a_total
    }
    stats_b = {
        "correct": sum(1 for m in matches if m['correct_b']),
        "total": total,
        "accuracy": sum(1 for m in matches if m['correct_b']) / total * 100 if total > 0 else 0,
        "avg_confidence": df["conf_b"].dropna().mean() if not df.empty else None,
        "avg_narrative": sum(narrative_b_scores) / len(narrative_b_scores) if narrative_b_scores else None,
        "score_accuracy": score_b_hits / score_b_total * 100 if score_b_total > 0 else None,
        "score_samples": score_b_total,
        "tip_accuracy": tip_b_hits / tip_b_total * 100 if tip_b_total > 0 else None,
        "tip_samples": tip_b_total
    }

    return {
        "matches": matches,
        "stats_a": stats_a,
        "stats_b": stats_b,
        "a_wins": a_wins,
        "b_wins": b_wins,
        "ties": ties
    }


def get_prompt_text(prompt_key: str) -> str:
    """Load full prompt text for display."""
    if prompt_key in PROMPTS:
        return PROMPTS[prompt_key]["text"]
    # Try loading from file
    prompt_file = PROMPTS_DIR / f"{prompt_key}.txt"
    if prompt_file.exists():
        return prompt_file.read_text(encoding="utf-8")
    return f"Prompt '{prompt_key}' not found"


def get_evaluator_criteria() -> str:
    """Load evaluator criteria text."""
    prompt_file = PROMPTS_DIR / "v4_evaluator.txt"
    if prompt_file.exists():
        return prompt_file.read_text(encoding="utf-8")
    return "Evaluator prompt not found"


# ============================================================
# TAB 1: RONDA (Round Overview)
# ============================================================

def render_tab_ronda():
    """Render the RONDA tab."""
    st.header("Ronda Overview")

    # Round selector
    max_round = get_max_round()
    current_round = get_current_round()

    col1, col2, col3 = st.columns([1, 2, 1])

    with col1:
        if st.button("< Anterior", use_container_width=True):
            if st.session_state.get("selected_round", current_round) > 1:
                st.session_state.selected_round -= 1
                st.rerun()

    with col2:
        selected_round = st.selectbox(
            "Ronda",
            options=range(1, max_round + 1),
            index=st.session_state.get("selected_round", current_round) - 1,
            format_func=lambda x: f"Ronda {x}",
            label_visibility="collapsed"
        )
        st.session_state.selected_round = selected_round

    with col3:
        if st.button("Proxima >", use_container_width=True):
            if st.session_state.get("selected_round", current_round) < max_round:
                st.session_state.selected_round += 1
                st.rerun()

    st.markdown(f"### Ronda {selected_round} - Premier League 2025-26")

    # Load fixtures
    fixtures_df = get_fixtures_by_round(selected_round)

    if fixtures_df.empty:
        st.info("Nenhum jogo encontrado para esta ronda.")
        return

    # Get analysis status
    fixture_ids = fixtures_df["fixture_id"].tolist()
    analysis_status = get_analysis_status(fixture_ids)

    # Build display table
    rows = []
    for _, fix in fixtures_df.iterrows():
        fid = fix["fixture_id"]

        # Data status (quick check)
        data_status = get_fixture_data_status(fid)
        data_icon = {"complete": "OK", "partial": "PARCIAL", "missing": "FALTA"}.get(data_status, "?")

        # Analysis status
        analyses = analysis_status.get(fid, [])
        if analyses:
            analysis_prompt = analyses[0]["prompt"]
            analysis_correct = analyses[0]["is_correct"]
        else:
            analysis_prompt = None
            analysis_correct = None

        analysis_icon = analysis_prompt if analysis_prompt else "FALTA"

        # Result
        if fix["home_score"] is not None and fix["away_score"] is not None:
            result = f"{int(fix['home_score'])}-{int(fix['away_score'])}"
        else:
            result = "-"

        # Correctness
        if analysis_correct is True:
            correct_icon = "SIM"
        elif analysis_correct is False:
            correct_icon = "NAO"
        else:
            correct_icon = "-"

        rows.append({
            "Jogo": f"{fix['home_team']} vs {fix['away_team']}",
            "Data": fix["date"].strftime("%d/%m") if fix["date"] else "-",
            "Dados": data_icon,
            "Analise": analysis_icon,
            "Resultado": result,
            "Acertou?": correct_icon,
            "_fixture_id": fid
        })

    # Display as DataFrame
    display_df = pd.DataFrame(rows)

    st.dataframe(
        display_df[["Jogo", "Data", "Dados", "Analise", "Resultado", "Acertou?"]],
        use_container_width=True,
        hide_index=True
    )

    # Legend
    st.caption("Legenda: OK = Completo | PARCIAL = Parcial | FALTA = Ausente")

    # Quick stats
    st.markdown("---")
    col1, col2, col3, col4 = st.columns(4)

    with col1:
        st.metric("Jogos", len(rows))
    with col2:
        data_complete = sum(1 for r in rows if r["Dados"] == "OK")
        st.metric("Dados Completos", f"{data_complete}/{len(rows)}")
    with col3:
        with_analysis = sum(1 for r in rows if r["Analise"] != "FALTA")
        st.metric("Com Analise", f"{with_analysis}/{len(rows)}")
    with col4:
        correct = sum(1 for r in rows if r["Acertou?"] == "SIM")
        played = sum(1 for r in rows if r["Resultado"] != "-")
        if played > 0:
            st.metric("Acertos", f"{correct}/{played}")
        else:
            st.metric("Acertos", "-")


# ============================================================
# TAB 2: GERADOR (Generator) - NEW
# ============================================================

def render_tab_gerador():
    """Render the GERADOR tab - batch generate analyses."""
    st.header("Gerador de Analises")

    st.markdown("""
    Gera analises em batch para jogos selecionados usando o prompt escolhido.
    """)

    # 1. SELECCIONAR JOGOS
    st.markdown("### 1. Seleccionar Jogos")

    col1, col2 = st.columns(2)

    with col1:
        max_round = get_max_round()
        selected_round = st.selectbox(
            "Ronda",
            options=range(1, max_round + 1),
            index=min(st.session_state.get("selected_round", get_current_round()) - 1, max_round - 1),
            format_func=lambda x: f"Ronda {x}",
            key="gerador_round"
        )

    with col2:
        force_refresh = st.checkbox("Forcar regeneracao (ignora cache)", value=False, key="gerador_force")
        only_pending = st.checkbox(
            "Apenas jogos sem analise",
            value=True,
            key="gerador_pending",
            disabled=force_refresh
        )

    # Load fixtures
    fixtures_df = get_fixtures_by_round(selected_round)

    if fixtures_df.empty:
        st.warning("Nenhum jogo encontrado para esta ronda.")
        return

    # Show fixture list
    fixture_options = {}
    for _, fix in fixtures_df.iterrows():
        label = f"{fix['home_team']} vs {fix['away_team']}"
        fixture_options[label] = fix['fixture_id']

    # 2. SELECCIONAR PROMPT
    st.markdown("### 2. Seleccionar Prompt")

    prompt_options = {k: v["name"] for k, v in PROMPTS.items()}
    selected_prompt = st.selectbox(
        "Prompt Version",
        options=list(prompt_options.keys()),
        format_func=lambda x: f"{x} - {prompt_options[x]}",
        key="gerador_prompt"
    )

    # Show prompt preview
    with st.expander("Ver Prompt Completo"):
        prompt_text = get_prompt_text(selected_prompt)
        st.code(prompt_text[:3000] + "..." if len(prompt_text) > 3000 else prompt_text, language="text")
        st.caption(f"Total: {len(prompt_text)} caracteres")

    # Round overview
    fixture_ids = fixtures_df["fixture_id"].tolist()
    analysis_status = get_analysis_status(fixture_ids)
    status_rows = []
    data_complete = 0
    prompt_complete = 0

    for _, fix in fixtures_df.iterrows():
        fid = fix["fixture_id"]
        data_status = get_fixture_data_status(fid)
        analysis_for_prompt = [
            a for a in analysis_status.get(fid, []) if a["prompt"] == selected_prompt
        ]
        analysis_state = "OK" if analysis_for_prompt else "FALTA"
        confidence = analysis_for_prompt[0]["confidence"] if analysis_for_prompt else None

        if data_status == "complete":
            data_complete += 1
        if analysis_for_prompt:
            prompt_complete += 1

        status_rows.append({
            "Jogo": f"{fix['home_team']} vs {fix['away_team']}",
            "Dados": {"complete": "OK", "partial": "PARCIAL", "missing": "FALTA"}.get(data_status, "?"),
            "Analise": analysis_state,
            "Confianca": f"{confidence}%" if confidence is not None else "-"
        })

    st.markdown("### Estado da Ronda")
    st.dataframe(pd.DataFrame(status_rows), use_container_width=True, hide_index=True)

    col1, col2, col3 = st.columns(3)
    with col1:
        st.metric("Jogos", len(status_rows))
    with col2:
        st.metric("Dados completos", f"{data_complete}/{len(status_rows)}")
    with col3:
        st.metric("Analises neste prompt", f"{prompt_complete}/{len(status_rows)}")

    if force_refresh:
        st.info("Regeneracao ativa: analises existentes podem ser sobrescritas no cache.")

    # Filter fixtures if only_pending
    if only_pending and not force_refresh:
        pending_fixtures = get_fixtures_without_analysis(selected_round, selected_prompt)
        pending_ids = [f["id"] for f in pending_fixtures]
        fixture_options = {k: v for k, v in fixture_options.items() if v in pending_ids}

    if not fixture_options:
        st.info(f"Todos os jogos da Ronda {selected_round} ja tem analise para o prompt '{selected_prompt}'.")
        return

    # Multi-select fixtures
    selected_fixtures = st.multiselect(
        "Jogos a gerar",
        options=list(fixture_options.keys()),
        default=list(fixture_options.keys()),
        key="gerador_fixtures"
    )

    st.markdown(f"**Jogos seleccionados:** {len(selected_fixtures)}")

    # 3. GERAR
    st.markdown("### 3. Gerar")

    col1, col2 = st.columns([2, 1])
    with col1:
        generate_btn = st.button(
            f"GERAR ANALISES ({len(selected_fixtures)} jogos x {selected_prompt})",
            type="primary",
            use_container_width=True,
            disabled=len(selected_fixtures) == 0
        )

    # Generation logic
    if generate_btn and selected_fixtures:
        fixture_ids = [fixture_options[f] for f in selected_fixtures]

        progress_bar = st.progress(0)
        status_text = st.empty()
        results_container = st.container()

        # Import ClarityEngine directly for individual generation
        from src.analysis.predictor import ClarityEngine

        engine = ClarityEngine()
        results = []

        try:
            for i, fixture_id in enumerate(fixture_ids):
                match_label = [k for k, v in fixture_options.items() if v == fixture_id][0]
                status_text.markdown(f"Gerando: **{match_label}**...")
                progress_bar.progress((i) / len(fixture_ids))

                try:
                    result = engine.run_analysis(fixture_id, selected_prompt, force_refresh=force_refresh)
                    if result and "error" not in result:
                        results.append({"fixture": match_label, "status": "OK", "icon": "OK"})
                    else:
                        error_msg = result.get("error", "Unknown") if result else "No result"
                        results.append({"fixture": match_label, "status": error_msg, "icon": "ERRO"})
                except Exception as e:
                    results.append({"fixture": match_label, "status": str(e), "icon": "ERRO"})

                time.sleep(0.5)  # Rate limiting

            progress_bar.progress(1.0)
            status_text.markdown("**Concluido!**")

        finally:
            engine.close()

        # Show results
        with results_container:
            st.markdown("#### Resultados")
            for r in results:
                icon = "OK" if r["icon"] == "OK" else "ERRO"
                st.markdown(f"- {icon} {r['fixture']} - {r['status']}")

        # Clear cache to refresh data
        st.cache_data.clear()


# ============================================================
# TAB 3: DADOS (Data Validation)
# ============================================================

def render_tab_dados():
    """Render the DADOS tab."""
    st.header("Validacao de Dados")

    # Fixture selector
    fixtures = get_all_fixtures()
    if not fixtures:
        st.warning("Nenhum jogo encontrado.")
        return

    fixture_options = {f["label"]: f["id"] for f in fixtures}
    selected_label = st.selectbox(
        "Seleccionar Jogo",
        options=list(fixture_options.keys())
    )
    selected_fixture_id = fixture_options[selected_label]

    # Load data
    validator = DataValidator()

    try:
        coverage = validator.check_data_coverage(selected_fixture_id)
        tt_report = validator.check_time_travel_safety(selected_fixture_id)
        raw_json = validator.get_raw_context_json(selected_fixture_id)
    finally:
        validator.close()

    if not coverage:
        st.error("Nao foi possivel carregar dados para este jogo.")
        return

    # Header with match info
    st.markdown(f"### {coverage.home_team} vs {coverage.away_team}")
    st.caption(f"Data: {coverage.match_date}")

    col1, col2 = st.columns(2)

    # Coverage section
    with col1:
        st.markdown("#### Data Coverage")

        # Score gauge
        score = coverage.overall_score
        st.progress(score / 100)
        st.markdown(f"**Score: {score:.0f}%**")

        # Sources list
        for src in coverage.sources:
            status_icon = {"complete": "OK", "partial": "PARCIAL", "missing": "FALTA"}.get(src.status, "?")
            st.markdown(f"{status_icon} **{src.name}**: {src.details}")

    # Time-travel section
    with col2:
        st.markdown("#### Time-Travel Check")

        if tt_report:
            if tt_report.is_safe:
                st.success("SAFE - Sem data leaks detectados")
            else:
                st.error("UNSAFE - Possiveis data leaks")

            st.markdown(f"**Match date:** {tt_report.match_date}")

            if tt_report.warnings:
                st.markdown("**Warnings:**")
                for w in tt_report.warnings:
                    icon = "AVISO" if w.severity == "warning" else "ERRO"
                    st.markdown(f"{icon} {w.message}")
            else:
                st.markdown("Nenhum warning detectado.")
        else:
            st.warning("Nao foi possivel verificar time-travel safety.")

    # Raw JSON expander
    st.markdown("---")
    with st.expander("Ver MatchContext JSON (debug)"):
        if raw_json:
            st.code(raw_json, language="json")
        else:
            st.warning("JSON nao disponivel")


# ============================================================
# TAB 4: ANALISES (Analysis Viewer) - ENHANCED
# ============================================================

def render_tab_analises():
    """Render the ANALISES tab with full transparency."""
    st.header("Visualizador de Analises")

    # Fixture selector
    fixtures = get_all_fixtures()
    if not fixtures:
        st.warning("Nenhum jogo encontrado.")
        return

    fixture_options = {f["label"]: f["id"] for f in fixtures}
    selected_label = st.selectbox(
        "Seleccionar Jogo",
        options=list(fixture_options.keys()),
        key="analises_fixture"
    )
    selected_fixture_id = fixture_options[selected_label]

    # Load analyses with full context
    data = get_analysis_with_context(selected_fixture_id)
    analyses = data.get("analyses", [])

    if not analyses:
        st.info("Nenhuma analise encontrada para este jogo.")
        st.markdown("Use o separador **GERADOR** para criar analises.")
        return

    # Prompt version selector
    prompt_versions = list(set(a["prompt_version"] for a in analyses))
    selected_prompt = st.selectbox(
        "Versao do Prompt",
        options=prompt_versions,
        key="analises_prompt"
    )

    # Get selected analysis
    analysis = next((a for a in analyses if a["prompt_version"] == selected_prompt), None)
    if not analysis:
        st.error("Analise nao encontrada.")
        return

    # Header
    st.markdown(f"### {analysis['home_team']} vs {analysis['away_team']}")

    # Main prediction display
    col1, col2 = st.columns([2, 1])

    with col1:
        st.markdown("#### Previsao")
        st.markdown(f"**Score:** {analysis['predicted_score']}")
        st.markdown(f"**Confianca:** {analysis['confidence']}%")
        if analysis['betting_recommendation']:
            st.markdown(f"**Tip:** {analysis['betting_recommendation']}")

        # Headline from full_json
        full_json = analysis.get("full_json", {})
        narrative = full_json.get("narrative", {})
        if narrative.get("headline"):
            st.markdown(f"**Headline:** \"{narrative['headline']}\"")

    with col2:
        st.markdown("#### Metadata")
        st.markdown(f"**Prompt:** {analysis['prompt_version']}")
        st.markdown(f"**Gerado:** {analysis['created_at']}")

        # Actual result
        if analysis['actual_home'] is not None and analysis['actual_away'] is not None:
            actual = f"{int(analysis['actual_home'])}-{int(analysis['actual_away'])}"
            st.markdown(f"**Resultado Real:** {actual}")

    # Narrative section
    st.markdown("---")
    st.markdown("#### Narrativa")

    if narrative:
        if narrative.get("game_flow"):
            st.markdown(f"**Game Flow:** {narrative['game_flow']}")
        if narrative.get("tactical_dynamic"):
            st.markdown(f"**Tactical Dynamic:** {narrative['tactical_dynamic']}")
    else:
        st.info("Narrativa nao disponivel nesta analise.")

    # Evidence chain + risk factors
    st.markdown("---")
    st.markdown("#### Evidencias e Riscos")

    evidence_chain = full_json.get("evidence_chain", {})
    if evidence_chain:
        for key, value in evidence_chain.items():
            label = key.replace("_", " ").title()
            if isinstance(value, (dict, list)):
                st.markdown(f"**{label}:**")
                st.json(value)
            else:
                st.markdown(f"**{label}:** {value}")
    else:
        st.info("Sem evidence chain disponivel.")

    risk_factors = full_json.get("risk_factors") or full_json.get("risk", [])
    if risk_factors:
        st.markdown("**Risk Factors:**")
        if isinstance(risk_factors, list):
            for risk in risk_factors:
                st.markdown(f"- {risk}")
        else:
            st.markdown(str(risk_factors))

    # DADOS USADOS (MatchContext)
    st.markdown("---")
    with st.expander("DADOS USADOS (MatchContext)", expanded=False):
        # Load fresh context for this fixture
        validator = DataValidator()
        try:
            raw_json = validator.get_raw_context_json(selected_fixture_id)
            if raw_json:
                context_data = json.loads(raw_json)

                # Display key metrics
                col1, col2 = st.columns(2)

                with col1:
                    st.markdown("**HOME**")
                    home = context_data.get("home", {})
                    identity = home.get("identity", {})
                    form = home.get("form", {})

                    st.markdown(f"- Elo: {identity.get('elo', 'N/A')}")
                    st.markdown(f"- Form: {form.get('results', 'N/A')}")
                    st.markdown(f"- xG/match: {identity.get('season_xg_per_match', 'N/A')}")
                    st.markdown(f"- PPDA: {identity.get('season_ppda', 'N/A')}")

                with col2:
                    st.markdown("**AWAY**")
                    away = context_data.get("away", {})
                    identity = away.get("identity", {})
                    form = away.get("form", {})

                    st.markdown(f"- Elo: {identity.get('elo', 'N/A')}")
                    st.markdown(f"- Form: {form.get('results', 'N/A')}")
                    st.markdown(f"- xG/match: {identity.get('season_xg_per_match', 'N/A')}")
                    st.markdown(f"- PPDA: {identity.get('season_ppda', 'N/A')}")

                # Odds
                odds = context_data.get("odds", {})
                if odds.get("home_win"):
                    st.markdown(f"**Odds:** H {odds.get('home_win', 'N/A')} | D {odds.get('draw', 'N/A')} | A {odds.get('away_win', 'N/A')}")

                # Full JSON toggle
                with st.expander("Ver JSON completo"):
                    st.json(context_data)
            else:
                st.warning("MatchContext nao disponivel")
        finally:
            validator.close()

    # PROMPT USADO
    st.markdown("---")
    with st.expander("PROMPT USADO", expanded=False):
        prompt_text = get_prompt_text(analysis['prompt_version'])
        st.markdown(f"**{analysis['prompt_version']}** ({len(prompt_text)} chars)")
        st.code(prompt_text[:2000] + "..." if len(prompt_text) > 2000 else prompt_text, language="text")

    # FACTOR WEIGHTS (Glass Box)
    st.markdown("---")
    with st.expander("FACTOR WEIGHTS (Glass Box)", expanded=False):
        glass_box = full_json.get("glass_box_logic", {}) or full_json.get("weighting_decision", {})
        factor_weights = glass_box.get("factor_weights", {})

        if factor_weights:
            for factor, weight in factor_weights.items():
                if isinstance(weight, (int, float)):
                    bar_width = int(min(weight * 100, 100))
                    st.markdown(f"**{factor}:** {weight:.2f}")
                    st.progress(min(weight, 1.0))
        else:
            st.info("Factor weights nao disponiveis nesta analise.")

        # Reasoning
        if glass_box.get("reasoning"):
            st.markdown("**Reasoning:**")
            st.markdown(glass_box["reasoning"])

    # Full analysis JSON
    st.markdown("---")
    with st.expander("JSON COMPLETO DA ANALISE", expanded=False):
        st.json(full_json)

    # Match reality
    st.markdown("---")
    st.markdown("#### Realidade Pos-Jogo")
    reality = get_match_reality(selected_fixture_id)
    if reality:
        if reality.get("score_home") is not None and reality.get("score_away") is not None:
            actual_score = f"{int(reality['score_home'])}-{int(reality['score_away'])}"
            st.markdown(f"**Score Real:** {actual_score}")
        if reality.get("narrative_summary"):
            st.markdown(f"**Resumo:** {reality['narrative_summary']}")
        if reality.get("key_events"):
            st.markdown("**Eventos-chave:**")
            for event in reality["key_events"]:
                st.markdown(f"- {event}")
        if reality.get("luck_factor") is not None:
            st.markdown(f"**Luck Factor:** {reality['luck_factor']}")
        if reality.get("xg_home") is not None and reality.get("xg_away") is not None:
            st.markdown(f"**xG:** {reality['xg_home']} (H) vs {reality['xg_away']} (A)")
    else:
        st.info("Sem dados de realidade para este jogo.")

    # Evaluation (if exists)
    evaluation = get_evaluation_for_report(analysis["id"])
    if evaluation:
        st.markdown("---")
        st.markdown("#### Avaliacao")

        col1, col2, col3 = st.columns(3)

        with col1:
            score = evaluation.get("narrative_score", 0) or 0
            st.metric("Narrative Score", f"{score}/100")

        with col2:
            score_acc = evaluation.get("score_accuracy")
            st.metric("Score Accuracy", "SIM" if score_acc else "NAO" if score_acc is False else "-")

        with col3:
            tip_acc = evaluation.get("tip_accuracy")
            st.metric("Tip Accuracy", "SIM" if tip_acc else "NAO" if tip_acc is False else "-")

        # Feedback
        if evaluation.get("narrative_feedback"):
            with st.expander("Feedback Detalhado"):
                st.markdown(evaluation["narrative_feedback"])

                if evaluation.get("narrative_critical_flags"):
                    st.markdown("**Critical Flags:**")
                    for flag in evaluation["narrative_critical_flags"]:
                        st.markdown(f"- {flag}")

        if evaluation.get("score_explanation"):
            st.markdown("**Explicacao Score Accuracy:**")
            st.markdown(evaluation["score_explanation"])

        if evaluation.get("tip_explanation"):
            st.markdown("**Explicacao Tip Accuracy:**")
            st.markdown(evaluation["tip_explanation"])


# ============================================================
# TAB 5: AVALIADOR (Evaluator) - NEW
# ============================================================

def render_tab_avaliador():
    """Render the AVALIADOR tab - run and view evaluations."""
    st.header("Avaliador de Analises")

    st.markdown("""
    Avalia analises pre-jogo contra a realidade pos-jogo usando 3 dimensoes:
    1. **Narrative Quality** - Qualidade da narrativa/analise
    2. **Score Accuracy** - Precisao do score previsto
    3. **Tip Accuracy** - Precisao da recomendacao de aposta
    """)

    # Show evaluation criteria
    st.markdown("### Criterios de Avaliacao")

    with st.expander("Ver Criterios Completos"):
        criteria = get_evaluator_criteria()
        st.code(criteria, language="text")

    # Summary by prompt
    st.markdown("---")
    st.markdown("### Resumo de Avaliacoes")
    summary_df = get_evaluation_summary()
    if summary_df.empty:
        st.info("Sem avaliacoes registadas ainda.")
    else:
        summary_df = summary_df.copy()
        summary_df["avg_narrative_score"] = summary_df["avg_narrative_score"].apply(
            lambda x: f"{x:.1f}" if pd.notna(x) else "-"
        )
        summary_df["score_accuracy"] = summary_df["score_accuracy"].apply(
            lambda x: f"{x:.1f}%" if pd.notna(x) else "-"
        )
        summary_df["tip_accuracy"] = summary_df["tip_accuracy"].apply(
            lambda x: f"{x:.1f}%" if pd.notna(x) else "-"
        )
        summary_df.columns = [
            "Prompt",
            "Avaliacoes",
            "Narrative Score",
            "Score Accuracy",
            "Tip Accuracy"
        ]
        st.dataframe(summary_df, use_container_width=True, hide_index=True)

    # Get unevaluated analyses
    st.markdown("---")
    st.markdown("### Analises por Avaliar")

    unevaluated = get_unevaluated_analyses(limit=100)

    if not unevaluated:
        st.success("Todas as analises com reality data ja foram avaliadas.")
    else:
        prompt_versions = sorted({a["prompt_version"] for a in unevaluated})
        prompt_filter = st.selectbox(
            "Filtrar por prompt",
            options=["Todos"] + prompt_versions,
            key="avaliador_prompt_filter"
        )

        if prompt_filter != "Todos":
            unevaluated = [a for a in unevaluated if a["prompt_version"] == prompt_filter]

        st.markdown(f"**{len(unevaluated)} analises por avaliar**")

        if not unevaluated:
            st.info("Nenhuma analise por avaliar com este filtro.")
        else:
            # Group by round
            by_round = {}
            for a in unevaluated:
                r = a["round"]
                if r not in by_round:
                    by_round[r] = []
                by_round[r].append(a)

            # Show summary
            for round_num in sorted(by_round.keys(), reverse=True):
                count = len(by_round[round_num])
                st.markdown(f"- Ronda {round_num}: {count} analises")

            # Evaluation buttons
            col1, col2 = st.columns(2)

            with col1:
                eval_all_btn = st.button(
                    f"AVALIAR TODAS ({len(unevaluated)})",
                    type="primary",
                    use_container_width=True
                )

            with col2:
                # Specific round evaluation
                round_to_eval = st.selectbox(
                    "Avaliar ronda especifica",
                    options=sorted(by_round.keys(), reverse=True),
                    format_func=lambda x: f"Ronda {x} ({len(by_round[x])} analises)"
                )
                eval_round_btn = st.button(
                    f"AVALIAR RONDA {round_to_eval}",
                    use_container_width=True
                )

            force_refresh_eval = st.checkbox("Forcar reavaliacao (ignora cache)", value=False)

            # Run evaluation
            if eval_all_btn or eval_round_btn:
                from src.analysis.evaluator import AnalysisEvaluator

                if eval_round_btn:
                    analyses_to_eval = by_round.get(round_to_eval, [])
                else:
                    analyses_to_eval = unevaluated

                if not analyses_to_eval:
                    st.warning("Nenhuma analise para avaliar.")
                else:
                    progress_bar = st.progress(0)
                    status_text = st.empty()
                    results_container = st.container()

                    evaluator = AnalysisEvaluator()
                    results = []

                    try:
                        for i, a in enumerate(analyses_to_eval):
                            match_label = f"{a['home_team']} vs {a['away_team']} ({a['prompt_version']})"
                            status_text.markdown(f"Avaliando: **{match_label}**...")
                            progress_bar.progress(i / len(analyses_to_eval))

                            try:
                                result = evaluator.evaluate_analysis(a["report_id"], force_refresh=force_refresh_eval)
                                if result:
                                    score = result.get("narrative_quality", {}).get("score", "?")
                                    results.append({"match": match_label, "status": f"Score: {score}", "icon": "OK"})
                                else:
                                    results.append({"match": match_label, "status": "Skipped", "icon": "SKIP"})
                            except Exception as e:
                                results.append({"match": match_label, "status": str(e), "icon": "ERRO"})

                            time.sleep(0.5)

                        progress_bar.progress(1.0)
                        status_text.markdown("**Concluido!**")

                    finally:
                        evaluator.close()

                    # Show results
                    with results_container:
                        st.markdown("#### Resultados")
                        for r in results:
                            st.markdown(f"- {r['icon']} {r['match']} - {r['status']}")

                    st.cache_data.clear()

    # Individual evaluation view
    st.markdown("---")
    st.markdown("### Ver Avaliacao Individual")

    # Get fixtures with evaluations
    conn = get_connection()
    if conn:
        query = """
            SELECT DISTINCT ae.fixture_id, f.home_team, f.away_team, f.round, f.date
            FROM analysis_evaluations ae
            JOIN fixtures f ON ae.fixture_id = f.id
            ORDER BY f.date DESC
            LIMIT 50
        """
        eval_fixtures = pd.read_sql(query, conn)
        conn.close()

        if not eval_fixtures.empty:
            fixture_options = {}
            for _, row in eval_fixtures.iterrows():
                label = f"{row['home_team']} vs {row['away_team']} (R{row['round']})"
                fixture_options[label] = row['fixture_id']

            selected_eval_fixture = st.selectbox(
                "Seleccionar Jogo Avaliado",
                options=list(fixture_options.keys()),
                key="avaliador_fixture"
            )

            if selected_eval_fixture:
                fixture_id = fixture_options[selected_eval_fixture]

                # Get evaluations for this fixture
                conn = get_connection()
                if conn:
                    query = """
                        SELECT
                            ae.report_id, ae.prompt_version,
                            ae.narrative_score, ae.narrative_feedback, ae.narrative_critical_flags,
                            ae.score_accuracy, ae.score_explanation,
                            ae.tip_accuracy, ae.tip_explanation,
                            ae.evaluation_json,
                            ar.predicted_score, ar.confidence,
                            mr.score_home, mr.score_away
                        FROM analysis_evaluations ae
                        JOIN analysis_reports ar ON ae.report_id = ar.id
                        JOIN match_reality mr ON ae.fixture_id = mr.fixture_id
                        WHERE ae.fixture_id = %s
                    """
                    evals = pd.read_sql(query, conn, params=(fixture_id,))
                    conn.close()

                    if not evals.empty:
                        for _, ev in evals.iterrows():
                            st.markdown(f"#### Prompt: {ev['prompt_version']}")

                            actual = f"{int(ev['score_home'])}-{int(ev['score_away'])}"
                            pred_ok = "SIM" if ev['score_accuracy'] else "NAO"
                            tip_ok = "SIM" if ev['tip_accuracy'] else "NAO"

                            col1, col2, col3, col4 = st.columns(4)

                            with col1:
                                st.metric("Real", actual)

                            with col2:
                                st.metric("Previsto", ev['predicted_score'], pred_ok)

                            with col3:
                                st.metric("Confianca", f"{ev['confidence']}%")

                            with col4:
                                st.metric("Tip", tip_ok)

                            st.metric("Narrative Score", f"{ev['narrative_score']}/100")

                            if ev['narrative_feedback']:
                                with st.expander("Feedback"):
                                    st.markdown(ev['narrative_feedback'])

                            if ev['score_explanation']:
                                st.markdown(f"**Score Accuracy:** {ev['score_explanation']}")

                            if ev['tip_explanation']:
                                st.markdown(f"**Tip Accuracy:** {ev['tip_explanation']}")

                            critical_flags = ev['narrative_critical_flags']
                            if isinstance(critical_flags, str):
                                try:
                                    critical_flags = json.loads(critical_flags)
                                except:
                                    critical_flags = []

                            if critical_flags:
                                st.markdown("**Critical Flags:**")
                                for flag in critical_flags:
                                    st.markdown(f"- `{flag}`")

                            if ev.get("evaluation_json"):
                                with st.expander("Evaluation JSON"):
                                    evaluation_json = ev["evaluation_json"]
                                    if isinstance(evaluation_json, str):
                                        try:
                                            evaluation_json = json.loads(evaluation_json)
                                        except:
                                            evaluation_json = {"raw": evaluation_json}
                                    st.json(evaluation_json)

                            st.markdown("---")


# ============================================================
# TAB 6: COMPARADOR (Comparator) - ENHANCED
# ============================================================

def render_tab_comparador():
    """Render the COMPARADOR tab - compare prompt performance."""
    st.header("Comparador de Prompts")

    # Get available prompts
    prompt_list = list(PROMPTS.keys())

    if len(prompt_list) < 2:
        st.warning("Necessarios pelo menos 2 prompts para comparar.")
        return

    # Prompt selection
    col1, col2 = st.columns(2)

    with col1:
        prompt_a = st.selectbox(
            "Prompt A",
            options=prompt_list,
            index=0,
            format_func=lambda x: f"{x} - {PROMPTS[x]['name']}",
            key="comp_prompt_a"
        )

    with col2:
        other_prompts = [p for p in prompt_list if p != prompt_a]
        prompt_b = st.selectbox(
            "Prompt B",
            options=other_prompts,
            index=0 if other_prompts else None,
            format_func=lambda x: f"{x} - {PROMPTS[x]['name']}",
            key="comp_prompt_b"
        )

    if not prompt_b:
        st.warning("Seleccione dois prompts diferentes.")
        return

    # Get comparison data
    comparison = get_prompt_comparison_data(prompt_a, prompt_b)

    if not comparison.get("matches"):
        st.info(f"Nenhum jogo encontrado com analises de ambos '{prompt_a}' e '{prompt_b}'.")
        return

    # Overall stats
    st.markdown("### Resumo")

    stats_a = comparison["stats_a"]
    stats_b = comparison["stats_b"]

    col1, col2 = st.columns(2)

    with col1:
        st.markdown(f"#### {prompt_a}")
        st.metric("Analises", stats_a["total"])
        st.metric("Score Accuracy", f"{stats_a['accuracy']:.1f}%")
        st.metric("Acertos", f"{stats_a['correct']}/{stats_a['total']}")

        avg_conf_a = stats_a.get("avg_confidence")
        if avg_conf_a is not None:
            st.markdown(f"**Confianca media:** {avg_conf_a:.1f}%")
        if stats_a.get("avg_narrative") is not None:
            st.markdown(f"**Narrative Score (avg):** {stats_a['avg_narrative']:.1f}")
        if stats_a.get("score_accuracy") is not None:
            st.markdown(
                f"**Score Accuracy (eval):** {stats_a['score_accuracy']:.1f}% ({stats_a['score_samples']})"
            )
        if stats_a.get("tip_accuracy") is not None:
            st.markdown(
                f"**Tip Accuracy (eval):** {stats_a['tip_accuracy']:.1f}% ({stats_a['tip_samples']})"
            )

    with col2:
        st.markdown(f"#### {prompt_b}")
        st.metric("Analises", stats_b["total"])
        st.metric("Score Accuracy", f"{stats_b['accuracy']:.1f}%")
        st.metric("Acertos", f"{stats_b['correct']}/{stats_b['total']}")

        avg_conf_b = stats_b.get("avg_confidence")
        if avg_conf_b is not None:
            st.markdown(f"**Confianca media:** {avg_conf_b:.1f}%")
        if stats_b.get("avg_narrative") is not None:
            st.markdown(f"**Narrative Score (avg):** {stats_b['avg_narrative']:.1f}")
        if stats_b.get("score_accuracy") is not None:
            st.markdown(
                f"**Score Accuracy (eval):** {stats_b['score_accuracy']:.1f}% ({stats_b['score_samples']})"
            )
        if stats_b.get("tip_accuracy") is not None:
            st.markdown(
                f"**Tip Accuracy (eval):** {stats_b['tip_accuracy']:.1f}% ({stats_b['tip_samples']})"
            )

    # Winner
    st.markdown("---")
    diff = stats_a['accuracy'] - stats_b['accuracy']
    if abs(diff) < 1:
        st.markdown(f"### Resultado: **EMPATE**")
    elif diff > 0:
        st.markdown(f"### Vencedor: **{prompt_a}** (+{diff:.1f}% accuracy)")
    else:
        st.markdown(f"### Vencedor: **{prompt_b}** (+{abs(diff):.1f}% accuracy)")

    # Head-to-head wins
    st.markdown(f"**Confronto directo:** {prompt_a} {comparison['a_wins']} - {comparison['ties']} - {comparison['b_wins']} {prompt_b}")
    if stats_a.get("score_samples") or stats_b.get("score_samples"):
        st.caption(
            f"Cobertura de avaliacoes: {prompt_a} {stats_a.get('score_samples', 0)} | {prompt_b} {stats_b.get('score_samples', 0)}"
        )

    # Head-to-head table
    st.markdown("---")
    st.markdown("### Confronto Directo (Mesmos Jogos)")

    matches_df = pd.DataFrame(comparison["matches"])

    # Format for display
    display_data = []
    for m in comparison["matches"]:
        correct_a = "SIM" if m['correct_a'] else "NAO" if m['correct_a'] is False else "-"
        correct_b = "SIM" if m['correct_b'] else "NAO" if m['correct_b'] is False else "-"

        display_data.append({
            "Jogo": m['match'],
            f"{prompt_a}": f"{m['pred_a']} {correct_a}",
            f"{prompt_b}": f"{m['pred_b']} {correct_b}",
            "Real": m['actual'],
            "Vencedor": m['winner']
        })

    st.dataframe(
        pd.DataFrame(display_data),
        use_container_width=True,
        hide_index=True
    )

    # Performance tracker (existing functionality)
    st.markdown("---")
    st.markdown("### Leaderboard Global")

    tracker = PerformanceTracker()

    try:
        leaderboard = tracker.get_prompt_leaderboard()

        if leaderboard:
            lb_data = []
            for i, p in enumerate(leaderboard):
                trend_icon = {"up": "SUBIU", "down": "DESCEU", "stable": "ESTAVEL"}.get(p.trend, "")
                crown = "[1] " if i == 0 else ""
                lb_data.append({
                    "Prompt": f"{crown}{p.prompt_version}",
                    "Jogos": p.total_predictions,
                    "Acertos": p.correct_predictions,
                    "Accuracy": f"{p.accuracy:.1f}%",
                    "Trend": f"{trend_icon} {p.trend_delta:+.1f}%"
                })

            st.dataframe(
                pd.DataFrame(lb_data),
                use_container_width=True,
                hide_index=True
            )
        else:
            st.info("Sem dados de leaderboard.")
    finally:
        tracker.close()


# ============================================================
# WORKFLOW VIEWS (LEAGUE > ROUND > WORKFLOW)
# ============================================================

def get_status_label(fixtures_total: int, analyses_total: int, evaluations_total: int) -> tuple[str, str]:
    if fixtures_total == 0:
        return "SEM DADOS", "ce-pill--muted"
    if evaluations_total >= fixtures_total:
        return "COMPLETO", "ce-pill"
    if analyses_total > 0:
        return "EM PROGRESSO", "ce-pill"
    return "PENDENTE", "ce-pill--muted"


def render_league_overview():
    """Render league cards."""
    st.header("Ligas")

    leagues_df = get_league_overview()
    if leagues_df.empty:
        st.info("Nenhuma liga encontrada.")
        return

    seasons = sorted(leagues_df["season"].unique(), reverse=True)
    selected_season = seasons[0]
    if len(seasons) > 1:
        selected_season = st.selectbox("Temporada", options=seasons, key="league_season")

    filtered = leagues_df[leagues_df["season"] == selected_season]
    columns = st.columns(2)

    for idx, row in filtered.reset_index(drop=True).iterrows():
        col = columns[idx % 2]
        with col:
            with st.container():
                status_label, status_class = get_status_label(
                    int(row["fixtures_total"]),
                    int(row["analyses_total"]),
                    int(row["evaluations_total"])
                )

                st.markdown(f"### {row['league']}")
                st.caption(f"Temporada {row['season']}")
                st.markdown(
                    f"<span class='ce-pill {status_class}'>{status_label}</span>",
                    unsafe_allow_html=True
                )

                stats_col1, stats_col2, stats_col3 = st.columns(3)
                with stats_col1:
                    st.metric("Jogos", int(row["fixtures_total"]))
                with stats_col2:
                    st.metric("Analises", int(row["analyses_total"]))
                with stats_col3:
                    st.metric("Avaliacoes", int(row["evaluations_total"]))

                if st.button(
                    "Abrir Liga",
                    key=f"open_league_{row['league']}_{row['season']}",
                    use_container_width=True
                ):
                    st.session_state.selected_league = row["league"]
                    st.session_state.selected_season = row["season"]
                    st.session_state.view = "rounds"
                    st.session_state.current_step = "fixtures"
                    st.rerun()


def render_rounds_overview(league: str, season: str):
    """Render round cards for a league."""
    st.header(f"{league} • {season}")

    if st.button("Voltar às ligas", use_container_width=False, key="back_to_leagues"):
        st.session_state.view = "leagues"
        st.rerun()

    rounds_df = get_round_stats(league, season)
    if rounds_df.empty:
        st.info("Nenhuma ronda encontrada para esta liga.")
        return

    top_prompts = get_round_top_prompt(league, season)
    columns = st.columns(2)

    for idx, row in rounds_df.reset_index(drop=True).iterrows():
        col = columns[idx % 2]
        with col:
            with st.container():
                round_num = int(row["round"])
                fixtures_total = int(row["fixtures_total"])
                analyses_total = int(row["analyses_total"])
                evaluations_total = int(row["evaluations_total"])
                status_label, status_class = get_status_label(
                    fixtures_total,
                    analyses_total,
                    evaluations_total
                )

                st.markdown(f"### Ronda {round_num}")
                st.markdown(
                    f"<span class='ce-pill {status_class}'>{status_label}</span>",
                    unsafe_allow_html=True
                )

                last_update = row["last_update"]
                last_label = last_update.strftime("%d/%m/%Y") if hasattr(last_update, "strftime") else "-"
                st.caption(f"Ultima atividade: {last_label}")
                prompt_label = top_prompts.get(round_num, "-")

                stats_col1, stats_col2, stats_col3 = st.columns(3)
                with stats_col1:
                    st.metric("Jogos", fixtures_total)
                with stats_col2:
                    st.metric("Analises", analyses_total)
                with stats_col3:
                    st.metric("Avaliacoes", evaluations_total)

                st.markdown(f"**Prompt principal:** {prompt_label}")

                if st.button(
                    f"Abrir Ronda {round_num}",
                    key=f"open_round_{league}_{season}_{round_num}",
                    use_container_width=True
                ):
                    st.session_state.selected_round = round_num
                    st.session_state.view = "round_detail"
                    st.session_state.current_step = "fixtures"
                    st.rerun()


def render_stepper(current_step: str) -> str:
    steps = [
        ("fixtures", "Fixtures"),
        ("prompt", "Prompt"),
        ("generate", "Generate"),
        ("review", "Review"),
        ("evaluate", "Evaluate"),
        ("compare", "Compare"),
        ("iterate", "Iterate")
    ]

    cols = st.columns(len(steps))
    for idx, (key, label) in enumerate(steps):
        with cols[idx]:
            button_type = "primary" if current_step == key else "secondary"
            if st.button(label, key=f"step_{key}", use_container_width=True, type=button_type):
                st.session_state.current_step = key
                st.rerun()

    return st.session_state.current_step


def render_step_fixtures(league: str, season: str, round_num: int):
    with st.container():
        st.markdown("### Fixtures da Ronda")
        fixtures_df = get_fixtures_by_round(round_num, season=season, league=league)
        if fixtures_df.empty:
            st.info("Nenhum jogo encontrado para esta ronda.")
            return

        fixture_ids = fixtures_df["fixture_id"].tolist()
        analysis_status = get_analysis_status(fixture_ids)

        rows = []
        for _, fix in fixtures_df.iterrows():
            fid = fix["fixture_id"]
            data_status = get_fixture_data_status(fid)
            data_icon = {"complete": "OK", "partial": "PARCIAL", "missing": "FALTA"}.get(data_status, "?")

            analyses = analysis_status.get(fid, [])
            analysis_prompt = analyses[0]["prompt"] if analyses else "-"
            analysis_correct = analyses[0]["is_correct"] if analyses else None

            if fix["home_score"] is not None and fix["away_score"] is not None:
                result = f"{int(fix['home_score'])}-{int(fix['away_score'])}"
            else:
                result = "-"

            if analysis_correct is True:
                correct_icon = "SIM"
            elif analysis_correct is False:
                correct_icon = "NAO"
            else:
                correct_icon = "-"

            rows.append({
                "Jogo": f"{fix['home_team']} vs {fix['away_team']}",
                "Data": fix["date"].strftime("%d/%m") if fix["date"] else "-",
                "Dados": data_icon,
                "Prompt": analysis_prompt,
                "Resultado": result,
                "Acertou?": correct_icon
            })

        st.dataframe(pd.DataFrame(rows), use_container_width=True, hide_index=True)


def render_step_prompt():
    with st.container():
        st.markdown("### Seleccionar Prompt")
        prompt_options = {k: v["name"] for k, v in PROMPTS.items()}
        selected_prompt = st.selectbox(
            "Prompt Version",
            options=list(prompt_options.keys()),
            format_func=lambda x: f"{x} - {prompt_options[x]}",
            key="workflow_prompt"
        )
        st.session_state.selected_prompt = selected_prompt

        with st.expander("Ver prompt completo"):
            prompt_text = get_prompt_text(selected_prompt)
            st.code(prompt_text[:3000] + "..." if len(prompt_text) > 3000 else prompt_text, language="text")
            st.caption(f"Total: {len(prompt_text)} caracteres")


def render_step_generate(league: str, season: str, round_num: int):
    with st.container():
        st.markdown("### Gerar Analises")

        selected_prompt = st.session_state.get("selected_prompt") or list(PROMPTS.keys())[0]
        force_refresh = st.checkbox("Forcar regeneracao (ignora cache)", value=False, key="workflow_force")
        only_pending = st.checkbox(
            "Apenas jogos sem analise",
            value=True,
            key="workflow_pending",
            disabled=force_refresh
        )

        fixtures_df = get_fixtures_by_round(round_num, season=season, league=league)
        if fixtures_df.empty:
            st.warning("Nenhum jogo encontrado para esta ronda.")
            return

        fixture_options = {
            f"{fix['home_team']} vs {fix['away_team']}": fix["fixture_id"]
            for _, fix in fixtures_df.iterrows()
        }

        if only_pending and not force_refresh:
            pending_fixtures = get_fixtures_without_analysis(
                round_num,
                selected_prompt,
                season=season,
                league=league
            )
            pending_ids = [f["id"] for f in pending_fixtures]
            fixture_options = {k: v for k, v in fixture_options.items() if v in pending_ids}

        if not fixture_options:
            st.info("Todos os jogos desta ronda ja tem analise para o prompt seleccionado.")
            return

        selected_fixtures = st.multiselect(
            "Jogos a gerar",
            options=list(fixture_options.keys()),
            default=list(fixture_options.keys()),
            key="workflow_fixtures"
        )

        st.markdown(f"**Jogos seleccionados:** {len(selected_fixtures)}")

        generate_btn = st.button(
            f"GERAR ANALISES ({len(selected_fixtures)} jogos x {selected_prompt})",
            type="primary",
            use_container_width=True,
            disabled=len(selected_fixtures) == 0
        )

        if generate_btn and selected_fixtures:
            fixture_ids = [fixture_options[f] for f in selected_fixtures]

            progress_bar = st.progress(0)
            status_text = st.empty()
            results_container = st.container()

            from src.analysis.predictor import ClarityEngine

            engine = ClarityEngine()
            results = []

            try:
                for i, fixture_id in enumerate(fixture_ids):
                    match_label = [k for k, v in fixture_options.items() if v == fixture_id][0]
                    status_text.markdown(f"Gerando: **{match_label}**...")
                    progress_bar.progress((i) / len(fixture_ids))

                    try:
                        result = engine.run_analysis(fixture_id, selected_prompt, force_refresh=force_refresh)
                        if result and "error" not in result:
                            results.append({"fixture": match_label, "status": "OK", "icon": "OK"})
                        else:
                            error_msg = result.get("error", "Unknown") if result else "No result"
                            results.append({"fixture": match_label, "status": error_msg, "icon": "ERRO"})
                    except Exception as e:
                        results.append({"fixture": match_label, "status": str(e), "icon": "ERRO"})

                    time.sleep(0.4)

                progress_bar.progress(1.0)
                status_text.markdown("**Concluido!**")

            finally:
                engine.close()

            with results_container:
                st.markdown("#### Resultados")
                for r in results:
                    icon = "OK" if r["icon"] == "OK" else "ERRO"
                    st.markdown(f"- {icon} {r['fixture']} - {r['status']}")

            st.cache_data.clear()


def render_step_review(league: str, season: str, round_num: int):
    with st.container():
        st.markdown("### Revisao de Analises")
        fixtures_df = get_fixtures_by_round(round_num, season=season, league=league)
        if fixtures_df.empty:
            st.info("Nenhuma analise encontrada para esta ronda.")
            return

        fixture_options = {
            f"{fix['home_team']} vs {fix['away_team']}": fix["fixture_id"]
            for _, fix in fixtures_df.iterrows()
        }

        selected_label = st.selectbox(
            "Seleccionar Jogo",
            options=list(fixture_options.keys()),
            key="workflow_review_fixture"
        )
        selected_fixture_id = fixture_options[selected_label]

        data = get_analysis_with_context(selected_fixture_id)
        analyses = data.get("analyses", [])

        if not analyses:
            st.info("Nenhuma analise encontrada para este jogo.")
            return

        prompt_versions = list(set(a["prompt_version"] for a in analyses))
        selected_prompt = st.selectbox(
            "Versao do Prompt",
            options=prompt_versions,
            key="workflow_review_prompt"
        )

        analysis = next((a for a in analyses if a["prompt_version"] == selected_prompt), None)
        if not analysis:
            st.error("Analise nao encontrada.")
            return

        col1, col2 = st.columns([2, 1])
        with col1:
            st.markdown("#### Previsao")
            st.markdown(f"**Score:** {analysis['predicted_score']}")
            st.markdown(f"**Confianca:** {analysis['confidence']}%")
            if analysis["betting_recommendation"]:
                st.markdown(f"**Tip:** {analysis['betting_recommendation']}")
        with col2:
            st.markdown("#### Metadata")
            st.markdown(f"**Prompt:** {analysis['prompt_version']}")
            st.markdown(f"**Gerado:** {analysis['created_at']}")

        st.markdown("---")
        with st.expander("Ver narrativa"):
            full_json = analysis.get("full_json", {})
            narrative = full_json.get("narrative", {})
            if narrative:
                for key, value in narrative.items():
                    st.markdown(f"**{key.replace('_', ' ').title()}:** {value}")
            else:
                st.info("Narrativa nao disponivel nesta analise.")

        with st.expander("Ver contexto completo"):
            validator = DataValidator()
            try:
                raw_json = validator.get_raw_context_json(selected_fixture_id)
                st.json(raw_json)
            finally:
                validator.close()

    metrics_df = get_round_metrics_table(league, season, round_num)
    if not metrics_df.empty:
        metrics_df = metrics_df.copy()
        metrics_df["accuracy"] = metrics_df["accuracy"].map(lambda x: f"{x:.1f}%" if pd.notna(x) else "-")
        metrics_df["score_accuracy"] = metrics_df["score_accuracy"].map(lambda x: f"{x:.1f}%" if pd.notna(x) else "-")
        metrics_df["tip_accuracy"] = metrics_df["tip_accuracy"].map(lambda x: f"{x:.1f}%" if pd.notna(x) else "-")
        metrics_df["narrative_avg"] = metrics_df["narrative_avg"].map(lambda x: f"{x:.1f}" if pd.notna(x) else "-")
        metrics_df.columns = [
            "Prompt",
            "Analises",
            "Accuracy",
            "Score Accuracy",
            "Tip Accuracy",
            "Narrative Avg"
        ]

        st.markdown("### Key Metrics")
        st.dataframe(metrics_df, use_container_width=True, hide_index=True)


def render_step_evaluate():
    with st.container():
        render_tab_avaliador()


def render_step_compare():
    with st.container():
        render_tab_comparador()


def render_step_iterate():
    with st.container():
        st.markdown("### Iterar")
        st.markdown("Inicie um novo ciclo com um prompt diferente.")
        if st.button("Escolher novo prompt", key="iterate_prompt", type="primary"):
            st.session_state.current_step = "prompt"
            st.rerun()


def render_round_detail(league: str, season: str, round_num: int):
    st.header(f"{league} • {season}")

    if st.button("Voltar às rondas", key="back_to_rounds"):
        st.session_state.view = "rounds"
        st.rerun()

    st.markdown(f"## Ronda {round_num}")
    round_stats = get_round_stats(league, season)
    round_row = round_stats[round_stats["round"] == round_num]
    if not round_row.empty:
        row = round_row.iloc[0]
        stats_col1, stats_col2, stats_col3 = st.columns(3)
        with stats_col1:
            st.metric("Jogos", int(row["fixtures_total"]))
        with stats_col2:
            st.metric("Analises", int(row["analyses_total"]))
        with stats_col3:
            st.metric("Avaliacoes", int(row["evaluations_total"]))
    st.markdown("---")

    render_stepper(st.session_state.get("current_step", "fixtures"))
    st.markdown("---")

    step = st.session_state.get("current_step", "fixtures")
    if step == "fixtures":
        render_step_fixtures(league, season, round_num)
    elif step == "prompt":
        render_step_prompt()
    elif step == "generate":
        render_step_generate(league, season, round_num)
    elif step == "review":
        render_step_review(league, season, round_num)
    elif step == "evaluate":
        render_step_evaluate()
    elif step == "compare":
        render_step_compare()
    elif step == "iterate":
        render_step_iterate()


# ============================================================
# MAIN APP
# ============================================================

def main():
    st.title("Clarity Engine v4")

    leagues_df = get_league_overview()

    if leagues_df.empty:
        st.info("Sem ligas disponiveis.")
        return

    default_league = leagues_df.iloc[0]["league"]
    default_season = leagues_df.iloc[0]["season"]

    if "selected_league" not in st.session_state:
        st.session_state.selected_league = default_league
    if "selected_season" not in st.session_state:
        st.session_state.selected_season = default_season
    if "selected_round" not in st.session_state:
        st.session_state.selected_round = get_current_round(
            season=st.session_state.selected_season,
            league=st.session_state.selected_league
        )
    if "view" not in st.session_state:
        st.session_state.view = "leagues"
    if "current_step" not in st.session_state:
        st.session_state.current_step = "fixtures"

    view = st.session_state.view
    if view == "leagues":
        render_league_overview()
    elif view == "rounds":
        render_rounds_overview(
            st.session_state.selected_league,
            st.session_state.selected_season
        )
    elif view == "round_detail":
        render_round_detail(
            st.session_state.selected_league,
            st.session_state.selected_season,
            st.session_state.selected_round
        )
    else:
        st.session_state.view = "leagues"
        render_league_overview()


if __name__ == "__main__":
    main()
