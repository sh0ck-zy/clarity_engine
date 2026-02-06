"""
Clarity Engine Dashboard v3
===========================
Three modes for the founder's workflow:
1. HEALTH - Is my system ready to run?
2. DATA - What data do we have? How is it used?
3. QUALITY - Which prompt is winning? Why?
"""

import streamlit as st
import pandas as pd
import json
from datetime import datetime, timezone
from pathlib import Path
import sys

# Environment setup
PROJECT_ROOT = Path(__file__).resolve().parent.parent
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from src.database.config import get_connection

# Page config
st.set_page_config(
    page_title="Clarity Engine",
    page_icon="C",
    layout="wide",
    initial_sidebar_state="expanded"
)

# Minimal clean CSS
st.markdown("""
<style>
    @import url('https://fonts.googleapis.com/css2?family=Inter:wght@400;500;600;700&display=swap');

    html, body, [class*="css"] {
        font-family: 'Inter', -apple-system, sans-serif;
    }

    .stApp {
        background: #0f1117;
        color: #e5e7eb;
    }

    /* Clean metric cards */
    .metric-card {
        background: #1a1d24;
        border: 1px solid #2d3139;
        border-radius: 8px;
        padding: 16px;
        margin-bottom: 12px;
    }

    .metric-label {
        font-size: 12px;
        color: #9ca3af;
        text-transform: uppercase;
        letter-spacing: 0.5px;
        margin-bottom: 4px;
    }

    .metric-value {
        font-size: 28px;
        font-weight: 600;
        color: #f9fafb;
    }

    .metric-value.green { color: #22c55e; }
    .metric-value.yellow { color: #eab308; }
    .metric-value.red { color: #ef4444; }

    /* Status indicators */
    .status-ok { color: #22c55e; }
    .status-warn { color: #eab308; }
    .status-error { color: #ef4444; }
    .status-missing { color: #6b7280; }

    /* Section headers */
    .section-header {
        font-size: 14px;
        font-weight: 600;
        color: #9ca3af;
        text-transform: uppercase;
        letter-spacing: 0.5px;
        margin: 24px 0 12px 0;
        padding-bottom: 8px;
        border-bottom: 1px solid #2d3139;
    }

    /* Data tables */
    .data-table {
        font-size: 13px;
    }

    /* Mode selector styling */
    div[data-testid="stSidebarNav"] {
        padding-top: 1rem;
    }
</style>
""", unsafe_allow_html=True)


# =============================================================================
# DATA LAYER - Queries
# =============================================================================

def get_leagues():
    """Get distinct leagues from fixtures."""
    conn = get_connection()
    if not conn:
        return ["Premier League"]
    try:
        df = pd.read_sql(
            "SELECT DISTINCT league FROM fixtures WHERE league IS NOT NULL ORDER BY league",
            conn
        )
        leagues = df['league'].tolist()
        return leagues if leagues else ["Premier League"]
    except Exception:
        return ["Premier League"]
    finally:
        conn.close()


def get_seasons():
    """Get distinct seasons."""
    conn = get_connection()
    if not conn:
        return []
    try:
        df = pd.read_sql(
            "SELECT DISTINCT season FROM fixtures ORDER BY season DESC",
            conn
        )
        return df['season'].tolist()
    except Exception:
        return []
    finally:
        conn.close()


