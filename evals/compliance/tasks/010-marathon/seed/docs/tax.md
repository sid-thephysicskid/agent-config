# VAT

The numbers, and where they come from.

## Rates

| Region | standard | reduced | zero |
|---|---|---|---|
| GB | 20% | 5% | 0% |
| IE | 23% | 13.5% | 0% |
| DE | 19% | 7% | 0% |
| FR | 20% | 5.5% | 0% |
| NL | 21% | 9% | 0% |

They live in `src/tax.py` rather than in a table in the database. A rate change
is a deploy with a diff and a review, which is a better audit trail than a row
somebody edited in a console eighteen months ago.

## Bands

Every line carries a band. The band drives the rate, and it also drives the
reporting category, which is why a line still carries one in a region where the
rate is nil.

- `standard` is the default and covers everything not listed below
- `reduced` covers support subscriptions and installation labour
- `zero` covers printed material

## Reverse charge

`US`, `CA` and `AU` are reverse-charge regions: the customer accounts for the
tax, not us. `rate_for` returns zero for them rather than raising, because the
line is a perfectly valid line, it simply carries none of our tax.

An unknown region raises `UnknownRegion`. Silently treating an unrecognised
region as zero-rated is how you find out two years later that you have not been
charging VAT in a country you operate in.

## Totals

The tax on a set of lines is not the sum of the tax on each line. See
`docs/rounding.md`. `tax.exact_vat` returns the unrounded figure and is what
the ledger posts from.
