import json

from meal_to_cart.counsel import (NullCounsel, apply_ranking, from_env, parse_rank,
                                  parse_risk)

RANK_WRAPPED = json.dumps({"content": [{"type": "text", "text": json.dumps({
    "verdict": "ranked",
    "ranking": [{"id": "b", "score": 3.74, "confidence": 0.78},
                {"id": "c", "score": 0.70, "confidence": 0.71},
                {"id": "a", "score": 0.69, "confidence": 0.67}],
})}]})

RISK_WRAPPED = json.dumps({"content": [{"type": "text", "text": json.dumps({
    "decision_id": "tool_risk",
    "verdict": "ask_human",
    "reason": "learned_verdict_head(p=0.841)",
    "confidence": 0.841,
})}]})


def test_a_wrapped_jev_response_parses_into_a_ranking():
    ranked = parse_rank(RANK_WRAPPED)
    assert ranked is not None
    assert [r.item_id for r in ranked] == ["b", "c", "a"]
    assert ranked[0].score == 3.74


def test_the_real_dill_case_puts_the_herb_first():
    """The measured result, as a regression test."""
    ranked = parse_rank(RANK_WRAPPED)
    assert ranked is not None
    assert ranked[0].item_id == "b"      # Fresh Dill
    assert ranked[-1].item_id == "a"     # Dilly Bites snack pack


def test_a_wrapped_laya_response_parses_into_a_risk():
    risk = parse_risk(RISK_WRAPPED)
    assert risk is not None
    assert risk.verdict == "ask_human"
    assert risk.confidence == 0.841


def test_garbage_is_none_rather_than_an_exception():
    assert parse_rank({"content": [{"text": "not json"}]}) is None
    assert parse_rank({"no": "ranking"}) is None
    assert parse_risk({"nothing": True}) is None
    assert parse_rank({"ranking": [{"id": "a"}]}) is None


def test_ranking_reorders_without_losing_candidates():
    cands = [{"item_id": "a", "title": "snack"},
             {"item_id": "b", "title": "herb"},
             {"item_id": "c", "title": "weird"}]
    ranked = parse_rank(RANK_WRAPPED)
    assert ranked is not None
    out = apply_ranking(cands, ranked)
    assert [c["item_id"] for c in out] == ["b", "c", "a"]


def test_unscored_candidates_are_kept_at_the_end():
    cands = [{"item_id": "x", "title": "unscored"}, {"item_id": "b", "title": "herb"}]
    ranked = parse_rank(RANK_WRAPPED)
    assert ranked is not None
    assert [c["item_id"] for c in apply_ranking(cands, ranked)] == ["b", "x"]


def test_with_no_configuration_the_advisor_is_a_no_op():
    import os

    from meal_to_cart.counsel import ENV_VAR

    saved = os.environ.pop(ENV_VAR, None)
    try:
        counsel = from_env()
        assert isinstance(counsel, NullCounsel)
        assert counsel.available is False
    finally:
        if saved is not None:
            os.environ[ENV_VAR] = saved
