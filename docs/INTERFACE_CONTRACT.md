# Interface Contract — Detection Pack → Triage Automation

**Version:** 1.0 (against detection rules v1.1.0)
**Status:** Authoritative for Sprint 1 build
**Upstream:** `mcp-tool-shadowing-detections` (four Scheduled analytics rules)
**Downstream:** `mcp-alert-triage-automation` (this repo)

This document defines the seam between the two projects: what the detection side
guarantees when a rule fires, and what the triage pipeline is entitled to consume.
It is the spec the pipeline is built against. If a deployed rule's custom-detail
keys change, **this contract must be re-versioned** — the contract exists precisely
to catch that kind of drift (see Platform Constraints).

---

## 1. Boundary

- **Detection side guarantees:** for each detected Tool Shadowing event, a Microsoft
  Sentinel incident is created by a live Scheduled analytics rule, grouped one
  incident per MCP session, carrying a defined set of custom details including the
  trigger key.
- **Triage side consumes:** the incident's trigger key (`SessionId`), reconstructs
  the full session from the raw table, enriches and scores deterministically, and
  responds (comment / auto-close / escalate / HITL-gated containment).
- **The seam is the incident.** The triage pipeline reads from the incident and from
  the raw table — never from rule internals or from sibling incidents.

---

## 2. Trigger

| Property | Value |
|----------|-------|
| Trigger event | Sentinel incident created by one of the four detection rules |
| Detection source | `Scheduled detection` (live analytics rules, not manual queries) |
| Grouping | One incident per MCP session (`matchingMethod: Selected`, grouped by `SessionId`) |
| Trigger key | **`SessionId`** — read from the incident's alert custom details |
| Trigger key verified | Yes — present and populated in live incidents (e.g. `75682b09-de40-4138-9a37-358265f95b89`) |

The pipeline is invoked per incident. Because grouping is per session, **one incident
corresponds to exactly one `SessionId`**, which is the unit the pipeline investigates.

---

## 3. Per-rule reference table

When the pipeline receives an incident, it identifies the source rule (by rule ID or
title pattern) and parses the custom details guaranteed for that rule. This table is
the single lookup for "given incident X, here are the fields available."

| # | Rule (displayName) | Rule ID | Severity | Schedule (freq/period) | Incident title pattern | Watchlist dep |
|---|--------------------|---------|----------|------------------------|------------------------|---------------|
| 1 | MCP Poisoned Tool Description Ingested | `a4979fe7-5e82-4463-b8ad-acca29a50e30` | High | 15m / 15m | `MCP poisoned tool description: {ServerName}/{ToolName}` | none |
| 2 | MCP Cross-Tool Reference in Description | `afbff648-6597-49a1-8dc7-647901866a29` | High | 15m / 15m | `MCP cross-tool reference: {ToolName} references {ReferencedTool}` | MCPToolNames |
| 3 | MCP Tool Description Hash Drift | `7dd49f2d-339a-479e-b9ce-c20749b66313` | Medium | 30m / 30m | `MCP tool description drift: {ServerName}/{ToolName}` | MCPToolDescriptions |
| 4 | MCP Original Recipient Tell at Tool Execution | `685e5313-88e8-4924-a7f1-fbdd00c5bbb3` | High | 5m / 5m | `MCP Tool Shadowing executed: send_email redirected to {Recipient}` | none |

All four: `aggregationKind: SingleAlert`, threshold > 0, no entity mappings, grouped by
`SessionId`.

---

## 4. Custom details per rule (as deployed)

These are the **exact deployed key names** the pipeline parses off each incident's
alert. Keys are the published labels; values are the underlying KQL columns. Note the
abbreviated `ToolDescLength` (see Platform Constraints §6).

### Rule 1 — Poisoned Tool Description
`ServerName`, `ToolName`, `ToolDescriptionHash`, **`ToolDescLength`**, `SessionId`,
`HostApp`, `ModelName`, `IngestionAgent`

