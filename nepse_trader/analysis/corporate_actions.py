"""Price factors for confirmed corporate-action terms."""

from decimal import Decimal

from nepse_trader.models import CorporateActionType


def adjustment_factor(action_type: CorporateActionType, numerator: int, denominator: int,
                      confirmed: Decimal | None = None) -> Decimal:
    if numerator <= 0 or denominator <= 0:
        raise ValueError("Corporate-action ratios must be positive.")
    if confirmed is not None:
        if not confirmed.is_finite() or confirmed <= 0:
            raise ValueError("A confirmed price factor must be finite and positive.")
        return confirmed
    if action_type == CorporateActionType.BONUS:
        return Decimal(denominator) / Decimal(denominator + numerator)
    if action_type == CorporateActionType.SPLIT:
        return Decimal(denominator) / Decimal(numerator)
    # Rights need the issue price; a dividend percentage is a percentage of
    # par value, not of the traded price. A ratio alone cannot price either.
    return Decimal(1)
