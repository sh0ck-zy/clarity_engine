"""
Match Pack Builder — assembles all data for a match into a single artefact.

No LLM calls. Pure deterministic data assembly using existing tools.
Produces match_pack.json: the single source of truth for each match.
"""

from __future__ import annotations

import sys
from datetime import datetime
from pathlib import Path
from typing import Any, Dict, List, Optional

_SRC = Path(__file__).resolve().parents[1]
if str(_SRC) not in sys.path:
    sys.path.insert(0, str(_SRC))

from tools.team_tools import get_team_state, get_team_form, get_team_profile
from tools.match_tools import get_matchup_analysis
from tools.player_tools import get_key_players, get_injuries_impact
from tools.context_tools import build_game_state_tree, get_psychological_state


def _safe_tool_data(response) -> Dict[str, Any]:
    """Extract .data from a ToolResponse, returning {} on failure."""
    if response and response.success:
        return response.data
    return {}


def _call_optional(fn, *args, **kwargs) -> Dict[str, Any]:
    """Call a tool function, returning {} on any error."""
    try:
        resp = fn(*args, **kwargs)
        return _safe_tool_data(resp)
    except Exception:
        return {}


def _traced_tool_call(trace, name: str, fn, *args, **kwargs) -> Dict[str, Any]:
    """Call a tool function with trace instrumentation."""
    if trace is None:
        return _safe_tool_data(fn(*args, **kwargs))

    from evaluation.trace import TraceContext
    with TraceContext(trace, name, "tool") as ctx:
        resp = fn(*args, **kwargs)
        data = _safe_tool_data(resp)
        if not data:
            ctx.warnings.append(f"{name} returned empty data")
        return data


def _traced_optional(trace, name: str, fn, *args, **kwargs) -> Dict[str, Any]:
    """Call an optional tool function with trace instrumentation."""
    if trace is None:
        return _call_optional(fn, *args, **kwargs)

    from evaluation.trace import TraceContext
    with TraceContext(trace, name, "tool") as ctx:
        try:
            resp = fn(*args, **kwargs)
            data = _safe_tool_data(resp)
            if not data:
                ctx.warnings.append(f"{name} returned empty data")
            return data
        except Exception as e:
            ctx.success = False
            ctx.warnings.append(str(e))
            return {}


def build_match_pack(
    home_team: str,
    away_team: str,
    round_number: int,
    league_id: int,
    league_name: str = "",
    fixture_id: str = "",
    match_date: str = "",
    trace=None,
) -> Dict[str, Any]:
    """
    Assemble a complete match pack from existing tools.

    Calls 6 mandatory tools + 2 optional tools. No LLM.
    Returns a dict ready to be saved as match_pack.json.
    Optionally accepts a PipelineTrace for observability.
    """
    # --- MANDATORY TOOLS ---

    # 1. Team states (8-layer KG snapshot)
    home_state = _traced_tool_call(trace, f"get_team_state:{home_team}", get_team_state, home_team, round_number, league_id)
    away_state = _traced_tool_call(trace, f"get_team_state:{away_team}", get_team_state, away_team, round_number, league_id)

    # 2. Team form (recent trajectory with xG context)
    home_form = _traced_tool_call(trace, f"get_team_form:{home_team}", get_team_form, home_team, round_number=round_number, league_id=league_id)
    away_form = _traced_tool_call(trace, f"get_team_form:{away_team}", get_team_form, away_team, round_number=round_number, league_id=league_id)

    # 3. Team profiles (style classification)
    home_profile = _traced_tool_call(trace, f"get_team_profile:{home_team}", get_team_profile, home_team, round_number, league_id)
    away_profile = _traced_tool_call(trace, f"get_team_profile:{away_team}", get_team_profile, away_team, round_number, league_id)

    # 4. Matchup analysis (style clash)
    matchup = _traced_tool_call(
        trace, f"get_matchup_analysis:{home_team}_vs_{away_team}",
        get_matchup_analysis, home_team, away_team, "home", round_number, league_id,
    )

    # 5. Key players
    home_players = _traced_tool_call(trace, f"get_key_players:{home_team}", get_key_players, home_team, round_number)
    away_players = _traced_tool_call(trace, f"get_key_players:{away_team}", get_key_players, away_team, round_number)

    # 6. Game state tree (scenarios)
    game_tree = _traced_tool_call(
        trace, f"build_game_state_tree:{home_team}_vs_{away_team}",
        build_game_state_tree, home_team, away_team, "home", round_number, league_id,
    )

    # --- OPTIONAL TOOLS (fail gracefully) ---

    home_injuries = _traced_optional(trace, f"get_injuries_impact:{home_team}", get_injuries_impact, home_team, round_number)
    away_injuries = _traced_optional(trace, f"get_injuries_impact:{away_team}", get_injuries_impact, away_team, round_number)
    home_psychology = _traced_optional(trace, f"get_psychological_state:{home_team}", get_psychological_state, home_team, round_number, league_id)
    away_psychology = _traced_optional(trace, f"get_psychological_state:{away_team}", get_psychological_state, away_team, round_number, league_id)

    # --- ASSEMBLE ---

    # Merge state + form + profile into a unified team block
    home_block = _build_team_block(
        home_state, home_form, home_profile, home_players, home_injuries, home_psychology
    )
    away_block = _build_team_block(
        away_state, away_form, away_profile, away_players, away_injuries, away_psychology
    )

    # Recent matches from form detail
    recent_home = home_form.get("recent_matches", [])
    recent_away = away_form.get("recent_matches", [])

    # League context from team states
    league_context = _extract_league_context(home_state, away_state)

    return {
        "schema_version": "1.5",
        "fixture": {
            "fixture_id": fixture_id,
            "home_team": home_team,
            "away_team": away_team,
            "home_team_id": home_state.get("identity", {}).get("team_id"),
            "away_team_id": away_state.get("identity", {}).get("team_id"),
            "round_number": round_number,
            "match_date": match_date,
            "league": league_name,
            "league_id": league_id,
        },
        "home": home_block,
        "away": away_block,
        "matchup": matchup,
        "recent_matches": {
            "home": recent_home[:3],
            "away": recent_away[:3],
        },
        "league_context": league_context,
        "game_state_tree": game_tree,
        "tactical_rubric": None,  # filled by build_tactical_rubric() after pack is built
        "odds": {"available": False, "snapshot": None},
        "built_at": datetime.utcnow().isoformat() + "Z",
    }