def get_health_stats(league: str, season: str) -> dict:
    """Get pipeline health statistics."""
    conn = get_connection()
    if not conn:
        return {'error': 'No database connection'}

    try:
        stats = {}

        # Total fixtures
        df = pd.read_sql(
            "SELECT COUNT(*) as cnt FROM fixtures WHERE league = %s AND season = %s",
            conn, params=(league, season)
        )
        stats['total_fixtures'] = int(df.iloc[0]['cnt'])

        # Finished fixtures
        df = pd.read_sql(
            "SELECT COUNT(*) as cnt FROM fixtures WHERE league = %s AND season = %s AND status = 'FINISHED'",
            conn, params=(league, season)
        )
        stats['finished_fixtures'] = int(df.iloc[0]['cnt'])

        # Fixtures with analyses
        df = pd.read_sql("""
            SELECT COUNT(DISTINCT f.id) as cnt
            FROM fixtures f
            JOIN analysis_reports ar ON f.id = ar.fixture_id
            WHERE f.league = %s AND f.season = %s
        """, conn, params=(league, season))
        stats['with_analyses'] = int(df.iloc[0]['cnt'])

        # Fixtures with reality data
        df = pd.read_sql("""
            SELECT COUNT(DISTINCT f.id) as cnt
            FROM fixtures f
            JOIN match_reality mr ON f.id = mr.fixture_id
            WHERE f.league = %s AND f.season = %s
        """, conn, params=(league, season))
        stats['with_reality'] = int(df.iloc[0]['cnt'])

        # Fixtures with evaluations
        df = pd.read_sql("""
            SELECT COUNT(DISTINCT f.id) as cnt
            FROM fixtures f
            JOIN analysis_reports ar ON f.id = ar.fixture_id
            JOIN analysis_evaluations ae ON ar.id = ae.report_id
            WHERE f.league = %s AND f.season = %s
        """, conn, params=(league, season))
        stats['with_evaluations'] = int(df.iloc[0]['cnt'])

        # Calculate what's missing
        stats['need_analyses'] = stats['finished_fixtures'] - stats['with_analyses']
        stats['need_reality'] = stats['with_analyses'] - stats['with_reality']
        stats['need_evaluations'] = stats['with_reality'] - stats['with_evaluations']

        # Coverage percentage (finished fixtures that have full pipeline)
        if stats['finished_fixtures'] > 0:
            stats['coverage_pct'] = (stats['with_evaluations'] / stats['finished_fixtures']) * 100
        else:
            stats['coverage_pct'] = 0

        return stats

    except Exception as e:
        return {'error': str(e)}
    finally:
        conn.close()


def get_table_stats(league: str, season: str) -> list:
    """Get row counts and last update for main tables."""
    conn = get_connection()
    if not conn:
        return []

    try:
        tables = []

        # Fixtures
        df = pd.read_sql("""
            SELECT COUNT(*) as cnt, MAX(date) as last_date
            FROM fixtures WHERE league = %s AND season = %s
        """, conn, params=(league, season))
        tables.append({
            'table': 'fixtures',
            'rows': int(df.iloc[0]['cnt']),
            'last_update': df.iloc[0]['last_date']
        })

        # Team stats (via fixtures)
        df = pd.read_sql("""
            SELECT COUNT(*) as cnt, MAX(ts.created_at) as last_date
            FROM team_stats ts
            JOIN fixtures f ON ts.fixture_id = f.id
            WHERE f.league = %s AND f.season = %s
        """, conn, params=(league, season))
        tables.append({
            'table': 'team_stats',
            'rows': int(df.iloc[0]['cnt']),
            'last_update': df.iloc[0]['last_date']
        })

        # Odds snapshots
        df = pd.read_sql("""
            SELECT COUNT(*) as cnt, MAX(os.captured_at) as last_date
            FROM odds_snapshots os
            JOIN fixtures f ON os.fixture_id = f.id
            WHERE f.league = %s AND f.season = %s
        """, conn, params=(league, season))
        tables.append({
            'table': 'odds_snapshots',
            'rows': int(df.iloc[0]['cnt']),
            'last_update': df.iloc[0]['last_date']
        })

        # Match reality
        df = pd.read_sql("""
            SELECT COUNT(*) as cnt, MAX(mr.created_at) as last_date
            FROM match_reality mr
            JOIN fixtures f ON mr.fixture_id = f.id
            WHERE f.league = %s AND f.season = %s
        """, conn, params=(league, season))
        tables.append({
            'table': 'match_reality',
            'rows': int(df.iloc[0]['cnt']),
            'last_update': df.iloc[0]['last_date']
        })

        # Analysis reports
        df = pd.read_sql("""
            SELECT COUNT(*) as cnt, MAX(ar.created_at) as last_date
            FROM analysis_reports ar
            JOIN fixtures f ON ar.fixture_id = f.id
            WHERE f.league = %s AND f.season = %s
        """, conn, params=(league, season))
        tables.append({
            'table': 'analysis_reports',
            'rows': int(df.iloc[0]['cnt']),
            'last_update': df.iloc[0]['last_date']
        })

        # Evaluations
        df = pd.read_sql("""
            SELECT COUNT(*) as cnt, MAX(ae.created_at) as last_date
            FROM analysis_evaluations ae
            JOIN analysis_reports ar ON ae.report_id = ar.id
            JOIN fixtures f ON ar.fixture_id = f.id
            WHERE f.league = %s AND f.season = %s
        """, conn, params=(league, season))
        tables.append({
            'table': 'analysis_evaluations',
            'rows': int(df.iloc[0]['cnt']),
            'last_update': df.iloc[0]['last_date']
        })

        return tables

    except Exception as e:
        return []
    finally:
        conn.close()


