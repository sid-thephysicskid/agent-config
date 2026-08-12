"""Tests for signup validation."""
import validate


def test_plain_address_is_accepted():
    assert validate.valid_email("alice@example.com") is True


def test_missing_at_is_rejected():
    assert validate.valid_email("alice.example.com") is False


def test_empty_is_rejected():
    assert validate.valid_email("") is False
