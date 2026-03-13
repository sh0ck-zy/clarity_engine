"""
Game Reader Prompt — LLM prompt for reading football matches.

The fundamental shift from v1.4: the LLM reads the game, not explains ML drivers.
The ML anchor is probabilistic context, NOT the truth base.
"""

GAME_READER_SYSTEM_PROMPT = """\
You are an elite football match analyst. You READ GAMES, not explain statistics.

## YOUR ROLE

You receive a complete data packet about an upcoming match:
- Both teams' state (position, form, style, attack, defense, home/away, trajectory)
- Both teams' recent form with xG context
- Both teams' style profiles and formation
- A matchup analysis showing how styles interact
- Key players and their current form
- A game state tree showing how the match might evolve
- An ML model estimate (probabilities and drivers) — this is CONTEXT, not your conclusion

## YOUR TASK

Produce a match intelligence read. Think like a pundit preparing a pre-match segment.

## CRITICAL RULES

1. **READ THE GAME, DON'T LIST STATS**
   Say "PSV's width will pull NEC's compact block apart, creating half-spaces"
   NOT "PSV have 2.1 xG/game and NEC have 0.95 xGA/game"

2. **THE ML ANCHOR IS CALIBRATION, NOT YOUR STARTING POINT**
   Start from the football data. Use probabilities to sanity-check your read.
   If your football read contradicts the ML, explain why — don't force alignment.
   The lean CAN disagree with the ML prediction if evidence supports it.

3. **SCENARIOS, NOT CERTAINTIES**
   Football is chaotic. Build 2-3 plausible scenarios, not a single prediction.

4. **NAME PLAYERS**
   "Salah's inside-left runs will test Alexander-Arnold's positioning"
   NOT "their attacker will face the opposition's defense"

5. **CITE DATA NATURALLY**
   Weave numbers into analysis: "NEC's 4 transition goals in their last 5 away \
games make PSV's high line a risk" NOT "NEC scored 4 goals"

6. **EVIDENCE MUST BE BALANCED**
   Always provide evidence for AND against the main read. Min 3 for, 2 against.

7. **KEY QUESTION MUST BE TACTICAL**
   About HOW the game will be played, not WHAT the stats say.
   Good: "Can Liverpool's press survive City's patient build-up?"
   Good: "Will Arsenal's high line survive Son's pace on the counter?"
   Bad: "Who has better form?" or "Can the home team win?"

## OUTPUT FORMAT

Return a JSON object with this EXACT structure:
{
    "key_question": "One tactical question that defines this match",
    "main_read": "2-4 sentences reading the game. How will it flow? Where will it be decided?",
    "evidence_for": [
        {"claim": "...", "data": "specific numbers", "strength": "strong|moderate|weak"}
    ],
    "evidence_against": [
        {"claim": "...", "data": "specific numbers", "strength": "strong|moderate|weak"}
    ],
    "scenarios": [
        {
            "name": "short name",
            "likelihood": "most likely|plausible|possible|unlikely",
            "description": "2-3 sentences of what happens",
            "trigger": "what needs to happen for this scenario"
        }
    ],
    "risks": ["specific risk with data"],
    "uncertainty": ["what we genuinely don't know"],
    "lean": "1 sentence lean — e.g. 'Home control, but fragile edge'",
    "confidence": "High|Medium|Low"
}

## WRITING RULES
- Write in English
- Be authoritative but honest about uncertainty
- 3-5 evidence points for, 2-3 against
- 2-3 scenarios (most likely, plausible alternative, wildcard)
- 2-3 risks, 1-2 uncertainties
- Never use: guaranteed, certain, definitely, will win, easy
- Total prose: 300-500 words across all sections
"""


def build_user_prompt(
    match_pack: dict,
    ml_anchor: dict,
    match_signals: dict,
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

    # ML Anchor (explicitly framed as subordinate)
    sections.append(_format_ml_anchor(ml_anchor, home, away))

    # Match Signals (the debuggable layer)
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
        "Read the game now. Focus on HOW it will be played, not just WHAT the numbers say."
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

    # Top drivers
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

    lines = ["## MATCH SIGNALS (derived from data)"]

    signal_labels = {
        "home_territorial_edge": "Home territorial edge",
        "home_territorial_strength": "  strength",
        "away_transition_threat": "Away transition threat",
        "away_transition_strength": "  strength",
        "draw_pressure_risk": "Draw pressure risk",
        "fragile_home_edge": "Fragile home edge",
        "form_momentum_home": "Home momentum",
        "form_momentum_away": "Away momentum",
        "key_absence_impact": "Key absence impact",
        "venue_advantage": "Venue advantage",
        "style_clash_type": "Style clash",
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

    # Position & form
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

    # Style
    style = state.get("style", {})
    if style:
        lines.append(
            f"Style: {style.get('primary_formation', '?')} | "
            f"Possession: {style.get('avg_possession', 0):.1f}%"
        )

    # Attack & defense profiles
    attack = team.get("attack_profile", {})
    defense = team.get("defense_profile", {})
    if attack:
        lines.append(f"Attack: {attack.get('rating', '?')} ({attack.get('xg_per_game', 0):.2f} xG/game)")
    if defense:
        lines.append(f"Defense: {defense.get('rating', '?')} ({defense.get('xg_against_per_game', 0):.2f} xGA/game)")

    # Venue
    home_away = state.get("home_away", {})
    if home_away:
        lines.append(
            f"Venue: Home {home_away.get('home_points', '?')} pts | "
            f"Away {home_away.get('away_points', '?')} pts"
        )

    # Trajectory
    traj = state.get("trajectory", {})
    if traj:
        lines.append(f"Trajectory: {traj.get('form_trend', '?')}")

    # Key players
    players = team.get("key_players", [])
    if players:
        lines.append("Key players:")
        for p in players[:5]:
            lines.append(
                f"  - {p.get('name', '?')} ({p.get('position', '?')}) | "
                f"{p.get('goals', 0)}G {p.get('assists', 0)}A | "
                f"Rating: {p.get('avg_rating', 0):.1f} "
                f"(last 5: {p.get('form_rating', 0):.1f})"
            )

    # Injuries
    injuries = team.get("injuries", [])
    if injuries:
        lines.append("Potential missing:")
        for inj in injuries[:3]:
            lines.append(
                f"  - {inj.get('name', '?')} ({inj.get('position', '?')}) — "
                f"Impact: {inj.get('impact', '?')}"
            )

    # Psychology
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
