import sys
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parents[1]
sys.path.append(str(PROJECT_ROOT / "src"))

from database.config import get_connection

def reset_ai_tables():
    print("🧹 A limpar memória da AI (Reports + Reality)...")
    conn = get_connection()
    if not conn: return

    try:
        cur = conn.cursor()
        # TRUNCATE é mais rápido e reinicia os IDs
        cur.execute("TRUNCATE TABLE analysis_reports, match_reality RESTART IDENTITY CASCADE;")
        conn.commit()
        print("✅ Sucesso! A base de dados está limpa e pronta para novos testes.")
        print("   (Nota: Os jogos e stats brutos foram mantidos).")
    except Exception as e:
        print(f"❌ Erro ao limpar: {e}")
        conn.rollback()
    finally:
        conn.close()

if __name__ == "__main__":
    confirm = input("Tem a certeza? Isto apaga TODAS as previsões e auditorias. (s/n): ")
    if confirm.lower() == 's':
        reset_ai_tables()
    else:
        print("Operação cancelada.")