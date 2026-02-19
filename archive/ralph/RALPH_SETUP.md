# Ralph Wiggum Setup - Multi-Agent Edition

## What is Ralph Wiggum?

Ralph Wiggum is an autonomous AI coding technique named after The Simpsons character. The core idea: **a bash loop repeatedly feeds an AI agent a prompt until all tasks are complete**.

> "Ralph is a Bash loop." - Geoffrey Huntley (creator)

### The Key Insight

The power of Ralph is **naive persistence** - the AI sees its own previous work (via git commits), confronts its failures, and iterates until it solves the problem. No human in the loop.

### Why OpenCode, Not Claude Code?

**Claude Code plugin** (`/ralph-loop`):
- Agent controls the loop internally
- Uses hooks to intercept exit and re-feed prompt
- More "magic", less control

**OpenCode + bash script** (this setup):
- WE control the loop externally
- Agent runs once, completes one story, exits
- We re-invoke with same prompt
- Agent sees its git commits from previous runs
- More explicit, easier to debug

**Both achieve the same result**: autonomous multi-hour coding sessions.

---

## How It Works

```
┌─────────────────────────────────────────────────────┐
│                    RALPH LOOP                        │
│                                                      │
│  ┌──────────────┐                                   │
│  │   ralph.sh   │ ◄─── You start this               │
│  └──────┬───────┘                                   │
│         │                                           │
│         ▼                                           │
│  ┌──────────────┐                                   │
│  │ Read prd.json│ ◄─── Which stories need work?     │
│  └──────┬───────┘                                   │
│         │                                           │
│         ▼                                           │
│  ┌──────────────┐                                   │
│  │ Run opencode │ ◄─── Agent picks highest priority │
│  │  with prompt │      story with passes: false     │
│  └──────┬───────┘                                   │
│         │                                           │
│         ▼                                           │
│  ┌──────────────┐                                   │
│  │Agent commits │ ◄─── Updates prd.json too         │
│  │ + updates PRD│                                   │
│  └──────┬───────┘                                   │
│         │                                           │
│         ▼                                           │
│  ┌──────────────┐     ┌─────────────────────┐       │
│  │ All stories  │─NO─▶│ Loop: next iteration│       │
│  │  complete?   │     └─────────────────────┘       │
│  └──────┬───────┘                                   │
│         │YES                                        │
│         ▼                                           │
│  ┌──────────────┐                                   │
│  │<promise>     │ ◄─── Agent signals done           │
│  │ COMPLETE     │                                   │
│  │</promise>    │                                   │
│  └──────────────┘                                   │
│                                                      │
└─────────────────────────────────────────────────────┘
```

---

## File Structure

```
ralph/
├── prd.json          # Product Requirements Document (task list)
├── prompt.md         # Instructions for the agent
├── progress.txt      # Agent's work log (patterns + history)
├── ralph.sh          # The loop script
├── ralph_run.log     # Output log from runs
├── .ralph_state      # Temporary state during runs
└── RALPH_SETUP.md    # This file
```

---

## Quick Start

### 1. Install an agent CLI

```bash
# OpenCode (default)
# Install from https://opencode.ai

# Claude CLI
# Install from https://docs.anthropic.com/claude-code

# Codex CLI
# Install from https://github.com/openai/codex
```

### 2. Configure your PRD
Edit `prd.json` with your user stories.

### 3. Run Ralph
```bash
# From project root - choose your agent:
./ralph/ralph.sh 20                    # OpenCode (default)
./ralph/ralph.sh 20 claude             # Claude CLI
./ralph/ralph.sh 20 codex              # Codex CLI

# Or with custom model
RALPH_MODEL="google/gemini-2.5-pro" ./ralph/ralph.sh 20 opencode
RALPH_MODEL="opus" ./ralph/ralph.sh 20 claude

# Or with custom timeout (60 min per iteration)
RALPH_TIMEOUT=3600 ./ralph/ralph.sh 20
```

**OpenCode model names** (run `opencode models` to see all):
- `openai/gpt-5.2-codex` (default)
- `google/gemini-2.5-pro`
- `google/gemini-2.5-flash`

### 4. Monitor Progress
```bash
# In another terminal
tail -f ralph/ralph_run.log

# Or watch commits
watch -n 10 'git log --oneline -5'

# Or check PRD status
watch -n 30 'jq -r ".userStories[] | \"\\(.id): \\(if .passes then \"✅\" else \"❌\" end)\"" ralph/prd.json'
```

---

## Configuration

| Variable | Default | Description |
|----------|---------|-------------|
| `RALPH_MODEL` | `anthropic/claude-sonnet-4-20250514` | Model to use |
| `RALPH_TIMEOUT` | `1800` (30 min) | Max seconds per iteration |
| `RALPH_STUCK_THRESHOLD` | `3` | Iterations without commits before warning |
| `RALPH_COOLDOWN` | `5` | Seconds between iterations |

---

## Common Issues

### Agent keeps repeating same story
**Fix**: Manually update PRD `passes: true`

### Agent stuck on failing tests
**Fix**: Update prompt.md to allow skipping tests for environment issues

### Scraping tasks failing (403 errors)
**Fix**: Document in progress.txt and move on, don't retry indefinitely

### No commits detected
**Check**: `grep -i "error" ralph/ralph_run.log | tail -20`

---

## Resources

- [Ralph Wiggum Guide](https://www.aihero.dev/tips-for-ai-coding-with-ralph-wiggum)
- [OpenCode](https://opencode.ai/)
- [DEV.to - Ralph Approach](https://dev.to/sivarampg/the-ralph-wiggum-approach-running-ai-coding-agents-for-hours-not-minutes-57c1)
