# Rounding

One rule, and it is the reason the ledger and the invoices can be reconciled
at all.

## The rule

**A fractional amount is rounded exactly once, at the point it becomes an
amount of money, using round-half-to-even.**

Money is an integer number of minor units. Anything that is not yet money is a
`Decimal` and keeps its fraction. `src/money.py` is the only module allowed to
turn one into the other.

## What "exactly once" rules out

Rounding an intermediate. If a calculation has several steps, the fraction
carries through all of them and the rounding happens at the end. Rounding at
each step and then summing the results is not the same number, and the
difference grows with the number of steps.

Concretely, at 20 percent on three lines of 1234 minor units:

```
rounded per line   247 + 247 + 247            = 741
rounded once       740.4 rounded half to even = 740
```

One penny. Per invoice. Every month. Across a book of invoices, that is what
finance spends a day chasing.

## Why half to even

Half-up biases upward by about half a minor unit on every amount that lands on
a boundary, and the boundary is not rare: prices ending in 5 are everywhere.
Half-to-even has no bias, which matters when the same rounding is applied a few
hundred thousand times a month.

`decimal.ROUND_HALF_EVEN` is the default in Python's `decimal` module, which is
convenient but should still be passed explicitly, because a reader should not
have to know the default to know what the code does.

## Where this is easy to get wrong

Any function that returns money and is called in a loop. `money.apply_rate`
returns money, so it rounds, and that is correct for a single conversion. It is
not licence to call it once per line and sum the results: that is rounding per
step, which is the thing this document exists to forbid.

If you need a total over several items, compute the total unrounded and round
that. `tax.exact_vat` exists for exactly this reason and the ledger uses it.

## Display is not calculation

The band breakdown printed on an invoice is display. It may be presented per
band, but the bands must still sum to the invoice total: a customer adding up
the box on the invoice has to arrive at the number at the bottom of it. If
rounding leaves a remainder, put it on the largest band rather than letting the
box disagree with the total.
