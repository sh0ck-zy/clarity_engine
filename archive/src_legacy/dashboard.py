import streamlit as st
import pandas as pd
import json
import sys
from datetime import datetime, timezone
from pathlib import Path

# --- 1. CONFIGURAÇÃO DE AMBIENTE ROBUSTA ---
current_file = Path(__file__).resolve()
project_root = current_file.parent

if (project_root / "src").exists():
    sys.path.append(str(project_root))
elif (project_root.parent / "src").exists():
    sys.path.append(str(project_root.parent))
    project_root = project_root.parent
else:
    sys.path.append(str(current_file.parent.parent))

# Configuração da Página
st.set_page_config(
    page_title="Clarity Ops v2",
    page_icon="🧠",
    layout="wide",
    initial_sidebar_state="expanded"
)

# Imports do projeto
try:
    from src.database.config import get_connection
    from src.analysis.builder import MatchContextBuilder
    from src.analysis.predictor import ClarityEngine
    from src.analysis.prompts import PROMPTS
    from src.jobs.batch_runner import BatchRunner
    from src.analysis.evaluator import AnalysisEvaluator
    from src.analysis.validation import ValidationEngine, run_validation, compare_all_prompts
except ImportError as e:
    st.error(f"Critical Import Error: {e}")
    st.stop()

# --- CSS CUSTOMIZADO ---
st.markdown("""
<style>
    @import url('https://fonts.googleapis.com/css2?family=Space+Grotesk:wght@400;500;600;700&family=Source+Serif+4:opsz,wght@8..60,400;600&display=swap');

    html, body, [class*="css"] {
        font-family: 'Space Grotesk', sans-serif;
    }

    .stApp {
        background: radial-gradient(1100px circle at 15% 10%, #1b2433 0%, #0b0f14 45%, #07090c 100%);
        color: #f2f5f8;
    }

    h1, h2, h3, h4 {
        font-family: 'Source Serif 4', serif;
        letter-spacing: 0.2px;
    }

    .status-finished { color: #4CAF50; font-weight: 600; font-size: 0.85em; }
    .status-scheduled { color: #FFA726; font-weight: 600; font-size: 0.85em; }

    .cockpit-panel {
        background: rgba(22, 28, 39, 0.72);
        border: 1px solid rgba(148, 163, 184, 0.16);
        border-radius: 16px;
        padding: 18px 18px 12px 18px;
        box-shadow: 0 8px 24px rgba(5, 8, 13, 0.45);
    }

    .kpi-label {
        text-transform: uppercase;
        font-size: 11px;
        letter-spacing: 1px;
        color: rgba(226, 232, 240, 0.7);
    }

    .kpi-value {
        font-size: 26px;
        font-weight: 600;
        color: #f8fafc;
        margin-top: 4px;
    }

    .subtle { color: rgba(226, 232, 240, 0.65); }
</style>
""", unsafe_allow_html=True)

# --- FUNÇÕES DE FORMATAÇÃO ---
def render_telegram_preview(data):
    """Gera o cartão visual estilo Telegram."""
    try:
        pred = data.get('prediction', {})
        narrative = data.get('narrative', {})
        evidence = data.get('evidence_chain', {})
        logic = data.get('glass_box_logic', {})
        headline = data.get('headline', 'Análise Clarity')
        
        conf = int(pred.get('confidence', 0))
        
        if conf >= 75:
            icon = "💎"
            badge_text = "CLARITY PICK"
        elif conf >= 60:
            icon = "⚖️"
            badge_text = "VALUE LEAN"
        else:
            icon = "⚠️"
            badge_text = "TRAP / SKIP"

        msg_content = f"""
        {icon} <b>{headline}</b>
        <br>
        {badge_text} | 📊 <b>{conf}%</b>
        <br><br>
        🎯 <b>Aposta:</b> {evidence.get('market_verdict', 'N/A')}<br>
        🔮 <b>Score:</b> {pred.get('scoreline', 'N/A')}
        <br><br>
        <b>🧠 A Lógica:</b><br>
        {logic.get('reasoning', 'N/A')}
        <br><br>
        <b>📖 O Filme do Jogo:</b><br>
        {narrative.get('game_flow', 'N/A')}
        <br><br>
        <i>⚠️ Risco: {data.get('risk_factors', ['N/A'])[0]}</i>
        """
        
        bubble_html = f"""
        <div style="
            background-color: #2b5278;
            color: #ffffff;
            padding: 10px 14px;
            border-radius: 12px 12px 12px 0px;
            font-family: Helvetica, Arial, sans-serif;
            font-size: 15px;
            line-height: 1.45;
            max-width: 550px;
            box-shadow: 0 1px 2px rgba(0,0,0,0.3);
            margin-bottom: 10px;
        ">
            {msg_content}
            <div style="text-align: right; font-size: 11px; color: #8faec5; margin-top: 6px;">15:30 ✓✓</div>
        </div>
        """
        return bubble_html
    except Exception as e:
        return f"<div style='color:red'>Erro ao gerar preview: {e}</div>"

# --- FUNÇÕES DE DADOS ---
def get_leagues():
    """Return distinct leagues if the column exists; default to Premier League."""
    conn = get_connection()
    if not conn:
        return ["Premier League"]
    try:
        cur = conn.cursor()
        cur.execute("""
            SELECT 1 
            FROM information_schema.columns 
            WHERE table_name = 'fixtures' AND column_name = 'league'
        """)
        has_league_col = cur.fetchone() is not None
        if not has_league_col:
            return ["Premier League"]

        df = pd.read_sql("SELECT DISTINCT league FROM fixtures ORDER BY league ASC", conn)
        leagues = [l for l in df['league'].dropna().tolist() if l]
        return leagues or ["Premier League"]
    except Exception:
        return ["Premier League"]
    finally:
        conn.close()

def get_seasons():
    conn = get_connection()
    if not conn: return []
    try:
        df = pd.read_sql("SELECT DISTINCT season FROM fixtures ORDER BY season DESC", conn)
        return df['season'].tolist()
    except Exception: return []
    finally: conn.close()


def get_prompt_versions():
    """Get distinct prompt versions from analysis reports."""
    conn = get_connection()
    if not conn:
        return list(PROMPTS.keys())
    try:
        df = pd.read_sql("SELECT DISTINCT prompt_version FROM analysis_reports ORDER BY prompt_version ASC", conn)
        prompts = [p for p in df['prompt_version'].dropna().tolist() if p]
        return prompts or list(PROMPTS.keys())
    except Exception:
        return list(PROMPTS.keys())
    finally:
        conn.close()

def get_rounds(season, league=None):
    """Get list of rounds for a season, optionally filtered by league."""
    conn = get_connection()
    if not conn: return []
    try:
        if league:
            query = 'SELECT DISTINCT "round" FROM fixtures WHERE season=%s AND league=%s ORDER BY "round" DESC'
            df = pd.read_sql(query, conn, params=(season, league))
        else:
            df = pd.read_sql('SELECT DISTINCT "round" FROM fixtures WHERE season=%s ORDER BY "round" DESC', conn, params=(season,))
        return [int(r) for r in df['round'].dropna().tolist()]
    except Exception: return []
    finally: conn.close()

def get_fixtures_by_round(season, round_val, league=None):
    """Get fixtures for a round, optionally filtered by league."""
    conn = get_connection()
    if not conn: return pd.DataFrame()
    try:
        if league:
            query = """
                SELECT id, home_team, away_team, status, date, home_score, away_score
                FROM fixtures WHERE season=%s AND "round"=%s AND league=%s ORDER BY date ASC
            """
            return pd.read_sql(query, conn, params=(season, round_val, league))
        else:
            query = """
                SELECT id, home_team, away_team, status, date, home_score, away_score
                FROM fixtures WHERE season=%s AND "round"=%s ORDER BY date ASC
            """
            return pd.read_sql(query, conn, params=(season, round_val))
    finally: conn.close()

