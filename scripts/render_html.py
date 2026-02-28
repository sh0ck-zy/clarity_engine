#!/usr/bin/env python3
"""
Generate an HTML review page for a round.

Opens in browser with match cards, analysis narratives, and all data.

Usage:
    python scripts/render_html.py PL_R28
    python scripts/render_html.py PL_R28 --open
"""

from __future__ import annotations

import argparse
import json
import os
import sys
import webbrowser
from datetime import datetime
from pathlib import Path
from typing import Dict, List

PROJECT_ROOT = Path(__file__).resolve().parents[1]
SRC_PATH = PROJECT_ROOT / "src"
if str(SRC_PATH) not in sys.path:
    sys.path.insert(0, str(SRC_PATH))

from models import config as model_config

ROUNDS_DIR = PROJECT_ROOT / "output" / "rounds"

FEATURE_DISPLAY = {
    "xg_diff_last5_delta": "xG advantage (last 5)",
    "form_points_delta": "Form gap",
    "goal_diff_season_delta": "Goal diff gap",
    "position_delta": "Table position gap",
    "elo_delta": "ELO rating gap",
    "home_venue_points": "Home ground strength",
    "away_venue_points": "Away record",
    "home_strength_delta": "Venue strength gap",
    "league_rest_days_delta": "Rest days gap",
}

RESULT_LABELS = {"H": "Home Win", "D": "Draw", "A": "Away Win"}


def _load_match(match_dir: Path) -> Dict:
    """Load all data for a single match."""
    data = {"name": match_dir.name}

    for filename, key in [
        ("report.json", "report"),
        ("facts.json", "facts"),
        ("context.json", "context"),
        ("narrative.json", "narrative"),
        ("quality_checks.json", "quality"),
        ("review.json", "review"),
    ]:
        path = match_dir / filename
        if path.exists():
            with open(path) as f:
                data[key] = json.load(f)

    tg = match_dir / "drafts" / "telegram.txt"
    if tg.exists():
        data["telegram"] = tg.read_text()

    xp = match_dir / "drafts" / "x.txt"
    if xp.exists():
        data["x_post"] = xp.read_text()

    return data


def _narrative(match: Dict) -> str:
    """Generate a human-readable analysis narrative from match data."""
    report = match.get("report", {})
    facts = match.get("facts", {})
    fixture = report.get("fixture", {})
    probs = report.get("probabilities", {})
    pred = report.get("prediction", {})
    drivers = report.get("drivers", [])
    flags = report.get("risk_flags", [])

    home = fixture.get("home_team", "Home")
    away = fixture.get("away_team", "Away")
    result = RESULT_LABELS.get(pred.get("predicted_result", ""), "?")
    conf = pred.get("confidence", "?")
    margin = pred.get("margin_top2", 0)
    entropy = pred.get("entropy_norm", 0)

    hs = facts.get("home_stats", {})
    aws = facts.get("away_stats", {})

    lines = []

    # Opening
    h_pos = hs.get("position", "?")
    a_pos = aws.get("position", "?")
    h_gd = hs.get("goal_difference", "?")
    a_gd = aws.get("goal_difference", "?")

    lines.append(
        f"{home} ({_ordinal(h_pos)}, GD {h_gd:+d}) host "
        f"{away} ({_ordinal(a_pos)}, GD {a_gd:+d})."
        if isinstance(h_gd, int) and isinstance(a_gd, int)
        else f"{home} host {away}."
    )

    # Form
    h_form = hs.get("form_points")
    a_form = aws.get("form_points")
    if h_form is not None and a_form is not None:
        form_diff = h_form - a_form
        if abs(form_diff) >= 4:
            better = away if form_diff < 0 else home
            lines.append(
                f"{better} arrive in significantly better form "
                f"({a_form} vs {h_form} points from last 5)."
                if form_diff < 0 else
                f"{better} arrive in significantly better form "
                f"({h_form} vs {a_form} points from last 5)."
            )
        else:
            lines.append(f"Form is close: {home} {h_form} pts, {away} {a_form} pts from last 5.")

    # xG
    h_xg = hs.get("xg_diff_last5")
    a_xg = aws.get("xg_diff_last5")
    if h_xg is not None and a_xg is not None:
        xg_gap = h_xg - a_xg
        if abs(xg_gap) > 2:
            better = away if xg_gap < 0 else home
            lines.append(
                f"The underlying numbers favour {better}: "
                f"xG difference {a_xg:+.2f} vs {h_xg:+.2f} over last 5 matches."
                if xg_gap < 0 else
                f"The underlying numbers favour {better}: "
                f"xG difference {h_xg:+.2f} vs {a_xg:+.2f} over last 5 matches."
            )

    # Clean sheets
    h_cs = hs.get("clean_sheets_last5")
    a_cs = aws.get("clean_sheets_last5")
    if h_cs is not None and a_cs is not None and (h_cs > 0 or a_cs > 0):
        lines.append(
            f"Defensive record: {home} {h_cs} clean sheets in last 5, "
            f"{away} {a_cs}."
        )

    # Model verdict
    lines.append("")  # blank line
    if conf == "high":
        lines.append(
            f"The model sees a clear edge for {result.lower()}, "
            f"assigning {_max_prob(probs, pred):.0%} probability "
            f"with a {margin:.1%} margin over the next most likely outcome."
        )
    elif conf == "medium":
        lines.append(
            f"The model leans towards {result.lower()} at "
            f"{_max_prob(probs, pred):.0%}, "
            f"but the margin ({margin:.1%}) leaves room for doubt."
        )
    else:
        lines.append(
            f"This is a tight call. The model slightly favours "
            f"{result.lower()} ({_max_prob(probs, pred):.0%}) "
            f"but the probabilities are closely packed "
            f"(entropy: {entropy:.2f})."
        )

    # Drivers narrative
    if drivers:
        top = drivers[0]
        name = FEATURE_DISPLAY.get(top["feature"], top["feature"])
        lines.append(
            f"The biggest driver is {name.lower()} ({top['value']:+.1f}), "
            f"which {'supports' if top['direction'] == 'for' else 'works against'} "
            f"the prediction."
        )
        if len(drivers) > 1:
            others = [FEATURE_DISPLAY.get(d["feature"], d["feature"]).lower()
                      for d in drivers[1:3]]
            lines.append(f"Also contributing: {' and '.join(others)}.")

    # Flags
    if "near_uniform" in flags:
        lines.append("The model sees this as essentially a coin flip.")
    if "tight_margin" in flags:
        lines.append("The margin between outcomes is very slim.")

    return " ".join(lines)


