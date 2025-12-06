from typing import Iterable
import time
import pandas as pd

from src.analysis.predictor import ClarityEngine
from src.analysis.reality import RealitySeeker  # IMPORTANTE: Módulo da Verdade
from src.database.config import get_connection

class BatchRunner:
    """Runs model inference (Prediction or Truth) across fixtures."""

    def __init__(self) -> None:
        self.conn = get_connection()

    def _fetch_fixture_ids(self, season: str, round_id: str | int) -> Iterable[str]:
        if not self.conn:
            return []
        query = "SELECT id FROM fixtures WHERE season = %s"
        params = [season]
        if round_id != "all":
            query += " AND round = %s"
            params.append(round_id)
        df = pd.read_sql(query, self.conn, params=tuple(params))
        return df["id"].tolist()

    def run_specific_match(self, fixture_id: str, prompt_version: str = "hybrid", force: bool = False) -> None:
        """Executa análise (PREVISÃO) para um fixture específico (modo teste)."""
        print(f"\n🎯 Analisando fixture (Prediction): {fixture_id}")
        print(f"📝 Prompt: {prompt_version}")
        
        engine = ClarityEngine()
        try:
            result = engine.run_analysis(fixture_id, prompt_version, force_refresh=force)
            
            if result and "error" not in result:
                print(f"✅ Análise concluída com sucesso para {fixture_id}")
            else:
                error_msg = result.get("error", "Unknown error") if result else "No result returned"
                print(f"❌ Erro na análise: {error_msg}")
        except Exception as e:
            print(f"❌ Exceção durante análise: {e}")
            import traceback
            traceback.print_exc()
        finally:
            engine.close()

    def run_next_pending_batch(self, limit: int = 5, prompt_version: str = "hybrid", force: bool = False) -> None:
        """Executa PREVISÕES para os próximos N fixtures que têm stats mas não têm análise ainda."""
        if not self.conn:
            print("❌ Sem conexão à base de dados")
            return
        
        # Verificar se a tabela analysis_reports existe
        cursor = self.conn.cursor()
        cursor.execute("""
            SELECT EXISTS (
                SELECT FROM information_schema.tables 
                WHERE table_schema = 'public' 
                AND table_name = 'analysis_reports'
            )
        """)
        has_analysis_table = cursor.fetchone()[0]
        cursor.close()
        
        # Buscar fixtures que têm stats mas não têm análise
        if has_analysis_table:
            query = """
                SELECT DISTINCT f.id, f.date, f.home_team, f.away_team
                FROM fixtures f
                INNER JOIN team_stats ts ON f.id = ts.fixture_id
                WHERE f.status = 'FINISHED'
                AND f.id NOT IN (
                    SELECT DISTINCT fixture_id 
                    FROM analysis_reports 
                    WHERE prompt_version = %s
                )
                GROUP BY f.id, f.date, f.home_team, f.away_team
                HAVING COUNT(DISTINCT ts.team_name) = 2
                ORDER BY f.date DESC
                LIMIT %s
            """
            params = (prompt_version, limit)
        else:
            query = """
                SELECT DISTINCT f.id, f.date, f.home_team, f.away_team
                FROM fixtures f
                INNER JOIN team_stats ts ON f.id = ts.fixture_id
                WHERE f.status = 'FINISHED'
                GROUP BY f.id, f.date, f.home_team, f.away_team
                HAVING COUNT(DISTINCT ts.team_name) = 2
                ORDER BY f.date DESC
                LIMIT %s
            """
            params = (limit,)
        
        try:
            df = pd.read_sql(query, self.conn, params=params)
            
            if df.empty:
                print(f"✅ Todos os fixtures com stats já têm análise para o prompt '{prompt_version}'")
                return
            
            print(f"\n📋 Encontrados {len(df)} fixtures pendentes para análise")
            
            engine = ClarityEngine()
            success_count = 0
            
            try:
                for idx, row in df.iterrows():
                    fixture_id = row['id']
                    home = row['home_team']
                    away = row['away_team']
                    date = row['date']
                    
                    print(f"[{idx+1}/{len(df)}] 🧠 Analisando: {home} vs {away} ({date})")
                    
                    try:
                        result = engine.run_analysis(fixture_id, prompt_version, force_refresh=force)
                        if result and "error" not in result:
                            success_count += 1
                            print(f"   ✅ Sucesso\n")
                        else:
                            error_msg = result.get("error", "Unknown error") if result else "No result"
                            print(f"   ❌ Erro: {error_msg}\n")
                    except Exception as e:
                        print(f"   ❌ Exceção: {e}\n")
                    
                    if idx < len(df) - 1:
                        time.sleep(1)
                
                print(f"\n📊 Resumo: {success_count}/{len(df)} análises concluídas com sucesso")
                
            finally:
                engine.close()
                
        except Exception as e:
            print(f"❌ Erro ao buscar fixtures pendentes: {e}")
        finally:
            if self.conn:
                self.conn.close()

    # --- NOVOS MÉTODOS DE REALIDADE (TRUTH) ---

    def run_specific_reality_check(self, fixture_id: str):
        """Executa a busca da verdade para UM jogo específico."""
        print(f"\n🕵️‍♀️ A investigar a verdade para: {fixture_id}...")
        
        seeker = RealitySeeker()
        try:
            result = seeker.run_reality_check(fixture_id)
            if result:
                # Novo contrato: score.final + probabilistic_view + tactical_summary
                final_score = result.get("score", {}).get("final")
                luck = result.get("probabilistic_view", {}).get("luck_factor")
                game_flow = result.get("tactical_summary", {}).get("game_flow", "")

                print(f"✅ Sucesso! Score final: {final_score} | Luck: {luck}")
                if game_flow:
                    print(f"📝 Game flow (realidade): {game_flow[:200]}...")
            else:
                print("❌ Falha ao obter verdade.")
        except Exception as e:
            print(f"❌ Erro no Reality Seeker: {e}")
        finally:
            seeker.close()

    def run_truth_batch(self, limit: int = 5):
        """
        Executa a verificação de realidade (Ground Truth) para jogos terminados
        que ainda não têm registo na tabela match_reality.
        """
        if not self.conn: 
            print("❌ Sem conexão DB")
            return
        
        print(f"\n🕵️‍♀️ A procurar {limit} jogos terminados sem relatório de verdade...")
        
        # Query para encontrar jogos acabados SEM realidade na DB
        query = """
            SELECT f.id, f.home_team, f.away_team, f.date
            FROM fixtures f
            LEFT JOIN match_reality mr ON f.id = mr.fixture_id
            WHERE f.status = 'FINISHED' 
            AND mr.fixture_id IS NULL
            ORDER BY f.date DESC
            LIMIT %s
        """
        
        try:
            df = pd.read_sql(query, self.conn, params=(limit,))
            
            if df.empty:
                print("✅ Todos os jogos terminados já têm Relatório de Realidade.")
                return

            print(f"📋 Encontrados {len(df)} jogos para auditar.")
            
            seeker = RealitySeeker()
            
            try:
                for idx, row in df.iterrows():
                    fixture_id = row['id']
                    print(f"[{idx+1}/{len(df)}] 🔍 Auditando: {row['home_team']} vs {row['away_team']} ({row['date']})")
                    
                    result = seeker.run_reality_check(fixture_id)
                    
                    if result:
                        final_score = result.get("score", {}).get("final")
                        luck = result.get("probabilistic_view", {}).get("luck_factor")
                        print(f"   ✅ Verdade obtida: {final_score} (Luck: {luck})\n")
                    else:
                        print("   ❌ Falha ao obter verdade.\n")
                    
                    # Pausa para evitar rate limits do Google Search
                    if idx < len(df) - 1:
                        time.sleep(2)
            finally:
                seeker.close()
                
        except Exception as e:
            print(f"❌ Erro no batch de realidade: {e}")
        finally:
            if self.conn:
                self.conn.close()
