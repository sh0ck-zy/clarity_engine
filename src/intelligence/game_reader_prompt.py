"""
Game Reader Prompt — LLM prompt for reading football matches.

v1.8: Tighter output — 7 fields, ~300 words, scout briefing voice.
The LLM reads the game through pre-computed tactical factors, not raw numbers.
The ML anchor is probabilistic context, NOT the truth base.
"""

GAME_READER_SYSTEM_PROMPT = """\
You are an elite football match analyst. You READ GAMES like a scout — short, sharp, decisive.

## YOUR ROLE

You receive a complete data packet about an upcoming match:
- A TACTICAL RUBRIC with pre-computed factors covering context, attack/defense, matchup, and game state
- Both teams' state (position, form, style, attack, defense, home/away, trajectory)
- Both teams' recent form with xG context
- A matchup analysis and game state tree
- Key players and their current form
- An ML model estimate (probabilities and drivers) — this is CONTEXT, not your conclusion

## YOUR TASK: STRUCTURED REASONING

Before writing, answer these questions IN YOUR THINKING:

1. **THESIS**: What is the ONE central story of this match?
2. **MECHANISM**: What single tactical dynamic decides it?
3. **UNDERDOG ANGLE**: Why might the favourite lose?
4. **FRAGILITY**: What weakness do the numbers hide?
5. **KILL SWITCH**: What one event flips this read entirely?
6. **SCORE SHAPE**: What does the most likely scoreline corridor look like?

Then produce your output grounded in these answers.

## CRITICAL RULES

1. **SCOUT BRIEFING, NOT BLOG POST**
   Every sentence must have an angle. No filler. No "this promises to be an exciting contest."
   Write like you're briefing someone who's about to put money down.

2. **ONE THESIS, NOT A LIST**
   Your verdict is ONE claim about HOW this game plays out. Not "both teams are strong."

3. **WEAVE DATA IN, DON'T LIST IT**
   "Arsenal's 0.84 xGA profile shields them from Everton's low-volume transition game"
   NOT "Arsenal have 0.84 xGA per game. Everton average 1.1 xG per game."

4. **THE ML ANCHOR IS CALIBRATION, NOT YOUR STARTING POINT**
   Start from the tactical rubric. The lean CAN disagree with ML if evidence supports it.

5. **NAME PLAYERS WITH PURPOSE**
   "Saka's inside-left runs vs Everton's narrow 4-4-2 block" — the name adds tactical meaning.
   Don't name-drop without explaining the mechanism.

6. **RISKS MUST HAVE NUMBERS**
   "Draw pressure is real: entropy 0.94, combined last-5 average 2.1 goals" — not just "draw is possible."

## OUTPUT FORMAT

Return a JSON object with this EXACT structure (7 fields, ~250-350 words total):
{
    "verdict": "1 sentence. WHO wins and HOW — or why nobody does. This is your thesis.",
    "core_read": "3-4 sentences. The game narrative: how it flows, where it's decided, which mechanisms matter. Weave in 2-3 data points naturally. No stats listing.",
    "main_mechanism": "1 sentence. The single most important tactical dynamic that decides the outcome.",
    "main_risk": "1 sentence with a concrete data point. What threatens your verdict.",
    "kill_switch": "1 sentence. What one event would completely flip this read.",
    "best_score_range": "The most likely scoreline corridor, e.g. '1-0 or 1-1' or '2-1 or 2-2'",
    "lean": "1 qualified sentence with mechanism — e.g. 'Arsenal via Saka-side overloads and set-piece dominance, but draw gravity caps the ceiling'"
}

NOTE: "confidence" is NOT part of your output. It is calculated separately.
NOTE: "decision" (PICK/LEAN/WATCHLIST/NO_BET) is NOT your job. It is computed deterministically.

## WRITING RULES
- Write in English
- Max 350 words across ALL fields combined
- Every sentence must contain either a player name, a number, or a tactical mechanism
- Lean MUST include HOW (by what mechanism) — NOT just "Home win"
- Never use: guaranteed, certain, definitely, will win, easy, promises, exciting, fascinating
- Never use: "strong statistical backing", "comprehensive analysis", "data suggests"
- Voice: authoritative, concise, honest about uncertainty
"""


