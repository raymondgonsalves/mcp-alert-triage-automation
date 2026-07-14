# Finding: commit-latency race in autonomous triage response

**Date first observed:** 2026-07-10
**Root cause corrected:** 2026-07-13 (see "Superseding measurement" below)
**Sprint:** 4 (bounded LLM narrator)
**Finding severity:** Low — graceful degradation held throughout; no crash, no wrong verdict, no bad action
**Status:** Root cause **measured** (not inferred). Corrected fix designed; playbook delay + re-run scheduled 2026-07-14.

---

> ## ⚠️ SUPERSEDED — the original root cause below was WRONG
>
> The 2026-07-10 analysis attributed the failure to **`SecurityAlert` commit latency** and
> proposed a 45-second in-Function retry. That hypothesis **explained the symptom but was
> never measured.** It was deployed on 2026-07-13 and **failed** — the retry fired correctly
> and the reconstruction still found nothing.
>
> The `ingestion_time()` measurement taken on 2026-07-13 (below) shows the real blocker is
> the **`SecurityIncident` table**, whose Log Analytics copy lags the ARM incident resource
> by **~77 seconds** — more than twice the `SecurityAlert` lag the original fix targeted.
>
> **Read "Superseding measurement" as the authoritative root cause.** The original section is
> retained only as a record of the wrong turn and why it was wrong.

---

## What happened (2026-07-10) — original observation, still accurate

The first fully-autonomous end-to-end run (forwarder ingest → scheduled analytic rule →
incident → automation rule → playbook → Function) produced a *degraded* triage comment
instead of a scored, narrated assessment:

> [Triage pipeline - Sprint 3] Pipeline reached this incident, but no SessionId could be
> reconstructed (no matching alert in the lookback window). Manual review suggested.

- Incident: #9, GUID `75ab2604-39df-44b6-bb92-a90c4a9ccd8a`
- Incident created: `2026-07-10T14:22:33Z`
- Function comment written: `2026-07-10T14:22:45Z` (managed identity `func-mcp-triage-lab-rg`)
- Elapsed: **~12 seconds**

The autonomous chain fired correctly and fast. The Function took its designed
graceful-degradation branch. The failure was purely one of *timing*.

## Original root cause (2026-07-10) — ❌ WRONG, retained for the record

> *Hypothesis at the time:* the response automation outran **`SecurityAlert`** commit latency,
> so the reconstruction join found no alert row.
>
> *Fix built on it:* a bounded in-Function retry — on a no-result attempt, wait **45 seconds**
> and retry once (max 2 attempts).
>
> **Why it was wrong:** the hypothesis was plausible and fit the 12-second symptom, but it was
> **never verified against `ingestion_time()`**. It also overlooked that the reconstruction
> query *starts from `SecurityIncident`*, not `SecurityAlert` — so `SecurityAlert` was never
> the binding constraint.

---

## Superseding measurement (2026-07-13) — ✅ MEASURED root cause

The 45s retry was deployed and the pipeline re-run. **The retry fired correctly and the
reconstruction still failed.**

- Incident: #13, GUID `00c2a742-7582-4f6b-a4ac-b7506fda68a3`
- Incident created: `2026-07-13T20:02:50Z`
- Degraded comment written: `2026-07-13T20:03:49Z` — **~58s elapsed** (vs ~12s before)

The 58-second gap confirms the retry *did* execute (it slept its 45 seconds). The fix was
live; it simply did not wait long enough — and it was waiting on the wrong table.

### The reconstruction query depends on TWO tables

```kql
SecurityIncident                      -- query STARTS here
| where IncidentName == targetIncident
| mv-expand AlertId = todynamic(AlertIds)
| join kind=inner ( SecurityAlert ... ) on $left.AlertId == $right.SystemAlertId
```

It is an **inner join**. If *either* table has not committed, the result is empty.

### Measured commit latency (via `ingestion_time()`)