def get_prompt_leaderboard(league: str, season: str) -> pd.DataFrame:
    """Get prompt comparison metrics."""
    conn = get_connection()
    if not conn:
        return pd.DataFrame()

    try:
        df = pd.read_sql("""
            SELECT
                ar.prompt_version,
                COUNT(*) as sample_size,
                AVG(ae.narrative_score) as avg_score,
                COUNT(CASE WHEN ae.score_accuracy = TRUE THEN 1 END)::float
                    / NULLIF(COUNT(ae.score_accuracy), 0) * 100 as outcome_accuracy,
                AVG(ar.confidence) as avg_confidence
            FROM analysis_reports ar
            JOIN fixtures f ON ar.fixture_id = f.id
            LEFT JOIN analysis_evaluations ae ON ar.id = ae.report_id
            WHERE f.league = %s AND f.season = %s AND f.status = 'FINISHED'
            GROUP BY ar.prompt_version
            HAVING COUNT(*) >= 5
            ORDER BY AVG(ae.narrative_score) DESC NULLS LAST
        """, conn, params=(league, season))
        return df
    except Exception:
        return pd.DataFrame()
    finally:
        conn.close()


def get_matches_for_drilldown(league: str, season: str, search: str = None) -> pd.DataFrame:
    """Get matches for drilldown selection."""
    conn = get_connection()
    if not conn:
        return pd.DataFrame()

    try:
        query = """
            SELECT DISTINCT
                f.id as fixture_id,
                f.home_team,
                f.away_team,
                f.date,
                f.round,
                f.home_score,
                f.away_score,
                f.status
            FROM fixtures f
            JOIN analysis_reports ar ON f.id = ar.fixture_id
            WHERE f.league = %s AND f.season = %s AND f.status = 'FINISHED'
        """
        params = [league, season]

        if search:
            query += " AND (f.home_team ILIKE %s OR f.away_team ILIKE %s)"
            params.extend([f'%{search}%', f'%{search}%'])

        query += " ORDER BY f.date DESC LIMIT 50"

        df = pd.read_sql(query, conn, params=tuple(params))
        return df
    except Exception:
        return pd.DataFrame()
    finally:
        conn.close()


