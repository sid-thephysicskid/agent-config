"""FX conversion, for the indicative line on the report and nothing else.

Nothing is ever billed in a converted amount. The rate here is a month-end
snapshot committed with the code, because a report that reads a live rate
gives a different answer every time it is run and cannot be reproduced.
"""
from . import money

# Snapshot, 2026-07-31. Update with the month, not with the market.
RATES = {
    ("GBP", "EUR"): "1.1740",
    ("EUR", "GBP"): "0.8518",
    ("GBP", "USD"): "1.2685",
    ("USD", "GBP"): "0.7883",
    ("EUR", "USD"): "1.0805",
    ("USD", "EUR"): "0.9255",
}


class NoRate(Exception):
    pass


def rate(source, target):
    if source == target:
        return "1.0000"
    try:
        return RATES[(source, target)]
    except KeyError:
        raise NoRate("no snapshot rate for %s to %s" % (source, target))


def convert(minor, source, target):
    """Convert an amount in minor units. Indicative only."""
    if source == target:
        return int(minor)
    return money.apply_rate(minor, rate(source, target))


def round_trip_drift(minor, source, target):
    """How much is lost converting out and back, in minor units.

    Used by nothing in production. It exists because someone asks about it
    roughly once a quarter and this is cheaper than answering again.
    """
    return convert(convert(minor, source, target), target, source) - int(minor)