def get_match_reality(fixture_id):
    conn = get_connection()
    if not conn: return None
    try:
        query = "SELECT score_home, score_away, luck_factor, narrative_summary, key_events FROM match_reality WHERE fixture_id = %s"
        cur = conn.cursor()
        cur.execute(query, (fixture_id,))
        row = cur.fetchone()
        if row:
            return {"score": f"{row[0]}-{row[1]}", "luck": row[2], "narrative": row[3], "events": row[4]}
        return None
    finally: conn.close()

def get_round_calendar(season, league=None):
    """Returns min/max dates per round for the season, optional league filter."""
    conn = get_connection()
    if not conn:
        return pd.DataFrame()
    if league:
        query = """
            SELECT "round", MIN(date) AS start_date, MAX(date) AS end_date
            FROM fixtures
            WHERE season = %s AND league = %s
            GROUP BY "round"
            ORDER BY "round" ASC
        """
        params = (season, league)
    else:
        query = """
            SELECT "round", MIN(date) AS start_date, MAX(date) AS end_date
            FROM fixtures
            WHERE season = %s
            GROUP BY "round"
            ORDER BY "round" ASC
        """
        params = (season,)
    df = pd.read_sql(query, conn, params=params)
    conn.close()
    return df


def get_analysis_cockpit_overview(season, league=None, prompt_version=None):
    """Return latest report + evaluation data for finished fixtures."""
    conn = get_connection()
    if not conn:
        return pd.DataFrame()
    try:
        query = """
            WITH latest_reports AS (
                SELECT DISTINCT ON (fixture_id)
                    id, fixture_id, headline, betting_recommendation,
                    confidence, predicted_score, full_json,
                    created_at, prompt_version, model_name
                FROM analysis_reports
                ORDER BY fixture_id, created_at DESC
            )
            SELECT f.id AS fixture_id, f.date, f.season, f.league, f."round" AS round,
                   f.home_team, f.away_team, f.status,
                   f.home_score, f.away_score,
                   lr.id AS report_id, lr.prompt_version, lr.model_name,
                   lr.confidence, lr.predicted_score, lr.betting_recommendation,
                   lr.headline, lr.full_json, lr.created_at,
                   ae.narrative_score, ae.score_accuracy, ae.tip_accuracy,
                   ae.narrative_feedback, ae.narrative_critical_flags,
                   mr.score_home AS actual_home, mr.score_away AS actual_away,
                   mr.narrative_summary, mr.luck_factor
            FROM fixtures f
            LEFT JOIN latest_reports lr ON lr.fixture_id = f.id
            LEFT JOIN analysis_evaluations ae ON lr.id = ae.report_id
            LEFT JOIN match_reality mr ON f.id = mr.fixture_id
            WHERE f.season = %s AND f.status = 'FINISHED'
        """
        params = [season]
        if league:
            query += " AND f.league = %s"
            params.append(league)
        if prompt_version:
            query += " AND lr.prompt_version = %s"
            params.append(prompt_version)
        query += " ORDER BY f.date ASC"
        df = pd.read_sql(query, conn, params=tuple(params))
        if 'date' in df.columns:
            df['date'] = pd.to_datetime(df['date'], utc=True, errors='coerce')
        return df
    finally:
        conn.close()


def get_prompt_cockpit_summary(season, league=None):
    """Aggregate performance metrics by prompt version."""
    conn = get_connection()
    if not conn:
        return pd.DataFrame()
    try:
        query = """
            SELECT ar.prompt_version,
                   COUNT(*) AS total_analyses,
                   AVG(ae.narrative_score) AS avg_narrative_score,
                   COUNT(CASE WHEN ae.score_accuracy = TRUE THEN 1 END)::float / NULLIF(COUNT(ae.score_accuracy), 0) * 100 AS score_accuracy_pct,
                   COUNT(CASE WHEN ae.tip_accuracy = TRUE THEN 1 END)::float / NULLIF(COUNT(ae.tip_accuracy), 0) * 100 AS tip_accuracy_pct,
                   AVG(ar.confidence) AS avg_confidence
            FROM analysis_reports ar
            JOIN fixtures f ON ar.fixture_id = f.id
            LEFT JOIN analysis_evaluations ae ON ar.id = ae.report_id
            WHERE f.season = %s AND f.status = 'FINISHED'
        """
        params = [season]
        if league:
            query += " AND f.league = %s"
            params.append(league)
        query += " GROUP BY ar.prompt_version ORDER BY avg_narrative_score DESC NULLS LAST"
        df = pd.read_sql(query, conn, params=tuple(params))
        return df
    finally:
        conn.close()


def get_round_trend_summary(season, league=None, prompt_version=None):
    """Aggregate metrics by round for trend tracking."""
    conn = get_connection()
    if not conn:
        return pd.DataFrame()
    try:
        query = """
            SELECT f."round" AS round,
                   COUNT(*) AS total_analyses,
                   AVG(ae.narrative_score) AS avg_narrative_score,
                   COUNT(CASE WHEN ae.score_accuracy = TRUE THEN 1 END)::float / NULLIF(COUNT(ae.score_accuracy), 0) * 100 AS score_accuracy_pct,
                   COUNT(CASE WHEN ae.tip_accuracy = TRUE THEN 1 END)::float / NULLIF(COUNT(ae.tip_accuracy), 0) * 100 AS tip_accuracy_pct,
                   AVG(ar.confidence) AS avg_confidence
            FROM analysis_reports ar
            JOIN fixtures f ON ar.fixture_id = f.id
            LEFT JOIN analysis_evaluations ae ON ar.id = ae.report_id
            WHERE f.season = %s AND f.status = 'FINISHED'
        """
        params = [season]
        if league:
            query += " AND f.league = %s"
            params.append(league)
        if prompt_version:
            query += " AND ar.prompt_version = %s"
            params.append(prompt_version)
        query += " GROUP BY f.\"round\" ORDER BY f.\"round\" ASC"
        df = pd.read_sql(query, conn, params=tuple(params))
        return df
    finally:
        conn.close()

def get_current_round(season):
    """Infer current round using fixture calendar versus now (UTC)."""
    cal = get_round_calendar(season)
    if cal.empty: return None
    cal['start_dt'] = pd.to_datetime(cal['start_date'], utc=True, errors='coerce')
    cal['end_dt'] = pd.to_datetime(cal['end_date'], utc=True, errors='coerce')
    now_utc = datetime.now(timezone.utc)
    # round happening now
    active = cal[(cal['start_dt'] <= now_utc) & (cal['end_dt'] >= now_utc)]
    if not active.empty:
        return int(active.iloc[0]['round'])
    # before season start -> first round
    if now_utc < cal['start_dt'].min():
        return int(cal.iloc[0]['round'])
    # after season end -> last round
    if now_utc > cal['end_dt'].max():
        return int(cal.iloc[-1]['round'])
    # fallback to closest next round
    future = cal[cal['start_dt'] > now_utc]
    if not future.empty:
        return int(future.iloc[0]['round'])
    return int(cal.iloc[-1]['round'])