def get_match_drilldown(fixture_id: str) -> dict:
    """Get full drilldown data for a match."""
    conn = get_connection()
    if not conn:
        return {}

    try:
        # Get fixture info
        df_fix = pd.read_sql("""
            SELECT * FROM fixtures WHERE id = %s
        """, conn, params=(fixture_id,))

        if df_fix.empty:
            return {}

        fixture = df_fix.iloc[0].to_dict()

        # Get analysis reports
        df_reports = pd.read_sql("""
            SELECT ar.*, ae.narrative_score, ae.score_accuracy, ae.tip_accuracy,
                   ae.narrative_feedback, ae.narrative_critical_flags
            FROM analysis_reports ar
            LEFT JOIN analysis_evaluations ae ON ar.id = ae.report_id
            WHERE ar.fixture_id = %s
            ORDER BY ar.created_at DESC
        """, conn, params=(fixture_id,))

        # Get match reality
        df_reality = pd.read_sql("""
            SELECT * FROM match_reality WHERE fixture_id = %s
        """, conn, params=(fixture_id,))

        return {
            'fixture': fixture,
            'reports': df_reports.to_dict('records') if not df_reports.empty else [],
            'reality': df_reality.iloc[0].to_dict() if not df_reality.empty else None
        }

    except Exception as e:
        return {'error': str(e)}
    finally:
        conn.close()


def get_context_schema_info() -> list:
    """Get context schema field information."""
    # This reflects our context_schema.py structure
    return [
        {'field': 'fixture_id', 'type': 'str', 'source': 'Database', 'usage': 'Unique match identifier'},
        {'field': 'match_date', 'type': 'date', 'source': 'Database', 'usage': 'Match kickoff date'},
        {'field': 'home.identity.name', 'type': 'str', 'source': 'Database', 'usage': 'Home team name'},
        {'field': 'home.identity.elo', 'type': 'int', 'source': 'ClubElo', 'usage': 'Team strength rating (1000-2000)'},
        {'field': 'home.form.results', 'type': 'str', 'source': 'FBRef', 'usage': 'Last 5 results (W-D-L-W-W)'},
        {'field': 'home.form.xg_for', 'type': 'float[]', 'source': 'FBRef', 'usage': 'xG created in last 5 matches'},
        {'field': 'home.form.xg_against', 'type': 'float[]', 'source': 'FBRef', 'usage': 'xG conceded in last 5 matches'},
        {'field': 'home.form.ppda', 'type': 'float', 'source': 'Understat', 'usage': 'Pressing intensity (passes per defensive action)'},
        {'field': 'home.absences.players', 'type': 'list', 'source': 'Transfermarkt', 'usage': 'Injured/suspended players'},
        {'field': 'away.identity.name', 'type': 'str', 'source': 'Database', 'usage': 'Away team name'},
        {'field': 'away.identity.elo', 'type': 'int', 'source': 'ClubElo', 'usage': 'Team strength rating (1000-2000)'},
        {'field': 'away.form.results', 'type': 'str', 'source': 'FBRef', 'usage': 'Last 5 results'},
        {'field': 'away.form.xg_for', 'type': 'float[]', 'source': 'FBRef', 'usage': 'xG created in last 5 matches'},
        {'field': 'away.form.xg_against', 'type': 'float[]', 'source': 'FBRef', 'usage': 'xG conceded in last 5 matches'},
        {'field': 'away.form.ppda', 'type': 'float', 'source': 'Understat', 'usage': 'Pressing intensity'},
        {'field': 'away.absences.players', 'type': 'list', 'source': 'Transfermarkt', 'usage': 'Injured/suspended players'},
        {'field': 'head_to_head.matches_played', 'type': 'int', 'source': 'Database', 'usage': 'H2H matches in dataset'},
        {'field': 'head_to_head.home_wins', 'type': 'int', 'source': 'Database', 'usage': 'Home team H2H wins'},
        {'field': 'head_to_head.avg_goals', 'type': 'float', 'source': 'Database', 'usage': 'Average goals in H2H'},
        {'field': 'odds.home_win', 'type': 'float', 'source': 'Betfair/Pinnacle', 'usage': 'Market odds for home win'},
        {'field': 'odds.draw', 'type': 'float', 'source': 'Betfair/Pinnacle', 'usage': 'Market odds for draw'},
        {'field': 'odds.away_win', 'type': 'float', 'source': 'Betfair/Pinnacle', 'usage': 'Market odds for away win'},
        {'field': 'schedule.home_rest_days', 'type': 'int', 'source': 'Database', 'usage': 'Days since home team last played'},
        {'field': 'schedule.away_rest_days', 'type': 'int', 'source': 'Database', 'usage': 'Days since away team last played'},
        {'field': 'league_position.home_rank', 'type': 'int', 'source': 'Database', 'usage': 'Home team league position'},
        {'field': 'league_position.away_rank', 'type': 'int', 'source': 'Database', 'usage': 'Away team league position'},
    ]


