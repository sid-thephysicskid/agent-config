# ledger

Billing for a small products-and-services business. Invoices in, postings out,
one reconciliation at the end of the month.

## Run it

```bash
python3 -m src.report                        # the monthly rollup
python3 -m unittest discover -s tests -t .   # the suite
python3 tools/regen_fixtures.py --check      # are the goldens current
```

Python 3.9 or newer, standard library only. No database, no network, no
configuration. The month in `src/report.py` is a committed sample so that the
report gives the same answer on every machine.

## The shape of it

| Module | What it owns |
|---|---|
| `src/money.py` | minor units, and the one rounding rule |
| `src/models.py` | the shapes that move between modules |
| `src/discount.py` | tier and volume discounts, which do not stack |
| `src/tax.py` | VAT rates and bands, by region |
| `src/invoice.py` | assembling lines into an invoice |
| `src/ledger.py` | double-entry postings, the system of record |
| `src/currency.py` | FX for the indicative report line only |
| `src/report.py` | the monthly rollup and the reconciliation |

`docs/` holds the rules the code is supposed to implement. Where the code and
the docs disagree, the docs are the specification and the code is the bug.
Start with `docs/rounding.md`: more incidents have come out of that one page
than out of everything else here combined.

## The reconciliation

The last line of `python3 -m src.report` compares what the invoices say
customers owe against what the ledger says they owe. Those two numbers are
computed down separate paths on purpose. It should read `clean`.

## Fixtures

`tests/fixtures/golden_invoices.json` pins every invoice shape anyone has
raised a ticket about. Regenerate with `python3 tools/regen_fixtures.py` when
behaviour changes deliberately, and read the diff before committing it. A
golden file updated without being read is a test that has stopped testing.

## Conventions

- Money is an `int` of minor units everywhere except inside `src/money.py`
- Anything not yet money is a `Decimal` and keeps its fraction
- An invoice is immutable once issued; corrections are credit notes
- Tests are `unittest`, standard library, no plugins
