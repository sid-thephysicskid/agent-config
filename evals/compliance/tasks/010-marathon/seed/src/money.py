"""Money in minor units, and the one rounding rule the whole service obeys.

Everything downstream of this module assumes two things:

  1. an amount of money is an `int` number of minor units (pence), never a
     float and never a Decimal that escaped
  2. a fractional amount is rounded exactly once, at the point it becomes an
     amount of money, using round-half-to-even

`docs/rounding.md` explains why. The short version is that a service which
rounds twice cannot reconcile against a ledger that rounds once, and the
difference shows up as pence that nobody can account for.
"""
from decimal import Decimal, ROUND_HALF_EVEN

UNIT = Decimal("1")


def to_minor(amount):
    """A decimal amount of currency as an integer number of minor units.

    >>> to_minor("12.345")
    1234
    >>> to_minor("12.355")
    1236
    """
    return int((Decimal(str(amount)) * 100).quantize(UNIT, rounding=ROUND_HALF_EVEN))


def to_major(minor):
    """Minor units back to a decimal amount, for display only."""
    return Decimal(int(minor)) / Decimal(100)


def apply_rate(minor, rate):
    """Apply a rate (a proportion, not a percentage) to an amount.

    Returns minor units.
    """
    return int((Decimal(int(minor)) * Decimal(str(rate)))
               .quantize(UNIT, rounding=ROUND_HALF_EVEN))


def share(minor, numerator, denominator):
    """Split an amount proportionally. Returns minor units."""
    if denominator == 0:
        return 0
    return int((Decimal(int(minor)) * Decimal(int(numerator)) / Decimal(int(denominator)))
               .quantize(UNIT, rounding=ROUND_HALF_EVEN))


def total(amounts):
    """Sum a sequence of minor-unit amounts.

    Exists so that call sites read the same whether they are summing two
    amounts or two thousand, and so there is one place to look if a total ever
    disagrees with its parts.
    """
    out = 0
    for a in amounts:
        out += int(a)
    return out


def format_minor(minor, symbol="GBP "):
    """Human-readable, for reports and nothing else."""
    sign = "-" if minor < 0 else ""
    whole, part = divmod(abs(int(minor)), 100)
    return "%s%s%d.%02d" % (sign, symbol, whole, part)
