#!/bin/bash
# Ralph Wiggum Loop - OpenCode Edition (Fixed)
# Usage: ./ralph/ralph.sh [max_iterations]

set -e

# --- CONFIGURATION ---
MAX_ITERATIONS=${1:-200}
MODEL="openai/gpt-5.2-codex"
# ---------------------

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
PRD_FILE="$SCRIPT_DIR/prd.json"
PROGRESS_FILE="$SCRIPT_DIR/progress.txt"
PROMPT_FILE="$SCRIPT_DIR/prompt.md"

# (Legacy Archive/Branch Logic removed for brevity - add back if needed)

echo "🚀 Starting Ralph (OpenCode) - Max Iterations: $MAX_ITERATIONS"
echo "🧠 Model: $MODEL"

for i in $(seq 1 $MAX_ITERATIONS); do
  echo ""
  echo "═══════════════════════════════════════════════════════"
  echo "  Iteration $i of $MAX_ITERATIONS"
  echo "═══════════════════════════════════════════════════════"
  
  # 1. Read Prompt
  PROMPT_CONTENT=$(cat "$PROMPT_FILE")

  # 2. RUN OPENCODE CORRECTLY
  # We use 'run' command which accepts the message as an argument.
  # We removed -p and -q as they were causing errors.
  
  OUTPUT=$(~/.opencode/bin/opencode run "$PROMPT_CONTENT" \
    --model "$MODEL" \
    2>&1 | tee /dev/tty) || true
  
  # 3. Check Completion
  if echo "$OUTPUT" | grep -q "<promise>COMPLETE</promise>"; then
    echo ""
    echo "✅ Ralph signaled COMPLETE!"
    exit 0
  fi
  
  echo "⏳ Cooling down (5s)..."
  sleep 5
done

echo "⚠️ Reached max iterations without completion."
exit 1