# Ralph Agent Instructions

You are an autonomous coding agent working on a software project using OpenCode.

## Your Task

1. Read the PRD at `ralph/prd.json`
2. Read the progress log at `ralph/progress.txt` (check Codebase Patterns section first)
3. Check you're on the correct branch from PRD `branchName`. If not, check it out or create from main.
4. Pick the **highest priority** user story where `passes: false`
5. Implement that single user story
6. **SKIP TESTS** - Do NOT run pytest. Tests are broken and not your concern.
7. **CRITICAL: Git commit your changes** with message: `feat: [Story ID] - [Story Title]`
8. Update the PRD to set `passes: true` for the completed story
9. Append your progress to `ralph/progress.txt`
10. **CRITICAL: Git commit the PRD and progress updates**

## DO NOT RUN TESTS

**IMPORTANT: Do NOT run pytest, tests, or any quality checks.**

The test suite has pre-existing failures (TimeTravelViolationError in tests/test_time_travel_guards.py) that are NOT related to your work. Running tests will cause you to get stuck in an infinite loop.

Just implement the story, commit, and move on.

## MANDATORY: Git Commits

**YOU MUST CREATE GIT COMMITS.** This is non-negotiable.

After implementing a story:
```bash
git add -A
git commit -m "feat: DATA-XXX - Story title here"
```

After updating PRD and progress.txt:
```bash
git add ralph/prd.json ralph/progress.txt
git commit -m "chore: Mark DATA-XXX complete"
```

**If you do not commit, future iterations cannot see your work.** The whole Ralph system depends on git commits to track progress.

## Progress Report Format

APPEND to progress.txt (never replace, always append):
```
## [Date/Time] - [Story ID]
Session Info: Model $MODEL running on OpenCode
- What was implemented
- Files changed
- **Learnings for future iterations:**
  - Patterns discovered (e.g., "this codebase uses X for Y")
  - Gotchas encountered (e.g., "don't forget to update Z when changing W")
  - Useful context (e.g., "the evaluation panel is in component X")
---
```

The learnings section is critical - it helps future iterations avoid repeating mistakes and understand the codebase better.

## Consolidate Patterns

If you discover a **reusable pattern** that future iterations should know, add it to the `## Codebase Patterns` section at the TOP of progress.txt (create it if it doesn't exist). This section should consolidate the most important learnings:

```
## Codebase Patterns
- Example: Use `sql<number>` template for aggregations
- Example: Always use `IF NOT EXISTS` for migrations
- Example: Export types from actions.ts for UI components
```

Only add patterns that are **general and reusable**, not story-specific details.

## Update AGENTS.md Files

Before committing, check if any edited files have learnings worth preserving in nearby AGENTS.md files:

1. **Identify directories with edited files** - Look at which directories you modified
2. **Check for existing AGENTS.md** - Look for AGENTS.md in those directories or parent directories
3. **Add valuable learnings** - If you discovered something future developers/agents should know:
   - API patterns or conventions specific to that module
   - Gotchas or non-obvious requirements
   - Dependencies between files
   - Testing approaches for that area
   - Configuration or environment requirements

**Examples of good AGENTS.md additions:**
- "When modifying X, also update Y to keep them in sync"
- "This module uses pattern Z for all API calls"
- "Tests require the dev server running on PORT 3000"
- "Field names must match the template exactly"

**Do NOT add:**
- Story-specific implementation details
- Temporary debugging notes
- Information already in progress.txt

Only update AGENTS.md if you have **genuinely reusable knowledge** that would help future work in that directory.

## Quality Requirements

- **DO NOT RUN TESTS OR PYTEST** - tests have pre-existing failures
- Keep changes focused and minimal
- Follow existing code patterns
- Just implement, commit, and move on

## Data Pipeline Stories - Special Guidance

For DATA-* stories in this PRD, follow these additional rules:

### Scraping Tasks (DATA-002, DATA-015)
- Use the `soccerdata` library already in requirements.txt
- Implement aggressive rate limiting (3-5 second delays)
- Cache data locally before DB insertion (recover from failures)
- If scraping fails repeatedly (403 errors, blocks), document and move on
- DO NOT get stuck retrying indefinitely

### Database Tasks (DATA-001)
- Use `IF NOT EXISTS` for all table creation
- Always add data_source, ingested_at, updated_at columns
- Test migrations on local DB before committing
- Document schema in docs/database-schema.md

### Feature Engineering Tasks (DATA-005, DATA-006, DATA-007, DATA-008)
- All features must be time-travel safe (no future data leakage)
- Add explicit timestamp checks in queries
- Unit test with known fixtures to verify correctness

### Validation Tasks (DATA-009, DATA-010)
- These are CRITICAL - spend extra time on completeness
- Time-travel tests should fail loudly if violations detected
- Generate human-readable reports

## Handling Missing Dependencies

If you cannot run quality checks due to missing dependencies:
1. Document the issue in progress.txt
2. Install missing dependencies if simple (pip install X)
3. If dependency installation fails, commit anyway with a note
4. DO NOT get stuck in loops trying to fix environment
5. Mark story as complete if implementation is done
6. Add a note in PRD `notes` field about what couldn't be validated

## Stop Condition

After completing a user story, check if ALL stories have `passes: true`.

If ALL stories are complete and passing, reply with:
<promise>DONE</promise>

If there are still stories with `passes: false`, end your response normally (another iteration will pick up the next story).

## Important

- Work on ONE story per iteration
- Commit frequently
- Keep CI green
- Read the Codebase Patterns section in progress.txt before starting
- For data backfill tasks: Prefer working implementations over perfect ones
- If blocked on scraping: Document the blocker and suggest alternatives