def build_user_prompt(
    match_pack: dict,
    ml_anchor: dict,
    match_signals: dict,
    tactical_rubric: dict = None,
    confidence_level: str = "",
    data_warnings: list = None,
) -> str:
    """Build the user prompt from match data artefacts."""
    fixture = match_pack.get("fixture", {})
    home = fixture.get("home_team", "Home")
    away = fixture.get("away_team", "Away")
    round_num = fixture.get("round_number", "?")
    league = fixture.get("league", "")

    sections = [
        f"Read the game: **{home}** vs **{away}** | {league} Round {round_num}\n",
    ]

    # Inject pre-calculated confidence level
    if confidence_level:
        sections.append(
            f"## CONFIDENCE LEVEL (pre-calculated, do not override)\n"
            f"Confidence level for this match: **{confidence_level}**\n"
            f"This is determined by ML margin, data quality, and signal alignment. "
            f"Use it in your analysis but do not change it."
        )

    # Inject data quality warnings
    if data_warnings:
        warn_lines = ["## DATA QUALITY WARNINGS"]
        for w in data_warnings:
            if isinstance(w, dict):
                warn_lines.append(f"  - {w.get('issue', str(w))}")
            else:
                warn_lines.append(f"  - {w}")
        warn_lines.append(
            "Treat warned fields as MISSING data. Do NOT cite them as evidence."
        )
        sections.append("\n".join(warn_lines))

    # TACTICAL RUBRIC (primary analytical lens)
    if tactical_rubric:
        from intelligence.tactical_rubric import render_rubric_for_prompt
        rubric_text = render_rubric_for_prompt(tactical_rubric)
        if rubric_text:
            sections.append(rubric_text)

    # ML Anchor (subordinate context)
    sections.append(_format_ml_anchor(ml_anchor, home, away))

    # Match Signals (hard checks)
    sections.append(_format_signals(match_signals))

    # Home team
    sections.append(_format_team(match_pack.get("home", {}), home, "HOME"))

    # Away team
    sections.append(_format_team(match_pack.get("away", {}), away, "AWAY"))

    # Matchup
    sections.append(_format_matchup(match_pack.get("matchup", {})))

    # Game state tree
    sections.append(_format_game_tree(match_pack.get("game_state_tree", {})))

    # Recent matches
    sections.append(_format_recent(match_pack.get("recent_matches", {}), home, away))

    sections.append(
        "Read the game now. Use the tactical rubric to ground your analysis. "
        "Focus on your THESIS — one central claim about how this match plays out. "
        "Be a scout, not a commentator."
    )

    return "\n\n".join(s for s in sections if s)


def _format_ml_anchor(anchor: dict, home: str, away: str) -> str:
    """Format ML anchor as subordinate context."""
    probs = anchor.get("probabilities", {})
    pred = anchor.get("predicted_result", "?")
    conf = anchor.get("confidence", "?")

    pred_name = {"H": home, "D": "Draw", "A": away}.get(pred, pred)

    lines = [
        "## ML ANCHOR (calibration context, not your starting point)",
        f"Model estimate: {home} {probs.get('H', 0):.0%} | Draw {probs.get('D', 0):.0%} | {away} {probs.get('A', 0):.0%}",
        f"Prediction: {pred_name} ({conf} confidence)",
    ]

    drivers = anchor.get("drivers", [])
    if drivers:
        lines.append("Top signals:")
        for d in drivers[:5]:
            name = d.get("display_name", d.get("feature", "?"))
            direction = d.get("direction", "?")
            hint = d.get("interpretation_hint", "")
            lines.append(f"  - {name}: {direction} — {hint}")

    flags = anchor.get("risk_flags", [])
    if flags:
        lines.append(f"Risk flags: {', '.join(flags)}")

    lines.append(
        "Use this as calibration. Your job is to read the game from the football data."
    )

    return "\n".join(lines)


def _format_signals(signals_data: dict) -> str:
    """Format match signals for the prompt."""
    signals = signals_data.get("signals", {})
    if not signals:
        return ""

    lines = [
        "## MATCH SIGNALS (hard checks — use to validate your reasoning)",
        "These are binary/categorical facts derived from data. If your analysis contradicts a signal, explain why.",
    ]

    signal_labels = {
        "home_territorial_edge": "Home territorial edge",
        "home_territorial_strength": "  strength",
        "away_transition_threat": "Away transition threat",
        "away_transition_strength": "  strength",
        "draw_pressure_risk": "Draw pressure risk",
        "fragile_home_edge": "Fragile home edge",
        "venue_advantage": "Venue advantage",
        "upset_potential": "Upset potential",
        "ml_confidence_justified": "ML confidence support",
    }

    for key, label in signal_labels.items():
        val = signals.get(key)
        if val is not None:
            lines.append(f"  {label}: {val}")

    return "\n".join(lines)


