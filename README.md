# plan-policy-override

Human-approved, scoped, expiring exceptions to policy findings on
InspectablePlans. Part of the trustworthy agentic AI prototype for
project BRJP26100123 (BITS–RMIT).

A policy check flags a plan. A human reviewer can waive a MEDIUM or
LOW finding — for one rule, optionally one step, for one exact plan
version, until a date. HIGH findings can never be overridden.

## The rules

- An override names one `rule_id`, and optionally one `step_id`.
  With no `step_id` it waives every finding for that rule in the plan.
- It binds to one exact `plan_id` + `plan_version`. A revised plan
  needs a fresh override.
- The `reason` must be at least 10 characters. "ok" is not a reason.
- It must expire in the future. An expired override waives nothing.
- Duplicate override ids are rejected. The log (`overrides.jsonl`)
  is append-only.

## Usage

```bash
python3 policy_override.py examples/plan.json examples/findings.json examples/overrides.jsonl --today 2026-11-21
python3 policy_override.py examples/plan.json examples/findings.json examples/overrides.jsonl --json --out report.json
```

Exit codes: `0` no findings remain, `1` a HIGH finding remains
(blocked), `2` only MEDIUM/LOW findings remain (needs review).

## Example

In `examples/`, OVR-1 waives the MEDIUM budget finding (ORG-01)
until 2026-12-31. OVR-2 tries to waive the HIGH send-gate finding
(SEC-01) and is rejected, so the verdict stays **BLOCKED** — see
`examples/override-report.md`.

## Tests

```bash
python3 -m unittest discover -s tests -v
```

9 tests, standard library only.
