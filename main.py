import argparse
from src.jobs.batch_runner import BatchRunner


def main():
    parser = argparse.ArgumentParser(description="Clarity Engine CLI")
    
    # Argumentos
    parser.add_argument("--test", type=str, help="ID do jogo para teste single")
    parser.add_argument("--truth-single", type=str, help="ID do jogo para verdade single")
    parser.add_argument("--batch", action="store_true", help="Corre batch de pendentes (default 5)")
    parser.add_argument("--truth", action="store_true", help="Corre batch de verdade pendentes")
    
    # Novos Argumentos para Rondas
    parser.add_argument("--round", type=int, help="Número da ronda (Gameweek) para processar")
    parser.add_argument("--mode", choices=["predict", "truth", "both"], default="both", help="Modo para a ronda: predict, truth ou both")
    parser.add_argument("--prompt", type=str, default="hybrid", help="Versão do prompt (hybrid/contrarian)")

    args = parser.parse_args()
    runner = BatchRunner()

    print(f"--- CLARITY ENGINE ({args.prompt}) ---")

    # 1. Single Test Prediction
    if args.test:
        runner.run_specific_match(args.test, prompt_version=args.prompt)
    
    # 2. Single Truth Check
    elif args.truth_single:
        runner.run_specific_reality_check(args.truth_single)

    # 3. Processar por RONDA (O teu novo workflow)
    elif args.round:
        r = args.round
        if args.mode in ["predict", "both"]:
            runner.run_round_predictions(r, prompt_version=args.prompt)
        
        if args.mode in ["truth", "both"]:
            runner.run_round_truth(r)

    # 4. Batches Genéricos (Legado)
    elif args.batch:
        runner.run_next_pending_batch(limit=5, prompt_version=args.prompt)
    elif args.truth:
        runner.run_truth_batch(limit=5)
    
    else:
        print("⚠️  Nenhum argumento válido fornecido.")
        print("Exemplos:")
        print("  python main.py --round 14 --mode predict")
        print("  python main.py --round 14 --mode truth")
        print("  python main.py --round 14 --mode both")
        print("  python main.py --test <fixture_id>")


if __name__ == "__main__":
    main()
