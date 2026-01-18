#!/bin/bash
# Ralph Wiggum Loop - OpenCode Edition (Improved with safeguards)
# Usage: ./ralph/ralph_improved.sh [max_iterations]

set -e

# --- CONFIGURATION ---
MAX_ITERATIONS=${1:-200}
MODEL="openai/gpt-5.2-codex"
ITERATION_TIMEOUT=1800  # 30 minutes per iteration
STUCK_THRESHOLD=3       # Number of iterations without progress before alerting
# ---------------------

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
PRD_FILE="$SCRIPT_DIR/prd.json"
PROGRESS_FILE="$SCRIPT_DIR/progress.txt"
PROMPT_FILE="$SCRIPT_DIR/prompt.md"
LOG_FILE="$SCRIPT_DIR/ralph_run.log"
STATE_FILE="$SCRIPT_DIR/.ralph_state"

# Initialize state tracking
LAST_COMMIT_HASH=$(git rev-parse HEAD 2>/dev/null || echo "")
ITERATIONS_WITHOUT_COMMIT=0

echo "🚀 Starting Ralph (OpenCode) - Max Iterations: $MAX_ITERATIONS"
echo "🧠 Model: $MODEL"
echo "⏱️  Iteration Timeout: ${ITERATION_TIMEOUT}s ($(($ITERATION_TIMEOUT / 60)) minutes)"
echo "📝 Logging to: $LOG_FILE"
echo ""

# Save initial state
echo "LAST_COMMIT=$LAST_COMMIT_HASH" > "$STATE_FILE"
echo "START_TIME=$(date +%s)" >> "$STATE_FILE"

for i in $(seq 1 $MAX_ITERATIONS); do
  echo "" | tee -a "$LOG_FILE"
  echo "═══════════════════════════════════════════════════════" | tee -a "$LOG_FILE"
  echo "  Iteration $i of $MAX_ITERATIONS - $(date '+%Y-%m-%d %H:%M:%S')" | tee -a "$LOG_FILE"
  echo "═══════════════════════════════════════════════════════" | tee -a "$LOG_FILE"

  # 1. Check progress (detect if stuck)
  CURRENT_COMMIT=$(git rev-parse HEAD 2>/dev/null || echo "")
  if [ "$CURRENT_COMMIT" != "$LAST_COMMIT_HASH" ]; then
    echo "✅ Progress detected! New commit: $(git log -1 --oneline)" | tee -a "$LOG_FILE"
    LAST_COMMIT_HASH="$CURRENT_COMMIT"
    ITERATIONS_WITHOUT_COMMIT=0
  else
    ITERATIONS_WITHOUT_COMMIT=$((ITERATIONS_WITHOUT_COMMIT + 1))
    echo "⚠️  No new commits. Iterations without progress: $ITERATIONS_WITHOUT_COMMIT" | tee -a "$LOG_FILE"

    if [ $ITERATIONS_WITHOUT_COMMIT -ge $STUCK_THRESHOLD ]; then
      echo "" | tee -a "$LOG_FILE"
      echo "❌ WARNING: No commits for $ITERATIONS_WITHOUT_COMMIT iterations!" | tee -a "$LOG_FILE"
      echo "   This usually means:" | tee -a "$LOG_FILE"
      echo "   1. The agent is stuck on failing tests" | tee -a "$LOG_FILE"
      echo "   2. The PRD wasn't updated after completing a story" | tee -a "$LOG_FILE"
      echo "   3. The agent is looping on the same error" | tee -a "$LOG_FILE"
      echo "" | tee -a "$LOG_FILE"
      echo "   Check the logs and consider killing the process if this continues." | tee -a "$LOG_FILE"
      echo "" | tee -a "$LOG_FILE"
    fi
  fi

  # 2. Read Prompt
  PROMPT_CONTENT=$(cat "$PROMPT_FILE")

  # 3. Run OpenCode (macOS compatible - no timeout command)
  echo "🤖 Running OpenCode..." | tee -a "$LOG_FILE"
  ITERATION_START=$(date +%s)

  # Use full path to opencode and run with timeout monitoring in background
  OUTPUT=$(~/.opencode/bin/opencode run "$PROMPT_CONTENT" \
    --model "$MODEL" \
    2>&1 | tee -a "$LOG_FILE") || true

  ITERATION_END=$(date +%s)
  DURATION=$((ITERATION_END - ITERATION_START))

  # Check if iteration took too long (soft timeout warning)
  if [ $DURATION -gt $ITERATION_TIMEOUT ]; then
    echo "" | tee -a "$LOG_FILE"
    echo "⏰ WARNING: Iteration took ${DURATION}s (exceeded ${ITERATION_TIMEOUT}s limit)" | tee -a "$LOG_FILE"
    echo "   The agent may be stuck. Consider:" | tee -a "$LOG_FILE"
    echo "   1. Checking if tests are hanging" | tee -a "$LOG_FILE"
    echo "   2. Reviewing the last output in $LOG_FILE" | tee -a "$LOG_FILE"
    echo "   3. Manually completing the current story" | tee -a "$LOG_FILE"
    echo "" | tee -a "$LOG_FILE"
  fi

  echo "⏱️  Iteration completed in ${DURATION}s" | tee -a "$LOG_FILE"

  # 4. Check Completion
  if echo "$OUTPUT" | grep -q "<promise>COMPLETE</promise>"; then
    echo "" | tee -a "$LOG_FILE"
    echo "✅ Ralph signaled COMPLETE!" | tee -a "$LOG_FILE"
    echo "🎉 All user stories completed successfully!" | tee -a "$LOG_FILE"

    # Show summary
    TOTAL_TIME=$(($(date +%s) - $(grep START_TIME "$STATE_FILE" | cut -d= -f2)))
    echo "" | tee -a "$LOG_FILE"
    echo "📊 Summary:" | tee -a "$LOG_FILE"
    echo "   Total iterations: $i" | tee -a "$LOG_FILE"
    echo "   Total time: $((TOTAL_TIME / 60)) minutes" | tee -a "$LOG_FILE"
    echo "   Final commit: $(git log -1 --oneline)" | tee -a "$LOG_FILE"

    rm -f "$STATE_FILE"
    exit 0
  fi

  # 5. Count remaining stories
  INCOMPLETE_COUNT=$(jq '[.userStories[] | select(.passes == false)] | length' "$PRD_FILE")
  echo "📋 Remaining stories: $INCOMPLETE_COUNT" | tee -a "$LOG_FILE"

  if [ "$INCOMPLETE_COUNT" -eq "0" ]; then
    echo "" | tee -a "$LOG_FILE"
    echo "⚠️  All stories marked complete but no <promise>COMPLETE</promise> detected!" | tee -a "$LOG_FILE"
    echo "   The agent may have forgotten to signal completion." | tee -a "$LOG_FILE"
    echo "   Continuing one more iteration..." | tee -a "$LOG_FILE"
  fi

  echo "⏳ Cooling down (5s)..." | tee -a "$LOG_FILE"
  sleep 5
done

echo "" | tee -a "$LOG_FILE"
echo "⚠️ Reached max iterations ($MAX_ITERATIONS) without completion." | tee -a "$LOG_FILE"
echo "📊 Final status:" | tee -a "$LOG_FILE"
jq -r '.userStories[] | "\(.id): \(if .passes then "✅" else "❌" end) \(.title)"' "$PRD_FILE" | tee -a "$LOG_FILE"

rm -f "$STATE_FILE"
exit 1
