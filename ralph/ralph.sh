#!/bin/bash
# Ralph Wiggum Loop - Multi-Agent Edition
#
# Key difference from Claude Code: WE control the loop, not the agent.
# The agent runs, completes ONE story, then exits. We re-invoke.
#
# Usage: ./ralph/ralph.sh [max_iterations] [agent]
#
# Examples:
#   ./ralph/ralph.sh 20                    # 20 iterations with opencode (default)
#   ./ralph/ralph.sh 20 claude             # 20 iterations with claude CLI
#   ./ralph/ralph.sh 20 codex              # 20 iterations with codex CLI
#   RALPH_MODEL="gpt-4o" ./ralph/ralph.sh 20 opencode  # custom model
#
# Environment variables:
#   RALPH_MODEL - Model to use (agent-specific defaults if not set)
#   RALPH_TIMEOUT - Timeout per iteration in seconds (default: 1800)
#   RALPH_STUCK_THRESHOLD - Iterations without commit before warning (default: 3)
#   RALPH_COOLDOWN - Seconds between iterations (default: 5)

set -e

# --- CONFIGURATION ---
MAX_ITERATIONS=${1:-50}
AGENT="${2:-opencode}"
ITERATION_TIMEOUT=${RALPH_TIMEOUT:-1800}
STUCK_THRESHOLD=${RALPH_STUCK_THRESHOLD:-3}
COOLDOWN=${RALPH_COOLDOWN:-5}
PROMISE=${RALPH_PROMISE:-DONE}
# ---------------------

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
PROJECT_ROOT="$(cd "$SCRIPT_DIR/.." && pwd)"
PRD_FILE="$SCRIPT_DIR/prd.json"
PROGRESS_FILE="$SCRIPT_DIR/progress.txt"
PROMPT_FILE="$SCRIPT_DIR/prompt.md"
LOG_FILE="$SCRIPT_DIR/ralph_run.log"
STATE_FILE="$SCRIPT_DIR/.ralph_state"

# Check dependencies
if ! command -v jq &> /dev/null; then
  echo "Error: jq is required. Install with: brew install jq"
  exit 1
fi

# Configure agent command based on selection
case "$AGENT" in
  opencode)
    # OpenCode uses its own model names: openai/gpt-5.2-codex, google/gemini-2.5-pro, etc.
    MODEL="${RALPH_MODEL:-openai/gpt-5.2-codex}"
    if [ -f "$HOME/.opencode/bin/opencode" ]; then
      AGENT_CMD="$HOME/.opencode/bin/opencode"
    elif command -v opencode &> /dev/null; then
      AGENT_CMD="opencode"
    else
      echo "Error: opencode not found. Install from: https://opencode.ai"
      exit 1
    fi
    # Note: opencode run takes message as positional args, writes prompt to temp file
    ;;
  claude)
    MODEL="${RALPH_MODEL:-opus}"
    if command -v claude &> /dev/null; then
      AGENT_CMD="claude"
    else
      echo "Error: claude CLI not found. Install from: https://docs.anthropic.com/claude-code"
      exit 1
    fi
    ;;
  codex)
    MODEL="${RALPH_MODEL:-o3}"
    if command -v codex &> /dev/null; then
      AGENT_CMD="codex"
    else
      echo "Error: codex CLI not found. Install from: https://github.com/openai/codex"
      exit 1
    fi
    ;;
  *)
    echo "Error: Unknown agent '$AGENT'. Supported: opencode, claude, codex"
    exit 1
    ;;
esac

# Initialize state
LAST_COMMIT_HASH=$(git -C "$PROJECT_ROOT" rev-parse HEAD 2>/dev/null || echo "")
ITERATIONS_WITHOUT_COMMIT=0
START_TIME=$(date +%s)

# Clear log if starting fresh
[ ! -f "$STATE_FILE" ] && > "$LOG_FILE"

echo "LAST_COMMIT=$LAST_COMMIT_HASH" > "$STATE_FILE"
echo "START_TIME=$START_TIME" >> "$STATE_FILE"

log() { echo "$1" | tee -a "$LOG_FILE"; }

log ""
log "═══════════════════════════════════════════════════════"
log "  Ralph Wiggum - Multi-Agent Edition"
log "═══════════════════════════════════════════════════════"
log ""
log "🚀 Max Iterations: $MAX_ITERATIONS"
log "🤖 Agent: $AGENT"
log "🧠 Model: $MODEL"
log "⏱️  Timeout: ${ITERATION_TIMEOUT}s"
log "🧾 Completion Promise: $PROMISE"
log "📝 Log: $LOG_FILE"
log ""

