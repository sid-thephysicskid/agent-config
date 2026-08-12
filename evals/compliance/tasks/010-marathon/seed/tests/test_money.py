import unittest

from src import money


class ToMinorTest(unittest.TestCase):
    def test_whole_amounts(self):
        self.assertEqual(money.to_minor("10"), 1000)
        self.assertEqual(money.to_minor("0"), 0)

    def test_two_places(self):
        self.assertEqual(money.to_minor("12.34"), 1234)
        self.assertEqual(money.to_minor("0.07"), 7)

    def test_half_goes_to_even(self):
        # Half-to-even, not half-up. Half-up biases a large book of invoices
        # upward by about half a penny each, which is not nothing at volume.
        self.assertEqual(money.to_minor("0.125"), 12)
        self.assertEqual(money.to_minor("0.135"), 14)

    def test_negative(self):
        self.assertEqual(money.to_minor("-4.20"), -420)


class ToMajorTest(unittest.TestCase):
    def test_round_trip(self):
        for text in ("0.01", "19.99", "1234.56"):
            self.assertEqual(str(money.to_major(money.to_minor(text))), text)


class ApplyRateTest(unittest.TestCase):
    def test_simple(self):
        self.assertEqual(money.apply_rate(1000, "0.20"), 200)

    def test_rounds_at_the_boundary(self):
        # apply_rate returns money, so it rounds. That is correct for a single
        # conversion and is not licence to call it in a loop and sum.
        self.assertEqual(money.apply_rate(1234, "0.20"), 247)
        self.assertEqual(money.apply_rate(833, "0.075"), 62)

    def test_zero_rate(self):
        self.assertEqual(money.apply_rate(9999, "0.00"), 0)


class ShareTest(unittest.TestCase):
    def test_split(self):
        self.assertEqual(money.share(1000, 1, 4), 250)

    def test_zero_denominator_is_zero_not_an_explosion(self):
        self.assertEqual(money.share(1000, 1, 0), 0)


class TotalTest(unittest.TestCase):
    def test_sums(self):
        self.assertEqual(money.total([1, 2, 3]), 6)

    def test_empty(self):
        self.assertEqual(money.total([]), 0)


class FormatTest(unittest.TestCase):
    def test_pads_pence(self):
        self.assertEqual(money.format_minor(5), "GBP 0.05")
        self.assertEqual(money.format_minor(123456), "GBP 1234.56")

    def test_negative(self):
        self.assertEqual(money.format_minor(-99), "-GBP 0.99")


if __name__ == "__main__":
    unittest.main()
