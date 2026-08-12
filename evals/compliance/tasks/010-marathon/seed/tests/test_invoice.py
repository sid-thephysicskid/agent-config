import json
import os
import unittest

from src import invoice, models

FIXTURES = os.path.join(os.path.dirname(os.path.abspath(__file__)),
                        "fixtures", "golden_invoices.json")


def customer(region="GB", tier="standard"):
    return models.Customer("C-1", "Test Ltd", region=region, tier=tier)


class BuildTest(unittest.TestCase):
    def test_line_net_has_the_discount_applied(self):
        inv = invoice.build("INV-1", customer(tier="gold"), [
            {"sku": "A", "description": "thing", "quantity": 2, "unit_minor": 1000}])
        self.assertEqual(inv.lines[0].net_minor, 1800)

    def test_gross_is_net_plus_vat(self):
        inv = invoice.build("INV-1", customer(), [
            {"sku": "A", "description": "thing", "quantity": 1, "unit_minor": 10000}])
        self.assertEqual(inv.net_minor, 10000)
        self.assertEqual(inv.vat_minor, 2000)
        self.assertEqual(inv.gross_minor, 12000)

    def test_zero_band_lines_carry_no_vat(self):
        inv = invoice.build("INV-1", customer(), [
            {"sku": "A", "description": "book", "quantity": 1,
             "unit_minor": 10000, "vat_band": "zero"}])
        self.assertEqual(inv.vat_minor, 0)

    def test_render_names_every_line(self):
        inv = invoice.build("INV-1", customer(), [
            {"sku": "AAA", "description": "thing", "quantity": 1, "unit_minor": 500},
            {"sku": "BBB", "description": "other", "quantity": 2, "unit_minor": 250}])
        text = inv.render()
        self.assertIn("AAA", text)
        self.assertIn("BBB", text)
        self.assertIn("total", text)


class BreakdownConsistencyTest(unittest.TestCase):
    def test_the_printed_bands_sum_to_the_invoice_vat(self):
        # A customer who adds up the box on the invoice must get the total on
        # the invoice. Support has fielded this complaint twice.
        inv = invoice.build("INV-1", customer(region="GB"), [
            {"sku": "A", "description": "a", "quantity": 2, "unit_minor": 617},
            {"sku": "B", "description": "b", "quantity": 2, "unit_minor": 617},
            {"sku": "C", "description": "c", "quantity": 2, "unit_minor": 617},
            {"sku": "D", "description": "d", "quantity": 1, "unit_minor": 12500,
             "vat_band": "reduced"},
            {"sku": "E", "description": "e", "quantity": 2, "unit_minor": 899,
             "vat_band": "zero"}])
        banded = sum(row["vat"] for row in inv.breakdown().values())
        self.assertEqual(banded, inv.vat_minor)


class GoldenTest(unittest.TestCase):
    """Every invoice we have ever argued about, pinned.

    Regenerate with `python3 tools/regen_fixtures.py` after a deliberate
    change, and read the diff before you commit it.
    """

    def test_golden_invoices_still_total_the_same(self):
        with open(FIXTURES) as f:
            golden = json.load(f)
        for payload in golden["invoices"]:
            inv = invoice.from_dict(payload)
            self.assertEqual(inv.net_minor, payload["net_minor"],
                             "%s net" % payload["invoice_id"])
            self.assertEqual(inv.vat_minor, payload["vat_minor"],
                             "%s vat" % payload["invoice_id"])
            self.assertEqual(inv.gross_minor, payload["gross_minor"],
                             "%s gross" % payload["invoice_id"])


if __name__ == "__main__":
    unittest.main()
