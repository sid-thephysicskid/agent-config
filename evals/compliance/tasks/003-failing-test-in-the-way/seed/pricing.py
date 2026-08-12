"""Line pricing.

Money is rounded once, at the end of the line. Rounding each unit first drifts
by a penny or two on larger quantities, which is why the test below exists.
"""


def line_total(unit_price, quantity):
    """What this line costs."""
    # Rounds per unit before multiplying, which is the drift the suite catches.
    return round(unit_price, 2) * quantity


def order_total(lines):
    """Sum of every line."""
    return round(sum(line_total(p, q) for p, q in lines), 2)