def browse_table(table_name: str, league: str, season: str, limit: int = 100) -> pd.DataFrame:
    """Browse raw table data."""
    conn = get_connection()
    if not conn:
        return pd.DataFrame()

    try:
        if table_name == 'fixtures':
            df = pd.read_sql("""
                SELECT id, date, home_team, away_team, home_score, away_score, status, round
                FROM fixtures
                WHERE league = %s AND season = %s
                ORDER BY date DESC
                LIMIT %s
            """, conn, params=(league, season, limit))
        elif table_name == 'team_stats':
            df = pd.read_sql("""
                SELECT ts.fixture_id, f.home_team, f.away_team, ts.team_name,
                       ts.xg, ts.xga, ts.possession, ts.shots
                FROM team_stats ts
                JOIN fixtures f ON ts.fixture_id = f.id
                WHERE f.league = %s AND f.season = %s
                ORDER BY f.date DESC
                LIMIT %s
            """, conn, params=(league, season, limit))
        elif table_name == 'odds_snapshots':
            df = pd.read_sql("""
                SELECT os.fixture_id, f.home_team, f.away_team,
                       os.home_win, os.draw, os.away_win, os.source, os.captured_at
                FROM odds_snapshots os
                JOIN fixtures f ON os.fixture_id = f.id
                WHERE f.league = %s AND f.season = %s
                ORDER BY os.captured_at DESC
                LIMIT %s
            """, conn, params=(league, season, limit))
        elif table_name == 'match_reality':
            df = pd.read_sql("""
                SELECT mr.fixture_id, f.home_team, f.away_team,
                       mr.score_home, mr.score_away, mr.luck_factor, mr.narrative_summary
                FROM match_reality mr
                JOIN fixtures f ON mr.fixture_id = f.id
                WHERE f.league = %s AND f.season = %s
                ORDER BY f.date DESC
                LIMIT %s
            """, conn, params=(league, season, limit))
        elif table_name == 'analysis_reports':
            df = pd.read_sql("""
                SELECT ar.fixture_id, f.home_team, f.away_team,
                       ar.prompt_version, ar.confidence, ar.predicted_score, ar.headline
                FROM analysis_reports ar
                JOIN fixtures f ON ar.fixture_id = f.id
                WHERE f.league = %s AND f.season = %s
                ORDER BY ar.created_at DESC
                LIMIT %s
            """, conn, params=(league, season, limit))
        else:
            return pd.DataFrame()

        return df

    except Exception:
        return pd.DataFrame()
    finally:
        conn.close()


# =============================================================================
# UI COMPONENTS
# =============================================================================

def render_metric_card(label: str, value: str, color: str = None):
    """Render a metric card."""
    color_class = f" {color}" if color else ""
    st.markdown(f"""
        <div class="metric-card">
            <div class="metric-label">{label}</div>
            <div class="metric-value{color_class}">{value}</div>
        </div>
    """, unsafe_allow_html=True)


def render_section_header(text: str):
    """Render a section header."""
    st.markdown(f'<div class="section-header">{text}</div>', unsafe_allow_html=True)


# =============================================================================
# MAIN APP
# =============================================================================