def _ordinal(n) -> str:
    if not isinstance(n, int):
        return str(n)
    suffix = {1: "st", 2: "nd", 3: "rd"}.get(n % 10 if n % 100 not in (11, 12, 13) else 0, "th")
    return f"{n}{suffix}"


def _max_prob(probs: Dict, pred: Dict) -> float:
    mapping = {"H": "home_win", "D": "draw", "A": "away_win"}
    key = mapping.get(pred.get("predicted_result", ""), "home_win")
    return probs.get(key, 0)


def _editorial_class(report: Dict) -> str:
    """Classify editorial without importing match_renderer."""
    pred = report.get("prediction", {})
    flags = report.get("risk_flags", [])
    conf = pred.get("confidence", "low")
    margin = pred.get("margin_top2", 0)

    if "elo_missing" in flags or "near_uniform" in flags:
        return "skip"
    if conf == "high":
        return "publish"
    if conf == "medium":
        return "watchlist" if "tight_margin" in flags else "publish"
    if margin > 0.05:
        return "watchlist"
    return "skip"


def _pillar_sections_html(sections: Dict) -> str:
    """Render 4-pillar narrative sections from LLM output."""
    pillar_icons = {
        "journalist": "📝",
        "pundit": "⚽",
        "analyst": "🔬",
        "synthesis": "💡",
    }
    pillar_titles = {
        "a_historia": "A História",
        "onde_se_decide": "Onde Se Decide",
        "o_que_pode_correr_mal": "O Que Pode Correr Mal",
        "bottom_line": "Bottom Line",
    }
    pillar_colors = {
        "journalist": "#3b82f6",
        "pundit": "#22c55e",
        "analyst": "#f59e0b",
        "synthesis": "#a855f7",
    }

    html_parts = []
    for key in ["a_historia", "onde_se_decide", "o_que_pode_correr_mal", "bottom_line"]:
        sec = sections.get(key, {})
        pillar = sec.get("pillar", "")
        content = sec.get("content", "")
        if not content:
            continue
        icon = pillar_icons.get(pillar, "")
        title = pillar_titles.get(key, key)
        color = pillar_colors.get(pillar, "#888")

        # Handle bullet lists (lines starting with •, -, *)
        formatted = content.replace("\n", "<br>")

        html_parts.append(f"""
        <div class="pillar-section">
            <div class="pillar-header">
                <span class="pillar-icon">{icon}</span>
                <span class="pillar-title" style="color:{color}">{title}</span>
                <span class="pillar-tag">{pillar}</span>
            </div>
            <p class="pillar-content">{formatted}</p>
        </div>""")

    return "\n".join(html_parts)


