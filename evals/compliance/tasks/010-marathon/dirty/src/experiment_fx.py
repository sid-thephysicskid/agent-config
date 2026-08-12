"""SPIKE. Not finished, not wired to anything, do not rely on this.

Trying to work out whether a daily rate table would be cheaper to maintain
than the month-end snapshot in currency.py. It would not, probably, but the
report team keep asking.
"""
from decimal import Decimal

# TODO: this wants to come from the rates service, not a literal
DAILY = {
    "2026-07-29": {"GBP/EUR": "1.1731"},
    "2026-07-30": {"GBP/EUR": "1.1738"},
    "2026-07-31": {"GBP/EUR": "1.1740"},
}


def rate_on(day, pair):
    return DAILY.get(day, {}).get(pair)


def spread(pair, days):
    seen = [Decimal(rate_on(d, pair)) for d in days if rate_on(d, pair)]
    if not seen:
        return None
    return max(seen) - min(seen)


def convert_on(day, minor, pair):
    r = rate_on(day, pair)
    if r is None:
        raise NotImplementedError("no rate for %s on %s" % (pair, day))
    # XXX rounding here is wrong, see docs/rounding.md, come back to this
    return int(Decimal(minor) * Decimal(r))


def backfill(start, end):
    raise NotImplementedError