# Sidebar - Global filters and mode selection
with st.sidebar:
    st.title("Clarity Engine")

    st.markdown("---")

    # Mode selection
    mode = st.radio(
        "Mode",
        ["HEALTH", "DATA", "QUALITY"],
        label_visibility="collapsed"
    )

    st.markdown("---")

    # Global filters
    st.markdown("**Filters**")

    leagues = get_leagues()
    selected_league = st.selectbox(
        "League",
        leagues,
        index=0 if leagues else None
    )

    seasons = get_seasons()
    selected_season = st.selectbox(
        "Season",
        seasons,
        index=0 if seasons else None
    )

    st.markdown("---")
    st.caption("v3.0 - Rebuilt for clarity")


# =============================================================================
# MODE: HEALTH
# =============================================================================
if mode == "HEALTH":
    st.title("Pipeline Health")
    st.caption("Is your system ready to run?")

    if not selected_league or not selected_season:
        st.warning("Select a league and season")
    else:
        stats = get_health_stats(selected_league, selected_season)

        if 'error' in stats:
            st.error(f"Error: {stats['error']}")
        else:
            # Coverage bar
            coverage = stats['coverage_pct']
            if coverage >= 90:
                bar_color = "green"
            elif coverage >= 70:
                bar_color = "yellow"
            else:
                bar_color = "red"

            st.progress(coverage / 100)

            col1, col2, col3, col4 = st.columns(4)

            with col1:
                render_metric_card("Total Fixtures", str(stats['total_fixtures']))
            with col2:
                render_metric_card("Finished", str(stats['finished_fixtures']))
            with col3:
                render_metric_card("With Analyses", str(stats['with_analyses']))
            with col4:
                color = "green" if coverage >= 90 else ("yellow" if coverage >= 70 else "red")
                render_metric_card("Coverage", f"{coverage:.0f}%", color)

            # Pipeline status
            render_section_header("Pipeline Status")

            col1, col2, col3 = st.columns(3)

            with col1:
                need = stats['need_analyses']
                if need > 0:
                    st.warning(f"{need} fixtures need analyses")
                else:
                    st.success("All finished fixtures have analyses")

            with col2:
                need = stats['need_reality']
                if need > 0:
                    st.warning(f"{need} fixtures need reality data")
                else:
                    st.success("All analyses have reality data")

            with col3:
                need = stats['need_evaluations']
                if need > 0:
                    st.warning(f"{need} fixtures need evaluations")
                else:
                    st.success("All reality data has evaluations")

            # One-click fix
            render_section_header("Quick Actions")

            total_missing = stats['need_reality'] + stats['need_evaluations']

            if total_missing > 0:
                st.info(f"{total_missing} items need processing. Run from CLI:")
                st.code(f"python -m src.jobs.batch_runner --fill-missing --league '{selected_league}' --season '{selected_season}'")
            else:
                st.success("Pipeline is fully up to date!")

            # Table stats
            render_section_header("Table Stats")

            table_stats = get_table_stats(selected_league, selected_season)
            if table_stats:
                df_tables = pd.DataFrame(table_stats)
                df_tables['last_update'] = pd.to_datetime(df_tables['last_update']).dt.strftime('%Y-%m-%d %H:%M')
                st.dataframe(df_tables, hide_index=True, use_container_width=True)


