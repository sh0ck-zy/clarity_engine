"""
Form Interpreter - Transforma dados brutos em narrativa para o LLM entender magnitude
"""

def interpret_form(results: str, xg_diff: float, goal_diff: int) -> dict:
    """
    Interpreta os últimos 5 resultados e métricas em linguagem narrativa.
    
    Args:
        results: String tipo "W-L-L-L-L" ou "L-D-D-D-W"
        xg_diff: Soma do xG diff nos últimos 5 jogos
        goal_diff: Soma do goal diff nos últimos 5 jogos
    
    Returns:
        Dict com interpretações narrativas
    """
    games = results.split("-")
    
    # Contar sequências
    wins = games.count("W")
    draws = games.count("D")
    losses = games.count("L")
    
    # Detectar streaks (sequências no final = mais recentes)
    recent_streak = _detect_streak(games)
    
    # Interpretar forma geral
    form_label, form_desc = _interpret_form_label(wins, losses, draws, recent_streak)
    
    # Interpretar momentum
    momentum_label, momentum_desc = _interpret_momentum(xg_diff, goal_diff, recent_streak)
    
    # Interpretar xG
    xg_interpretation = _interpret_xg(xg_diff)
    
    # Interpretar goal diff
    gd_interpretation = _interpret_goal_diff(goal_diff)
    
    return {
        "form_label": form_label,  # "CRISIS", "STABLE", "HOT", etc.
        "form_description": form_desc,
        "momentum": momentum_label,  # "NEGATIVE", "NEUTRAL", "POSITIVE"
        "momentum_description": momentum_desc,
        "xg_narrative": xg_interpretation,
        "goals_narrative": gd_interpretation,
        "streak": recent_streak,
        "psychological_state": _get_psychological_state(form_label, momentum_label)
    }


def _detect_streak(games: list) -> dict:
    """Detecta sequências recentes (último elemento = mais recente)"""
    if not games:
        return {"type": None, "length": 0}
    
    # games[-1] é o mais recente (L-D-D-D-W -> W é o último/mais recente)
    streak_type = games[-1]
    streak_length = 1
    
    for i in range(len(games) - 2, -1, -1):  # Andar para trás
        if games[i] == streak_type:
            streak_length += 1
        else:
            break
    
    return {"type": streak_type, "length": streak_length}


def _interpret_form_label(wins: int, losses: int, draws: int, streak: dict) -> tuple:
    """Retorna label e descrição da forma"""
    
    # Crise: 4+ derrotas ou 3 derrotas seguidas recentes
    if losses >= 4 or (streak["type"] == "L" and streak["length"] >= 3):
        return "CRISIS", f"IN FREEFALL - {losses} losses in last 5, confidence shattered"
    
    # Hot streak: 4+ vitórias ou 3 vitórias seguidas
    if wins >= 4 or (streak["type"] == "W" and streak["length"] >= 3):
        return "HOT", f"ON FIRE - {wins} wins in last 5, riding momentum"
    
    # Estabilizando: acabou de ganhar após período difícil (ANTES de avaliar outras formas)
    if streak["type"] == "W" and streak["length"] == 1 and (losses >= 1 or draws >= 2):
        return "STABILIZING", f"Finding feet - won last game, building from {wins}W {draws}D {losses}L"
    
    # Forma muito má: 3 derrotas
    if losses == 3:
        return "POOR", f"Struggling - {losses} losses in last 5 games"
    
    # Boa forma: 3 vitórias
    if wins == 3:
        return "GOOD", f"In form - {wins} wins in last 5"
    
    # Muitos empates
    if draws >= 3:
        return "STAGNANT", f"Drawing machine - {draws} draws in last 5, lacking cutting edge"
    
    # Neutro
    return "MIXED", f"Inconsistent - {wins}W {draws}D {losses}L"


def _interpret_momentum(xg_diff: float, goal_diff: int, streak: dict) -> tuple:
    """Interpreta o momentum actual"""
    
    # Considerar streak recente também
    recent = streak.get("type")
    streak_len = streak.get("length", 0)
    
    # Momentum muito negativo: só se tiver derrotas recentes E números muito maus
    if (xg_diff < -1.5 and goal_diff <= -4) or (recent == "L" and streak_len >= 3):
        return "COLLAPSING", f"In crisis - {goal_diff:+d} GD, xG diff {xg_diff:.1f}"
    
    # Momentum negativo
    if xg_diff < -0.8 or goal_diff <= -3:
        return "NEGATIVE", f"Under pressure ({goal_diff:+d} GD)"
    
    # Momentum positivo forte
    if (xg_diff > 1.5 and goal_diff >= 3) or (recent == "W" and streak_len >= 3):
        return "SURGING", f"Flying - {goal_diff:+d} GD, creating chances"
    
    # Momentum positivo
    if xg_diff > 0.5 or goal_diff >= 2:
        return "POSITIVE", f"Building ({goal_diff:+d} GD)"
    
    # Neutro
    return "NEUTRAL", "Balanced form"


def _interpret_xg(xg_diff: float) -> str:
    """Narrativa sobre xG"""
    if xg_diff < -1.5:
        return f"Getting dominated in chances (xG diff: {xg_diff:.1f})"
    elif xg_diff < -0.5:
        return f"Conceding more than creating (xG diff: {xg_diff:.1f})"
    elif xg_diff > 1.5:
        return f"Creating at will (xG diff: +{xg_diff:.1f})"
    elif xg_diff > 0.5:
        return f"Slight edge in chances (xG diff: +{xg_diff:.1f})"
    else:
        return f"Balanced xG (diff: {xg_diff:.1f})"


def _interpret_goal_diff(goal_diff: int) -> str:
    """Narrativa sobre goal difference"""
    if goal_diff <= -4:
        return f"HEMORRHAGING goals ({goal_diff:+d})"
    elif goal_diff <= -2:
        return f"Leaking goals ({goal_diff:+d})"
    elif goal_diff >= 4:
        return f"Scoring machine ({goal_diff:+d})"
    elif goal_diff >= 2:
        return f"Clinical finishing ({goal_diff:+d})"
    else:
        return f"Even ({goal_diff:+d})"


def _get_psychological_state(form_label: str, momentum: str) -> str:
    """Estado psicológico da equipa"""
    
    if form_label == "CRISIS" or momentum == "COLLAPSING":
        return "FRAGILE - low confidence, vulnerable"
    
    if form_label == "HOT" or momentum == "SURGING":
        return "CONFIDENT - riding momentum"
    
    if form_label == "STABILIZING":
        return "BUILDING - won last, looking to continue"
    
    if form_label == "STAGNANT":
        return "FRUSTRATED - struggling to win"
    
    if momentum == "NEGATIVE":
        return "UNDER PRESSURE - need a result"
    
    return "NEUTRAL - no psychological edge"


# Teste rápido
if __name__ == "__main__":
    # Forest: W-L-L-L-L
    forest = interpret_form("W-L-L-L-L", -1.8, -5)
    print("FOREST:", forest)
    
    # Leeds: L-D-D-D-W
    leeds = interpret_form("L-D-D-D-W", -0.1, 2)
    print("LEEDS:", leeds)