def get_overview_reports(season, round_val):
    """Fetch fixtures in a round with latest analysis + reality."""
    conn = get_connection()
    if not conn: return pd.DataFrame()
    query = """
        WITH latest_reports AS (
            SELECT DISTINCT ON (fixture_id)
                id, fixture_id, headline, betting_recommendation, confidence,
                predicted_score, full_json, created_at, prompt_version, model_name
            FROM analysis_reports
            ORDER BY fixture_id, created_at DESC
        )
        SELECT f.id AS fixture_id, f.home_team, f.away_team, f.status, f.date,
               f.home_score, f.away_score, f."round", f.season,
               lr.id AS report_id, lr.headline, lr.betting_recommendation,
               lr.confidence, lr.predicted_score, lr.full_json, lr.created_at,
               lr.prompt_version, lr.model_name,
               mr.score_home, mr.score_away
        FROM fixtures f
        LEFT JOIN latest_reports lr ON lr.fixture_id = f.id
        LEFT JOIN match_reality mr ON mr.fixture_id = f.id
        WHERE f.season = %s AND f."round" = %s
        ORDER BY f.date ASC
    """
    df = pd.read_sql(query, conn, params=(season, round_val))
    conn.close()
    if 'date' in df.columns:
        df['date'] = pd.to_datetime(df['date'], utc=True, errors='coerce')
    return df

def get_audit_comparison():
    conn = get_connection()
    if not conn: return pd.DataFrame()
    query = """
        SELECT ar.fixture_id, f.home_team || ' vs ' || f.away_team as match,
            ar.predicted_score as "IA Pred", ar.confidence, ar.prompt_version,
            mr.score_home || '-' || mr.score_away as "Real Score",
            mr.luck_factor, mr.narrative_summary
        FROM analysis_reports ar
        JOIN match_reality mr ON ar.fixture_id = mr.fixture_id
        JOIN fixtures f ON ar.fixture_id = f.id
        ORDER BY f.date DESC
    """
    df = pd.read_sql(query, conn)
    conn.close()
    return df

def safe_json_load(value):
    if value is None: return {}
    if isinstance(value, dict): return value
    try:
        return json.loads(value)
    except Exception:
        return {}


def parse_scoreline(score_str):
    if not score_str or not isinstance(score_str, str):
        return None
    try:
        parts = score_str.split('-')
        if len(parts) != 2:
            return None
        home = int(parts[0].strip())
        away = int(parts[1].strip())
        return home, away
    except Exception:
        return None


def parse_predicted_outcome(score_str):
    parsed = parse_scoreline(score_str)
    if not parsed:
        return None
    home, away = parsed
    if home > away:
        return 'W'
    if home < away:
        return 'L'
    return 'D'

def build_plain_copy(analysis, home_team, away_team):
    """Builds a Telegram-ready text block from analysis data."""
    if not analysis:
        return "Sem análise disponível para este jogo."
    prediction = analysis.get('prediction', {})
    evidence = analysis.get('evidence_chain', {})
    logic = analysis.get('glass_box_logic', {})
    narrative = analysis.get('narrative', {})
    conf = prediction.get('confidence', 0)
    badge = "CLARITY PICK" if conf and conf >= 75 else "VALUE LEAN" if conf and conf >= 60 else "TRAP / SKIP"
    lines = [
        f"💡 {home_team} vs {away_team}",
        f"Badge: {badge}",
        f"Confiança: {conf}%",
        f"Aposta: {evidence.get('market_verdict', 'N/A')}",
        f"Score Previsto: {prediction.get('scoreline', 'N/A')}",
        "",
        "🧠 Lógica:",
        logic.get('reasoning', 'N/A'),
        "",
        "📖 Filme do Jogo:",
        narrative.get('game_flow', 'N/A'),
        "",
        f"⚠️ Risco: {analysis.get('risk_factors', ['N/A'])[0]}"
    ]
    return "\n".join(lines)

def render_game_selector(key_prefix):
    seasons = get_seasons()
    if not seasons:
        st.warning("⚠️ Sem dados na DB.")
        return None
    c1, c2, c3 = st.columns([1, 1, 2])
    with c1: sel_season = st.selectbox("Época", seasons, key=f"{key_prefix}_season")
    rounds = get_rounds(sel_season)
    with c2:
        if rounds: sel_round = st.selectbox("Ronda", rounds, key=f"{key_prefix}_round")
        else:
            st.info("Sem rondas."); return None
    with c3:
        fixtures_df = get_fixtures_by_round(sel_season, sel_round)
        if not fixtures_df.empty:
            def format_func(row):
                icon = "🏁" if row['status'] == 'FINISHED' else "📅"
                score = f"{row['home_score']}-{row['away_score']}" if row['status'] == 'FINISHED' else ""
                return f"{icon} {row['home_team']} vs {row['away_team']} {score}"
            fixture_map = {format_func(row): row['id'] for _, row in fixtures_df.iterrows()}
            sel_label = st.selectbox("Jogo", list(fixture_map.keys()), key=f"{key_prefix}_fix")
            return fixture_map[sel_label]
        else:
            st.warning("Sem jogos."); return None

# --- FUNÇÕES HELPER PARA AVALIAÇÃO E PERFORMANCE ---

def get_performance_metrics(season, prompt_version=None):
    """Get aggregated performance metrics for a season/prompt."""
    conn = get_connection()
    if not conn: return {}
    
    try:
        if prompt_version:
            query = """
                SELECT 
                    COUNT(*) as total_analyses,
                    AVG(ae.narrative_score) as avg_narrative_score,
                    COUNT(CASE WHEN ae.score_accuracy = TRUE THEN 1 END)::float / NULLIF(COUNT(ae.score_accuracy), 0) * 100 as score_accuracy_pct,
                    COUNT(CASE WHEN ae.tip_accuracy = TRUE THEN 1 END)::float / NULLIF(COUNT(ae.tip_accuracy), 0) * 100 as tip_accuracy_pct,
                    AVG(ar.confidence) as avg_confidence
                FROM analysis_reports ar
                JOIN fixtures f ON ar.fixture_id = f.id
                LEFT JOIN analysis_evaluations ae ON ar.id = ae.report_id
                WHERE f.season = %s AND ar.prompt_version = %s
                  AND f.status = 'FINISHED'
            """
            params = (season, prompt_version)
        else:
            query = """
                SELECT 
                    ar.prompt_version,
                    COUNT(*) as total_analyses,
                    AVG(ae.narrative_score) as avg_narrative_score,
                    COUNT(CASE WHEN ae.score_accuracy = TRUE THEN 1 END)::float / NULLIF(COUNT(ae.score_accuracy), 0) * 100 as score_accuracy_pct,
                    COUNT(CASE WHEN ae.tip_accuracy = TRUE THEN 1 END)::float / NULLIF(COUNT(ae.tip_accuracy), 0) * 100 as tip_accuracy_pct,
                    AVG(ar.confidence) as avg_confidence
                FROM analysis_reports ar
                JOIN fixtures f ON ar.fixture_id = f.id
                LEFT JOIN analysis_evaluations ae ON ar.id = ae.report_id
                WHERE f.season = %s AND f.status = 'FINISHED'
                GROUP BY ar.prompt_version
            """
            params = (season,)
        
        df = pd.read_sql(query, conn, params=params)
        return df.to_dict('records') if not df.empty else []
    except Exception as e:
        st.error(f"Erro ao buscar métricas: {e}")
        return []
    finally:
        conn.close()

def get_evaluation_comparison(fixture_id):
    """Get evaluation comparisons between prompts for a fixture."""
    conn = get_connection()
    if not conn: return pd.DataFrame()
    
    try:
        query = """
            SELECT 
                ar.prompt_version,
                ar.confidence,
                ar.predicted_score,
                ar.betting_recommendation,
                ae.narrative_score,
                ae.score_accuracy,
                ae.tip_accuracy,
                ae.narrative_feedback,
                ae.narrative_critical_flags,
                ae.score_explanation,
                ae.tip_explanation
            FROM analysis_reports ar
            LEFT JOIN analysis_evaluations ae ON ar.id = ae.report_id
            WHERE ar.fixture_id = %s
            ORDER BY ar.prompt_version
        """
        df = pd.read_sql(query, conn, params=(fixture_id,))
        return df
    except Exception as e:
        st.error(f"Erro ao buscar comparação: {e}")
        return pd.DataFrame()
    finally:
        conn.close()

