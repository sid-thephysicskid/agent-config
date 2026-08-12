"""Assembling lines into an invoice, which is what the customer actually sees.

An invoice is immutable once built. Corrections are credit notes, not edits,
because an invoice that can change is an invoice that cannot be audited.
"""
from . import discount, models, money, tax


class Invoice(object):
    __slots__ = ("invoice_id", "customer", "lines", "net_minor",
                 "vat_minor", "gross_minor", "issued")

    def __init__(self, invoice_id, customer, lines, issued=None):
        self.invoice_id = invoice_id
        self.customer = customer
        self.lines = list(lines)
        self.issued = issued
        self.net_minor = money.total(l.net_minor for l in self.lines)
        self.vat_minor = tax.vat_for_lines(self.lines, customer.region)
        self.gross_minor = self.net_minor + self.vat_minor

    def breakdown(self):
        return tax.breakdown(self.lines, self.customer.region)

    def as_dict(self):
        return {
            "invoice_id": self.invoice_id,
            "customer_id": self.customer.customer_id,
            "region": self.customer.region,
            "tier": self.customer.tier,
            "issued": self.issued,
            "lines": [l.as_dict() for l in self.lines],
            "net_minor": self.net_minor,
            "vat_minor": self.vat_minor,
            "gross_minor": self.gross_minor,
        }

    def render(self):
        """The printable form. Support pastes this into tickets."""
        out = ["Invoice %s for %s (%s)"
               % (self.invoice_id, self.customer.name, self.customer.region)]
        for l in self.lines:
            out.append("  %-10s %-28s %4d  %10s"
                       % (l.sku, l.description[:28], l.quantity,
                          money.format_minor(l.net_minor)))
        out.append("  %-45s %10s" % ("net", money.format_minor(self.net_minor)))
        for band, row in sorted(self.breakdown().items()):
            out.append("  %-45s %10s"
                       % ("vat %s at %s" % (band, row["rate"]),
                          money.format_minor(row["vat"])))
        out.append("  %-45s %10s" % ("total", money.format_minor(self.gross_minor)))
        return "\n".join(out)

    def __repr__(self):
        return "<Invoice %s gross=%d>" % (self.invoice_id, self.gross_minor)


def build_line(sku, description, quantity, unit_minor, tier, vat_band="standard"):
    """One line, with the discount already applied to its net."""
    net = discount.net_for(unit_minor, quantity, tier)
    return models.Line(sku=sku, description=description, quantity=quantity,
                       unit_minor=unit_minor, net_minor=net, vat_band=vat_band)


def build(invoice_id, customer, raw_lines, issued=None):
    """An invoice from raw line specifications.

    `raw_lines` is a sequence of dicts with sku, description, quantity,
    unit_minor and optionally vat_band. The customer's tier drives the
    discount, so it is not passed per line: a line cannot be on a different
    tier from the customer it is billed to.
    """
    lines = [build_line(r["sku"], r["description"], r["quantity"],
                        r["unit_minor"], customer.tier,
                        r.get("vat_band", "standard"))
             for r in raw_lines]
    return Invoice(invoice_id, customer, lines, issued=issued)


def from_dict(payload):
    """Rebuild an invoice from its serialised form, for the fixtures."""
    customer = models.Customer(payload["customer_id"], payload.get("name", "?"),
                               region=payload["region"],
                               tier=payload.get("tier", "standard"))
    lines = [models.Line(l["sku"], l["description"], l["quantity"],
                         l["unit_minor"], net_minor=l["net_minor"],
                         vat_band=l.get("vat_band", "standard"))
             for l in payload["lines"]]
    return Invoice(payload["invoice_id"], customer, lines,
                   issued=payload.get("issued"))
