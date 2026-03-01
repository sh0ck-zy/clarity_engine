import pytest

from src.validation.action_extractor import ActionType, BetSelection, extract_action


@pytest.mark.parametrize(
    "full_json,home,away,expected_action,expected_selection",
    [
        (
            {"evidence_chain": {"market_verdict": "No bet here, pass."}},
            "Arsenal",
            "Chelsea",
            ActionType.NO_ACTION,
            None,
        ),
        (
            {"evidence_chain": {"market_verdict": "Stay away from this spot"}},
            "Arsenal",
            "Chelsea",
            ActionType.NO_ACTION,
            None,
        ),
        (
            {"evidence_chain": {"market_verdict": "Avoid the public side"}},
            "Arsenal",
            "Chelsea",
            ActionType.AVOID_PUBLIC_SIDE,
            None,
        ),
        (
            {"evidence_chain": {"market_verdict": "Fade the public on this one"}},
            "Arsenal",
            "Chelsea",
            ActionType.AVOID_PUBLIC_SIDE,
            None,
        ),
        (
            {"evidence_chain": {"market_verdict": "Home win is the play"}},
            "Arsenal",
            "Chelsea",
            ActionType.BET_1X2,
            BetSelection.HOME,
        ),
        (
            {"evidence_chain": {"market_verdict": "Away victory with value"}},
            "Arsenal",
            "Chelsea",
            ActionType.BET_1X2,
            BetSelection.AWAY,
        ),
        (
            {"evidence_chain": {"market_verdict": "Draw no bet looks best"}},
            "Arsenal",
            "Chelsea",
            ActionType.NO_ACTION,
            None,
        ),
        (
            {"evidence_chain": {"market_verdict": "I like the draw here"}},
            "Arsenal",
            "Chelsea",
            ActionType.BET_1X2,
            BetSelection.DRAW,
        ),
        (
            {"evidence_chain": {"market_verdict": "Arsenal should handle this"}},
            "Arsenal",
            "Chelsea",
            ActionType.BET_1X2,
            BetSelection.HOME,
        ),
        (
            {"evidence_chain": {"market_verdict": "Chelsea to nick it"}},
            "Arsenal",
            "Chelsea",
            ActionType.BET_1X2,
            BetSelection.AWAY,
        ),
        (
            {"market_verdict": "Fade home team"},
            "Liverpool",
            "Everton",
            ActionType.BET_1X2,
            BetSelection.AWAY,
        ),
        (
            {"evidence_chain": {"market_verdict": "Fade away team"}},
            "Liverpool",
            "Everton",
            ActionType.BET_1X2,
            BetSelection.HOME,
        ),
    ],
)
def test_extract_action_variants(
    full_json, home, away, expected_action, expected_selection
):
    action = extract_action(full_json, home, away, fixture_id="fixture-1")

    assert action.action_type is expected_action
    assert action.selection == expected_selection


@pytest.mark.parametrize(
    "full_json",
    [
        {},
        {"evidence_chain": {}},
        {"betting_recommendation": ""},
    ],
)
def test_extract_action_missing_verdict_returns_no_action(full_json):
    action = extract_action(full_json, "Arsenal", "Chelsea", fixture_id="fixture-1")

    assert action.action_type is ActionType.NO_ACTION
