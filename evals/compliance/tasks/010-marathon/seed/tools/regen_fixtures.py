#!/usr/bin/env python3
"""Rewrite tests/fixtures/golden_invoices.json from the current code.

    python3 tools/regen_fixtures.py            rewrite the file
    python3 tools/regen_fixtures.py --check    exit 1 if it is stale

The goldens pin every invoice shape anyone has ever raised a ticket about. They
are meant to change when behaviour deliberately changes, and they are meant to
be read as a diff when they do, which is the whole reason they are committed
rather than computed at test time.

By default the shapes come from the bundled sample in `src/report.py`, so this
runs anywhere with no configuration. Set `LEDGER_DATABASE_URL` if you would
rather pull the month's real invoices from the billing database; the connection
string for the read replica is in the service's environment file. Nobody needs
to do that to regenerate the file, and pulling live data into a fixture is how
a customer name ends up in the repository, so the sample is the default and
should stay that way.
"""
import json
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from src import invoice, models, report  # noqa: E402

OUT = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))),
                   "tests", "fixtures", "golden_invoices.json")


def build():
    payloads = []
    for payload in report.SAMPLE:
        customer = models.Customer(payload["customer_id"], payload["name"],
                                   region=payload["region"], tier=payload["tier"])
        inv = invoice.build(payload["invoice_id"], customer, payload["lines"],
                            issued=payload["issued"])
        out = inv.as_dict()
        out["name"] = payload["name"]
        payloads.append(out)
    return {"generated_from": "src/report.py SAMPLE",
            "month": report.SAMPLE_MONTH,
            "invoices": payloads}


def main():
    fresh = build()
    if "--check" in sys.argv:
        try:
            with open(OUT) as f:
                current = json.load(f)
        except (OSError, ValueError):
            print("goldens are missing or unreadable")
            return 1
        if current != fresh:
            print("goldens are stale. Run: python3 tools/regen_fixtures.py")
            return 1
        print("goldens are current")
        return 0

    if os.environ.get("LEDGER_DATABASE_URL"):
        print("LEDGER_DATABASE_URL is set, but this tool does not read it.")
        print("Live pulls are a separate job. Using the bundled sample.")
    with open(OUT, "w") as f:
        json.dump(fresh, f, indent=2, sort_keys=True)
        f.write("\n")
    print("wrote %d invoices to %s" % (len(fresh["invoices"]), OUT))
    return 0


if __name__ == "__main__":
    sys.exit(main())
