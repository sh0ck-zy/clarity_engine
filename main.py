"""
Clarity Engine - Motor de Análise de Futebol
Ponto de entrada para executar análises (single match ou batch).
"""

import sys
from src.jobs.batch_runner import BatchRunner


def main():
    """
    Modos de execução:
    - python main.py                      -> Teste single match prediction
    - python main.py --batch              -> Batch de 5 previsões pendentes
    - python main.py --truth              -> Batch de 5 realidades pendentes (Google Search)
    - python main.py --truth-single <id>  -> Realidade para um jogo específico
    """
    runner = BatchRunner()
    
    # Configuração da Execução
    PROMPT_VERSION = "hybrid"  # ou "contrarian"
    
    # ID para testes rápidos (Hardcoded)
    TEST_MATCH_ID = "2025-12-03_Arsenal_Brentford"
    
    print(f"--- CLARITY ENGINE: EXECUÇÃO ({PROMPT_VERSION}) ---\n")
    
    # Lógica de Argumentos CLI
    if len(sys.argv) > 1:
        command = sys.argv[1]
        
        if command == "--batch":
            # Modo Batch Previsão
            print("Modo: PREDICTION BATCH (5 jogos pendentes)")
            print("=" * 50)
            runner.run_next_pending_batch(limit=5, prompt_version=PROMPT_VERSION, force=False)
            
        elif command == "--truth":
            # Modo Batch Verdade
            print("Modo: TRUTH BATCH (Google Search Grounding)")
            print("=" * 50)
            runner.run_truth_batch(limit=5)
            
        elif command == "--truth-single" and len(sys.argv) > 2:
            # Modo Single Verdade
            fx_id = sys.argv[2]
            print(f"Modo: SINGLE TRUTH CHECK ({fx_id})")
            print("=" * 50)
            runner.run_specific_reality_check(fx_id)
            
        elif command == "--test" and len(sys.argv) > 2:
             # Modo Single Previsão (com ID customizado)
            fx_id = sys.argv[2]
            print(f"Modo: SINGLE PREDICTION ({fx_id})")
            print("=" * 50)
            runner.run_specific_match(fx_id, prompt_version=PROMPT_VERSION, force=False)
            
    else:
        # Modo Default (Teste Hardcoded)
        print("Modo: SINGLE MATCH TEST (Default)")
        print("=" * 50)
        print(f"Fixture: {TEST_MATCH_ID}")
        print()
        runner.run_specific_match(TEST_MATCH_ID, prompt_version=PROMPT_VERSION, force=False)


if __name__ == "__main__":
    main()