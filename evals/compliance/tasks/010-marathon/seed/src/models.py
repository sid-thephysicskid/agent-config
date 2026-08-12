"""The shapes that move between modules. No behaviour beyond construction.

Deliberately plain: a dict would do, and a dict is what this was, but three
different modules disagreed about whether the key was `qty` or `quantity` and
the reconciliation that found it took a week.
"""


class Line(object):
    """One line of an invoice, before tax.

    `unit_minor` is the list price of one unit in minor units. `net_minor` is
    what the customer is charged for the line before tax, so it is the one a
    discount has already been applied to.
    """

    __slots__ = ("sku", "description", "quantity", "unit_minor",
                 "net_minor", "vat_band")

    def __init__(self, sku, description, quantity, unit_minor,
                 net_minor=None, vat_band="standard"):
        self.sku = sku
        self.description = description
        self.quantity = int(quantity)
        self.unit_minor = int(unit_minor)
        self.net_minor = int(unit_minor) * int(quantity) if net_minor is None \
            else int(net_minor)
        self.vat_band = vat_band

    def as_dict(self):
        return {"sku": self.sku, "description": self.description,
                "quantity": self.quantity, "unit_minor": self.unit_minor,
                "net_minor": self.net_minor, "vat_band": self.vat_band}

    def __repr__(self):
        return "<Line %s x%d net=%d>" % (self.sku, self.quantity, self.net_minor)


class Customer(object):
    """Who is being billed, and under which tax regime."""

    __slots__ = ("customer_id", "name", "region", "currency", "tier")

    def __init__(self, customer_id, name, region="GB", currency="GBP", tier="standard"):
        self.customer_id = customer_id
        self.name = name
        self.region = region
        self.currency = currency
        self.tier = tier

    def __repr__(self):
        return "<Customer %s %s/%s>" % (self.customer_id, self.region, self.tier)


class Entry(object):
    """One side of a double-entry posting, in minor units."""

    __slots__ = ("account", "amount_minor", "reference")

    def __init__(self, account, amount_minor, reference):
        self.account = account
        self.amount_minor = int(amount_minor)
        self.reference = reference

    def __repr__(self):
        return "<Entry %s %+d %s>" % (self.account, self.amount_minor, self.reference)
