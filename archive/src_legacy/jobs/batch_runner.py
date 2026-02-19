from typing import Iterable
import time
import pandas as pd

from src.analysis.predictor import ClarityEngine
from src.analysis.reality import RealitySeeker  # IMPORTANTE: Módulo da Verdade
from src.analysis.evaluator import AnalysisEvaluator
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

    def run_round_predictions(self, round_id: int, season: str = "2025-2026", prompt_version: str = "hybrid"):
        """Gera previsões para TODOS os jogos de uma ronda específica."""
        print(f"\n🚀 A iniciar previsões para a Ronda {round_id} ({season})...")
        
        if not self.conn:
            return

        query = """
            SELECT id, home_team, away_team 
            FROM fixtures 
            WHERE season = %s AND round = %s 
            ORDER BY date ASC
        """
        
        try:
            df = pd.read_sql(query, self.conn, params=(season, round_id))
            if df.empty:
                print(f"⚠️  Nenhum jogo encontrado para a Ronda {round_id}.")
                return

            print(f"📋 Encontrados {len(df)} jogos na Ronda {round_id}.")
            engine = ClarityEngine()

            for idx, row in df.iterrows():
                print(f"[{idx+1}/{len(df)}] 🧠 Analisando: {row['home_team']} vs {row['away_team']}")
                engine.run_analysis(row['id'], prompt_version, force_refresh=False)
            
            engine.close()
            print(f"✅ Ronda {round_id} concluída (Previsões).")

        except Exception as e:
            print(f"❌ Erro na Ronda {round_id}: {e}")

    def run_round_truth(self, round_id: int, season: str = "2025-2026"):
        """Gera a 'Verdade' apenas para jogos que AINDA NÃO têm relatório."""
        print(f"\n🕵️‍♀️ A auditar a verdade para a Ronda {round_id} ({season})...")
        
        if not self.conn:
            return

        query = """
            SELECT f.id, f.home_team, f.away_team, f.date 
            FROM fixtures f
            LEFT JOIN match_reality mr ON f.id = mr.fixture_id
            WHERE f.season = %s 
              AND f.round = %s 
              AND f.status = 'FINISHED'
              AND mr.fixture_id IS NULL 
            ORDER BY f.date ASC
        """
        
        try:
            df = pd.read_sql(query, self.conn, params=(season, round_id))
            if df.empty:
                print(f"✅ Ronda {round_id} já está totalmente auditada (ou sem jogos terminados).")
                return

            print(f"📋 A auditar {len(df)} jogos NOVOS da Ronda {round_id}.")
            seeker = RealitySeeker()

            for idx, row in df.iterrows():
                print(f"[{idx+1}/{len(df)}] 🔍 Auditando: {row['home_team']} vs {row['away_team']}")
                seeker.run_reality_check(row['id'])
                time.sleep(1)  # Pausa simpática para a API
            
            if hasattr(seeker, 'close'):
                seeker.close()
            
            print(f"✅ Novos jogos da Ronda {round_id} auditados.")

        except Exception as e:
            print(f"❌ Erro na Auditoria da Ronda {round_id}: {e}")

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
        print(f"\n🕵️‍♀️ A investigar a verdade para: {fixture_id}...")
        
        seeker = RealitySeeker()
        try:
            result = seeker.run_reality_check(fixture_id)
            if result:
                # --- ATUALIZADO PARA NOVA ESTRUTURA ---
                final_score = result.get("score", {}).get("final", "N/A")
                
                # Campos novos do Auditor Forense
                truth = result.get("truth_vector", {})
                audit = result.get("stat_audit", {})
                
                winner = truth.get("actual_winner", "?")
                luck = truth.get("luck_factor", "?")
                lie = audit.get("stat_lie_detected", False)
                
                print(f"✅ Sucesso! Score: {final_score} | Vencedor Real: {winner}")
                print(f"⚖️  Luck Factor: {luck} | Stats Mentiram? {'SIM' if lie else 'Não'}")
                print(f"📝 Veredicto: {audit.get('explanation', '')[:150]}...")
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
    
    def run_round_predictions_for_prompts(self, round_id: int, prompt_versions: list, season: str = "2025-2026", progress_callback=None):
        """
        Gera previsões para TODOS os jogos de uma ronda específica para múltiplos prompts.
        
        Args:
            round_id: Número da ronda
            prompt_versions: Lista de versões de prompt (ex: ["hybrid", "v3"])
            season: Época
            progress_callback: Função callback(opcional) chamada com (current, total, fixture_id, prompt_version)
        """
        print(f"\n🚀 A iniciar previsões multi-prompt para a Ronda {round_id} ({season})...")
        print(f"📝 Prompts: {', '.join(prompt_versions)}")
        
        if not self.conn:
            return
        
        query = """
            SELECT id, home_team, away_team 
            FROM fixtures 
            WHERE season = %s AND round = %s 
            ORDER BY date ASC
        """
        
        try:
            df = pd.read_sql(query, self.conn, params=(season, round_id))
            if df.empty:
                print(f"⚠️  Nenhum jogo encontrado para a Ronda {round_id}.")
                return
            
            total_tasks = len(df) * len(prompt_versions)
            current_task = 0
            
            engine = ClarityEngine()
            
            try:
                for prompt_version in prompt_versions:
                    print(f"\n📋 Processando prompt: {prompt_version}")
                    for idx, row in df.iterrows():
                        current_task += 1
                        if progress_callback:
                            progress_callback(current_task, total_tasks, row['id'], prompt_version)
                        
                        print(f"[{current_task}/{total_tasks}] 🧠 Analisando ({prompt_version}): {row['home_team']} vs {row['away_team']}")
                        engine.run_analysis(row['id'], prompt_version, force_refresh=False)
                        time.sleep(0.5)  # Pequena pausa entre análises
                
                print(f"\n✅ Ronda {round_id} concluída para todos os prompts.")
            finally:
                engine.close()
                
        except Exception as e:
            print(f"❌ Erro na Ronda {round_id}: {e}")
            import traceback
            traceback.print_exc()
    
    def generate_reality_for_finished_matches(
        self,
        season: str = "2025-2026",
        limit: int = None,
        progress_callback=None
    ):
        """
        Gera match_reality para jogos finalizados que não têm reality data.

        Args:
            season: Época a processar
            limit: Número máximo de jogos (None = todos)
            progress_callback: Função callback(current, total, fixture_id)

        Returns:
            dict: Resumo com contagens de sucesso/falha
        """
        print(f"\n🕵️ A gerar Reality Data para jogos finalizados ({season})...")

        if not self.conn:
            print("❌ Sem conexão DB")
            return {"success": 0, "failed": 0, "skipped": 0}

        # Query para encontrar jogos finalizados SEM reality data
        query = """
            SELECT f.id, f.home_team, f.away_team, f.date
            FROM fixtures f
            LEFT JOIN match_reality mr ON f.id = mr.fixture_id
            WHERE f.season = %s
              AND f.status = 'FINISHED'
              AND mr.fixture_id IS NULL
            ORDER BY f.date DESC
        """

        params = [season]
        if limit:
            query += " LIMIT %s"
            params.append(limit)

        try:
            df = pd.read_sql(query, self.conn, params=tuple(params))

            if df.empty:
                print("✅ Todos os jogos finalizados já têm Reality Data.")
                return {"success": 0, "failed": 0, "skipped": 0}

            print(f"📋 Encontrados {len(df)} jogos para gerar reality data.")

            seeker = RealitySeeker()
            success_count = 0
            failed_count = 0

            try:
                for idx, row in df.iterrows():
                    fixture_id = row['id']

                    if progress_callback:
                        progress_callback(idx + 1, len(df), fixture_id)

                    print(f"[{idx+1}/{len(df)}] 🔍 Reality: {row['home_team']} vs {row['away_team']} ({row['date']})")

                    try:
                        result = seeker.run_reality_check(fixture_id)

                        if result:
                            success_count += 1
                            print(f"   ✅ Reality data gerada\n")
                        else:
                            failed_count += 1
                            print(f"   ❌ Falha ao gerar reality data\n")
                    except Exception as e:
                        failed_count += 1
                        print(f"   ❌ Erro: {e}\n")

                    # Pausa para evitar rate limits
                    if idx < len(df) - 1:
                        time.sleep(2)

                print(f"\n📊 Resumo: {success_count} sucesso, {failed_count} falhas")
                return {"success": success_count, "failed": failed_count, "skipped": 0}

            finally:
                if hasattr(seeker, 'close'):
                    seeker.close()

        except Exception as e:
            print(f"❌ Erro ao gerar reality data: {e}")
            import traceback
            traceback.print_exc()
            return {"success": 0, "failed": 0, "skipped": 0}

    def evaluate_analyses_batch(
        self,
        season: str = "2025-2026",
        prompt_version: str = None,
        limit: int = None,
        progress_callback=None
    ):
        """
        Gera analysis_evaluations para análises de jogos com reality data.

        Args:
            season: Época a processar
            prompt_version: Versão específica do prompt (None = todas)
            limit: Número máximo de análises (None = todas)
            progress_callback: Função callback(current, total, report_id)

        Returns:
            dict: Resumo com contagens de sucesso/falha
        """
        print(f"\n🔍 A avaliar análises ({season})...")

        if not self.conn:
            print("❌ Sem conexão DB")
            return {"success": 0, "failed": 0, "skipped": 0}

        # Build query - buscar análises que têm reality mas não têm evaluation
        query = """
            SELECT ar.id, ar.fixture_id, ar.prompt_version, f.home_team, f.away_team, f.date
            FROM analysis_reports ar
            JOIN fixtures f ON ar.fixture_id = f.id
            JOIN match_reality mr ON f.id = mr.fixture_id
            LEFT JOIN analysis_evaluations ae ON ar.id = ae.report_id
            WHERE f.season = %s
              AND f.status = 'FINISHED'
              AND ae.report_id IS NULL
        """

        params = [season]

        if prompt_version:
            query += " AND ar.prompt_version = %s"
            params.append(prompt_version)

        query += " ORDER BY f.date DESC"

        if limit:
            query += " LIMIT %s"
            params.append(limit)
        
        try:
            df = pd.read_sql(query, self.conn, params=tuple(params))

            if df.empty:
                print("✅ Todas as análises com reality data já foram avaliadas.")
                return {"success": 0, "failed": 0, "skipped": 0}

            print(f"📋 Encontradas {len(df)} análises para avaliar.")

            evaluator = AnalysisEvaluator()
            success_count = 0
            failed_count = 0
            skipped_count = 0

            try:
                for idx, row in df.iterrows():
                    report_id = row['id']

                    if progress_callback:
                        progress_callback(idx + 1, len(df), report_id)

                    print(f"[{idx+1}/{len(df)}] 🔍 Avaliando: {row['home_team']} vs {row['away_team']} ({row['prompt_version']})")

                    try:
                        result = evaluator.evaluate_analysis(report_id, force_refresh=False)
                        if result:
                            success_count += 1
                            print(f"   ✅ Avaliação concluída\n")
                        else:
                            skipped_count += 1
                            print(f"   ⚠️  Avaliação falhou ou foi ignorada\n")
                    except Exception as e:
                        failed_count += 1
                        print(f"   ❌ Erro: {e}\n")

                    time.sleep(0.5)  # Pausa entre avaliações

                print(f"\n📊 Resumo: {success_count} sucesso, {failed_count} falhas, {skipped_count} ignoradas")
                return {"success": success_count, "failed": failed_count, "skipped": skipped_count}

            finally:
                evaluator.close()

        except Exception as e:
            print(f"❌ Erro ao avaliar análises: {e}")
            import traceback
            traceback.print_exc()
            return {"success": 0, "failed": 0, "skipped": 0}

    def evaluate_round_analyses(self, round_id: int, prompt_versions: list = None, season: str = "2025-2026", progress_callback=None):
        """
        Avalia análises de uma ronda específica (mantido para compatibilidade).
        DEPRECATED: Use evaluate_analyses_batch() instead.
        """
        print(f"\n🔍 A avaliar análises da Ronda {round_id} ({season})...")

        if not self.conn:
            print("❌ Sem conexão DB")
            return {"success": 0, "failed": 0, "skipped": 0}

        # Build query
        if prompt_versions:
            placeholders = ','.join(['%s'] * len(prompt_versions))
            query = f"""
                SELECT ar.id, ar.fixture_id, ar.prompt_version, f.home_team, f.away_team
                FROM analysis_reports ar
                JOIN fixtures f ON ar.fixture_id = f.id
                LEFT JOIN match_reality mr ON f.id = mr.fixture_id
                WHERE f.season = %s
                  AND f.round = %s
                  AND f.status = 'FINISHED'
                  AND mr.fixture_id IS NOT NULL
                  AND ar.prompt_version IN ({placeholders})
                ORDER BY f.date ASC
            """
            params = (season, round_id) + tuple(prompt_versions)
        else:
            query = """
                SELECT ar.id, ar.fixture_id, ar.prompt_version, f.home_team, f.away_team
                FROM analysis_reports ar
                JOIN fixtures f ON ar.fixture_id = f.id
                LEFT JOIN match_reality mr ON f.id = mr.fixture_id
                WHERE f.season = %s
                  AND f.round = %s
                  AND f.status = 'FINISHED'
                  AND mr.fixture_id IS NOT NULL
                ORDER BY f.date ASC
            """
            params = (season, round_id)

        try:
            df = pd.read_sql(query, self.conn, params=params)

            if df.empty:
                print(f"⚠️  Nenhuma análise encontrada para avaliar na Ronda {round_id}.")
                return {"success": 0, "failed": 0, "skipped": 0}

            print(f"📋 Encontradas {len(df)} análises para avaliar.")

            evaluator = AnalysisEvaluator()
            success_count = 0
            failed_count = 0
            skipped_count = 0

            try:
                for idx, row in df.iterrows():
                    report_id = row['id']

                    if progress_callback:
                        progress_callback(idx + 1, len(df), report_id)

                    print(f"[{idx+1}/{len(df)}] 🔍 Avaliando: {row['home_team']} vs {row['away_team']} ({row['prompt_version']})")

                    try:
                        result = evaluator.evaluate_analysis(report_id, force_refresh=False)
                        if result:
                            success_count += 1
                            print(f"   ✅ Avaliação concluída\n")
                        else:
                            skipped_count += 1
                            print(f"   ⚠️  Avaliação falhou ou foi ignorada\n")
                    except Exception as e:
                        failed_count += 1
                        print(f"   ❌ Erro: {e}\n")

                    time.sleep(0.5)  # Pausa entre avaliações

                print(f"\n📊 Resumo: {success_count} sucesso, {failed_count} falhas, {skipped_count} ignoradas")
                return {"success": success_count, "failed": failed_count, "skipped": skipped_count}

            finally:
                evaluator.close()

        except Exception as e:
            print(f"❌ Erro ao buscar análises: {e}")
            import traceback
            traceback.print_exc()
            return {"success": 0, "failed": 0, "skipped": 0}