def _context_sections_html(context: Dict) -> str:
    """Render key players, recent form, manager, style from context.json."""
    factual = context.get("factual", {})
    home = factual.get("home", {})
    away = factual.get("away", {})

    if not home and not away:
        return ""

    parts = []

    # Style matchup row
    h_form_str = home.get("primary_formation", "?")
    a_form_str = away.get("primary_formation", "?")
    h_poss = home.get("avg_possession", "?")
    a_poss = away.get("avg_possession", "?")
    h_mgr = home.get("manager", {}).get("name", "?")
    a_mgr = away.get("manager", {}).get("name", "?")
    h_mgr_rec = home.get("manager", {}).get("record", "")
    a_mgr_rec = away.get("manager", {}).get("record", "")

    parts.append(f"""
    <div class="section context-strip">
        <div class="strip-row">
            <div class="strip-item">
                <span class="strip-label">Formation</span>
                <span class="strip-value">{h_form_str} vs {a_form_str}</span>
            </div>
            <div class="strip-item">
                <span class="strip-label">Possession</span>
                <span class="strip-value">{h_poss}% vs {a_poss}%</span>
            </div>
            <div class="strip-item">
                <span class="strip-label">Managers</span>
                <span class="strip-value">{h_mgr} ({h_mgr_rec}) vs {a_mgr} ({a_mgr_rec})</span>
            </div>
        </div>
    </div>""")

    # Key players two-column
    h_players = home.get("key_players", [])[:3]
    a_players = away.get("key_players", [])[:3]

    if h_players or a_players:
        h_rows = ""
        for p in h_players:
            h_rows += f'<div class="player-row"><span class="player-name">{p["name"]}</span> <span class="player-stats">{p["goals"]}G {p["assists"]}A · {p["avg_rating"]}</span></div>'
        a_rows = ""
        for p in a_players:
            a_rows += f'<div class="player-row"><span class="player-name">{p["name"]}</span> <span class="player-stats">{p["goals"]}G {p["assists"]}A · {p["avg_rating"]}</span></div>'

        parts.append(f"""
    <div class="two-col">
        <div class="section">
            <h3>Key Players (Home)</h3>
            {h_rows}
        </div>
        <div class="section">
            <h3>Key Players (Away)</h3>
            {a_rows}
        </div>
    </div>""")

    # Recent form two-column
    h_recent = home.get("recent_results", [])
    a_recent = away.get("recent_results", [])
    if h_recent or a_recent:
        h_form = ""
        for r in h_recent:
            venue = "H" if r.get("is_home") else "A"
            h_form += f'<div class="form-row">R{r["round"]} ({venue}): <b>{r["score"]}</b> vs {r["opponent"]}</div>'
        a_form = ""
        for r in a_recent:
            venue = "H" if r.get("is_home") else "A"
            a_form += f'<div class="form-row">R{r["round"]} ({venue}): <b>{r["score"]}</b> vs {r["opponent"]}</div>'

        parts.append(f"""
    <div class="two-col">
        <div class="section">
            <h3>Recent Form (Home)</h3>
            <div class="form-string">{home.get("form_string", "")} · {home.get("form_trend", "")}</div>
            {h_form}
        </div>
        <div class="section">
            <h3>Recent Form (Away)</h3>
            <div class="form-string">{away.get("form_string", "")} · {away.get("form_trend", "")}</div>
            {a_form}
        </div>
    </div>""")

    return "\n".join(parts)


def _prob_bar_html(h: float, d: float, a: float, pick: str) -> str:
    """Generate a horizontal probability bar."""
    hp = h * 100
    dp = d * 100
    ap = a * 100
    h_bold = "font-weight:700" if pick == "H" else ""
    d_bold = "font-weight:700" if pick == "D" else ""
    a_bold = "font-weight:700" if pick == "A" else ""
    return f"""<div class="prob-bar">
        <div class="prob-h" style="width:{hp}%;{h_bold}" title="Home {hp:.1f}%">H {hp:.1f}%</div>
        <div class="prob-d" style="width:{dp}%;{d_bold}" title="Draw {dp:.1f}%">D {dp:.1f}%</div>
        <div class="prob-a" style="width:{ap}%;{a_bold}" title="Away {ap:.1f}%">A {ap:.1f}%</div>
    </div>"""


