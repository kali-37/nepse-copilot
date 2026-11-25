from __future__ import annotations

import pytest

from nepse_trader.advisor.confidence import (
    MARKET_CEILING,
    Confidence,
    ConfidenceError,
    band_for,
    blend,
    certain,
    confidence_from_history,
    market,
)


def test_user_facing_bands_preserve_the_pinned_wording() -> None:
    assert band_for(1.0) == ("CERTAIN", "arithmetic, not a forecast")
    assert band_for(0.95) == ("NEAR_CERTAIN", "very strong evidence")
    assert band_for(0.80) == ("STRONG", "strongly favoured")
    assert band_for(0.60) == ("LIKELY", "more likely than not")
    assert band_for(0.40) == ("COIN_FLIP", "a coin flip — size it small")
    assert band_for(0.20) == ("UNLIKELY", "unlikely — do not size up")
    assert band_for(0.00) == ("REMOTE", "remote")


def test_market_forecasts_cannot_enter_the_money_in_bank_band() -> None:
    confidence = market(0.999, "excellent measured history")
    assert MARKET_CEILING == 0.90
    assert confidence.value == MARKET_CEILING
    assert confidence.band == "STRONG"


def test_only_certain_can_construct_exactly_one() -> None:
    with pytest.raises(ConfidenceError):
        Confidence(1.0, "directional forecast")

    arithmetic = certain("CostEngine arithmetic")
    assert arithmetic.value == 1.0
    assert arithmetic.band == "CERTAIN"


def test_confidence_requires_an_auditable_basis_and_rounds_to_two_decimals() -> None:
    with pytest.raises(ConfidenceError):
        Confidence(0.5, "")

    confidence = Confidence(0.7567, "12 comparable calls", sample_size=12)
    assert confidence.value == 0.76
    assert confidence.sample_size == 12
    assert confidence.as_dict()["sample_size"] == 12


def test_history_is_shrunk_and_never_claims_certainty() -> None:
    empty = confidence_from_history(0, 0, prior=0.45)
    one_lucky_call = confidence_from_history(1, 1, prior=0.45)
    perfect_twelve = confidence_from_history(12, 12, prior=0.45)

    assert empty.value == 0.45
    assert one_lucky_call.value == 0.45
    assert 0.70 < perfect_twelve.value < MARKET_CEILING
    assert perfect_twelve.sample_size == 12


def test_blend_uses_the_weakest_link_not_an_average() -> None:
    edge = Confidence(0.42, "historical edge", sample_size=30)
    liquidity = Confidence(0.88, "liquidity history", sample_size=80)
    result = blend(edge, liquidity)

    assert result.value == 0.42
    assert result.sample_size == 30
    assert "historical edge" in result.basis
