"""Policy overrides for InspectablePlans (BRJP26100123, Week 3).

A policy check can flag a plan, but a human reviewer can approve a
*scoped, expiring* exception for a MEDIUM or LOW finding. HIGH findings
can never be overridden -- they stay blocked, no matter who asks.

An override is a single JSON object, one per line in overrides.jsonl:

    {"id": "OVR-1", "rule_id": "ORG-01", "step_id": "s2",
     "plan_id": "summarise-paper", "plan_version": 2,
     "reviewer": "akhila", "reason": "Budget is $6 for this one-off run.",
     "expires": "2026-12-31"}

Rules, in plain words:
- An override names one rule, and optionally one step. With no step_id
  it waives every finding for that rule in that plan version.
- It binds to one exact plan id + version. A revised plan needs a
  fresh override; an old one does not carry over silently.
- The reason must be at least 10 characters -- "ok" is not a reason.
- It must expire in the future. An expired override is ignored, not
  an error in the file, but it waives nothing.
- Duplicate override ids are rejected. The log is append-only; to end
  an override early, add a revocation, don't edit the file in place.

Usage:
    python3 policy_override.py plan.json findings.json overrides.jsonl
    python3 policy_override.py plan.json findings.json overrides.jsonl --today 2026-11-21 --json

Exit codes: 0 = no remaining findings, 1 = a HIGH finding remains
(blocked), 2 = only MEDIUM/LOW findings remain (needs review).
"""
import argparse
import json
import sys
from datetime import date

MIN_REASON_LEN = 10


def parse_date(value):
    """Parse a YYYY-MM-DD date, returning a date or None."""
    try:
        year, month, day = (int(part) for part in str(value).split("-"))
        return date(year, month, day)
    except (ValueError, TypeError, AttributeError):
        return None


def validate_override(override, plan, seen_ids, today):
    """Return a list of errors; empty means the override is well-formed.

    Well-formed is not the same as applicable: a well-formed override
    may still match no finding, which apply_overrides reports
    separately instead of treating it as a file error.
    """
    errors = []
    if not isinstance(override, dict):
        return ["override is not an object"]
    oid = override.get("id")
    if not oid:
        errors.append("missing id")
    elif oid in seen_ids:
        errors.append(f"duplicate override id: {oid}")
    if not override.get("rule_id"):
        errors.append("missing rule_id")
    if not override.get("reviewer"):
        errors.append("missing reviewer")
    reason = override.get("reason", "")
    if len(str(reason).strip()) < MIN_REASON_LEN:
        errors.append("reason must be at least 10 characters")
    expires = parse_date(override.get("expires"))
    if expires is None:
        errors.append("expires must be a YYYY-MM-DD date")
    elif expires <= today:
        errors.append(f"override expired on {override.get('expires')}")
    if override.get("plan_id") != plan.get("id"):
        errors.append("plan_id does not match the plan")
    if override.get("plan_version") != plan.get("version"):
        errors.append("plan_version does not match the plan")
    return errors


def is_active(override, today):
    """True when the override has not expired yet."""
    expires = parse_date(override.get("expires"))
    return expires is not None and expires > today


def apply_overrides(findings, overrides, plan, today=None):
    """Apply overrides to policy findings.

    Returns (remaining, applied, rejected) where rejected is a list of
    {"override": ..., "reason": ...} dicts. HIGH findings are never
    waived. An override that matches no finding is rejected, so a
    typo in a rule id cannot silently look like a waiver.
    """
    today = today or date.today()
    remaining = list(findings)
    applied = []
    rejected = []
    seen_ids = set()
    for override in overrides:
        errors = validate_override(override, plan, seen_ids, today)
        if isinstance(override, dict) and override.get("id"):
            seen_ids.add(override["id"])
        if errors:
            rejected.append({"override": override, "reason": "; ".join(errors)})
            continue
        matches = [
            f for f in remaining
            if f.get("rule_id") == override["rule_id"]
            and (override.get("step_id") is None
                 or f.get("step_id") == override["step_id"])
        ]
        if not matches:
            rejected.append({"override": override,
                             "reason": "matches no remaining finding"})
            continue
        waivable = [f for f in matches if f.get("severity") != "HIGH"]
        if not waivable:
            rejected.append({"override": override,
                             "reason": "HIGH findings cannot be overridden"})
            continue
        for finding in waivable:
            remaining.remove(finding)
        applied.append({"override": override,
                        "waived": [f.get("rule_id") for f in waivable]})
    return remaining, applied, rejected


def verdict(remaining):
    """One-line verdict for the remaining findings."""
    if not remaining:
        return "CLEAN"
    if any(f.get("severity") == "HIGH" for f in remaining):
        return "BLOCKED"
    return "NEEDS REVIEW"


def render_markdown(plan, remaining, applied, rejected):
    lines = [f"# Policy overrides — {plan.get('id')} v{plan.get('version')}",
             "", f"Verdict: **{verdict(remaining)}**", ""]
    lines.append("## Applied overrides")
    if applied:
        for item in applied:
            ovr = item["override"]
            lines.append(f"- {ovr['id']}: {ovr['rule_id']} waived "
                         f"({', '.join(item['waived'])}) by {ovr['reviewer']} "
                         f"until {ovr['expires']} — {ovr['reason']}")
    else:
        lines.append("- none")
    lines.append("")
    lines.append("## Remaining findings")
    if remaining:
        for finding in remaining:
            lines.append(f"- [{finding.get('severity')}] {finding.get('rule_id')} "
                         f"({finding.get('step_id', '-')}) — "
                         f"{finding.get('message', '')}")
    else:
        lines.append("- none")
    lines.append("")
    lines.append("## Rejected overrides")
    if rejected:
        for item in rejected:
            ovr = item["override"]
            oid = ovr.get("id") if isinstance(ovr, dict) else "?"
            lines.append(f"- {oid}: {item['reason']}")
    else:
        lines.append("- none")
    return "\n".join(lines) + "\n"


def load_json(path):
    with open(path, encoding="utf-8") as handle:
        return json.load(handle)


def load_jsonl(path):
    overrides = []
    with open(path, encoding="utf-8") as handle:
        for line in handle:
            line = line.strip()
            if line:
                overrides.append(json.loads(line))
    return overrides


def main(argv=None):
    parser = argparse.ArgumentParser(description="Apply policy overrides to findings.")
    parser.add_argument("plan")
    parser.add_argument("findings")
    parser.add_argument("overrides")
    parser.add_argument("--today", default=None,
                        help="YYYY-MM-DD; defaults to today")
    parser.add_argument("--json", action="store_true",
                        help="print a JSON report instead of Markdown")
    parser.add_argument("--out", default=None, help="write the report to a file")
    args = parser.parse_args(argv)
    today = parse_date(args.today) if args.today else date.today()
    if today is None:
        print("error: --today must be YYYY-MM-DD", file=sys.stderr)
        return 2
    plan = load_json(args.plan)
    findings = load_json(args.findings)
    overrides = load_jsonl(args.overrides)
    remaining, applied, rejected = apply_overrides(findings, overrides, plan, today)
    result = {"verdict": verdict(remaining), "remaining": remaining,
              "applied": applied, "rejected": rejected}
    report = json.dumps(result, indent=2) + "\n" if args.json \
        else render_markdown(plan, remaining, applied, rejected)
    if args.out:
        with open(args.out, "w", encoding="utf-8") as handle:
            handle.write(report)
    else:
        print(report, end="")
    if not remaining:
        return 0
    if any(f.get("severity") == "HIGH" for f in remaining):
        return 1
    return 2


if __name__ == "__main__":
    raise SystemExit(main())
