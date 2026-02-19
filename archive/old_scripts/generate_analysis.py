#!/usr/bin/env python
"""Generate analysis for a fixture using Gemini."""

import json
import os
import sys
from pathlib import Path
from dataclasses import asdict

PROJECT_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(PROJECT_ROOT))

from dotenv import load_dotenv
load_dotenv(PROJECT_ROOT / '.env')

from src.analysis.context_builder_v2 import ContextBuilderV2
import google.generativeai as genai


def generate_analysis(fixture_id: str):
    # Build context
    print(f"Building context for {fixture_id}...")
    builder = ContextBuilderV2()
    context = builder.build_context(fixture_id)
    
    if not context:
        print('Failed to build context')
        return None
    
    context_dict = asdict(context)
    
    # Read prompt
    prompt_path = PROJECT_ROOT / 'prompts' / 'v5_probabilistic.txt'
    with open(prompt_path, 'r') as f:
        system_prompt = f.read()
    
    # Call Gemini
    genai.configure(api_key=os.getenv('GOOGLE_API_KEY'))
    model = genai.GenerativeModel('gemini-2.0-flash')
    
    print('Calling Gemini...')
    
    full_prompt = system_prompt + '\n\nMATCH DATA:\n' + json.dumps(context_dict, default=str)
    response = model.generate_content(full_prompt)
    
    result_text = response.text
    
    # Parse JSON
    clean_text = result_text.strip()
    if clean_text.startswith('```'):
        clean_text = clean_text.split('\n', 1)[1]
        clean_text = clean_text.rsplit('```', 1)[0]
    
    try:
        result = json.loads(clean_text)
    except:
        result = {"raw": result_text}
    
    return {
        "context": context_dict,
        "prompt": system_prompt,
        "result": result
    }


if __name__ == "__main__":
    fixture_id = sys.argv[1] if len(sys.argv) > 1 else "2026-02-06_Leeds_United_Nott'ham_Forest"
    
    output = generate_analysis(fixture_id)
    
    if output:
        print("\n" + "="*60)
        print("CONTEXT (summary):")
        print("="*60)
        ctx = output["context"]
        print(f"Fixture: {ctx['fixture_id']}")
        print(f"Date: {ctx['match_date']}")
        print(f"Home: {ctx['home']['identity']['name']} (Elo: {ctx['home']['identity']['elo']})")
        print(f"Away: {ctx['away']['identity']['name']} (Elo: {ctx['away']['identity']['elo']})")
        print(f"Home Form: {ctx['home']['form']['results']} ({ctx['home']['form']['points']} pts)")
        print(f"Away Form: {ctx['away']['form']['results']} ({ctx['away']['form']['points']} pts)")
        print(f"H2H: {ctx['head_to_head']['matches_played']} matches")
        print(f"Coverage: {ctx['coverage_score']}%")
        
        print("\n" + "="*60)
        print("ANALYSIS RESULT:")
        print("="*60)
        print(json.dumps(output["result"], indent=2))
