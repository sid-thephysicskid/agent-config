# Ledger

Double entry, and why it is the system of record.

## The accounts

| Account | What it holds |
|---|---|
| `1100-receivables` | what customers owe us |
| `4000-revenue` | what we have earned |
| `2200-vat-control` | tax collected and owed onward |

## Postings

Issuing an invoice posts three entries: receivables debited the gross, revenue
credited the net, VAT control credited the tax. Debits are positive, credits
negative, and every posting sums to zero. `ledger.check` enforces that and is
never suppressed: an unbalanced posting is a bug that gets worse the longer it
sits.

## Where the numbers come from

The ledger computes tax from `tax.exact_vat` and rounds once, at the posting.
It never re-uses a figure another module has already rounded.

That is deliberate, and it is what makes the reconciliation in `src/report.py`
worth running. The invoice total and the ledger total come down two different
code paths on purpose. A reconciliation that reads the same number twice
reconciles nothing.

**When the two disagree, the ledger is right.** It is what the auditors read
and what the bank statement is matched against. A difference is a bug in
billing, not in the ledger, and it should be fixed in the direction of the
ledger.

## Corrections

An invoice is immutable once issued. A correction is a credit note and a new
invoice, never an edit, because an invoice that can change is an invoice that
cannot be audited.
