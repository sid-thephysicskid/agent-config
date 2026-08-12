"""Double-entry postings for an issued invoice.

The ledger is the system of record. When the ledger and the invoice disagree,
the ledger is right and the invoice is a bug, because the ledger is what the
auditors read and what the bank reconciles against.

See `docs/ledger.md`. The rule that matters here: the ledger computes tax from
the unrounded figure and rounds once, at the posting. It never re-uses a
number another module has already rounded.
"""
from decimal import Decimal, ROUND_HALF_EVEN

from . import models, tax

UNIT = Decimal("1")

REVENUE = "4000-revenue"
VAT_CONTROL = "2200-vat-control"
RECEIVABLES = "1100-receivables"


class Unbalanced(Exception):
    """Raised when a set of entries does not sum to zero. Never suppressed."""


def post(invoice):
    """The entries for one invoice. Debits positive, credits negative."""
    net = invoice.net_minor
    vat = int(tax.exact_vat(invoice.lines, invoice.customer.region)
              .quantize(UNIT, rounding=ROUND_HALF_EVEN))
    ref = invoice.invoice_id
    entries = [
        models.Entry(RECEIVABLES, net + vat, ref),
        models.Entry(REVENUE, -net, ref),
        models.Entry(VAT_CONTROL, -vat, ref),
    ]
    check(entries)
    return entries


def check(entries):
    """Every posting sums to zero, or it is not a posting."""
    out = sum(e.amount_minor for e in entries)
    if out != 0:
        raise Unbalanced("entries sum to %d, not 0" % out)
    return True


def balance(entries, account=None):
    """The balance of one account, or of everything if no account is named."""
    return sum(e.amount_minor for e in entries
               if account is None or e.account == account)


def receivable_total(entries):
    """What the customers between them owe, in minor units.

    This is the number the bank statement is reconciled against, so it is the
    number that gets noticed when it is wrong.
    """
    return balance(entries, RECEIVABLES)


def post_all(invoices):
    entries = []
    for inv in invoices:
        entries.extend(post(inv))
    check(entries)
    return entries
