#!/usr/bin/env python3
"""
Batch Analysis - Aggregate insights across multiple rounds.

Usage:
    python scripts/batch_analysis.py PL_R25 PL_R26 PL_R27
    python scripts/batch_analysis.py --all-pl  # All PL rounds with narratives
"""

import argparse
import json
from pathlib import Path
from datetime import datetime
from collections import defaultdict

PROJECT_ROOT = Path(__file__).resolve().parents[1]
OUTPUT_DIR = PROJECT_ROOT / "output" / "rounds"


def load_round_data(round_name: str) -> dict:
    """Load all data for a round."""
    round_dir = OUTPUT_DIR / round_name
    
    if not round_dir.exists():
        return None
    
    data = {
        "round": round_name,
        "matches": [],
        "quality": None,
        "validation": None,
        "config": None,
    }
    
    # Load config
    config_file = round_dir / "round_config.json"
    if config_file.exists():
        data["config"] = json.loads(config_file.read_text())
    
    # Load quality report
    quality_file = round_dir / "quality_report.json"
    if quality_file.exists():
        data["quality"] = json.loads(quality_file.read_text())
    
    # Load validation report
    validation_file = round_dir / "validation_report.json"
    if validation_file.exists():
        data["validation"] = json.loads(validation_file.read_text())
    
    # Load per-match data
    matches_dir = round_dir / "matches"
    if matches_dir.exists():
        for match_dir in sorted(matches_dir.iterdir()):
            if not match_dir.is_dir():
                continue
            
            match_data = {"name": match_dir.name}
            
            # Load context
            context_file = match_dir / "context.json"
            if context_file.exists():
                match_data["context"] = json.loads(context_file.read_text())
            
            # Load narrative
            narrative_file = match_dir / "narrative.json"
            if narrative_file.exists():
                match_data["narrative"] = json.loads(narrative_file.read_text())
            
            # Load report
            report_file = match_dir / "report.json"
            if report_file.exists():
                match_data["report"] = json.loads(report_file.read_text())
            
            data["matches"].append(match_data)
    
    return data