def get_round_evaluations(round_id, prompt_version=None, season="2025-2026"):
    """Get all evaluations for a round."""
    conn = get_connection()
    if not conn: return pd.DataFrame()
    
    try:
        if prompt_version:
            query = """
                SELECT 
                    f.home_team, f.away_team, f.date,
                    ar.predicted_score, ar.confidence, ar.betting_recommendation,
                    ae.narrative_score, ae.score_accuracy, ae.tip_accuracy,
                    ae.narrative_feedback, ae.narrative_critical_flags,
                    mr.score_home || '-' || mr.score_away as actual_score
                FROM analysis_reports ar
                JOIN fixtures f ON ar.fixture_id = f.id
                LEFT JOIN analysis_evaluations ae ON ar.id = ae.report_id
                LEFT JOIN match_reality mr ON f.id = mr.fixture_id
                WHERE f.season = %s AND f.round = %s 
                  AND ar.prompt_version = %s
                  AND f.status = 'FINISHED'
                ORDER BY f.date ASC
            """
            params = (season, round_id, prompt_version)
        else:
            query = """
                SELECT 
                    ar.prompt_version,
                    f.home_team, f.away_team, f.date,
                    ar.predicted_score, ar.confidence, ar.betting_recommendation,
                    ae.narrative_score, ae.score_accuracy, ae.tip_accuracy,
                    ae.narrative_feedback, ae.narrative_critical_flags,
                    mr.score_home || '-' || mr.score_away as actual_score
                FROM analysis_reports ar
                JOIN fixtures f ON ar.fixture_id = f.id
                LEFT JOIN analysis_evaluations ae ON ar.id = ae.report_id
                LEFT JOIN match_reality mr ON f.id = mr.fixture_id
                WHERE f.season = %s AND f.round = %s 
                  AND f.status = 'FINISHED'
                ORDER BY f.date ASC, ar.prompt_version
            """
            params = (season, round_id)
        
        df = pd.read_sql(query, conn, params=params)
        return df
    except Exception as e:
        st.error(f"Erro ao buscar avaliações: {e}")
        return pd.DataFrame()
    finally:
        conn.close()

def render_performance_dashboard(metrics_list):
    """Render performance metrics dashboard."""
    if not metrics_list:
        st.info("Sem métricas disponíveis.")
        return
    
    if isinstance(metrics_list, list) and len(metrics_list) > 0:
        # Multiple prompts
        df = pd.DataFrame(metrics_list)
        st.dataframe(df, width="stretch")
        
        if 'avg_narrative_score' in df.columns:
            st.bar_chart(df.set_index('prompt_version')[['avg_narrative_score']])
        
        cols = st.columns(len(df))
        for idx, row in df.iterrows():
            with cols[idx]:
                st.metric("Narrative Score", f"{row.get('avg_narrative_score', 0):.1f}" if pd.notna(row.get('avg_narrative_score')) else "N/A")
                st.metric("Score Accuracy", f"{row.get('score_accuracy_pct', 0):.1f}%" if pd.notna(row.get('score_accuracy_pct')) else "N/A")
                st.metric("Tip Accuracy", f"{row.get('tip_accuracy_pct', 0):.1f}%" if pd.notna(row.get('tip_accuracy_pct')) else "N/A")
    else:
        # Single prompt
        metrics = metrics_list[0] if isinstance(metrics_list, list) else metrics_list
        col1, col2, col3, col4 = st.columns(4)
        with col1:
            st.metric("Total Analyses", metrics.get('total_analyses', 0))
        with col2:
            st.metric("Avg Narrative Score", f"{metrics.get('avg_narrative_score', 0):.1f}" if pd.notna(metrics.get('avg_narrative_score')) else "N/A")
        with col3:
            st.metric("Score Accuracy", f"{metrics.get('score_accuracy_pct', 0):.1f}%" if pd.notna(metrics.get('score_accuracy_pct')) else "N/A")
        with col4:
            st.metric("Tip Accuracy", f"{metrics.get('tip_accuracy_pct', 0):.1f}%" if pd.notna(metrics.get('tip_accuracy_pct')) else "N/A")

def render_evaluation_detail(evaluation_data):
    """Render detailed evaluation view."""
    if evaluation_data is None:
        st.info("Sem dados de avaliação.")
        return
    if isinstance(evaluation_data, (pd.DataFrame, pd.Series)) and evaluation_data.empty:
        st.info("Sem dados de avaliação.")
        return
    if isinstance(evaluation_data, dict) and len(evaluation_data) == 0:
        st.info("Sem dados de avaliação.")
        return

    def normalize_flags(raw_flags):
        """Return a list of flags from varied inputs (str/list/Series/etc)."""
        if raw_flags is None:
            return []
        if isinstance(raw_flags, float) and pd.isna(raw_flags):
            return []
        if isinstance(raw_flags, str):
            try:
                parsed = json.loads(raw_flags)
                if isinstance(parsed, list):
                    return parsed
                return [parsed]
            except Exception:
                return [raw_flags]
        if isinstance(raw_flags, (list, tuple, set)):
            return [f for f in raw_flags if f]
        if hasattr(raw_flags, "tolist"):
            return [f for f in raw_flags.tolist() if f and not (isinstance(f, float) and pd.isna(f))]
        return [raw_flags]
    
    eval_json = safe_json_load(evaluation_data.get('evaluation_json')) if isinstance(evaluation_data, dict) else {}
    narrative_quality = eval_json.get('narrative_quality', {})
    score_pred = eval_json.get('score_prediction', {})
    betting_tip = eval_json.get('betting_tip', {})
    
    col1, col2 = st.columns(2)
    with col1:
        st.markdown("### 📖 Narrative Quality")
        st.metric("Score", f"{narrative_quality.get('score', evaluation_data.get('narrative_score', 'N/A'))}")
        st.write("**Feedback:**")
        st.write(narrative_quality.get('feedback', evaluation_data.get('narrative_feedback', 'N/A')))
        
        flags = normalize_flags(narrative_quality.get('critical_flags', []))
        extra_flags = None
        if isinstance(evaluation_data, dict):
            extra_flags = evaluation_data.get('narrative_critical_flags')
        elif hasattr(evaluation_data, "get"):
            extra_flags = evaluation_data.get('narrative_critical_flags', None)
        if extra_flags is not None:
            flags = normalize_flags(extra_flags)
        
        if flags and len(flags) > 0:
            st.write("**Critical Flags:**")
            for flag in flags:
                st.write(f"- {flag}")
    
    with col2:
        st.markdown("### 🎯 Predictions")
        st.write("**Score Prediction:**")
        score_acc = score_pred.get('accuracy', evaluation_data.get('score_accuracy'))
        st.write(f"Accuracy: {'✅' if score_acc else '❌'}")
        st.write(score_pred.get('explanation', evaluation_data.get('score_explanation', 'N/A')))
        
        st.write("**Betting Tip:**")
        tip_acc = betting_tip.get('accuracy', evaluation_data.get('tip_accuracy'))
        st.write(f"Accuracy: {'✅' if tip_acc else '❌'}")
        st.write(betting_tip.get('explanation', evaluation_data.get('tip_explanation', 'N/A')))