# Show initial status
INCOMPLETE_COUNT=$(jq '[.userStories[] | select(.passes == false)] | length' "$PRD_FILE")
log "📋 Stories remaining: $INCOMPLETE_COUNT"

[ "$INCOMPLETE_COUNT" -eq "0" ] && { log "✅ All stories complete!"; rm -f "$STATE_FILE"; exit 0; }

# Main loop
for i in $(seq 1 $MAX_ITERATIONS); do
  log ""
  log "═══════════════════════════════════════════════════════"
  log "  Iteration $i of $MAX_ITERATIONS - $(date '+%Y-%m-%d %H:%M:%S')"
  log "═══════════════════════════════════════════════════════"

  # Check for progress
  CURRENT_COMMIT=$(git -C "$PROJECT_ROOT" rev-parse HEAD 2>/dev/null || echo "")
  if [ "$CURRENT_COMMIT" != "$LAST_COMMIT_HASH" ]; then
    log "✅ Progress! Commit: $(git -C "$PROJECT_ROOT" log -1 --oneline)"
    LAST_COMMIT_HASH="$CURRENT_COMMIT"
    ITERATIONS_WITHOUT_COMMIT=0
  else
    ITERATIONS_WITHOUT_COMMIT=$((ITERATIONS_WITHOUT_COMMIT + 1))
    [ $ITERATIONS_WITHOUT_COMMIT -ge $STUCK_THRESHOLD ] && \
      log "⚠️  WARNING: No commits for $ITERATIONS_WITHOUT_COMMIT iterations (stuck?)"
  fi

  # Status
  INCOMPLETE_COUNT=$(jq '[.userStories[] | select(.passes == false)] | length' "$PRD_FILE")
  NEXT_STORY=$(jq -r '[.userStories[] | select(.passes == false)] | sort_by(.priority) | .[0] | "\(.id): \(.title)"' "$PRD_FILE")
  log "📋 Remaining: $INCOMPLETE_COUNT | Next: $NEXT_STORY"

  [ "$INCOMPLETE_COUNT" -eq "0" ] && break

  # Run agent from project root
  cd "$PROJECT_ROOT"

  log "🤖 Running $AGENT ($MODEL)..."
  ITERATION_START=$(date +%s)

  set +e
  case "$AGENT" in
    opencode)
      # OpenCode: use --prompt flag with file path, or pass short message
      # For long prompts, we tell it to read the prompt file
      OUTPUT=$($AGENT_CMD run "Read ralph/prompt.md and follow those instructions. Work on the highest priority story in ralph/prd.json where passes=false. Output <promise>${PROMISE}</promise> only when all stories are complete." --model "$MODEL" 2>&1 | tee -a "$LOG_FILE")
      ;;
    claude)
      # Claude CLI: use -p for prompt
      OUTPUT=$($AGENT_CMD -p "$(cat "$PROMPT_FILE")" --model "$MODEL" --allowedTools "Bash,Read,Write,Edit,Glob,Grep" 2>&1 | tee -a "$LOG_FILE")
      ;;
    codex)
      # Codex: pass prompt directly
      OUTPUT=$($AGENT_CMD "$(cat "$PROMPT_FILE")" --model "$MODEL" 2>&1 | tee -a "$LOG_FILE")
      ;;
  esac
  set -e

  DURATION=$(($(date +%s) - ITERATION_START))
  log "⏱️  Completed in ${DURATION}s"

  # Check completion
  if echo "$OUTPUT" | grep -q "<promise>${PROMISE}</promise>"; then
    TOTAL_TIME=$(($(date +%s) - START_TIME))
    log ""
    log "✅ RALPH COMPLETE!"
    log "📊 Total: $i iterations, $((TOTAL_TIME / 60))m $((TOTAL_TIME % 60))s"
    rm -f "$STATE_FILE"
    exit 0
  fi

  log "⏳ Cooling down (${COOLDOWN}s)..."
  sleep $COOLDOWN
done

log ""
log "⚠️ MAX ITERATIONS ($MAX_ITERATIONS) reached"
jq -r '.userStories[] | "\(if .passes then "✅" else "❌" end) \(.id): \(.title)"' "$PRD_FILE" | tee -a "$LOG_FILE"
rm -f "$STATE_FILE"
exit 1
