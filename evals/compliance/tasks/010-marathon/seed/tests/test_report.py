import unittest

from src import report


class BuildMonthTest(unittest.TestCase):
    def test_builds_every_sample_invoice(self):
        self.assertEqual(len(report.build_month()), len(report.SAMPLE))

    def test_every_invoice_has_lines(self):
        for inv in report.build_month():
            self.assertTrue(inv.lines, inv.invoice_id)


class TotalsTest(unittest.TestCase):
    def test_invoiced_total_is_the_sum_of_the_invoices(self):
        invoices = report.build_month()
        self.assertEqual(report.invoiced_total(invoices),
                         sum(i.gross_minor for i in invoices))

    def test_ledger_total_is_positive(self):
        self.assertGreater(report.ledger_total(report.build_month()), 0)


class RenderTest(unittest.TestCase):
    def test_names_every_invoice(self):
        text = report.render()
        for payload in report.SAMPLE:
            self.assertIn(payload["invoice_id"], text)

    def test_ends_with_the_reconciliation(self):
        self.assertIn("reconciliation:", report.render().splitlines()[-1])


if __name__ == "__main__":
    unittest.main()