### Rule 2 — Cross-Tool Reference
`ServerName`, `ToolName`, `ReferencedTool`, `ReferencedServer`, `ToolDescriptionHash`,
**`ToolDescLength`**, `SessionId`, `HostApp`, `ModelName`, `IngestionAgent`

### Rule 3 — Hash Drift
`ServerName`, `ToolName`, `ObservedHash`, `ApprovedHash`, `Notes`, **`ToolDescLength`**,
`SessionId`, `HostApp`, `ModelName`, `IngestionAgent`

### Rule 4 — Recipient Tell (execution layer)
`Recipient`, `ToolName`, `CallId`, `UserPromptHash`, `SessionId`, `HostApp`, `ModelName`

> Rule 4's detail set is deliberately different — it fires at **execution**
> (`EventType == ToolCallInvoked`), not at description ingestion, so it carries
> execution-context fields (Recipient, CallId, UserPromptHash) and no ServerName /
> hashes / ToolDescLength.

**Shared across all four:** `SessionId`, `ToolName`, `HostApp`, `ModelName`. The
pipeline can rely on these regardless of which rule fired.

---

## 5. Session reconstruction

The custom details are a summary; the pipeline reconstructs the full session from the
raw table:

```kql
MCPProtocolLogs_CL
| where SessionId == "<trigger SessionId>"
| order by EventTime asc
```

- **`EventTime`** is the true event-occurrence time (use this for the session timeline).
- **`TimeGenerated`** is **ingestion time** (changed via DCR transform on 2026-06-22;
  formerly equal to EventTime). Do not use `TimeGenerated` for event ordering — use
  `EventTime`.
- Event types in a session: `SessionStart`, `ToolDescriptionLoaded`, `ToolCallInvoked`,
  `ToolResultReturned`, `SessionEnd`.

---

## 6. Platform constraints (deploy-time realities)

Discovered standing the rules up live; documented so the pipeline reads the correct
field names and future rule edits stay within limits.

1. **Custom-detail keys cap at 20 characters.** `ToolDescriptionLength` (21) does not
   fit and is published as **`ToolDescLength`** (14). The value still maps to the full
   `ToolDescriptionLength` column. **The pipeline must read `ToolDescLength`.**
   `ToolDescriptionHash` (19) fits and is unabbreviated.
2. **Alert override fields cap at 3 `{{column}}` placeholders each.** Affects alert
   title/description text only — cosmetic, does not change what the pipeline reads.
   Noted so future override edits stay within the limit.

---

## 7. Correlation model (important)

**The pipeline does NOT correlate by reading sibling incidents.** The four rules run on
staggered cadences (5/15/15/30 min), so at the moment one incident fires, the related
incidents from other rules may not exist yet. Cross-layer confidence is established by
**re-querying `MCPProtocolLogs_CL` on the SessionId**, not by checking whether other
incidents exist.

Example: when the Rule 4 (execution) incident fires, the pipeline confirms whether the
description-layer detections (Rules 1/2/3) also match that session by running their
detection logic against the session's rows — not by looking for incidents 1/2/3 in the
queue.

---

## 8. Incident metadata available to the pipeline

Per incident, the pipeline can read:

- Incident title (dynamic, per §3 patterns)
- Severity (per §3)
- Category (Rule 1 Defense evasion; Rules 2/3 Initial access; Rule 4 Exfiltration)
- Detection source (`Scheduled detection`)
- Alert custom details (per §4) — including the `SessionId` trigger key

---

## 9. Versioning

- Rules are **v1.1.0**. This contract is **v1.0** against them.
- **Any change to deployed custom-detail key names breaks this contract** and requires
  a contract bump + a corresponding pipeline change. The `ToolDescriptionLength` ->
  `ToolDescLength` episode is the canonical example of why this section exists: a
  silently-renamed key means the pipeline cannot find the field.
