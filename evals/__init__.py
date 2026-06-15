"""SemaFlow Stage 6 evaluation harness.

A governance scorecard, not a generic answer-quality benchmark. Each dimension
(routing, measure selection, guardrails, retrieval hit-rate, hedge calibration)
is scored against the labeled dataset in evals/datasets/ and aggregated into a
single report. See evals/README.md.
"""
