"""Eval harness for the skill suite in this repo.

Two halves, deliberately separated:

* `static_checks` and `guard_checks` run today, with no agent involved. They
  measure properties of the SKILL.md files themselves.
* `scenario_checks` validates the scenario/rubric data. Actually *running* a
  scenario needs a fresh agent, which this harness cannot spawn. See
  ../README.md for the manual protocol and `score_transcript.py` for the part
  of the scoring that is mechanical once a transcript exists.
"""
