import unittest

from src import invoice, ledger, models


def one_invoice(region="GB", tier="standard", lines=None):
    customer = models.Customer("C-1", "Test Ltd", region=region, tier=tier)
    return invoice.build("INV-1", customer, lines or [
        {"sku": "A", "description": "thing", "quantity": 1, "unit_minor": 10000}])


class PostTest(unittest.TestCase):
    def test_three_entries(self):
        self.assertEqual(len(ledger.post(one_invoice())), 3)

    def test_entries_balance(self):
        self.assertEqual(ledger.balance(ledger.post(one_invoice())), 0)

    def test_receivable_is_net_plus_vat(self):
        entries = ledger.post(one_invoice())
        self.assertEqual(ledger.receivable_total(entries), 12000)

    def test_revenue_is_credited_net(self):
        entries = ledger.post(one_invoice())
        self.assertEqual(ledger.balance(entries, ledger.REVENUE), -10000)


class CheckTest(unittest.TestCase):
    def test_unbalanced_entries_raise(self):
        bad = [models.Entry(ledger.REVENUE, 100, "X"),
               models.Entry(ledger.RECEIVABLES, -99, "X")]
        with self.assertRaises(ledger.Unbalanced):
            ledger.check(bad)


class PostAllTest(unittest.TestCase):
    def test_many_invoices_still_balance(self):
        invoices = [one_invoice(), one_invoice(region="NL"), one_invoice(tier="gold")]
        self.assertEqual(ledger.balance(ledger.post_all(invoices)), 0)


if __name__ == "__main__":
    unittest.main()
