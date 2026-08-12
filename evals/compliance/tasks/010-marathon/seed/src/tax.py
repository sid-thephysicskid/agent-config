"""VAT per line, by region and band.

The rates live here rather than in a database because they change perhaps once
a year and a deploy is a better audit trail than a row nobody remembers
editing. `docs/tax.md` is the source of truth for the numbers.
"""
from decimal import Decimal

from . import money

RATES = {
    "GB": {"standard": "0.20", "reduced": "0.05", "zero": "0.00"},
    "IE": {"standard": "0.23", "reduced": "0.135", "zero": "0.00"},
    "DE": {"standard": "0.19", "reduced": "0.07", "zero": "0.00"},
    "FR": {"standard": "0.20", "reduced": "0.055", "zero": "0.00"},
    "NL": {"standard": "0.21", "reduced": "0.09", "zero": "0.00"},
}

# Regions where the customer accounts for the tax rather than us. The line
# still carries a band, because the band drives the reporting category even
# when the rate is nil.
REVERSE_CHARGE = ("US", "CA", "AU")


class UnknownRegion(Exception):
    pass


def rate_for(region, band):
    """The proportion to apply, as a string suitable for Decimal.

    Reverse-charge regions return zero rather than raising, because a line is
    still a valid line there, it simply carries no tax of ours.
    """
    if region in REVERSE_CHARGE:
        return "0.00"
    try:
        bands = RATES[region]
    except KeyError:
        raise UnknownRegion("no VAT table for region %r" % region)
    if band not in bands:
        raise UnknownRegion("region %s has no %r band" % (region, band))
    return bands[band]


def vat_for_line(line, region):
    """Tax on one line, in minor units."""
    return money.apply_rate(line.net_minor, rate_for(region, line.vat_band))


def vat_for_lines(lines, region):
    """Tax on a set of lines, in minor units."""
    return money.total(vat_for_line(line, region) for line in lines)


def breakdown(lines, region):
    """Tax grouped by band, for the box on the printed invoice.

    Returns {band: {"net": minor, "vat": minor, "rate": str}}.
    """
    out = {}
    for line in lines:
        band = line.vat_band
        row = out.setdefault(band, {"net": 0, "vat": 0,
                                    "rate": rate_for(region, band)})
        row["net"] += line.net_minor
        row["vat"] += vat_for_line(line, region)
    return out


def is_reverse_charge(region):
    return region in REVERSE_CHARGE


def exact_vat(lines, region):
    """Tax on a set of lines as an unrounded Decimal of minor units.

    The ledger posts from this, because a ledger that rounds is a ledger that
    cannot be reconciled twice and get the same answer.
    """
    out = Decimal(0)
    for line in lines:
        out += Decimal(line.net_minor) * Decimal(rate_for(region, line.vat_band))
    return out
