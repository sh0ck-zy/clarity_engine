"""
Script de Diagnóstico da Base de Dados
Valida se os dados estão prontos para o ClarityEngine processar análises.
"""

import sys
import json
from pathlib import Path

# Adicionar a raiz do projeto ao path
PROJECT_ROOT = Path(__file__).resolve().parents[1]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.append(str(PROJECT_ROOT))

from src.database.config import get_connection
from src.analysis.builder import MatchContextBuilder


def run_diagnosis():
    print("🩺 A INICIAR DIAGNÓSTICO DO CLARITY ENGINE...\n")
    
    # 1. VERIFICAR CONEXÃO À BASE DE DADOS
    print("--- 1. CONEXÃO À BASE DE DADOS ---")
    conn = get_connection()
    if not conn:
        print("❌ ERRO CRÍTICO: Não foi possível conectar à base de dados.")
        print("   Verifica o ficheiro .env e a variável DATABASE_URL")
        return
    print("✅ Conexão à base de dados estabelecida.\n")
    
    try:
        cursor = conn.cursor()
        
        # 2. VERIFICAR DADOS BRUTOS (DB)
        print("--- 2. ESTADO DA BASE DE DADOS ---")
        
        # Verificar se as tabelas existem
        cursor.execute("""
            SELECT table_name 
            FROM information_schema.tables 
            WHERE table_schema = 'public' 
            AND table_name IN ('fixtures', 'team_stats', 'analysis_reports')
        """)
        existing_tables = {row[0] for row in cursor.fetchall()}
        
        if 'fixtures' not in existing_tables:
            print("❌ ERRO CRÍTICO: Tabela 'fixtures' não existe.")
            print("   Executa: python scripts/init_db.py")
            conn.close()
            return
        
        if 'team_stats' not in existing_tables:
            print("❌ ERRO CRÍTICO: Tabela 'team_stats' não existe.")
            print("   Executa: python scripts/init_db.py")
            conn.close()
            return
        
        print("✅ Tabelas essenciais existem (fixtures, team_stats)")
        if 'analysis_reports' in existing_tables:
            print("✅ Tabela 'analysis_reports' existe (para cache de análises)")
        else:
            print("⚠️  Tabela 'analysis_reports' não existe (será criada na primeira análise)")
        
        # Contar fixtures
        cursor.execute("SELECT COUNT(*) FROM fixtures")
        fixture_count = cursor.fetchone()[0]
        
        # Contar fixtures com stats
        cursor.execute("""
            SELECT COUNT(DISTINCT f.id) 
            FROM fixtures f
            INNER JOIN team_stats ts ON f.id = ts.fixture_id
        """)
        fixtures_with_stats = cursor.fetchone()[0]
        
        # Contar fixtures com stats táticos (ppda/field_tilt)
        cursor.execute("""
            SELECT COUNT(DISTINCT f.id) 
            FROM fixtures f
            INNER JOIN team_stats ts ON f.id = ts.fixture_id
            WHERE ts.ppda IS NOT NULL OR ts.field_tilt IS NOT NULL
        """)
        fixtures_with_tactical = cursor.fetchone()[0]
        
        # Verificar se existe coluna elo
        cursor.execute("""
            SELECT column_name 
            FROM information_schema.columns 
            WHERE table_name = 'team_stats' AND column_name = 'elo'
        """)
        has_elo = cursor.fetchone() is not None
        
        print(f"\n📊 Estatísticas:")
        print(f"   • Fixtures totais: {fixture_count}")
        print(f"   • Fixtures com stats básicos (xG): {fixtures_with_stats} ({fixtures_with_stats/fixture_count*100 if fixture_count else 0:.1f}%)")
        print(f"   • Fixtures com stats táticos (PPDA/Tilt): {fixtures_with_tactical} ({fixtures_with_tactical/fixture_count*100 if fixture_count else 0:.1f}%)")
        print(f"   • Coluna 'elo' existe: {'✅ Sim' if has_elo else '⚠️  Não (pode ser adicionada via elo_backfill.py)'}")
        
        if fixture_count == 0:
            print("\n❌ ALERTA CRÍTICO: A base de dados está vazia.")
            print("   Executa os scrapers primeiro:")
            print("   • python src/ingestion/scraper.py")
            conn.close()
            return
        
        if fixtures_with_stats == 0:
            print("\n⚠️  AVISO: Nenhum fixture tem stats básicos (xG).")
            print("   Os scrapers podem não ter corrido corretamente.")
            conn.close()
            return
        
        # 3. BUSCAR UM FIXTURE DE EXEMPLO PARA TESTAR
        print("\n--- 3. BUSCANDO FIXTURE DE TESTE ---")
        cursor.execute("""
            SELECT f.id, f.date, f.home_team, f.away_team, f.status, f.season
            FROM fixtures f
            INNER JOIN team_stats ts ON f.id = ts.fixture_id
            WHERE f.status = 'FINISHED'
            GROUP BY f.id, f.date, f.home_team, f.away_team, f.status, f.season
            HAVING COUNT(DISTINCT ts.team_name) = 2
            ORDER BY f.date DESC
            LIMIT 1
        """)
        sample_fixture = cursor.fetchone()
        
        if not sample_fixture:
            print("⚠️  Nenhum fixture completo encontrado para teste.")
            print("   Precisa de fixtures FINISHED com stats de ambas as equipas.")
            conn.close()
            return
        
        fixture_id, date, home, away, status, season = sample_fixture
        print(f"✅ Fixture de teste encontrado:")
        print(f"   • ID: {fixture_id}")
        print(f"   • {home} vs {away}")
        print(f"   • Data: {date} | Temporada: {season} | Status: {status}")
        
        # 4. TESTAR O BUILDER (CONTEXTO)
        print("\n--- 4. TESTE DO MATCHCONTEXTBUILDER ---")
        print(f"A construir contexto JSON para: {home} vs {away}...")
        
        builder = MatchContextBuilder()
        try:
            context = builder.build_context(fixture_id)
            
            if not context or "error" in context:
                error_msg = context.get("error", "Unknown error") if context else "Builder retornou None"
                print(f"❌ FALHA: {error_msg}")
                print("   Verifica:")
                print("   • Se os dados na DB estão completos")
                print("   • Se o builder.py está a mapear corretamente os dados")
                builder.close()
                conn.close()
                return
            
            # Validar estrutura do JSON
            json_str = json.dumps(context, indent=2)
            size_kb = len(json_str.encode('utf-8')) / 1024
            print(f"✅ SUCESSO: Contexto gerado com {size_kb:.2f} KB")
            
            # Validar campos essenciais esperados pelo prompt
            required_structure = {
                'home': ['name', 'identity', 'form', 'context'],
                'away': ['name', 'identity', 'form', 'context'],
            }
            
            missing_keys = []
            for team_key in ['home', 'away']:
                if team_key not in context:
                    missing_keys.append(f"'{team_key}' (raiz)")
                    continue
                
                team_data = context[team_key]
                for required_key in required_structure[team_key]:
                    if required_key not in team_data:
                        missing_keys.append(f"'{team_key}.{required_key}'")
            
            if missing_keys:
                print(f"⚠️  AVISO: Faltam chaves esperadas: {', '.join(missing_keys)}")
            else:
                print("✅ Estrutura do JSON está correta para o Prompt V1")
            
            # Validar campos específicos dentro de identity e form
            validation_issues = []
            for team_key in ['home', 'away']:
                team_data = context.get(team_key, {})
                identity = team_data.get('identity', {})
                form = team_data.get('form', {})
                
                # Verificar identity
                identity_fields = ['elo', 'season_ppda', 'season_field_tilt', 'season_overall_xg', 'season_overall_xga']
                for field in identity_fields:
                    if field not in identity:
                        validation_issues.append(f"{team_key}.identity.{field}")
                
                # Verificar form
                form_fields = ['last_5_results', 'last_5_xg_diff', 'last_5_goal_diff', 'days_rest']
                for field in form_fields:
                    if field not in form:
                        validation_issues.append(f"{team_key}.form.{field}")
            
            if validation_issues:
                print(f"⚠️  AVISO: Campos específicos em falta: {', '.join(validation_issues)}")
            else:
                print("✅ Todos os campos essenciais estão presentes")
            
            # Mostrar amostra do contexto
            print("\n--- AMOSTRA DO CONTEXTO (Primeiras 20 linhas) ---")
            lines = json_str.split("\n")
            for line in lines[:20]:
                print(line)
            if len(lines) > 20:
                print("...")
            
            builder.close()
            
        except Exception as e:
            print(f"❌ ERRO no Builder: {e}")
            import traceback
            traceback.print_exc()
            builder.close()
            conn.close()
            return
        
        # 5. RESUMO FINAL
        print("\n--- 5. RESUMO DO DIAGNÓSTICO ---")
        print("✅ Base de dados: OK")
        print("✅ Dados disponíveis: OK")
        print("✅ Builder funcional: OK")
        print("\n🎯 O motor está pronto para processar análises!")
        print("\nPróximos passos:")
        print("   1. Edita main.py com os parâmetros desejados")
        print("   2. Executa: python main.py")
        print("   3. Começa com uma ronda pequena para validar a qualidade")
        
    except Exception as e:
        print(f"❌ ERRO durante diagnóstico: {e}")
        import traceback
        traceback.print_exc()
    finally:
        conn.close()


if __name__ == "__main__":
    run_diagnosis()