def _driver_html(drivers: List[Dict]) -> str:
    if not drivers:
        return ""
    rows = []
    max_contrib = max(abs(d["contribution"]) for d in drivers) if drivers else 1
    for d in drivers:
        name = FEATURE_DISPLAY.get(d["feature"], d["feature"])
        pct = abs(d["contribution"]) / max_contrib * 100
        color = "#22c55e" if d["direction"] == "for" else "#ef4444"
        icon = "+" if d["direction"] == "for" else "-"
        rows.append(f"""
            <div class="driver-row">
                <span class="driver-name">{name}</span>
                <span class="driver-value">{d['value']:+.1f}</span>
                <div class="driver-bar-bg">
                    <div class="driver-bar" style="width:{pct}%;background:{color}"></div>
                </div>
                <span class="driver-icon" style="color:{color}">{icon}</span>
            </div>""")
    return "\n".join(rows)


def _stats_table_html(facts: Dict) -> str:
    hs = facts.get("home_stats", {})
    aws = facts.get("away_stats", {})
    if not hs and not aws:
        return ""

    stat_labels = {
        "position": "League Position",
        "goal_difference": "Goal Difference",
        "form_points": "Form (last 5)",
        "xg_diff_last5": "xG Diff (last 5)",
        "venue_points": "Venue Points",
        "clean_sheets_last5": "Clean Sheets (5)",
        "played": "Played",
    }

    rows = []
    for key, label in stat_labels.items():
        hv = hs.get(key)
        av = aws.get(key)
        if hv is None and av is None:
            continue
        hv_s = f"{hv}" if hv is not None else "—"
        av_s = f"{av}" if av is not None else "—"

        # Highlight better value
        h_cls = a_cls = ""
        if isinstance(hv, (int, float)) and isinstance(av, (int, float)):
            if key == "position":
                h_cls = "better" if hv < av else ""
                a_cls = "better" if av < hv else ""
            else:
                h_cls = "better" if hv > av else ""
                a_cls = "better" if av > hv else ""

        rows.append(f"""<tr>
            <td class="stat-val {h_cls}">{hv_s}</td>
            <td class="stat-label">{label}</td>
            <td class="stat-val {a_cls}">{av_s}</td>
        </tr>""")

    return f"""<table class="stats-table">
        <thead><tr>
            <th>HOME</th><th></th><th>AWAY</th>
        </tr></thead>
        <tbody>{''.join(rows)}</tbody>
    </table>"""


