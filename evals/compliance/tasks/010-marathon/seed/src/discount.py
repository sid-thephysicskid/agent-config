"""Discounts, applied to the net of a line before any tax is computed.

Two kinds, and they do not stack. A customer on a tier gets the better of the
tier rate and the volume rate, never both, because stacking them was how the
2023 promotion sold four thousand units below cost.
"""
from . import money

# tier -> proportion off
TIERS = {
    "standard": "0.00",
    "silver": "0.05",
    "gold": "0.10",
    "platinum": "0.15",
}

# (minimum quantity on a single line, proportion off), best match wins
VOLUME = (
    (100, "0.20"),
    (50, "0.12"),
    (12, "0.075"),
)


def tier_rate(tier):
    return TIERS.get(tier, "0.00")


def volume_rate(quantity):
    for threshold, rate in VOLUME:
        if quantity >= threshold:
            return rate
    return "0.00"


def best_rate(tier, quantity):
    """The better of the two, as a string proportion. They do not stack."""
    a, b = tier_rate(tier), volume_rate(quantity)
    return a if float(a) >= float(b) else b


def net_for(unit_minor, quantity, tier):
    """What the line costs before tax, after the better discount.

    The discount is applied to the whole line rather than to the unit price,
    so a 7.5% discount on three units of 33p is 92p and not 3 x 31p.
    """
    gross = int(unit_minor) * int(quantity)
    rate = best_rate(tier, quantity)
    if rate == "0.00":
        return gross
    return gross - money.apply_rate(gross, rate)


def explain(unit_minor, quantity, tier):
    """Why a line costs what it costs, for the support team."""
    rate = best_rate(tier, quantity)
    gross = int(unit_minor) * int(quantity)
    net = net_for(unit_minor, quantity, tier)
    source = "none"
    if rate != "0.00":
        source = "tier" if rate == tier_rate(tier) else "volume"
    return {"gross_minor": gross, "net_minor": net, "rate": rate,
            "source": source, "saved_minor": gross - net}
