# Finding: Alert-commit race in autonomous triage response

**Date observed:** 2026-07-10
**Sprint:** 4 (bounded LLM narrator)
**Finding severity:** Low — graceful degradation held; no crash, no wrong verdict, no bad action
**Status:** Root-caused; bounded-retry fix designed, coded, and control-flow-tested; deploy + clean re-run scheduled 2026-07-13

## What happened

The first fully-autonomous end-to-end run (forwarder ingest → scheduled analytic rule →
incident → automation rule → playbook → Function) produced a *degraded* triage comment
instead of a scored, narrated assessment:

> [Triage pipeline - Sprint 3] Pipeline reached this incident, but no SessionId could be
> reconstructed (no matching alert in the lookback window). Manual review suggested.

- Incident: #9, GUID `75ab2604-39df-44b6-bb92-a90c4a9ccd8a`
- Incident created: `2026-07-10T14:22:33Z`
- Function comment written: `2026-07-10T14:22:45Z` (managed identity `func-mcp-triage-lab-rg`)
- Elapsed: **~12 seconds**

The autonomous chain fired correctly and fast — the managed identity responded 12s after
incident creation. The issue is purely timing, downstream of that.

## Root cause

A timing race between **response-automation speed** and **SecurityAlert commit latency**.

`_reconstruct_session_id` bridges incident → alert → SessionId via a join against
`SecurityAlert`. At T+12s the `SecurityAlert` row was not yet queryable (ingestion/commit
latency), so the join returned no rows → `_reconstruct_session_id` returned `None` → the
Function took its designed graceful-degradation branch and wrote the degraded comment.

**The Function behaved correctly.** This is a TIMING limitation, not a defect in the
degradation logic: the automation ran faster than the alert became queryable.

## Why earlier manual tests did not surface it

Manual `curl` invocation happens after natural human delay, by which point the
`SecurityAlert` row is already committed and queryable. Autonomous execution runs at full
speed with no such delay, exposing the race. Race conditions of this kind characteristically
pass manual testing and appear only under real autonomous timing.

## Planned fix (2026-07-13)

Bounded retry in `_reconstruct_session_id`:

- On a no-alert-found result, wait 45s and retry ONCE (max 2 attempts total).
- If still not found, return `None` and degrade gracefully as before (unchanged safety net).
- Bounded: never loops; worst case adds one 45s wait, then degrades.

Fix is coded and control-flow-tested: retry-on-race succeeds; no wasted retry when the alert
is already present; bounded to 2 attempts on genuine absence. **Not yet deployed.**

## Resume point (2026-07-13)

1. Drop in the retry-hardened `function_app.py` (496 lines; adds `_attempt_reconstruct_session_id`
   + the retry wrapper around `_reconstruct_session_id`).
2. Deploy: `func azure functionapp publish func-mcp-triage-lab-rg --python`; verify deployed
   behavior (deployed ≠ live until confirmed).
3. Re-run forwarder (dry-run then live); wait for the new autonomous incident.
4. Confirm the function log shows `Waiting 45s and retrying once` → `reconstructed on retry`,
   and the comment is the full narrated CRITICAL assessment (Trigger: automated).
5. Capture the clean autonomous narrated comment (CLI `jq` + Defender UI direct-URL).
6. Complete Sprint 4 closeout: commit code + figures + DAILY_LOG entry + README flip
   (Sprint 4 → Complete, Sprint 5 → Next). Gate 2 (function-key → managed-identity) still
   open before any public GitHub publish.