| Table | TimeGenerated | IngestedAt (queryable) | Commit lag |
|---|---|---|---|
| `SecurityAlert` | 20:02:34 | 20:03:06 | **32 s** |
| **`SecurityIncident`** | 20:02:50 | **20:04:07** | **77 s** ← binding constraint |

`AlertIds` **was** populated on the first `SecurityIncident` row
(`["28dae43c-2e38-8928-105e-e01f42c7e72e"]`), so an empty-linkage hypothesis is **ruled out**.
The blocker is purely the incident table's commit latency.

### Timeline — the Function missed by 18 seconds

| Time (UTC) | Event |
|---|---|
| 20:02:50 | Incident created (ARM resource) |
| 20:03:02 | Function attempt 1 → `SecurityIncident` not queryable ✗ |
| 20:03:06 | `SecurityAlert` commits (32 s) — *the table the old fix targeted; irrelevant* |
| 20:03:47 | Function attempt 2, after the 45 s retry → `SecurityIncident` **still** not queryable ✗ |
| 20:03:49 | Function exhausts attempts, writes degraded comment |
| **20:04:07** | **`SecurityIncident` finally commits — 18 seconds too late** |

### The conceptual error

The ARM API returned the incident at 20:02:50, which made it *feel* as though the incident
"existed." But the **`SecurityIncident` Log Analytics table is a separate copy** with its own
ingestion pipeline, and it lagged the ARM resource by 77 seconds.

**"The incident exists in ARM" and "the incident is queryable in KQL" are different facts about
different systems with different latencies** — and the reconstruction query depends on the
slower one.

## Corrected fix (to implement 2026-07-14)

**Add a 120-second `Delay` action to the playbook (`pb-mcp-triage-skeleton`), between the
trigger and the HTTP call to the Function.** Retain the Function's existing 45 s retry as a
variance backstop.

Rationale:

- **Right layer.** The orchestrator should not invoke the responder before the responder's
  input data exists. That is a scheduling concern, and the playbook is the scheduler.
- **No timeout risk.** A long sleep *inside* the Function pushes its runtime toward the Logic
  App's ~120 s synchronous HTTP limit. A delay *in the playbook* happens **before** the HTTP
  call, so the Function still returns in ~7–10 s.
- **No code change or redeploy** — a Designer edit.
- **Layered.** The 120 s delay covers the observed ~77 s lag with ~45 s of margin (the Function
  fires at ≈ T+122 s, allowing ~2 s of chain-startup latency); the Function's 45 s retry then
  absorbs variance beyond that, out to roughly T+167 s.

Rejected alternative: simply lengthening the in-Function sleep. It consumes Function execution
time and risks the playbook's HTTP timeout, while solving the problem at the wrong layer.

Noted for future work: the incident→alert linkage could be read from the **ARM API**
(immediately consistent) rather than the `SecurityIncident` table, removing the 77 s lag from
the critical path entirely and leaving only the 32 s alert lag. Cleaner, but a larger change.

## Resume point (2026-07-14)

1. Playbook Designer → `pb-mcp-triage-skeleton` → insert **Delay** (Schedule connector,
   Count `120`, Unit `Second`) between the trigger and the HTTP action → Save.
2. Re-run the forwarder (live).
3. Wait for the new autonomous incident (expect #14+); check its comment at ≈ T+130 s.
4. Verify four conditions: managed-identity author; `[Rule-based - Non AI generated] Severity:
   CRITICAL`; `[AI-generated explanation …]` with real narration; **Trigger: automated**.
5. Capture CLI `jq` + Defender UI (direct-URL if the list view hides the incident).
6. Sprint 4 closeout: commit code + figures + DAILY_LOG entry + README flip
   (Sprint 4 → Complete, Sprint 5 → Next).
7. **Gate 2 still open** — function key → managed identity on the playbook→Function hop,
   before any public GitHub publish.

## Lesson

A hypothesis that *explains* a symptom is not a *verified* cause. The original root cause fit
the evidence, was never measured, and was wrong — and the fix built on it failed in production.
`ingestion_time()` should have been the *first* diagnostic step, not the second.

**Measure the latency; don't infer it.**
