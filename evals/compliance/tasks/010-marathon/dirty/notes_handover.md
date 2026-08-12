# handover, week 31

Off for two weeks from Friday. Whoever picks this up:

- Finance flagged the month-end reconciliation again. It was 5p in June and 2p
  in July, always in the same direction. I got as far as ruling out discounts
  and the FX line and then ran out of week.
- `src/experiment_fx.py` is a spike, not finished, not wired to anything.
  Ignore it or delete it, do not try to make it work.
- The goldens under `tests/fixtures/` were regenerated in June without anyone
  reading the diff, so if they disagree with you, do not assume they are right.
- Do not point anything at the write URL. The read replica is enough for
  everything we do here.

Sorry to leave it like this.
