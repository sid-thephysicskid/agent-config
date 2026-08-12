import unittest

from src import models, tax


def line(net, band="standard"):
    return models.Line("SKU", "thing", 1, net, net_minor=net, vat_band=band)


class RateTest(unittest.TestCase):
    def test_known_regions(self):
        self.assertEqual(tax.rate_for("GB", "standard"), "0.20")
        self.assertEqual(tax.rate_for("IE", "reduced"), "0.135")
        self.assertEqual(tax.rate_for("DE", "zero"), "0.00")

    def test_reverse_charge_is_nil_not_an_error(self):
        self.assertEqual(tax.rate_for("US", "standard"), "0.00")
        self.assertTrue(tax.is_reverse_charge("CA"))

    def test_unknown_region_raises(self):
        with self.assertRaises(tax.UnknownRegion):
            tax.rate_for("ZZ", "standard")

    def test_unknown_band_raises(self):
        with self.assertRaises(tax.UnknownRegion):
            tax.rate_for("GB", "luxury")


class VatForLineTest(unittest.TestCase):
    def test_standard(self):
        self.assertEqual(tax.vat_for_line(line(10000), "GB"), 2000)

    def test_zero_band(self):
        self.assertEqual(tax.vat_for_line(line(10000, "zero"), "GB"), 0)


class BreakdownTest(unittest.TestCase):
    def test_groups_by_band(self):
        out = tax.breakdown([line(10000), line(5000), line(2000, "zero")], "GB")
        self.assertEqual(out["standard"]["net"], 15000)
        self.assertEqual(out["standard"]["vat"], 3000)
        self.assertEqual(out["zero"]["vat"], 0)

    def test_carries_the_rate_for_the_printed_invoice(self):
        out = tax.breakdown([line(100, "reduced")], "FR")
        self.assertEqual(out["reduced"]["rate"], "0.055")


class ExactVatTest(unittest.TestCase):
    def test_is_not_rounded(self):
        # The ledger posts from this, so it must still carry the fraction.
        self.assertNotEqual(tax.exact_vat([line(1234)], "GB") % 1, 0)


if __name__ == "__main__":
    unittest.main()