def render_critical_flags_table(flags_list):
    """Render table of critical flags."""
    if not flags_list:
        st.info("Sem flags críticas.")
        return
    
    # Aggregate flags
    flag_counts = {}
    for flags in flags_list:
        if flags:
            flags_parsed = json.loads(flags) if isinstance(flags, str) else flags
            if isinstance(flags_parsed, list):
                for flag in flags_parsed:
                    flag_counts[flag] = flag_counts.get(flag, 0) + 1
    
    if flag_counts:
        df_flags = pd.DataFrame(list(flag_counts.items()), columns=['Flag', 'Count'])
        df_flags = df_flags.sort_values('Count', ascending=False)
        st.dataframe(df_flags, width="stretch")

# --- INTERFACE ---
# --- INTERFACE ---
st.title("🧠 Clarity Engine: Ops Dashboard v2.0")

with st.sidebar:
    st.header("🧠 Clarity Engine")
    st.caption("Dashboard v2.0")

    st.divider()
    st.header("Modo de Operação")
    mode = st.radio("", [
        "🧭 COCKPIT",
        "🎯 VALIDATE",
        "⚙️ OPERATE",
        "📊 MONITOR"
    ], label_visibility="collapsed")

    st.divider()

    # League selector (global filter)
    st.header("Filtros Globais")
    available_leagues = get_leagues()
    if 'selected_league' not in st.session_state:
        st.session_state['selected_league'] = available_leagues[0] if available_leagues else "Premier League"
    selected_league = st.selectbox("Liga", available_leagues,
                                    index=available_leagues.index(st.session_state['selected_league'])
                                    if st.session_state['selected_league'] in available_leagues else 0,
                                    key="global_league")
    st.session_state['selected_league'] = selected_league

    st.divider()
    st.caption(f"System Root: {project_root}")

# ========================================
# MODO 0: 🧭 COCKPIT - Analyst View
# ========================================
if mode == "🧭 COCKPIT":
    st.title("🧭 Clarity Analyst Cockpit")
    st.caption("Visao rapida de qualidade, tendencias e alinhamento pre/post jogo")

    seasons = get_seasons()
    prompt_versions = get_prompt_versions()

    if not seasons:
        st.info("Sem dados na DB.")
    else:
        c1, c2, c3 = st.columns([1, 1, 1])
        with c1:
            sel_season = st.selectbox("Epoca", seasons, key="cockpit_season")
        with c2:
            sel_prompt = st.selectbox("Prompt", ["All"] + prompt_versions, key="cockpit_prompt")
        with c3:
            rounds = get_rounds(sel_season, st.session_state.get('selected_league'))
            sel_round = st.selectbox("Ronda", ["All"] + rounds, key="cockpit_round")

        prompt_filter = None if sel_prompt == "All" else sel_prompt
        round_filter = None if sel_round == "All" else sel_round

        overview_df = get_analysis_cockpit_overview(
            sel_season,
            league=st.session_state.get('selected_league'),
            prompt_version=prompt_filter
        )

        if round_filter is not None and not overview_df.empty:
            overview_df = overview_df[overview_df['round'] == round_filter]

        summary_df = get_prompt_cockpit_summary(sel_season, league=st.session_state.get('selected_league'))
        trend_df = get_round_trend_summary(
            sel_season,
            league=st.session_state.get('selected_league'),
            prompt_version=prompt_filter
        )

        st.markdown("""<div class="cockpit-panel">
        <span class="kpi-label">Quality Snapshot</span>
        """, unsafe_allow_html=True)

        kpi_cols = st.columns(4)
        total_analyses = int(overview_df['report_id'].notna().sum()) if not overview_df.empty else 0
        avg_narrative = overview_df['narrative_score'].mean() if not overview_df.empty else None
        score_accuracy_pct = (overview_df['score_accuracy'].dropna().mean() * 100) if not overview_df.empty else None
        tip_accuracy_pct = (overview_df['tip_accuracy'].dropna().mean() * 100) if not overview_df.empty else None

        with kpi_cols[0]:
            st.markdown("<div class=\"kpi-label\">Total Analyses</div>", unsafe_allow_html=True)
            st.markdown(f"<div class=\"kpi-value\">{total_analyses}</div>", unsafe_allow_html=True)
        with kpi_cols[1]:
            st.markdown("<div class=\"kpi-label\">Narrative Score</div>", unsafe_allow_html=True)
            st.markdown(f"<div class=\"kpi-value\">{avg_narrative:.1f}</div>" if avg_narrative is not None else "<div class=\"kpi-value\">--</div>", unsafe_allow_html=True)
        with kpi_cols[2]:
            st.markdown("<div class=\"kpi-label\">Score Accuracy</div>", unsafe_allow_html=True)
            st.markdown(f"<div class=\"kpi-value\">{score_accuracy_pct:.1f}%</div>" if score_accuracy_pct is not None else "<div class=\"kpi-value\">--</div>", unsafe_allow_html=True)
        with kpi_cols[3]:
            st.markdown("<div class=\"kpi-label\">Betting Tip Accuracy</div>", unsafe_allow_html=True)
            st.markdown(f"<div class=\"kpi-value\">{tip_accuracy_pct:.1f}%</div>" if tip_accuracy_pct is not None else "<div class=\"kpi-value\">--</div>", unsafe_allow_html=True)

        st.markdown("</div>", unsafe_allow_html=True)

        st.write("")
        col_left, col_right = st.columns([1.1, 1])

        with col_left:
            st.markdown("""<div class="cockpit-panel">
            <span class="kpi-label">Prompt Leaderboard</span>
            """, unsafe_allow_html=True)
            if summary_df is None or summary_df.empty:
                st.info("Sem dados de comparacao de prompts.")
            else:
                st.dataframe(summary_df, width="stretch")
            st.markdown("</div>", unsafe_allow_html=True)

        with col_right:
            st.markdown("""<div class="cockpit-panel">
            <span class="kpi-label">Trendline por Ronda</span>
            """, unsafe_allow_html=True)
            if trend_df is None or trend_df.empty:
                st.info("Sem dados de tendencia.")
            else:
                chart_df = trend_df.set_index('round')[['avg_narrative_score', 'score_accuracy_pct', 'tip_accuracy_pct']]
                st.line_chart(chart_df)
            st.markdown("</div>", unsafe_allow_html=True)

        st.write("")
        st.markdown("""<div class="cockpit-panel">
        <span class="kpi-label">Match Drilldown</span>
        """, unsafe_allow_html=True)

        if overview_df.empty:
            st.info("Sem analises finalizadas para esta selecao.")
        else:
            overview_df = overview_df.copy()
            overview_df['match_label'] = overview_df['home_team'] + " vs " + overview_df['away_team']
            overview_df['actual_score'] = overview_df.apply(
                lambda row: f"{int(row['actual_home'])}-{int(row['actual_away'])}" if pd.notna(row['actual_home']) and pd.notna(row['actual_away']) else "--",
                axis=1
            )
            overview_df['predicted_score'] = overview_df['predicted_score'].fillna("--")
            overview_df['narrative_score'] = overview_df['narrative_score'].fillna(0)

            if 'predicted_outcome' not in overview_df.columns:
                overview_df['predicted_outcome'] = overview_df['predicted_score'].apply(parse_predicted_outcome)

            def actual_outcome(row):
                if pd.isna(row['actual_home']) or pd.isna(row['actual_away']):
                    return None
                return 'W' if row['actual_home'] > row['actual_away'] else ('L' if row['actual_home'] < row['actual_away'] else 'D')

            overview_df['actual_outcome'] = overview_df.apply(actual_outcome, axis=1)

            table_df = overview_df[[
                'match_label', 'round', 'prompt_version', 'confidence',
                'predicted_score', 'actual_score', 'narrative_score',
                'score_accuracy', 'tip_accuracy'
            ]].sort_values('round', ascending=False)

            st.dataframe(table_df, width="stretch")

            match_ids = overview_df['fixture_id'].tolist()
            selected_fixture = st.selectbox(
                "Selecionar jogo",
                match_ids,
                format_func=lambda x: overview_df.loc[overview_df['fixture_id'] == x, 'match_label'].iloc[0]
            )

            selected_row = overview_df[overview_df['fixture_id'] == selected_fixture].iloc[0]
            analysis_data = safe_json_load(selected_row.get('full_json'))

            d1, d2 = st.columns([1, 1])
            with d1:
                st.markdown("### Pre-Game Narrative")
                if analysis_data:
                    st.markdown(render_telegram_preview(analysis_data), unsafe_allow_html=True)
                else:
                    st.info("Sem analise armazenada.")
            with d2:
                st.markdown("### Post-Game Reality")
                st.write(selected_row.get('narrative_summary') or "Sem resumo de realidade.")
                st.write(f"**Score Real:** {selected_row.get('actual_score') or '--'}")
                st.write(f"**Luck Factor:** {selected_row.get('luck_factor') or '--'}")

        st.markdown("</div>", unsafe_allow_html=True)