def analyze_batch(rounds: list[dict]) -> dict:
    """Analyze a batch of rounds."""
    
    analysis = {
        "generated_at": datetime.now().isoformat(),
        "rounds_analyzed": len(rounds),
        "total_matches": 0,
        
        # Quality metrics
        "quality": {
            "mean_mis": 0,
            "min_mis": 100,
            "max_mis": 0,
            "by_section": defaultdict(list),
        },
        
        # Prediction metrics
        "predictions": {
            "total": 0,
            "correct": 0,
            "accuracy": 0,
            "by_result": {"H": {"total": 0, "correct": 0}, "D": {"total": 0, "correct": 0}, "A": {"total": 0, "correct": 0}},
        },
        
        # Claims metrics
        "claims": {
            "total_extracted": 0,
            "total_verifiable": 0,
            "total_correct": 0,
            "accuracy": 0,
        },
        
        # System metadata (what we're using)
        "system": {
            "llm_model": None,
            "llm_versions": set(),
            "ml_model": None,
            "ml_features": [],
            "data_sources": ["team_states", "fotmob_player_performances", "manager_history", "fotmob_matches"],
            "total_tokens": 0,
            "total_cost": 0,
        },
        
        # Patterns and insights
        "insights": [],
    }
    
    mis_scores = []
    
    for round_data in rounds:
        if not round_data:
            continue
        
        analysis["total_matches"] += len(round_data["matches"])
        
        # Quality
        if round_data["quality"]:
            q = round_data["quality"]
            if "mean_mis" in q:
                # Convert from decimal to percentage if needed
                mis_val = q["mean_mis"]
                if mis_val < 1:
                    mis_val = mis_val * 100
                mis_scores.append(mis_val)
        
        # Validation
        if round_data["validation"]:
            v = round_data["validation"]
            analysis["predictions"]["total"] += v.get("matches_validated", 0)
            correct = int(v.get("prediction_accuracy", 0) * v.get("matches_validated", 0))
            analysis["predictions"]["correct"] += correct
            
            # Claims
            for match in v.get("per_match", []):
                analysis["claims"]["total_extracted"] += match.get("claims_extracted", 0)
                analysis["claims"]["total_verifiable"] += match.get("verifiable", 0)
                analysis["claims"]["total_correct"] += match.get("correct", 0)
        
        # System metadata from narratives
        for match in round_data["matches"]:
            if "narrative" in match:
                n = match["narrative"]
                analysis["system"]["llm_model"] = n.get("model", "unknown")
                analysis["system"]["llm_versions"].add(n.get("model", "unknown"))
                analysis["system"]["total_tokens"] += n.get("tokens_used", 0)
                analysis["system"]["total_cost"] += n.get("cost_estimate", 0)
            
            if "context" in match and "ml_inference" in match["context"]:
                ml = match["context"]["ml_inference"]
                if ml.get("drivers"):
                    for d in ml["drivers"]:
                        feat = d.get("feature")
                        if feat and feat not in analysis["system"]["ml_features"]:
                            analysis["system"]["ml_features"].append(feat)
        
        # Config
        if round_data["config"]:
            analysis["system"]["ml_model"] = round_data["config"].get("model_version", "unknown")
    
    # Compute aggregates
    if mis_scores:
        analysis["quality"]["mean_mis"] = round(sum(mis_scores) / len(mis_scores), 1)
        analysis["quality"]["min_mis"] = min(mis_scores)
        analysis["quality"]["max_mis"] = max(mis_scores)
    
    if analysis["predictions"]["total"] > 0:
        analysis["predictions"]["accuracy"] = round(
            analysis["predictions"]["correct"] / analysis["predictions"]["total"] * 100, 1
        )
    
    if analysis["claims"]["total_verifiable"] > 0:
        analysis["claims"]["accuracy"] = round(
            analysis["claims"]["total_correct"] / analysis["claims"]["total_verifiable"] * 100, 1
        )
    
    # Convert set to list for JSON
    analysis["system"]["llm_versions"] = list(analysis["system"]["llm_versions"])
    analysis["system"]["total_cost"] = round(analysis["system"]["total_cost"], 4)
    
    # Generate insights
    analysis["insights"] = generate_insights(analysis, rounds)
    
    return analysis


def generate_insights(analysis: dict, rounds: list[dict]) -> list[str]:
    """Generate human-readable insights from the batch analysis."""
    insights = []
    
    # Quality insight
    mis = analysis["quality"]["mean_mis"]
    if mis >= 90:
        insights.append(f"✅ Quality excellent: {mis}% MIS average across all rounds")
    elif mis >= 70:
        insights.append(f"🟡 Quality good: {mis}% MIS average, some room for improvement")
    else:
        insights.append(f"🔴 Quality needs work: {mis}% MIS average below threshold")
    
    # Prediction insight
    pred_acc = analysis["predictions"]["accuracy"]
    if pred_acc >= 50:
        insights.append(f"✅ Predictions above average: {pred_acc}% correct (football baseline ~33%)")
    elif pred_acc >= 33:
        insights.append(f"🟡 Predictions at baseline: {pred_acc}% correct")
    else:
        insights.append(f"🔴 Predictions below baseline: {pred_acc}% correct")
    
    # Claims insight
    claims_acc = analysis["claims"]["accuracy"]
    if claims_acc >= 60:
        insights.append(f"✅ Narrative claims mostly accurate: {claims_acc}%")
    elif claims_acc >= 40:
        insights.append(f"🟡 Narrative claims need improvement: {claims_acc}%")
    else:
        insights.append(f"🔴 Narrative claims low accuracy: {claims_acc}% - review prompts")
    
    # Cost insight
    cost = analysis["system"]["total_cost"]
    matches = analysis["total_matches"]
    if matches > 0:
        cost_per_match = cost / matches
        insights.append(f"💰 Cost efficiency: ${cost:.4f} total, ${cost_per_match:.4f}/match")
    
    # Variance insight
    if len(rounds) >= 3:
        pred_by_round = []
        for rd in rounds:
            if rd and rd.get("validation"):
                pred_by_round.append(rd["validation"].get("prediction_accuracy", 0) * 100)
        if pred_by_round:
            variance = max(pred_by_round) - min(pred_by_round)
            if variance > 30:
                insights.append(f"⚠️ High variance between rounds: {variance:.0f}pp spread - some rounds atypical")
    
    return insights


