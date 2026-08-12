import unittest

from src import discount


class RateTest(unittest.TestCase):
    def test_tier_rates(self):
        self.assertEqual(discount.tier_rate("gold"), "0.10")
        self.assertEqual(discount.tier_rate("unknown"), "0.00")

    def test_volume_thresholds(self):
        self.assertEqual(discount.volume_rate(11), "0.00")
        self.assertEqual(discount.volume_rate(12), "0.075")
        self.assertEqual(discount.volume_rate(50), "0.12")
        self.assertEqual(discount.volume_rate(100), "0.20")

    def test_they_do_not_stack(self):
        # gold is 10 percent, twelve units is 7.5 percent. The better one wins
        # and the other is discarded, not added.
        self.assertEqual(discount.best_rate("gold", 12), "0.10")
        self.assertEqual(discount.best_rate("gold", 50), "0.12")


class NetTest(unittest.TestCase):
    def test_no_discount(self):
        self.assertEqual(discount.net_for(1000, 3, "standard"), 3000)

    def test_applies_to_the_line_not_the_unit(self):
        self.assertEqual(discount.net_for(33, 3, "silver"), 94)

    def test_volume_beats_tier_when_it_should(self):
        self.assertEqual(discount.net_for(1000, 100, "silver"), 80000)


class ExplainTest(unittest.TestCase):
    def test_names_the_source(self):
        self.assertEqual(discount.explain(1000, 100, "silver")["source"], "volume")
        self.assertEqual(discount.explain(1000, 1, "gold")["source"], "tier")
        self.assertEqual(discount.explain(1000, 1, "standard")["source"], "none")

    def test_saved_is_gross_minus_net(self):
        out = discount.explain(1000, 12, "standard")
        self.assertEqual(out["saved_minor"], out["gross_minor"] - out["net_minor"])


if __name__ == "__main__":
    unittest.main()
