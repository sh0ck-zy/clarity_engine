#!/usr/bin/env python3
"""
Análise J26 - Testa 3 prompts em 5 jogos
"""
import sys
import json
from pathlib import Path
from datetime import datetime

PROJECT_ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(PROJECT_ROOT))

from openai import OpenAI
from dotenv import load_dotenv
import os

load_dotenv(PROJECT_ROOT / ".env")

from src.builders.robust_builder import RobustBuilder

# Jogos J26 com resultados reais
MATCHES = [
    ("2026-02-10_West_Ham_Manchester_Utd", "West Ham vs Man United", "1-1", "D"),
    ("2026-02-11_Manchester_City_Fulham", "Man City vs Fulham", "3-0", "H"),
    ("2026-02-11_Sunderland_Liverpool", "Sunderland vs Liverpool", "0-1", "A"),
    ("2026-02-12_Brentford_Arsenal", "Brentford vs Arsenal", "1-1", "D"),
    ("2026-02-11_Aston_Villa_Brighton", "Aston Villa vs Brighton", "1-0", "H"),
]

# Carregar prompts
def load_prompt(name):
    path = PROJECT_ROOT / "prompts" / f"{name}.txt"
    return path.read_text()

PROMPTS = {
    "v4_calibrated": load_prompt("v4_calibrated"),
    "v5_probabilistic": load_prompt("v5_probabilistic"),
    "v6_know_ball": load_prompt("v6_know_ball"),
}

def analyze_match(builder, client, fixture_id, prompt_name, prompt_text, model="gpt-4o"):
    """Corre uma análise para um jogo com um prompt específico"""
    ctx = builder.build_context(fixture_id)
    if "error" in ctx:
        return {"error": ctx["error"]}
    
    context_str = builder.format_for_llm(ctx)
    
    try:
        response = client.chat.completions.create(
            model=model,
            messages=[
                {"role": "system", "content": prompt_text},
                {"role": "user", "content": context_str}
            ],
            response_format={"type": "json_object"},
            temperature=0.3
        )
        return json.loads(response.choices[0].message.content)
    except Exception as e:
        return {"error": str(e)}

def extract_prediction(result, prompt_name):
    """Extrai previsão normalizada de cada formato de prompt"""
    if "error" in result:
        return {"result": "ERR", "score": "?", "confidence": 0}
    
    if prompt_name == "v5_probabilistic":
        # V5 dá probabilidades, não resultado direto
        h = result.get("home_win_pct", 0)
        d = result.get("draw_pct", 0)
        a = result.get("away_win_pct", 0)
        
        if h >= d and h >= a:
            res = "H"
        elif a >= d and a >= h:
            res = "A"
        else:
            res = "D"
        
        return {
            "result": res,
            "score": f"H:{h}% D:{d}% A:{a}%",
            "confidence": max(h, d, a),
            "probs": {"H": h, "D": d, "A": a}
        }
    else:
        # V4 e V6 têm formato similar
        pred = result.get("prediction", {})
        return {
            "result": pred.get("result", "?"),
            "score": pred.get("scoreline", "?"),
            "confidence": pred.get("confidence", 0)
        }