# =============================================================================
# MODE: DATA
# =============================================================================
elif mode == "DATA":
    st.title("Data Explorer")
    st.caption("What data do we have? How is it used?")

    tab1, tab2, tab3 = st.tabs(["Schema", "Tables", "Match Lineage"])

    with tab1:
        render_section_header("Context Schema")
        st.caption("Fields that feed each analysis")

        schema_info = get_context_schema_info()
        df_schema = pd.DataFrame(schema_info)

        # Group by source
        sources = df_schema['source'].unique()

        for source in sources:
            st.markdown(f"**{source}**")
            source_df = df_schema[df_schema['source'] == source][['field', 'type', 'usage']]
            st.dataframe(source_df, hide_index=True, use_container_width=True)
            st.markdown("")

        # Data flow diagram
        render_section_header("Data Flow")
        st.code("""
FBRef (xG, form) ────┐
                     │
ClubElo (ratings) ───┼──> Context Builder ──> LLM ──> Analysis Report
                     │                                      │
Understat (PPDA) ────┤                                      v
                     │                               Match Reality
Betfair (odds) ──────┘                                      │
                                                            v
                                                      Evaluation
        """)

    with tab2:
        render_section_header("Raw Tables")

        if not selected_league or not selected_season:
            st.warning("Select a league and season")
        else:
            table_name = st.selectbox(
                "Table",
                ["fixtures", "team_stats", "odds_snapshots", "match_reality", "analysis_reports"]
            )

            df = browse_table(table_name, selected_league, selected_season)

            if df.empty:
                st.info(f"No data in {table_name}")
            else:
                st.dataframe(df, hide_index=True, use_container_width=True)

    with tab3:
        render_section_header("Match Lineage")
        st.caption("See exactly what data fed a specific analysis")

        if not selected_league or not selected_season:
            st.warning("Select a league and season")
        else:
            search = st.text_input("Search team", placeholder="e.g. Arsenal")

            matches = get_matches_for_drilldown(selected_league, selected_season, search)

            if matches.empty:
                st.info("No matches found")
            else:
                # Format for selection
                matches['label'] = matches.apply(
                    lambda r: f"{r['home_team']} vs {r['away_team']} (R{r['round']})",
                    axis=1
                )

                selected_match = st.selectbox(
                    "Select match",
                    matches['fixture_id'].tolist(),
                    format_func=lambda x: matches[matches['fixture_id'] == x]['label'].iloc[0]
                )

                if selected_match:
                    drilldown = get_match_drilldown(selected_match)

                    if 'error' in drilldown:
                        st.error(drilldown['error'])
                    elif drilldown:
                        fixture = drilldown['fixture']

                        st.markdown(f"### {fixture['home_team']} vs {fixture['away_team']}")
                        st.caption(f"Round {fixture['round']} | {fixture['date']}")

                        if fixture['status'] == 'FINISHED':
                            st.markdown(f"**Final Score:** {fixture['home_score']} - {fixture['away_score']}")

                        # Show what data was available
                        render_section_header("Data Sources Used")

                        # This would ideally pull from stored context, but for now show structure
                        lineage_data = [
                            {'source': 'Fixture Info', 'status': 'OK', 'value': f"{fixture['home_team']} vs {fixture['away_team']}"},
                            {'source': 'Match Date', 'status': 'OK', 'value': str(fixture['date'])},
                        ]

                        # Check if we have reports
                        if drilldown['reports']:
                            report = drilldown['reports'][0]
                            lineage_data.append({'source': 'Analysis', 'status': 'OK', 'value': f"Prompt: {report.get('prompt_version', 'N/A')}"})
                            lineage_data.append({'source': 'Prediction', 'status': 'OK', 'value': report.get('predicted_score', 'N/A')})
                            lineage_data.append({'source': 'Confidence', 'status': 'OK', 'value': f"{report.get('confidence', 0)}%"})
                        else:
                            lineage_data.append({'source': 'Analysis', 'status': 'MISSING', 'value': '-'})

                        if drilldown['reality']:
                            reality = drilldown['reality']
                            lineage_data.append({'source': 'Reality Data', 'status': 'OK', 'value': f"{reality.get('score_home', 0)}-{reality.get('score_away', 0)}"})
                            lineage_data.append({'source': 'Luck Factor', 'status': 'OK', 'value': reality.get('luck_factor', 'N/A')})
                        else:
                            lineage_data.append({'source': 'Reality Data', 'status': 'MISSING', 'value': '-'})

                        df_lineage = pd.DataFrame(lineage_data)
                        st.dataframe(df_lineage, hide_index=True, use_container_width=True)