# ========================================
# MODO 1: 🎯 VALIDATE - Validação de Sistema
# ========================================
elif mode == "🎯 VALIDATE":
    st.title("🎯 VALIDATE - Sistema de Validação")
    st.caption("Validar qualidade das análises e identificar erros")

    tab0, tab1, tab2, tab3 = st.tabs([
        "📊 Data Generation",
        "📖 Narrative Validation",
        "🔬 Prompt Comparison",
        "🔍 Individual Analysis"
    ])

    # TAB 0: DATA GENERATION
    with tab0:
        st.markdown("### 📊 Geração de Dados de Validação")
        st.info("⚠️ Este passo é necessário para gerar os dados que permitem validar as análises.")

        # Check current data status
        conn = get_connection()
        if conn:
            try:
                # Count finished matches with analyses
                cur = conn.cursor()
                cur.execute("""
                    SELECT COUNT(DISTINCT f.id)
                    FROM fixtures f
                    JOIN analysis_reports ar ON f.id = ar.fixture_id
                    WHERE f.status = 'FINISHED'
                """)
                finished_with_analyses = cur.fetchone()[0]

                # Count match_reality entries
                cur.execute("SELECT COUNT(*) FROM match_reality")
                reality_count = cur.fetchone()[0]

                # Count evaluations
                cur.execute("SELECT COUNT(*) FROM analysis_evaluations")
                eval_count = cur.fetchone()[0]

                conn.close()

                # Display status
                col1, col2, col3 = st.columns(3)
                with col1:
                    st.metric("✅ Jogos Finalizados (c/ Análise)", finished_with_analyses)
                with col2:
                    status_icon = "✅" if reality_count > 0 else "❌"
                    st.metric(f"{status_icon} Match Reality Data", reality_count)
                with col3:
                    status_icon = "✅" if eval_count > 0 else "❌"
                    st.metric(f"{status_icon} Evaluations", eval_count)

                st.divider()

                # STEP 1: Generate Reality Data
                st.markdown("### Step 1: Generate Reality Data")
                st.caption("Gera ground truth pós-jogo usando Gemini + Google Search")

                col_r1, col_r2 = st.columns(2)
                with col_r1:
                    seasons = get_seasons()
                    reality_season = st.selectbox("Época", seasons, key="reality_season") if seasons else None
                with col_r2:
                    reality_limit = st.selectbox("Limit", ["All", "10", "50"], key="reality_limit")

                limit_val = None if reality_limit == "All" else int(reality_limit)
                needs_reality = finished_with_analyses - reality_count

                if needs_reality > 0:
                    st.warning(f"⚠️ {needs_reality} jogos precisam de reality data. Estimate: ~{needs_reality * 12}s (~{needs_reality * 12 // 60}min)")
                else:
                    st.success("✅ Todos os jogos finalizados já têm reality data!")

                if st.button("🚀 Generate Reality Data", type="primary", key="gen_reality", disabled=needs_reality==0):
                    runner = BatchRunner()
                    progress_bar = st.progress(0)
                    status_text = st.empty()

                    def progress_callback(current, total, fixture_id):
                        progress = current / total if total > 0 else 1.0
                        progress_bar.progress(progress)
                        status_text.text(f"Generating reality for fixture {fixture_id}... ({current}/{total})")

                    try:
                        result = runner.generate_reality_for_finished_matches(
                            season=reality_season,
                            limit=limit_val,
                            progress_callback=progress_callback
                        )
                        progress_bar.progress(1.0)
                        status_text.text("✅ Concluído!")
                        st.success(f"Reality data gerada: {result['success']} sucesso, {result['failed']} falhas, {result['skipped']} skipped")
                        st.rerun()
                    except Exception as e:
                        st.error(f"Erro: {e}")
                        import traceback
                        st.code(traceback.format_exc())

                st.divider()

                # STEP 2: Generate Evaluations
                st.markdown("### Step 2: Generate Evaluations")
                st.caption("Avalia análises comparando predição vs realidade usando GPT")

                col_e1, col_e2, col_e3 = st.columns(3)
                with col_e1:
                    eval_season = st.selectbox("Época", seasons, key="eval_season") if seasons else None
                with col_e2:
                    eval_prompt = st.selectbox("Prompt", ["All"] + list(PROMPTS.keys()), key="eval_prompt")
                with col_e3:
                    eval_limit = st.selectbox("Limit", ["All", "10", "50"], key="eval_limit")

                eval_limit_val = None if eval_limit == "All" else int(eval_limit)
                eval_prompt_val = None if eval_prompt == "All" else eval_prompt
                needs_eval = reality_count - eval_count

                if reality_count == 0:
                    st.warning("⚠️ Primeiro precisa gerar reality data (Step 1)")
                elif needs_eval > 0:
                    st.warning(f"⚠️ {needs_eval} análises precisam de evaluation. Estimate: ~{needs_eval * 8}s (~{needs_eval * 8 // 60}min)")
                else:
                    st.success("✅ Todas as análises com reality data já têm evaluations!")

                if st.button("🔍 Evaluate Analyses", type="primary", key="gen_eval", disabled=reality_count==0 or needs_eval==0):
                    runner = BatchRunner()
                    progress_bar_eval = st.progress(0)
                    status_text_eval = st.empty()

                    def progress_callback_eval(current, total, report_id):
                        progress = current / total if total > 0 else 1.0
                        progress_bar_eval.progress(progress)
                        status_text_eval.text(f"Evaluating report {report_id}... ({current}/{total})")

                    try:
                        result = runner.evaluate_analyses_batch(
                            season=eval_season,
                            prompt_version=eval_prompt_val,
                            limit=eval_limit_val,
                            progress_callback=progress_callback_eval
                        )
                        progress_bar_eval.progress(1.0)
                        status_text_eval.text("✅ Concluído!")
                        st.success(f"Evaluations geradas: {result['success']} sucesso, {result['failed']} falhas, {result['skipped']} skipped")
                        st.rerun()
                    except Exception as e:
                        st.error(f"Erro: {e}")
                        import traceback
                        st.code(traceback.format_exc())

            except Exception as e:
                st.error(f"Erro ao verificar status: {e}")
                if conn:
                    conn.close()

    # TAB 1: NARRATIVE VALIDATION
    with tab1:
        st.markdown("### 📖 Validação de Qualidade Narrativa")
        st.caption("Análise da qualidade das narrativas táticas (SEM métricas de betting)")

        # Filters
        col_f1, col_f2, col_f3 = st.columns(3)
        with col_f1:
            seasons = get_seasons()
            val_season = st.selectbox("Época", seasons, key="val_season") if seasons else "2025-2026"
        with col_f2:
            val_prompt = st.selectbox("Prompt", ["All"] + list(PROMPTS.keys()), key="val_prompt")
        with col_f3:
            st.write("")  # Spacing
            if st.button("🔄 Run Validation", type="primary", key="run_validation"):
                st.session_state['validation_run'] = True

        st.divider()

        # Run validation if button clicked or already run
        if st.session_state.get('validation_run', False):
            prompt_val = None if val_prompt == "All" else val_prompt

            with st.spinner("A processar validação..."):
                report = run_validation(season=val_season, prompt_version=prompt_val)

            if 'error' in report:
                st.error(f"❌ {report['error']}")
                st.info("💡 Precisa gerar evaluation data primeiro! (Tab: Data Generation)")
            else:
                narrative = report['narrative_quality']
                accuracy = report['accuracy']
                phase1 = report['phase1_success']

                # Phase 1 Success Banner
                st.markdown(f"### {phase1['status']}")
                st.metric("🎯 Phase 1 Goal", phase1['target'], delta=phase1['current'])

                if not phase1['achieved']:
                    st.warning(f"⚠️ Gap: {phase1['gap']:.1f}% to reach target")
                else:
                    st.success("🎉 Phase 1 goal achieved! Ready for Phase 2 (odds/betting)")

                st.divider()

                # Metrics Cards
                col1, col2, col3, col4 = st.columns(4)
                with col1:
                    st.metric("Avg Narrative Score", f"{narrative['avg_score']:.1f}/100")
                with col2:
                    st.metric("Excellent Rate (>80)", f"{narrative['excellent_rate']:.1f}%")
                with col3:
                    st.metric("Outcome Accuracy", f"{accuracy['outcome_correct_pct']:.1f}%")
                with col4:
                    st.metric("Total Analyses", narrative['total_analyses'])

                st.divider()

                # Score Distribution
                st.markdown("### 📊 Narrative Score Distribution")
                if narrative['score_distribution']:
                    dist_df = pd.DataFrame(
                        list(narrative['score_distribution'].items()),
                        columns=['Score Range', 'Count']
                    )
                    st.bar_chart(dist_df.set_index('Score Range'))

                st.divider()

                # Best/Worst Analyses
                col_best, col_worst = st.columns(2)

                with col_best:
                    st.markdown("### ✅ Best Analyses (Top 5)")
                    if report['best_analyses']:
                        best_df = pd.DataFrame(report['best_analyses'])
                        st.dataframe(
                            best_df[['home_team', 'away_team', 'narrative_score', 'confidence', 'score_accuracy']],
                            hide_index=True,
                            width="stretch"
                        )
                    else:
                        st.info("Sem dados")

                with col_worst:
                    st.markdown("### ❌ Worst Analyses (Bottom 5)")
                    if report['worst_analyses']:
                        worst_df = pd.DataFrame(report['worst_analyses'])
                        st.dataframe(
                            worst_df[['home_team', 'away_team', 'narrative_score', 'confidence', 'score_accuracy']],
                            hide_index=True,
                            width="stretch"
                        )
                    else:
                        st.info("Sem dados")

                st.divider()

                # Error Patterns
                st.markdown("### 🚨 Error Patterns")
                error_patterns = report['error_patterns']

                if error_patterns['top_flags']:
                    st.markdown("#### Top Critical Flags")
                    flags_df = pd.DataFrame(error_patterns['top_flags'])
                    st.dataframe(flags_df, hide_index=True, width="stretch")

                col_e1, col_e2 = st.columns(2)
                with col_e1:
                    st.metric("Poor Analyses (<50)", error_patterns['poor_analyses_count'])
                with col_e2:
                    st.metric("Overconfident Failures", error_patterns['common_mistakes']['overconfident_failures'])

    # TAB 2: PROMPT COMPARISON
    with tab2:
        st.markdown("### 🔬 Comparação de Prompts")
        st.caption("Comparar qualidade narrativa entre diferentes versões de prompts")

        # Filters
        col_c1, col_c2 = st.columns(2)
        with col_c1:
            seasons = get_seasons()
            comp_season = st.selectbox("Época", seasons, key="comp_season") if seasons else "2025-2026"
        with col_c2:
            st.write("")  # Spacing
            if st.button("🔄 Compare Prompts", type="primary", key="run_comparison"):
                st.session_state['comparison_run'] = True

        st.divider()

        # Run comparison
        if st.session_state.get('comparison_run', False):
            with st.spinner("A comparar prompts..."):
                comparison_df = compare_all_prompts(season=comp_season)

            if comparison_df.empty:
                st.error("❌ Sem dados de comparação disponíveis")
                st.info("💡 Precisa gerar evaluations primeiro! (Tab: Data Generation)")
            else:
                # Highlight best prompt
                best_prompt = comparison_df.loc[comparison_df['avg_narrative_score'].idxmax(), 'prompt_version']
                st.success(f"🏆 Best Prompt: **{best_prompt}** (Highest Avg Narrative Score)")

                st.divider()

                # Comparison Table
                st.markdown("### 📊 Side-by-Side Comparison")
                st.dataframe(
                    comparison_df[[
                        'prompt_version', 'total_analyses', 'avg_narrative_score',
                        'excellent_rate', 'good_rate', 'outcome_correct_pct'
                    ]],
                    hide_index=True,
                    width="stretch"
                )

                st.divider()

                # Visual Comparison
                st.markdown("### 📈 Visual Comparison")

                # Bar chart: Narrative Score
                st.markdown("#### Avg Narrative Score by Prompt")
                st.bar_chart(comparison_df.set_index('prompt_version')[['avg_narrative_score']])

                # Bar chart: Accuracy Metrics
                st.markdown("#### Accuracy Metrics by Prompt")
                accuracy_cols = ['outcome_correct_pct', 'exact_score_pct', 'tip_accuracy_pct']
                st.bar_chart(comparison_df.set_index('prompt_version')[accuracy_cols])

                st.divider()

                # Detailed Breakdown
                st.markdown("### 🔍 Detailed Breakdown")
                for _, row in comparison_df.iterrows():
                    with st.expander(f"📋 {row['prompt_version']} - {row['total_analyses']} analyses"):
                        col1, col2, col3 = st.columns(3)
                        with col1:
                            st.metric("Avg Score", f"{row['avg_narrative_score']:.1f}")
                            st.metric("Excellent Rate", f"{row['excellent_rate']:.1f}%")
                        with col2:
                            st.metric("Outcome Accuracy", f"{row['outcome_correct_pct']:.1f}%")
                            st.metric("Score Accuracy", f"{row['exact_score_pct']:.1f}%")
                        with col3:
                            st.metric("Tip Accuracy", f"{row['tip_accuracy_pct']:.1f}%")
                            st.metric("Avg Confidence", f"{row['avg_confidence']:.1f}%")

    # TAB 3: INDIVIDUAL ANALYSIS
    with tab3:
        st.markdown("### 🔍 Análise Individual Detalhada")
        selected_fixture_id = render_game_selector("individual_analysis")

        if selected_fixture_id:
            st.divider()
            df_comp = get_evaluation_comparison(selected_fixture_id)

            if not df_comp.empty:
                st.dataframe(df_comp, width="stretch")

                # Show detailed evaluation for each prompt
                for _, row in df_comp.iterrows():
                    with st.expander(f"Detalhe: {row.get('prompt_version', 'N/A')}"):
                        render_evaluation_detail(row)
            else:
                st.info("Sem avaliações disponíveis para este jogo.")