def main():
    print("=" * 60)
    print("CLARITY ENGINE - ANÁLISE J26")
    print("=" * 60)
    
    builder = RobustBuilder()
    client = OpenAI(api_key=os.getenv("OPENAI_API_KEY"))
    
    results = {}
    
    for fixture_id, match_name, real_score, real_result in MATCHES:
        print(f"\n📊 {match_name}")
        print(f"   Resultado real: {real_score} ({real_result})")
        print("-" * 50)
        
        results[fixture_id] = {
            "match_name": match_name,
            "real_score": real_score,
            "real_result": real_result,
            "analyses": {}
        }
        
        for prompt_name, prompt_text in PROMPTS.items():
            print(f"   🔄 {prompt_name}...", end=" ", flush=True)
            
            analysis = analyze_match(builder, client, fixture_id, prompt_name, prompt_text)
            prediction = extract_prediction(analysis, prompt_name)
            
            correct = prediction["result"] == real_result
            emoji = "✅" if correct else "❌"
            
            print(f"{emoji} {prediction['result']} ({prediction['score']})")
            
            results[fixture_id]["analyses"][prompt_name] = {
                "full": analysis,
                "prediction": prediction,
                "correct": correct
            }
    
    # Guardar resultados
    output_dir = Path(__file__).parent
    
    # Ficheiro por jogo
    for fixture_id, data in results.items():
        match_file = output_dir / f"{fixture_id.split('_', 1)[1].replace('_', '-')}.md"
        with open(match_file, "w") as f:
            f.write(f"# {data['match_name']}\n\n")
            f.write(f"**Resultado Real:** {data['real_score']} ({data['real_result']})\n\n")
            
            for prompt_name, analysis in data["analyses"].items():
                pred = analysis["prediction"]
                emoji = "✅" if analysis["correct"] else "❌"
                
                f.write(f"## {prompt_name} {emoji}\n\n")
                f.write(f"**Previsão:** {pred['result']} - {pred['score']}\n")
                f.write(f"**Confiança:** {pred['confidence']}%\n\n")
                
                if prompt_name == "v5_probabilistic" and "probs" in pred:
                    f.write(f"**Probabilidades:** H={pred['probs']['H']}% D={pred['probs']['D']}% A={pred['probs']['A']}%\n\n")
                
                f.write("```json\n")
                f.write(json.dumps(analysis["full"], indent=2, ensure_ascii=False))
                f.write("\n```\n\n")
    
    # Resumo
    with open(output_dir / "RESUMO.md", "w") as f:
        f.write("# RESUMO J26 - Análise de Prompts\n\n")
        f.write(f"**Data da análise:** {datetime.now().strftime('%Y-%m-%d %H:%M')}\n\n")
        
        # Tabela de resultados
        f.write("## Matriz de Previsões\n\n")
        f.write("| Jogo | Real | v4_calibrated | v5_probabilistic | v6_know_ball |\n")
        f.write("|------|------|---------------|------------------|-------------|\n")
        
        scores = {"v4_calibrated": 0, "v5_probabilistic": 0, "v6_know_ball": 0}
        
        for fixture_id, data in results.items():
            row = f"| {data['match_name']} | {data['real_result']} |"
            for prompt_name in ["v4_calibrated", "v5_probabilistic", "v6_know_ball"]:
                analysis = data["analyses"][prompt_name]
                pred = analysis["prediction"]
                emoji = "✅" if analysis["correct"] else "❌"
                row += f" {emoji} {pred['result']} |"
                if analysis["correct"]:
                    scores[prompt_name] += 1
            f.write(row + "\n")
        
        f.write("\n## Pontuação Final\n\n")
        f.write("| Prompt | Acertos | % |\n")
        f.write("|--------|---------|---|\n")
        
        for prompt_name, score in sorted(scores.items(), key=lambda x: -x[1]):
            pct = (score / len(MATCHES)) * 100
            f.write(f"| {prompt_name} | {score}/5 | {pct:.0f}% |\n")
        
        f.write("\n## Análise por Jogo\n\n")
        for fixture_id, data in results.items():
            f.write(f"### {data['match_name']}\n")
            f.write(f"**Real:** {data['real_score']} ({data['real_result']})\n\n")
            
            for prompt_name in ["v4_calibrated", "v5_probabilistic", "v6_know_ball"]:
                analysis = data["analyses"][prompt_name]
                pred = analysis["prediction"]
                emoji = "✅" if analysis["correct"] else "❌"
                f.write(f"- **{prompt_name}:** {emoji} {pred['result']} ({pred['score']})\n")
            f.write("\n")
    
    # JSON completo
    with open(output_dir / "results.json", "w") as f:
        json.dump(results, f, indent=2, ensure_ascii=False, default=str)
    
    print("\n" + "=" * 60)
    print("PONTUAÇÃO FINAL:")
    for prompt_name, score in sorted(scores.items(), key=lambda x: -x[1]):
        print(f"  {prompt_name}: {score}/5 ({(score/5)*100:.0f}%)")
    print("=" * 60)
    
    builder.close()
    print(f"\n✅ Resultados guardados em: {output_dir}")

if __name__ == "__main__":
    main()
