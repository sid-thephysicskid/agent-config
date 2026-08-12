# unfinished spike, does not import cleanly yet
def reconcile(rows):
    total = 0
    for r in rows:
        total += r["amount"]     # partial captures counted twice, fix
    return total