def print_batch_report(analysis: dict):
    """Print a formatted batch report."""
    print("=" * 70)
    print("BATCH ANALYSIS REPORT")
    print("=" * 70)
    print(f"Generated: {analysis['generated_at']}")
    print(f"Rounds: {analysis['rounds_analyzed']} | Matches: {analysis['total_matches']}")
    print()
    
    print("─" * 70)
    print("SYSTEM METADATA (What We're Using)")
    print("─" * 70)
    sys = analysis["system"]
    print(f"  LLM Model:     {sys['llm_model']}")
    print(f"  ML Model:      {sys['ml_model']}")
    print(f"  ML Features:   {', '.join(sys['ml_features'][:5])}...")
    print(f"  Data Sources:  {', '.join(sys['data_sources'])}")
    print(f"  Total Tokens:  {sys['total_tokens']:,}")
    print(f"  Total Cost:    ${sys['total_cost']:.4f}")
    print()
    
    print("─" * 70)
    print("QUALITY METRICS")
    print("─" * 70)
    q = analysis["quality"]
    print(f"  Mean MIS:  {q['mean_mis']}%")
    print(f"  Range:     {q['min_mis']}% - {q['max_mis']}%")
    print()
    
    print("─" * 70)
    print("PREDICTION METRICS")
    print("─" * 70)
    p = analysis["predictions"]
    print(f"  Accuracy:  {p['accuracy']}% ({p['correct']}/{p['total']})")
    print()
    
    print("─" * 70)
    print("NARRATIVE CLAIMS")
    print("─" * 70)
    c = analysis["claims"]
    print(f"  Extracted:   {c['total_extracted']}")
    print(f"  Verifiable:  {c['total_verifiable']}")
    print(f"  Correct:     {c['total_correct']}")
    print(f"  Accuracy:    {c['accuracy']}%")
    print()
    
    print("─" * 70)
    print("INSIGHTS")
    print("─" * 70)
    for insight in analysis["insights"]:
        print(f"  {insight}")
    print()
    
    print("=" * 70)


def main():
    parser = argparse.ArgumentParser(description="Batch analysis across rounds")
    parser.add_argument("rounds", nargs="*", help="Round names (e.g., PL_R25 PL_R26)")
    parser.add_argument("--all-pl", action="store_true", help="Analyze all PL rounds with narratives")
    parser.add_argument("--output", "-o", help="Output JSON file")
    args = parser.parse_args()
    
    round_names = args.rounds
    
    if args.all_pl:
        # Find all PL rounds
        round_names = []
        for d in sorted(OUTPUT_DIR.iterdir()):
            if d.is_dir() and d.name.startswith("PL_R"):
                # Check if has narratives
                matches_dir = d / "matches"
                if matches_dir.exists():
                    for m in matches_dir.iterdir():
                        if (m / "narrative.json").exists():
                            round_names.append(d.name)
                            break
    
    if not round_names:
        print("No rounds specified. Use --all-pl or provide round names.")
        return
    
    print(f"Loading {len(round_names)} rounds: {', '.join(round_names)}")
    
    rounds = []
    for name in round_names:
        data = load_round_data(name)
        if data:
            rounds.append(data)
        else:
            print(f"  Warning: {name} not found")
    
    analysis = analyze_batch(rounds)
    print_batch_report(analysis)
    
    if args.output:
        Path(args.output).write_text(json.dumps(analysis, indent=2))
        print(f"Saved to: {args.output}")
    
    # Also save to output dir
    batch_file = OUTPUT_DIR / "batch_analysis.json"
    batch_file.write_text(json.dumps(analysis, indent=2))
    print(f"Saved to: {batch_file}")


if __name__ == "__main__":
    main()