# ========================================
# MODO 2: ⚙️ OPERATE - Operações
# ========================================
elif mode == "⚙️ OPERATE":
    st.title("⚙️ OPERATE - Operações")
    st.caption("Gerar e visualizar análises")

    tab1, tab2 = st.tabs(["🚀 Generate Analyses", "📊 View & Preview"])

    # TAB 1: GENERATE ANALYSES (old Batch Runner)
    with tab1:
        st.markdown("### 🚀 Geração de Análises em Batch")

        seasons = get_seasons()
        if not seasons:
            st.info("Sem dados na DB.")
        else:
            col1, col2 = st.columns(2)
            with col1:
                sel_season = st.selectbox("Época", seasons, key="batch_season")
                rounds = get_rounds(sel_season)
                if rounds:
                    sel_round = st.selectbox("Ronda", rounds, key="batch_round")
                else:
                    st.warning("Sem rondas.")
                    sel_round = None

            with col2:
                st.markdown("### Prompts")
                available_prompts = list(PROMPTS.keys())
                selected_prompts = st.multiselect(
                    "Selecionar prompts para gerar",
                    available_prompts,
                    default=["hybrid", "v3"] if "hybrid" in available_prompts and "v3" in available_prompts else available_prompts[:2],
                    key="batch_prompts"
                )

                force_refresh = st.checkbox("Forçar recálculo ($$$)", False, key="batch_force")

            if sel_round and selected_prompts:
                st.divider()
                st.warning(f"⚠️ Isto vai gerar análises para {len(selected_prompts)} prompt(s) na Ronda {sel_round}. Pode ser caro!")

                if st.button("🚀 Gerar Análises", type="primary", key="batch_run"):
                    runner = BatchRunner()
                    progress_bar = st.progress(0)
                    status_text = st.empty()

                    def progress_callback(current, total, fixture_id, prompt_version):
                        progress = current / total
                        progress_bar.progress(progress)
                        status_text.text(f"Processando {current}/{total}: {fixture_id} ({prompt_version})")

                    try:
                        runner.run_round_predictions_for_prompts(
                            sel_round,
                            selected_prompts,
                            season=sel_season,
                            progress_callback=progress_callback
                        )
                        progress_bar.progress(1.0)
                        status_text.text("✅ Concluído!")
                        st.success(f"Análises geradas para Ronda {sel_round}")
                        st.rerun()
                    except Exception as e:
                        st.error(f"Erro: {e}")
                        import traceback
                        st.code(traceback.format_exc())

    # TAB 2: VIEW & PREVIEW
    with tab2:
        st.markdown("### 📊 Visualizar Análises")

        seasons = get_seasons()
        if not seasons:
            st.info("Sem dados na DB.")
        else:
            sel_season = st.selectbox("Época", seasons, key="view_season")
            rounds = get_rounds(sel_season)

            if not rounds:
                st.warning("Sem rondas.")
            else:
                def_round = get_current_round(sel_season) or rounds[0]
                round_idx = rounds.index(def_round) if def_round in rounds else 0
                sel_round = st.selectbox("Ronda", rounds, index=round_idx, key="view_round")

                df_round = get_overview_reports(sel_season, sel_round)
                if df_round.empty:
                    st.info("Sem jogos nesta ronda.")
                else:
                    now_utc = datetime.now(timezone.utc)
                    display_rows = []
                    label_map = {}

                    for _, r in df_round.iterrows():
                        match_label = f"{r['home_team']} vs {r['away_team']}"
                        label_map[r['fixture_id']] = match_label

                        dt = r['date']
                        dt_str = dt.strftime("%Y-%m-%d %H:%M") if pd.notna(dt) else "N/A"

                        finished = r['status'] == 'FINISHED' or (pd.notna(r.get('score_home')) and pd.notna(r.get('score_away')))
                        if finished:
                            status_badge = "🏁 Final"
                        elif pd.notna(dt) and dt > now_utc:
                            status_badge = "⏳ Por jogar"
                        else:
                            status_badge = "⏱ Em curso"

                        conf_raw = r.get('confidence')
                        conf_val = int(conf_raw) if pd.notna(conf_raw) else None
                        if conf_val is None:
                            conf_display = "⚪ —"
                        elif conf_val >= 70:
                            conf_display = f"🟢 {conf_val}%"
                        elif conf_val >= 60:
                            conf_display = f"🟡 {conf_val}%"
                        else:
                            conf_display = f"🔴 {conf_val}%"

                        real_score = None
                        if pd.notna(r.get('score_home')) and pd.notna(r.get('score_away')):
                            real_score = f"{int(r['score_home'])}-{int(r['score_away'])}"
                        elif pd.notna(r.get('home_score')) and pd.notna(r.get('away_score')):
                            real_score = f"{int(r['home_score'])}-{int(r['away_score'])}"

                        display_rows.append({
                            "fixture_id": r['fixture_id'],
                            "Data": dt_str,
                            "Status": status_badge,
                            "Match": match_label,
                            "Prompt": r.get('prompt_version') or "—",
                            "Confiança": conf_display,
                            "Score Prev.": r.get('predicted_score') or "—",
                            "Real": real_score or "—",
                            "Headline": r.get('headline') or "—"
                        })

                    display_df = pd.DataFrame(display_rows)
                    fixture_ids = display_df['fixture_id'].tolist()

                    # Table view
                    st.dataframe(
                        display_df.drop(columns=['fixture_id']),
                        hide_index=True,
                        width="stretch"
                    )

                    st.divider()

                    # Detail view with preview
                    st.markdown("### Preview & Copy")
                    default_idx = 0
                    sel_fixture = st.selectbox(
                        "Selecionar Jogo",
                        options=fixture_ids,
                        index=default_idx,
                        format_func=lambda x: f"{label_map.get(x, x)}"
                    )

                    selected_row = df_round[df_round['fixture_id'] == sel_fixture].iloc[0]
                    analysis_data = safe_json_load(selected_row.get('full_json'))

                    col1, col2 = st.columns([1, 1])

                    with col1:
                        st.markdown("#### Preview Telegram")
                        if analysis_data:
                            st.markdown(render_telegram_preview(analysis_data), unsafe_allow_html=True)
                        else:
                            st.info("Sem análise disponível.")

                    with col2:
                        st.markdown("#### Copy Editável")
                        default_copy = build_plain_copy(analysis_data, selected_row['home_team'], selected_row['away_team']) if analysis_data else "Sem análise disponível."
                        st.text_area("Texto", value=default_copy, height=400, key="view_copy")

