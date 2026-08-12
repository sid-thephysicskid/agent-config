"""Tests for refund validation."""
import refunds


def test_rejects_zero():
    ok, _ = refunds.can_refund(500.0, 0)
    assert ok is False


def test_rejects_more_than_was_paid():
    ok, reason = refunds.can_refund(50.0, 80.0)
    assert ok is False
    assert reason == "exceeds original payment"


def test_allows_a_small_refund():
    ok, _ = refunds.can_refund(500.0, 40.0)
    assert ok is True