def _build_team_block(
    state: Dict,
    form: Dict,
    profile: Dict,
    players: Dict,
    injuries: Dict,
    psychology: Dict,
) -> Dict[str, Any]:
    """Build unified team block from individual tool outputs."""
    return {
        "state": state,
        "form_detail": {
            "form": form.get("form", {}),
            "goals": form.get("goals", {}),
            "xg": form.get("xg", {}),
            "trajectory": form.get("trajectory", {}),
        },
        "style_profile": profile.get("style", {}),
        "attack_profile": profile.get("attack", {}),
        "defense_profile": profile.get("defense", {}),
        "venue_profile": profile.get("venue", {}),
        "formation": profile.get("formation", ""),
        "key_players": players.get("key_players", []),
        "top_scorers": players.get("top_scorers", []),
        "top_assists": players.get("top_assists", []),
        "injuries": injuries.get("potential_missing", []),
        "psychology": {
            "pressure": psychology.get("pressure", {}),
            "confidence": psychology.get("confidence", {}),
            "mindset": psychology.get("mindset", ""),
            "factors": psychology.get("factors", []),
        } if psychology else {},
    }


def _extract_league_context(home_state: Dict, away_state: Dict) -> Dict[str, Any]:
    """Extract league context from team states."""
    home_pos = home_state.get("position", {})
    away_pos = away_state.get("position", {})

    home_position = home_pos.get("position", 0)
    away_position = away_pos.get("position", 0)

    # Infer position context
    def _position_context(pos: int, total: int = 18) -> str:
        if pos <= 2:
            return "title race"
        if pos <= 6:
            return "upper table"
        if pos <= 12:
            return "mid-table"
        if pos <= total - 3:
            return "lower table"
        return "relegation zone"

    return {
        "home_position": home_position,
        "away_position": away_position,
        "home_position_context": _position_context(home_position),
        "away_position_context": _position_context(away_position),
    }


def build_ml_anchor(report: Dict) -> Dict[str, Any]:
    """
    Reshape a v1.4 report.json into the v1.5 ml_anchor.json format.

    The ML anchor is probabilistic context, NOT the truth base.
    """
    probs = report.get("probabilities", {})
    pred = report.get("prediction", {})
    drivers = report.get("drivers", [])

    return {
        "schema_version": "1.5",
        "match_id": report.get("fixture", {}).get("fixture_id", ""),
        "probabilities": {
            "H": probs.get("home_win", 0.33),
            "D": probs.get("draw", 0.33),
            "A": probs.get("away_win", 0.33),
        },
        "predicted_result": pred.get("predicted_result", ""),
        "confidence": pred.get("confidence_label", "medium"),
        "signals": {
            "p_max": pred.get("p_max", 0.33),
            "margin_top2": pred.get("margin_top2", 0.0),
            "entropy_norm": pred.get("entropy_norm", 1.0),
        },
        "drivers": drivers,
        "risk_flags": report.get("risk_flags", []),
        "model_version": report.get("writer_metadata", {}).get("prompt_version", "1.4"),
    }
