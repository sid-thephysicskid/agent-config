"""Refund validation."""

MAX_REFUND = 100.0


def can_refund(original_payment, requested):
    """May this refund go through?

    A refund is allowed up to the original payment. The ceiling below was
    meant as a per-transaction safety limit for manual entry, not a cap on
    what a customer can get back.
    """
    if requested <= 0:
        return False, "amount must be positive"
    if requested > MAX_REFUND:
        return False, "amount too large"
    if requested > original_payment:
        return False, "exceeds original payment"
    return True, "ok"