def _format_team(team: dict, name: str, label: str) -> str:
    """Format team data for the prompt."""
    state = team.get("state", {})
    form_detail = team.get("form_detail", {})

    lines = [f"## {label}: {name}"]

    pos = state.get("position", {})
    form = state.get("form", {})
    if pos:
        lines.append(
            f"Position: {pos.get('position', '?')}th | "
            f"{pos.get('points', '?')} pts | "
            f"W{pos.get('wins', 0)}-D{pos.get('draws', 0)}-L{pos.get('losses', 0)}"
        )
    if form:
        lines.append(
            f"Form: {form.get('form_string', '?')} ({form.get('form_points', '?')}/15) | "
            f"xG: +{form.get('xg_for_last5', 0):.1f} / -{form.get('xg_against_last5', 0):.1f} "
            f"(diff: {form.get('xg_diff_last5', 0):+.1f})"
        )

    style = state.get("style", {})
    if style:
        lines.append(
            f"Style: {style.get('primary_formation', '?')} | "
            f"Possession: {style.get('avg_possession', 0):.1f}%"
        )

    attack = team.get("attack_profile", {})
    defense = team.get("defense_profile", {})
    if attack:
        lines.append(f"Attack: {attack.get('rating', '?')} ({attack.get('xg_per_game', 0):.2f} xG/game)")
    if defense:
        lines.append(f"Defense: {defense.get('rating', '?')} ({defense.get('xg_against_per_game', 0):.2f} xGA/game)")

    home_away = state.get("home_away", {})
    if home_away:
        lines.append(
            f"Venue: Home {home_away.get('home_points', '?')} pts | "
            f"Away {home_away.get('away_points', '?')} pts"
        )

    traj = state.get("trajectory", {})
    if traj:
        lines.append(f"Trajectory: {traj.get('form_trend', '?')}")

    players = team.get("key_players", [])
    if players:
        lines.append("Key players:")
        for p in players[:5]:
            lines.append(
                f"  - {p.get('name', '?')} ({p.get('position', '?')}) | "
                f"{p.get('goals', 0)}G {p.get('assists', 0)}A | "
                f"Rating: {(p.get('avg_rating') or 0):.1f} "
                f"(last 5: {(p.get('form_rating') or 0):.1f})"
            )

    injuries = team.get("injuries", [])
    if injuries:
        lines.append("Potential missing:")
        for inj in injuries[:3]:
            lines.append(
                f"  - {inj.get('name', '?')} ({inj.get('position', '?')}) — "
                f"Impact: {inj.get('impact', '?')}"
            )

    psych = team.get("psychology", {})
    if psych and psych.get("mindset"):
        lines.append(f"Mindset: {psych.get('mindset', '')}")

    return "\n".join(lines)


def _format_matchup(matchup: dict) -> str:
    """Format matchup analysis for the prompt."""
    if not matchup:
        return ""

    lines = ["## MATCHUP"]

    verdict = matchup.get("verdict", "")
    if verdict:
        lines.append(f"Verdict: {verdict}")

    preds = matchup.get("predictions", {})
    if preds:
        lines.append(f"Possession edge: {preds.get('possession_edge', '?')}")
        lines.append(f"Expected total xG: {preds.get('expected_total_xg', '?')}")

    for side in ["team1", "team2"]:
        advs = matchup.get("advantages", {}).get(side, [])
        if advs:
            name = matchup.get(side, {}).get("name", side)
            lines.append(f"{name} advantages: {'; '.join(advs[:3])}")

    return "\n".join(lines)


def _format_game_tree(tree: dict) -> str:
    """Format game state tree for the prompt."""
    scenarios = tree.get("scenarios", {})
    if not scenarios:
        return ""

    lines = ["## GAME STATE TREE"]

    for key, scenario in scenarios.items():
        if isinstance(scenario, dict):
            name = key.replace("_", " ").title()
            desc = scenario.get("description", "")
            outcome = scenario.get("likely_outcome", "")
            prob = scenario.get("probability", "")

            line = f"  {name}"
            if prob:
                line += f" ({prob:.0%})"
            line += f": {desc}"
            if outcome:
                line += f" → {outcome}"
            lines.append(line)

    flow = tree.get("flow_prediction", "")
    if flow:
        lines.append(f"Flow prediction: {flow}")

    return "\n".join(lines)


def _format_recent(recent: dict, home: str, away: str) -> str:
    """Format recent matches for the prompt."""
    home_recent = recent.get("home", [])
    away_recent = recent.get("away", [])

    if not home_recent and not away_recent:
        return ""

    lines = ["## RECENT MATCHES"]

    if home_recent:
        lines.append(f"{home}:")
        for m in home_recent[:3]:
            h = m.get("home_team_name", "?")
            a = m.get("away_team_name", "?")
            hs = m.get("home_score", "?")
            aws = m.get("away_score", "?")
            lines.append(f"  R{m.get('round_number', '?')}: {h} {hs}-{aws} {a}")

    if away_recent:
        lines.append(f"{away}:")
        for m in away_recent[:3]:
            h = m.get("home_team_name", "?")
            a = m.get("away_team_name", "?")
            hs = m.get("home_score", "?")
            aws = m.get("away_score", "?")
            lines.append(f"  R{m.get('round_number', '?')}: {h} {hs}-{aws} {a}")

    return "\n".join(lines)
