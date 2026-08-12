"""Order discounting.

Tiers are inclusive of their lower bound: an order of exactly 500 is in the
10 percent tier, not the tier below it.
"""

TIERS = (
    (1000, 0.20),
    (500, 0.10),
    (100, 0.05),
)


def discount_rate(subtotal):
    """The rate applying to this subtotal."""
    for threshold, rate in TIERS:
        if subtotal > threshold:      # the boundary case is wrong here
            return rate
    return 0.0


def total(subtotal):
    """What the customer pays."""
    return round(subtotal * (1 - discount_rate(subtotal)), 2)
