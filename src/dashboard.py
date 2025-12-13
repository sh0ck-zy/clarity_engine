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
except ImportError as e:
    st.error(f"Critical Import Error: {e}")
    st.stop()

# --- CSS CUSTOMIZADO ---
st.markdown("""
<style>
    .stApp { background-color: #0e1117; color: #FAFAFA; }
    
    .status-finished { color: #4CAF50; font-weight: bold; font-size: 0.8em; }
    .status-scheduled { color: #FFA726; font-weight: bold; font-size: 0.8em; }
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
def get_seasons():
    conn = get_connection()
    if not conn: return []
    try:
        df = pd.read_sql("SELECT DISTINCT season FROM fixtures ORDER BY season DESC", conn)
        return df['season'].tolist()
    except Exception: return []
    finally: conn.close()

def get_rounds(season):
    conn = get_connection()
    if not conn: return []
    try:
        df = pd.read_sql('SELECT DISTINCT "round" FROM fixtures WHERE season=%s ORDER BY "round" DESC', conn, params=(season,))
        return [int(r) for r in df['round'].dropna().tolist()]
    except Exception: return []
    finally: conn.close()

def get_fixtures_by_round(season, round_val):
    conn = get_connection()
    if not conn: return pd.DataFrame()
    try:
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

def get_round_calendar(season):
    """Returns min/max dates per round for the season."""
    conn = get_connection()
    if not conn: return pd.DataFrame()
    query = """
        SELECT "round", MIN(date) AS start_date, MAX(date) AS end_date
        FROM fixtures
        WHERE season = %s
        GROUP BY "round"
        ORDER BY "round" ASC
    """
    df = pd.read_sql(query, conn, params=(season,))
    conn.close()
    return df

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

# --- INTERFACE ---
st.title("🧠 Clarity Engine: Ops Dashboard")

with st.sidebar:
    st.header("Modo de Engenheiro")
    mode = st.radio("Workflow", ["📊 Overview", "🧪 A/B Workbench", "🩻 Data Simulator"])
    st.divider()
    st.caption(f"System Root: {project_root}")

# === MODO 1: OVERVIEW ===
if mode == "📊 Overview":
    st.subheader("Overview de Análises (Ronda)")
    
    seasons = get_seasons()
    if not seasons:
        st.info("Sem dados na DB.")
    else:
        sel_season = st.selectbox("Época", seasons)
        rounds = get_rounds(sel_season)
        
        if not rounds:
            st.warning("Sem rondas.")
        else:
            def_round = get_current_round(sel_season) or rounds[0]
            round_idx = rounds.index(def_round) if def_round in rounds else 0
            sel_round = st.selectbox("Ronda", rounds, index=round_idx)
            
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
                        "Round": int(r["round"]) if pd.notna(r.get("round")) else "—",
                        "Status": status_badge,
                        "Match": match_label,
                        "Prompt": r.get('prompt_version') or "—",
                        "Confiança": conf_display,
                        "Aposta": r.get('betting_recommendation') or "—",
                        "Score Prev.": r.get('predicted_score') or "—",
                        "Real": real_score or "—",
                        "Headline": r.get('headline') or "—"
                    })
                
                display_df = pd.DataFrame(display_rows)
                fixture_ids = display_df['fixture_id'].tolist()
                
                c_table, c_detail = st.columns([2, 1])
                with c_table:
                    st.dataframe(
                        display_df.drop(columns=['fixture_id']),
                        hide_index=True,
                        use_container_width=True,
                        column_config={
                            "Data": st.column_config.TextColumn("Data", width="small"),
                            "Round": st.column_config.NumberColumn("Ronda", width="small"),
                            "Status": st.column_config.TextColumn("Estado", width="small"),
                            "Prompt": st.column_config.TextColumn("Prompt", width="small"),
                            "Confiança": st.column_config.TextColumn("Confiança", width="small"),
                            "Score Prev.": st.column_config.TextColumn("Score Prev."),
                            "Real": st.column_config.TextColumn("Real")
                        }
                    )
                
                with c_detail:
                    default_idx = 0
                    sel_fixture = st.selectbox(
                        "Jogo",
                        options=fixture_ids,
                        index=default_idx,
                        format_func=lambda x: f"{label_map.get(x, x)} ({display_df.loc[display_df['fixture_id']==x, 'Data'].iloc[0]})"
                    )
                    
                    selected_row = df_round[df_round['fixture_id'] == sel_fixture].iloc[0]
                    analysis_data = st.session_state.get('overview_latest', {}).get(sel_fixture) or safe_json_load(selected_row.get('full_json'))
                    
                    conf_val = selected_row.get('confidence')
                    if (pd.isna(conf_val) or conf_val is None) and analysis_data:
                        conf_val = analysis_data.get('prediction', {}).get('confidence')
                    conf_val = int(conf_val) if conf_val is not None and not pd.isna(conf_val) else 0
                    
                    if selected_row.get('predicted_score'):
                        pred_score = selected_row.get('predicted_score')
                    elif analysis_data:
                        pred_score = analysis_data.get('prediction', {}).get('scoreline', "—")
                    else:
                        pred_score = "—"
                    
                    real_score = "—"
                    if pd.notna(selected_row.get('score_home')) and pd.notna(selected_row.get('score_away')):
                        real_score = f"{int(selected_row['score_home'])}-{int(selected_row['score_away'])}"
                    elif pd.notna(selected_row.get('home_score')) and pd.notna(selected_row.get('away_score')):
                        real_score = f"{int(selected_row['home_score'])}-{int(selected_row['away_score'])}"
                    
                    st.metric("Confiança", f"{conf_val}%")
                    m1, m2 = st.columns(2)
                    with m1: st.metric("Score Prev.", pred_score)
                    with m2: st.metric("Real", real_score)
                    
                    st.markdown("### Preview Telegram")
                    if analysis_data:
                        st.markdown(render_telegram_preview(analysis_data), unsafe_allow_html=True)
                    else:
                        st.info("Sem análise gerada para este jogo.")
                    
                    st.markdown("### Copy Editável")
                    default_copy = build_plain_copy(analysis_data, selected_row['home_team'], selected_row['away_team']) if analysis_data else "Sem análise disponível."
                    st.text_area("Texto", value=default_copy, height=240, key=f"copy_{sel_fixture}")
                    
                    st.divider()
                    prompts_list = list(PROMPTS.keys())
                    def_idx = prompts_list.index(selected_row['prompt_version']) if selected_row.get('prompt_version') in prompts_list else 0
                    chosen_prompt = st.selectbox("Prompt", prompts_list, index=def_idx, key=f"prompt_{sel_fixture}")
                    force_cache = st.checkbox("Forçar recálculo ($)", False, key=f"force_{sel_fixture}")
                    
                    if st.button("Gerar/Atualizar Análise", key=f"gen_{sel_fixture}"):
                        engine = ClarityEngine()
                        with st.spinner("A gerar análise..."):
                            result = engine.run_analysis(sel_fixture, chosen_prompt, force_refresh=force_cache)
                        engine.close()
                        if isinstance(result, dict) and result.get("error"):
                            st.error(f"Erro na análise: {result['error']}")
                        else:
                            st.session_state.setdefault('overview_latest', {})[sel_fixture] = result
                            st.success("Análise atualizada.")
                            st.rerun()

# === MODO 2: A/B WORKBENCH ===
elif mode == "🧪 A/B Workbench":
    st.subheader("Laboratório de Comparação Profunda")
    selected_fixture_id = render_game_selector("ab_bench")
    st.divider()
    prompts = list(PROMPTS.keys())
    c_p1, c_p2, c_p3 = st.columns([1, 1, 1])
    with c_p1: prompt_a = st.selectbox("Prompt A (Azul)", prompts, index=0)
    with c_p2: prompt_b = st.selectbox("Prompt B (Vermelho)", prompts, index=min(1, len(prompts)-1))
    with c_p3: force_cache = st.checkbox("Forçar Recálculo ($)", False)
        
    if st.button("⚡ FIGHT! (Gerar Comparação)") and selected_fixture_id:
        engine = ClarityEngine()
        reality = get_match_reality(selected_fixture_id)
        if reality: st.success(f"🏁 RESULTADO REAL: {reality['score']} (Luck: {reality['luck']})")
        else: st.warning("📅 Jogo ainda não realizado (Comparação Preditiva Pura).")

        col_a, col_b = st.columns(2)
        with col_a:
            st.markdown(f"### 🔵 {PROMPTS[prompt_a]['name']}")
            with st.spinner(f"A processar {prompt_a}..."):
                res_a = engine.run_analysis(selected_fixture_id, prompt_a, force_refresh=force_cache)
                tab_prod, tab_brain, tab_json = st.tabs(["📱 Produto", "🧠 Cérebro", "📂 JSON"])
                with tab_prod: st.markdown(render_telegram_preview(res_a), unsafe_allow_html=True)
                with tab_brain:
                    weights = res_a.get('glass_box_logic', {}).get('factor_weights')
                    if weights: st.bar_chart(weights)
                    st.info(res_a.get('glass_box_logic', {}).get('reasoning', 'Sem raciocínio.'))
                with tab_json: st.json(res_a)

        with col_b:
            st.markdown(f"### 🔴 {PROMPTS[prompt_b]['name']}")
            with st.spinner(f"A processar {prompt_b}..."):
                res_b = engine.run_analysis(selected_fixture_id, prompt_b, force_refresh=force_cache)
                tab_prod_b, tab_brain_b, tab_json_b = st.tabs(["📱 Produto", "🧠 Cérebro", "📂 JSON"])
                with tab_prod_b: st.markdown(render_telegram_preview(res_b), unsafe_allow_html=True)
                with tab_brain_b:
                    weights_b = res_b.get('glass_box_logic', {}).get('factor_weights')
                    if weights_b: st.bar_chart(weights_b)
                    st.info(res_b.get('glass_box_logic', {}).get('reasoning', 'Sem raciocínio.'))
                with tab_json_b: st.json(res_b)
    
    st.divider()
    st.subheader("Histórico Geral")
    df_audit = get_audit_comparison()
    if not df_audit.empty: st.dataframe(df_audit, use_container_width=True, height=400)

# ==============================================================================
# MODO 3: DATA SIMULATOR (CORRIGIDO E MELHORADO)
# ==============================================================================
elif mode == "🩻 Data Simulator":
    st.subheader("Simulador de Contexto (What-If Analysis)")
    
    sim_id = render_game_selector("sim_bench")
    
    if sim_id and st.button("Carregar Dados Reais"):
        builder = MatchContextBuilder()
        real_context = builder.build_context(sim_id)
        st.session_state['sim_context'] = real_context
        # Limpar resultado anterior para evitar confusão
        if 'sim_result' in st.session_state:
            del st.session_state['sim_result']
        st.success("Dados carregados!")

    if 'sim_context' in st.session_state:
        # Layout: Editor (2/3) e Opções (1/3)
        c_edit, c_opts = st.columns([2, 1])
        
        with c_edit:
            st.markdown("### 📝 Editar Contexto")
            context_str = json.dumps(st.session_state['sim_context'], indent=2)
            edited_context_str = st.text_area("JSON Input", value=context_str, height=550)
        
        with c_opts:
            st.markdown("### ⚙️ Configuração")
            
            # 1. SELETOR DE PROMPT (Funcionalidade Solicitada)
            prompts_list = list(PROMPTS.keys())
            # Tentar selecionar 'v3' por defeito se existir
            def_idx = prompts_list.index("v3") if "v3" in prompts_list else 0
            selected_sim_prompt = st.selectbox("Escolher Prompt", prompts_list, index=def_idx)
            
            st.divider()
            
            if st.button("🧠 Correr Simulação"):
                try:
                    modified_context = json.loads(edited_context_str)
                    engine = ClarityEngine()
                    
                    # Usa a prompt explicitamente selecionada
                    sys_prompt = PROMPTS[selected_sim_prompt]["text"]
                    
                    with st.spinner(f"A simular com {selected_sim_prompt}..."):
                        resp = engine.client.chat.completions.create(
                            model="gpt-5.1", 
                            messages=[
                                {"role": "system", "content": sys_prompt},
                                {"role": "user", "content": json.dumps(modified_context)}
                            ],
                            response_format={"type": "json_object"}
                        )
                        # Guardar em session_state para persistência
                        st.session_state['sim_result'] = json.loads(resp.choices[0].message.content)
                        st.session_state['sim_prompt_used'] = selected_sim_prompt
                        
                except Exception as e:
                    st.error(f"Erro na simulação: {e}")

        # MOSTRAR RESULTADOS (Persistente)
        if 'sim_result' in st.session_state:
            st.divider()
            st.markdown(f"### 🔮 Resultado da Simulação ({st.session_state.get('sim_prompt_used', '?')})")
            
            sim_res = st.session_state['sim_result']
            
            col_res1, col_res2 = st.columns([1, 1])
            with col_res1:
                st.markdown(render_telegram_preview(sim_res), unsafe_allow_html=True)
            with col_res2:
                st.info("Raciocínio Glass Box")
                st.write(sim_res.get('glass_box_logic', {}).get('reasoning'))
                with st.expander("Ver JSON Completo"):
                    st.json(sim_res)

# Rodapé
st.sidebar.markdown("---")
st.sidebar.caption("Clarity Engine v0.5-Beta")