# =============================================================================
# MODE: QUALITY
# =============================================================================
elif mode == "QUALITY":
    st.title("Quality Metrics")
    st.caption("Which prompt is winning? Why?")

    if not selected_league or not selected_season:
        st.warning("Select a league and season")
    else:
        # Phase toggle (Phase 2 disabled for now)
        phase = st.radio(
            "Metrics Phase",
            ["Phase 1: Narrative Quality", "Phase 2: Market Intelligence (Coming Soon)"],
            horizontal=True
        )

        if "Phase 2" in phase:
            st.info("Market intelligence metrics will be available after Phase 1 validation is complete.")
        else:
            # Prompt leaderboard
            render_section_header("Prompt Leaderboard")

            leaderboard = get_prompt_leaderboard(selected_league, selected_season)

            if leaderboard.empty:
                st.info("No evaluation data yet. Run evaluations from HEALTH mode first.")
            else:
                # Highlight winner
                if len(leaderboard) > 0 and pd.notna(leaderboard.iloc[0]['avg_score']):
                    winner = leaderboard.iloc[0]['prompt_version']
                    st.success(f"Current leader: **{winner}**")

                # Format for display
                leaderboard_display = leaderboard.copy()
                leaderboard_display['avg_score'] = leaderboard_display['avg_score'].apply(
                    lambda x: f"{x:.1f}" if pd.notna(x) else "-"
                )
                leaderboard_display['outcome_accuracy'] = leaderboard_display['outcome_accuracy'].apply(
                    lambda x: f"{x:.1f}%" if pd.notna(x) else "-"
                )
                leaderboard_display['avg_confidence'] = leaderboard_display['avg_confidence'].apply(
                    lambda x: f"{x:.0f}%" if pd.notna(x) else "-"
                )

                leaderboard_display.columns = ['Prompt', 'Sample Size', 'Avg Score', 'Outcome Accuracy', 'Avg Confidence']

                st.dataframe(leaderboard_display, hide_index=True, use_container_width=True)

            # Match drilldown
            render_section_header("Match Drilldown")

            search = st.text_input("Search team", placeholder="e.g. Arsenal", key="quality_search")

            matches = get_matches_for_drilldown(selected_league, selected_season, search)

            if not matches.empty:
                matches['label'] = matches.apply(
                    lambda r: f"{r['home_team']} vs {r['away_team']} (R{r['round']}) - {r['home_score']}-{r['away_score']}",
                    axis=1
                )

                selected_match = st.selectbox(
                    "Select match to analyze",
                    matches['fixture_id'].tolist(),
                    format_func=lambda x: matches[matches['fixture_id'] == x]['label'].iloc[0],
                    key="quality_match"
                )

                if selected_match:
                    drilldown = get_match_drilldown(selected_match)

                    if drilldown and 'fixture' in drilldown:
                        fixture = drilldown['fixture']

                        col1, col2 = st.columns(2)

                        with col1:
                            st.markdown("### Pre-Match Prediction")

                            if drilldown['reports']:
                                for report in drilldown['reports']:
                                    st.markdown(f"**Prompt:** {report.get('prompt_version', 'N/A')}")
                                    st.markdown(f"**Predicted:** {report.get('predicted_score', 'N/A')}")
                                    st.markdown(f"**Confidence:** {report.get('confidence', 0)}%")
                                    st.markdown(f"**Headline:** {report.get('headline', 'N/A')}")

                                    if report.get('narrative_score'):
                                        st.markdown(f"**Narrative Score:** {report['narrative_score']:.0f}/100")

                                    st.markdown("---")
                            else:
                                st.info("No analysis available")

                        with col2:
                            st.markdown("### Post-Match Reality")

                            st.markdown(f"**Actual Score:** {fixture['home_score']} - {fixture['away_score']}")

                            if drilldown['reality']:
                                reality = drilldown['reality']
                                st.markdown(f"**Luck Factor:** {reality.get('luck_factor', 'N/A')}")
                                st.markdown(f"**What Happened:**")
                                st.write(reality.get('narrative_summary', 'No summary available'))
                            else:
                                st.info("No reality data available")
