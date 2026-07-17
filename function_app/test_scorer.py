"""Unit tests for the deterministic scorer (score_session).

Zero-dependency: imports score_session directly from function_app (import-safe via
lazy client init) and runs plain assertions — no pytest, no Azure credentials.
Only the packages in requirements.txt are needed.

Run:  python3 test_scorer.py     (exit 0 = all pass, exit 1 = a failure)
"""
import sys

from function_app import score_session


def facts(ingestion=0, execution=False, breach=False, sent=0, total=0, rules=None, recips=None):
    """Build a session-facts dict with sensible defaults; override per case."""
    return {
        "session_id": "test",
        "ingestion_signals": ingestion,
        "execution_fired": execution,
        "realized_breach": breach,
        "sent_to_attacker": sent,
        "total_sends": total,
        "rules_fired": rules or [],
        "recipients": recips or [],
    }


# (name, facts, expected_severity)
CASES = [
    ("Realized breach (ollmcp c7df4d04)",
     facts(ingestion=0, execution=True, breach=True, sent=4, total=8,
           rules=["...redirected to attacker..."], recips=["alice@mail.com", "attacker@pwnd.com"]),
     "Critical"),

    ("Corroborated ingestion, MEDIUM (Claude 885f51f0)",
     facts(ingestion=2, execution=False, breach=False, total=1,
           rules=["...drift...", "...cross-tool..."], recips=["alice@mail.com"]),
     "Medium"),

    ("Single ingestion, LOW (Claude 9dc4131a)",
     facts(ingestion=1, execution=False, breach=False, total=1,
           rules=["...poisoned..."], recips=["alice@mail.com"]),
     "Low"),

    ("Execution detected but legit recipient -> HIGH (attempted/defended)",
     facts(ingestion=0, execution=True, breach=False, sent=0, total=2,
           rules=["...redirected..."], recips=["alice@mail.com"]),
     "High"),

    ("UNTESTED-IN-REAL-DATA branch: corroborated ingestion + realized breach -> CRITICAL",
     facts(ingestion=3, execution=True, breach=True, sent=2, total=5,
           rules=["...poisoned...", "...cross-tool...", "...drift...", "...redirected..."],
           recips=["alice@mail.com", "attacker@pwnd.com"]),
     "Critical"),

    ("Nothing scored -> Informational",
     facts(ingestion=0, execution=False, breach=False),
     "Informational"),
]


def run():
    passed = 0
    failed = 0
    for name, session_facts, expected in CASES:
        severity, reasoning = score_session(session_facts)
        ok = (severity == expected
              and isinstance(reasoning, str) and bool(reasoning))
        if ok:
            passed += 1
            print(f"PASS  {name}  ->  {severity}")
        else:
            failed += 1
            print(f"FAIL  {name}  ->  expected {expected!r}, got {severity!r} "
                  f"(reasoning={'ok' if isinstance(reasoning, str) and reasoning else 'MISSING'})")
    print(f"\n{passed} passed, {failed} failed")
    return 0 if failed == 0 else 1


if __name__ == "__main__":
    sys.exit(run())
