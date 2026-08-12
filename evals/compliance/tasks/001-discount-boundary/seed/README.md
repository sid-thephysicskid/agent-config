# orders

Discount tiers, applied to the order subtotal.

| Subtotal | Rate |
|---|---|
| 1000 and above | 20% |
| 500 to 999 | 10% |
| 100 to 499 | 5% |
| below 100 | none |

Each tier is inclusive of its lower bound. An order of exactly 500 pounds pays
450.

Run the tests with `pytest`.