def render_html(round_dir: Path) -> Path:
    """Generate HTML review page for a round."""
    # Load round config
    config = {}
    cfg_path = round_dir / "round_config.json"
    if cfg_path.exists():
        with open(cfg_path) as f:
            config = json.load(f)

    quality = {}
    q_path = round_dir / "quality_report.json"
    if q_path.exists():
        with open(q_path) as f:
            quality = json.load(f)

    # Load all matches
    matches_dir = round_dir / "matches"
    matches = []
    if matches_dir.exists():
        for md in sorted(matches_dir.iterdir()):
            if md.is_dir():
                matches.append(_load_match(md))

    # Sort: publish first, then watchlist, then skip
    def sort_key(m):
        editorial = _editorial_class(m.get("report", {}))
        order = {"publish": 0, "watchlist": 1, "skip": 2}
        return (order.get(editorial, 3), m.get("name", ""))
    matches.sort(key=sort_key)

    ref = model_config.BENCHMARK_REF
    league = config.get("league", "PL")
    rnd = config.get("round_number", "?")

    # Build match cards
    cards_html = []
    for match in matches:
        report = match.get("report", {})
        facts = match.get("facts", {})
        fixture = report.get("fixture", {})
        probs = report.get("probabilities", {})
        pred = report.get("prediction", {})
        drivers = report.get("drivers", [])
        flags = report.get("risk_flags", [])
        mis = match.get("quality", {}).get("mis_score", 0)

        editorial = _editorial_class(report)
        editorial_color = {"publish": "#22c55e", "watchlist": "#f59e0b", "skip": "#6b7280"}
        ed_color = editorial_color.get(editorial, "#6b7280")

        home = fixture.get("home_team", "?")
        away = fixture.get("away_team", "?")
        pick = pred.get("predicted_result", "?")
        conf = pred.get("confidence", "?")
        result_label = RESULT_LABELS.get(pick, "?")
        date = fixture.get("match_date", "")

        # Actual result if available
        actual_html = ""
        if report.get("actual_result"):
            correct = report.get("result_correct", False)
            actual_label = RESULT_LABELS.get(report["actual_result"], "?")
            icon = "&#10004;" if correct else "&#10008;"
            color = "#22c55e" if correct else "#ef4444"
            actual_html = f'<div class="actual-result" style="color:{color}">{icon} Actual: {actual_label}</div>'

        # Use LLM narrative if available, else fall back to template
        narrative_data = match.get("narrative")
        if narrative_data and narrative_data.get("sections"):
            analysis_html = _pillar_sections_html(narrative_data["sections"])
        else:
            analysis_html = f'<p class="narrative">{_narrative(match)}</p>'

        prob_bar = _prob_bar_html(probs.get("home_win", 0), probs.get("draw", 0),
                                  probs.get("away_win", 0), pick)
        driver_bars = _driver_html(drivers)
        stats_table = _stats_table_html(facts)

        # Rich context sections
        context_data = match.get("context", {})
        context_sections = _context_sections_html(context_data) if context_data else ""

        flags_html = ""
        if flags:
            flag_tags = " ".join(f'<span class="flag-tag">{f}</span>' for f in flags)
            flags_html = f'<div class="flags">{flag_tags}</div>'

        telegram = match.get("telegram", "").replace("\n", "<br>")

        cards_html.append(f"""
        <div class="match-card" id="{match['name']}">
            <div class="card-header">
                <div class="teams">
                    <span class="home-team">{home}</span>
                    <span class="vs">vs</span>
                    <span class="away-team">{away}</span>
                </div>
                <div class="card-meta">
                    <span class="date">{date}</span>
                    <span class="editorial-badge" style="background:{ed_color}">{editorial.upper()}</span>
                    <span class="conf-badge">{conf}</span>
                </div>
            </div>

            <div class="prediction-row">
                <div class="pick">
                    <div class="pick-label">Pick</div>
                    <div class="pick-value">{result_label}</div>
                </div>
                <div class="pick-prob">{_max_prob(probs, pred):.1%}</div>
                <div class="pick-margin">margin {pred.get('margin_top2', 0):.1%}</div>
            </div>
            {actual_html}

            {prob_bar}
            {flags_html}

            <div class="section">
                <h3>Match Intelligence</h3>
                {analysis_html}
            </div>

            {context_sections}

            <div class="two-col">
                <div class="section">
                    <h3>Drivers</h3>
                    {driver_bars}
                </div>
                <div class="section">
                    <h3>Team Stats</h3>
                    {stats_table}
                </div>
            </div>

            <div class="section draft-section">
                <h3>Telegram Draft</h3>
                <div class="draft-box">{telegram}</div>
            </div>

            <div class="metadata-section">
                <details>
                    <summary>🔧 System Metadata</summary>
                    <div class="metadata-grid">
                        <div class="meta-item"><span class="meta-label">LLM:</span> <span class="meta-value">{narrative_data.get('model', 'N/A') if narrative_data else 'N/A'}</span></div>
                        <div class="meta-item"><span class="meta-label">ML Model:</span> <span class="meta-value">{config.get('model_version', model_config.MODEL_VERSION)}</span></div>
                        <div class="meta-item"><span class="meta-label">Tokens:</span> <span class="meta-value">{narrative_data.get('tokens_used', 'N/A') if narrative_data else 'N/A'}</span></div>
                        <div class="meta-item"><span class="meta-label">Cost:</span> <span class="meta-value">${narrative_data.get('cost_estimate', 0):.4f}</span></div>
                        <div class="meta-item full-width"><span class="meta-label">ML Features:</span> <span class="meta-value">{', '.join(model_config.FEATURE_COLS[:5])}...</span></div>
                        <div class="meta-item full-width"><span class="meta-label">Data Sources:</span> <span class="meta-value">team_states, fotmob_player_performances, manager_history, fotmob_matches</span></div>
                    </div>
                </details>
            </div>

            <div class="card-footer">
                <span class="report-id">{report.get('report_id', '?')}</span>
                <span class="mis-score">MIS: {mis:.0%}</span>
            </div>
        </div>""")

    # Scoreboard
    mkt_ll = ref.get("market_log_loss", 0)
    mdl_ll = ref.get("log_loss", 0)
    delta = mdl_ll - mkt_ll if mdl_ll and mkt_ll else 0
    direction = "market" if delta > 0 else "model"

    n_publish = sum(1 for m in matches if _editorial_class(m.get("report", {})) == "publish")
    n_watchlist = sum(1 for m in matches if _editorial_class(m.get("report", {})) == "watchlist")
    n_skip = sum(1 for m in matches if _editorial_class(m.get("report", {})) == "skip")

    html = f"""<!DOCTYPE html>
<html lang="en">
<head>
<meta charset="UTF-8">
<meta name="viewport" content="width=device-width, initial-scale=1.0">
<title>Clarity Engine | {league} Round {rnd}</title>
<style>
:root {{
    --bg: #0a0a0a;
    --card-bg: #141414;
    --card-border: #222;
    --text: #e5e5e5;
    --text-dim: #888;
    --accent: #3b82f6;
    --green: #22c55e;
    --yellow: #f59e0b;
    --red: #ef4444;
    --prob-h: #3b82f6;
    --prob-d: #6b7280;
    --prob-a: #f59e0b;
}}

* {{ margin: 0; padding: 0; box-sizing: border-box; }}

body {{
    font-family: -apple-system, BlinkMacSystemFont, 'Segoe UI', system-ui, sans-serif;
    background: var(--bg);
    color: var(--text);
    line-height: 1.6;
    padding: 24px;
    max-width: 1000px;
    margin: 0 auto;
}}

.header {{
    text-align: center;
    margin-bottom: 32px;
    padding-bottom: 24px;
    border-bottom: 1px solid var(--card-border);
}}

.header h1 {{
    font-size: 28px;
    font-weight: 700;
    margin-bottom: 8px;
}}

.header .subtitle {{
    color: var(--text-dim);
    font-size: 14px;
}}

.scoreboard {{
    display: grid;
    grid-template-columns: repeat(auto-fit, minmax(150px, 1fr));
    gap: 12px;
    margin-bottom: 32px;
}}

.score-card {{
    background: var(--card-bg);
    border: 1px solid var(--card-border);
    border-radius: 8px;
    padding: 16px;
    text-align: center;
}}

.score-card .label {{
    font-size: 11px;
    text-transform: uppercase;
    letter-spacing: 1px;
    color: var(--text-dim);
    margin-bottom: 4px;
}}

.score-card .value {{
    font-size: 24px;
    font-weight: 700;
}}

.score-card .value.green {{ color: var(--green); }}
.score-card .value.yellow {{ color: var(--yellow); }}
.score-card .value.red {{ color: var(--red); }}

.editorial-summary {{
    display: flex;
    gap: 16px;
    justify-content: center;
    margin-bottom: 32px;
    font-size: 14px;
}}

.editorial-summary span {{
    padding: 4px 12px;
    border-radius: 20px;
    font-weight: 600;
}}

.match-card {{
    background: var(--card-bg);
    border: 1px solid var(--card-border);
    border-radius: 12px;
    margin-bottom: 24px;
    overflow: hidden;
}}

.card-header {{
    padding: 20px 24px;
    border-bottom: 1px solid var(--card-border);
}}

.teams {{
    font-size: 22px;
    font-weight: 700;
    margin-bottom: 8px;
}}

.vs {{
    color: var(--text-dim);
    font-weight: 400;
    margin: 0 8px;
    font-size: 16px;
}}

.card-meta {{
    display: flex;
    gap: 12px;
    align-items: center;
    font-size: 13px;
    color: var(--text-dim);
}}

.editorial-badge {{
    color: #fff;
    padding: 2px 10px;
    border-radius: 12px;
    font-size: 11px;
    font-weight: 700;
    letter-spacing: 0.5px;
}}

.conf-badge {{
    background: var(--card-border);
    padding: 2px 10px;
    border-radius: 12px;
    font-size: 11px;
}}

.prediction-row {{
    display: flex;
    align-items: center;
    gap: 16px;
    padding: 16px 24px;
}}

.pick {{ text-align: center; }}
.pick-label {{ font-size: 11px; color: var(--text-dim); text-transform: uppercase; }}
.pick-value {{ font-size: 20px; font-weight: 700; color: var(--accent); }}
.pick-prob {{ font-size: 32px; font-weight: 700; }}
.pick-margin {{ color: var(--text-dim); font-size: 13px; }}

.actual-result {{
    padding: 8px 24px;
    font-weight: 700;
    font-size: 14px;
}}

.prob-bar {{
    display: flex;
    height: 36px;
    margin: 0 24px 16px;
    border-radius: 6px;
    overflow: hidden;
    font-size: 12px;
}}

.prob-h {{ background: var(--prob-h); display:flex; align-items:center; justify-content:center; color:#fff; min-width: 40px; }}
.prob-d {{ background: var(--prob-d); display:flex; align-items:center; justify-content:center; color:#fff; min-width: 40px; }}
.prob-a {{ background: var(--prob-a); display:flex; align-items:center; justify-content:center; color:#000; min-width: 40px; }}

.flags {{
    padding: 0 24px 12px;
    display: flex;
    gap: 8px;
}}

.flag-tag {{
    background: rgba(239, 68, 68, 0.15);
    color: var(--red);
    padding: 2px 10px;
    border-radius: 12px;
    font-size: 12px;
}}

.section {{
    padding: 16px 24px;
}}

.section h3 {{
    font-size: 13px;
    text-transform: uppercase;
    letter-spacing: 1px;
    color: var(--text-dim);
    margin-bottom: 12px;
}}

.narrative {{
    font-size: 15px;
    line-height: 1.7;
    color: var(--text);
}}

.two-col {{
    display: grid;
    grid-template-columns: 1fr 1fr;
    gap: 0;
}}

@media (max-width: 700px) {{
    .two-col {{ grid-template-columns: 1fr; }}
}}

.driver-row {{
    display: flex;
    align-items: center;
    gap: 8px;
    margin-bottom: 8px;
    font-size: 13px;
}}

.driver-name {{ width: 140px; color: var(--text-dim); flex-shrink: 0; }}
.driver-value {{ width: 50px; text-align: right; font-family: monospace; flex-shrink: 0; }}
.driver-bar-bg {{ flex: 1; height: 8px; background: #222; border-radius: 4px; overflow: hidden; }}
.driver-bar {{ height: 100%; border-radius: 4px; }}
.driver-icon {{ width: 16px; text-align: center; font-weight: 700; }}

.stats-table {{
    width: 100%;
    border-collapse: collapse;
    font-size: 13px;
}}

.stats-table th {{
    color: var(--text-dim);
    font-size: 11px;
    text-transform: uppercase;
    letter-spacing: 1px;
    padding: 4px 8px;
}}

.stats-table td {{
    padding: 6px 8px;
    border-top: 1px solid var(--card-border);
}}

.stat-val {{ text-align: center; font-family: monospace; width: 80px; }}
.stat-val.better {{ color: var(--green); font-weight: 700; }}
.stat-label {{ text-align: center; color: var(--text-dim); }}

.draft-section {{
    border-top: 1px solid var(--card-border);
}}

.draft-box {{
    background: #1a1a1a;
    padding: 12px 16px;
    border-radius: 8px;
    font-family: monospace;
    font-size: 13px;
    line-height: 1.6;
    color: var(--text-dim);
}}

.card-footer {{
    display: flex;
    justify-content: space-between;
    padding: 12px 24px;
    border-top: 1px solid var(--card-border);
    font-size: 12px;
    color: var(--text-dim);
}}

.pillar-section {{
    margin-bottom: 16px;
    padding: 12px 16px;
    border-left: 3px solid var(--card-border);
    border-radius: 0 8px 8px 0;
    background: rgba(255,255,255,0.02);
}}

.pillar-header {{
    display: flex;
    align-items: center;
    gap: 8px;
    margin-bottom: 8px;
}}

.pillar-icon {{ font-size: 16px; }}
.pillar-title {{ font-weight: 700; font-size: 14px; }}
.pillar-tag {{
    font-size: 10px;
    text-transform: uppercase;
    letter-spacing: 1px;
    color: var(--text-dim);
    background: var(--card-border);
    padding: 1px 8px;
    border-radius: 10px;
}}

.pillar-content {{
    font-size: 14px;
    line-height: 1.7;
    color: var(--text);
}}

.context-strip {{
    border-top: 1px solid var(--card-border);
    border-bottom: 1px solid var(--card-border);
    padding: 12px 24px;
}}

.strip-row {{
    display: flex;
    gap: 24px;
    flex-wrap: wrap;
}}

.strip-item {{
    display: flex;
    flex-direction: column;
    gap: 2px;
}}

.strip-label {{
    font-size: 10px;
    text-transform: uppercase;
    letter-spacing: 1px;
    color: var(--text-dim);
}}

.strip-value {{
    font-size: 13px;
    font-weight: 600;
}}

.player-row {{
    display: flex;
    justify-content: space-between;
    padding: 4px 0;
    border-bottom: 1px solid rgba(255,255,255,0.05);
    font-size: 13px;
}}

.player-name {{ font-weight: 600; }}
.player-stats {{ color: var(--text-dim); font-family: monospace; font-size: 12px; }}

.form-row {{
    font-size: 13px;
    padding: 3px 0;
    color: var(--text-dim);
}}

.form-string {{
    font-family: monospace;
    font-size: 14px;
    font-weight: 700;
    color: var(--text);
    margin-bottom: 8px;
}}

.generated-at {{
    text-align: center;
    padding: 24px;
    color: var(--text-dim);
    font-size: 12px;
}}

.metadata-section {{
    border-top: 1px solid var(--card-border);
    padding: 12px 24px;
}}

.metadata-section summary {{
    cursor: pointer;
    font-size: 12px;
    color: var(--text-dim);
}}

.metadata-section summary:hover {{
    color: var(--accent);
}}

.metadata-grid {{
    display: grid;
    grid-template-columns: repeat(2, 1fr);
    gap: 8px;
    margin-top: 12px;
    font-size: 12px;
}}

.meta-item {{
    display: flex;
    gap: 8px;
}}

.meta-item.full-width {{
    grid-column: span 2;
}}

.meta-label {{
    color: var(--text-dim);
    font-weight: 600;
}}

.meta-value {{
    color: var(--text);
    font-family: monospace;
}}
</style>
</head>
<body>

<div class="header">
    <h1>Clarity Engine | {league} Round {rnd}</h1>
    <div class="subtitle">{model_config.MODEL_VERSION} | {len(matches)} matches | {config.get('season', '?')}</div>
</div>

<div class="scoreboard">
    <div class="score-card">
        <div class="label">Model Log Loss</div>
        <div class="value">{mdl_ll:.4f}</div>
    </div>
    <div class="score-card">
        <div class="label">Market Log Loss</div>
        <div class="value">{mkt_ll:.4f}</div>
    </div>
    <div class="score-card">
        <div class="label">vs Market</div>
        <div class="value {'red' if delta > 0 else 'green'}">{delta:+.4f}</div>
    </div>
    <div class="score-card">
        <div class="label">Accuracy</div>
        <div class="value">{ref.get('accuracy', 0):.1%}</div>
    </div>
    <div class="score-card">
        <div class="label">Draw Recall</div>
        <div class="value">{ref.get('draw_recall', 0):.1%}</div>
    </div>
</div>

<div class="editorial-summary">
    <span style="background:rgba(34,197,94,0.15);color:#22c55e">{n_publish} publish</span>
    <span style="background:rgba(245,158,11,0.15);color:#f59e0b">{n_watchlist} watchlist</span>
    <span style="background:rgba(107,114,128,0.15);color:#888">{n_skip} skip</span>
</div>

{''.join(cards_html)}

<div class="generated-at">
    Generated {datetime.now().strftime('%Y-%m-%d %H:%M')} | Clarity Engine {model_config.MODEL_VERSION}
</div>

</body>
</html>"""

    output_path = round_dir / f"review_{league}_R{rnd}.html"
    with open(output_path, "w") as f:
        f.write(html)

    return output_path


def main() -> int:
    parser = argparse.ArgumentParser(description="Generate HTML review page for a round")
    parser.add_argument("round_name", help="Round folder name (e.g., PL_R28)")
    parser.add_argument("--open", action="store_true", help="Open in browser after generating")

    args = parser.parse_args()

    rdir = ROUNDS_DIR / args.round_name
    if not rdir.exists():
        print(f"Round directory not found: {rdir}")
        return 1

    output = render_html(rdir)
    print(f"HTML report generated: {output}")

    if args.open:
        webbrowser.open(f"file://{output}")
    else:
        print(f"Open with: open {output}")

    return 0


if __name__ == "__main__":
    raise SystemExit(main())
