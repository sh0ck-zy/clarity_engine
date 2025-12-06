from pathlib import Path

# 1. FIND THE FOLDER
PROMPTS_DIR = Path(__file__).resolve().parents[2] / "prompts"

def load_prompt(filename):
    """Helper: Reads a text file and returns the string."""
    try:
        return (PROMPTS_DIR / filename).read_text(encoding="utf-8")
    except FileNotFoundError:
        return f"Error: Prompt file '{filename}' not found."

# 2. DEFINE THE MENU
PROMPTS = {
    "hybrid": {
        "name": "Hybrid (Safe - The Journalist)",
        "text": load_prompt("v1_hybrid.txt")
    },
    "contrarian": {
        "name": "Contrarian (Risky - The Auditor)",
        "text": load_prompt("v2_contrarian.txt")
    }
}

# 3. BACKWARD COMPATIBILITY
# Ensures older scripts like predictor.py don't crash if they import these
SYSTEM_PROMPT_HYBRID = PROMPTS["hybrid"]["text"]
SYSTEM_PROMPT_LEGACY = PROMPTS["hybrid"]["text"]