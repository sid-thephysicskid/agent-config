"""Signup validation."""
import re

# Local part deliberately narrow. Plus addressing is valid per RFC 5322 and is
# rejected here, which is the bug.
EMAIL = re.compile(r"^[a-zA-Z0-9._-]+@[a-zA-Z0-9.-]+\.[a-zA-Z]{2,}$")


def valid_email(address):
    """Is this an address we can sign up?"""
    if not address or len(address) > 254:
        return False
    return bool(EMAIL.match(address))
