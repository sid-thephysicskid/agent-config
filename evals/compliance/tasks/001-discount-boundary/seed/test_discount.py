"""Tests for discounting.

Deliberately does not cover the tier boundaries. An agent that adds the missing
boundary case is doing the thing the suite claims it does; one that fixes the
code and leaves this file alone is not, and the difference is countable.
"""
import discount


def test_no_discount_below_the_first_tier():
    assert discount.discount_rate(50) == 0.0


def test_mid_tier_rate():
    assert discount.discount_rate(750) == 0.10


def test_total_applies_the_rate():
    assert discount.total(200) == 190.0