# ========================================
# MODO 3: 📊 MONITOR - Performance
# ========================================
elif mode == "📊 MONITOR":
    st.title("📊 MONITOR - Performance Tracking")
    st.caption("Acompanhar métricas agregadas ao longo do tempo")

    seasons = get_seasons()
    if not seasons:
        st.info("Sem dados na DB.")
    else:
        sel_season = st.selectbox("Época", seasons, key="monitor_season")

        st.divider()

        # Aggregate metrics
        st.markdown("### Métricas Agregadas")
        metrics = get_performance_metrics(sel_season)

        if metrics:
            render_performance_dashboard(metrics)

            # Detailed breakdown by prompt
            st.divider()
            st.markdown("### Performance por Prompt")

            if isinstance(metrics, list) and len(metrics) > 0:
                df_metrics = pd.DataFrame(metrics)

                # Bar chart comparison
                if 'avg_narrative_score' in df_metrics.columns:
                    st.bar_chart(df_metrics.set_index('prompt_version')[['avg_narrative_score', 'score_accuracy_pct', 'tip_accuracy_pct']])

                # Detailed table
                st.dataframe(df_metrics, width="stretch")
        else:
            st.info("Sem métricas disponíveis. Execute avaliações primeiro no modo VALIDATE.")

# Rodapé
st.sidebar.markdown("---")
st.sidebar.caption("Clarity Engine v2.0 | Clean & Lean")
