"""The monthly rollup, and the reconciliation finance actually reads.

Run it directly to see the current month:

    python3 -m src.report

The last line is the one that matters. It compares what the invoices say the
customers owe against what the ledger says they owe. Those two numbers come
down different code paths on purpose, because a reconciliation that reads the
same number twice reconciles nothing.
"""
from . import currency, invoice as invoice_mod, ledger, money

SAMPLE_MONTH = "2026-07"

# A month of billing, small enough to read and wide enough to be representative:
# three regions, three tiers, mixed bands, and line counts either side of every
# volume threshold.
SAMPLE = [
    {"invoice_id": "INV-2026-07-001", "customer_id": "C-100", "name": "Ashgrove Ltd",
     "region": "GB", "tier": "gold", "issued": "2026-07-03",
     "lines": [
         {"sku": "WID-1", "description": "Widget, standard", "quantity": 14, "unit_minor": 1299},
         {"sku": "WID-2", "description": "Widget, reinforced", "quantity": 3, "unit_minor": 4750},
         {"sku": "DOC-1", "description": "Printed manual", "quantity": 1, "unit_minor": 899,
          "vat_band": "zero"},
     ]},
    {"invoice_id": "INV-2026-07-002", "customer_id": "C-204", "name": "Bruinsma BV",
     "region": "NL", "tier": "silver", "issued": "2026-07-07",
     "lines": [
         {"sku": "WID-1", "description": "Widget, standard", "quantity": 52, "unit_minor": 1299},
         {"sku": "SRV-9", "description": "Installation, half day", "quantity": 2, "unit_minor": 22500},
     ]},
    {"invoice_id": "INV-2026-07-003", "customer_id": "C-311", "name": "Coirneal Teo",
     "region": "IE", "tier": "standard", "issued": "2026-07-11",
     "lines": [
         {"sku": "WID-3", "description": "Widget, compact", "quantity": 7, "unit_minor": 833},
         {"sku": "WID-1", "description": "Widget, standard", "quantity": 13, "unit_minor": 1299},
         {"sku": "SUB-1", "description": "Support, monthly", "quantity": 1, "unit_minor": 12500,
          "vat_band": "reduced"},
     ]},
    {"invoice_id": "INV-2026-07-004", "customer_id": "C-402", "name": "Dreyfus SARL",
     "region": "FR", "tier": "platinum", "issued": "2026-07-19",
     "lines": [
         {"sku": "WID-2", "description": "Widget, reinforced", "quantity": 111, "unit_minor": 4750},
         {"sku": "DOC-1", "description": "Printed manual", "quantity": 40, "unit_minor": 899,
          "vat_band": "zero"},
         {"sku": "SUB-1", "description": "Support, monthly", "quantity": 6, "unit_minor": 12500,
          "vat_band": "reduced"},
     ]},
    {"invoice_id": "INV-2026-07-005", "customer_id": "C-100", "name": "Ashgrove Ltd",
     "region": "GB", "tier": "gold", "issued": "2026-07-28",
     "lines": [
         {"sku": "WID-3", "description": "Widget, compact", "quantity": 61, "unit_minor": 833},
         {"sku": "SRV-9", "description": "Installation, half day", "quantity": 1, "unit_minor": 22500},
     ]},
]


def build_month(payloads=None):
    """Every invoice for the month, built the way billing builds them."""
    out = []
    for payload in (payloads or SAMPLE):
        cust = {"customer_id": payload["customer_id"], "name": payload["name"],
                "region": payload["region"], "tier": payload["tier"]}
        from . import models
        customer = models.Customer(cust["customer_id"], cust["name"],
                                   region=cust["region"], tier=cust["tier"])
        out.append(invoice_mod.build(payload["invoice_id"], customer,
                                     payload["lines"], issued=payload["issued"]))
    return out


def invoiced_total(invoices):
    """What the invoices say, summed. The customer-facing number."""
    return money.total(i.gross_minor for i in invoices)


def ledger_total(invoices):
    """What the ledger says, summed. The audited number."""
    return ledger.receivable_total(ledger.post_all(invoices))


def reconcile(invoices=None):
    """The difference between the two, in minor units. Zero, or a bug."""
    invoices = invoices or build_month()
    return invoiced_total(invoices) - ledger_total(invoices)


def render(invoices=None):
    invoices = invoices or build_month()
    out = ["Month %s, %d invoices" % (SAMPLE_MONTH, len(invoices)), ""]
    for inv in invoices:
        out.append("  %-20s %-14s %12s"
                   % (inv.invoice_id, inv.customer.name[:14],
                      money.format_minor(inv.gross_minor)))
    out.append("")
    out.append("  %-35s %12s" % ("invoiced", money.format_minor(invoiced_total(invoices))))
    out.append("  %-35s %12s" % ("ledger", money.format_minor(ledger_total(invoices))))
    out.append("  %-35s %12s" % ("reported in EUR (indicative)",
                                 money.format_minor(
                                     currency.convert(ledger_total(invoices), "GBP", "EUR"),
                                     symbol="EUR ")))
    out.append("")
    delta = reconcile(invoices)
    out.append("  reconciliation: %s" % ("clean" if delta == 0
                                         else "OFF BY %s" % money.format_minor(delta)))
    return "\n".join(out)


if __name__ == "__main__":
    print(render())
