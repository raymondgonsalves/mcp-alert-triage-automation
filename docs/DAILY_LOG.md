# Daily Log — MCP Alert Triage Automation

Project: `mcp-alert-triage-automation`
Builds on: `mcp-tool-shadowing-detections` (MCP Tool Shadowing KQL Detection Pack)
Arc position: **respond** (use → defend → analyze → detect → **respond**)

---

## 2026-06-18 — Sprint 0: decisions ratified, grouping fix shipped, major deployment-gap finding

### Decisions ratified (design spec §3)
- **Hosting:** Sentinel Automation Rule → Logic App playbook → Azure Function (Python). Covers two SC-200 objectives; matches the Logic App promised in the Detection Pack README.
- **RBAC:** Managed identity on the Function (Log Analytics Reader + Microsoft Sentinel Responder, workspace-scoped). Not reusing `mcp-forwarder-sp`. Confirmed the working account holds **Owner** on Azure subscription 1, so role assignment is unblocked.
- **LLM provider:** Provider-agnostic adapter behind a JSON-schema contract; ship Claude (Anthropic API) first, document Copilot for Security as the enterprise variant. Stance: *architecture is provider-agnostic; due diligence is provider-specific.*
- **Response realism:** comment write-back / auto-close / escalate = real (Sentinel REST API); server-disable containment = HITL-gated dry-run stub (no MDE in lab); **Teams notification = stub.**
- **Repo name locked:** `mcp-alert-triage-automation` (renamed from the provisional `mcp-alert-investigation-pipeline` to lead with the SOC outcome — triage automation — rather than the implementation).

### Teams notification → stub (rationale)
Investigated a real Teams webhook for the escalate branch. Found the working account is a guest (`#EXT#`) user in the lab tenant (`gonsalvesraygmail.onmicrosoft.com`); guest identities generally cannot create Power Automate flows / use the Workflows app. The current Office 365 Connector incoming webhook is also retired (final cutoff May 2026), so only the Power Automate Workflows path exists, which the guest account can't use. Standing up a member account + M365 Developer licenses was judged not worth the tenant-admin overhead for a non-load-bearing notification. **Decision: stub it** (log what it would post), upgradeable later via a one-function change.

### Correction logged
Earlier design/contract docs claimed all four rules grouped by `SessionId`. The actual deployed YAMLs grouped Rules 1–3 by `ServerName`/`ToolName` and Rule 4 by `SessionId`/`Recipient`. Corrected; the fix below standardizes all four on `SessionId`.

### Grouping fix shipped (Finding 1)
`matchingMethod: AllEntities` with zero entity mappings caused all alerts in the lookback window to collapse into a single incident — fatal for per-session triage. Fixed all four rules to `matchingMethod: Selected` + `groupByCustomDetails: [SessionId]`, bumped to **v1.1.0**, committed to the detection repo (`deadc95`).

### MAJOR FINDING — rules were never deployed as live analytics rules
Sentinel Analytics (Defender portal, workspace `law-mcp-detection-lab`, scope confirmed) shows **0 active rules**. The four detections have existed only as repo YAML and were validated by running the KQL in the Logs blade against ingested attack data — never instantiated as live **Scheduled** analytics rules. Implication: the triage pipeline triggers on incidents, which require live rules, which do not exist yet. **New Sprint 0 prerequisite: create the four rules as live Scheduled rules before any pipeline work.** Upside: doing so retroactively strengthens the Detection Pack claim from "queries detect" to "deployed rules generate incidents."

### Artifacts produced
- Design & Specification doc (repo name updated to locked value)
- Interface Contract doc (Detection Rules → Triage Automation)
- Numbered pipeline flow diagram (SVG + editable draw.io)
- Corrected v1.1.0 rule YAMLs (committed to detection repo)
- This project skeleton (`docs/`, README, .gitignore)

### SC-200 objectives covered
- Configure and manage analytics rules in Microsoft Sentinel SIEM (grouping configuration; rule deployment planning)

### Open / next (Sprint 0 remaining, dependency order)
1. Create the four rules as **live Scheduled analytics rules** (Import YAML vs manual Create — pending file-format check: repo YAML vs ARM template).
2. Timestamp probe — replay a small batch, inspect `TimeGenerated` (ingestion-time vs original April/May); apply DCR transform if needed.
3. Full replay — verify rules **fire** AND group **one incident per session**.
4. On green: begin Sprint 1 (walking skeleton: Automation Rule → playbook → Function reads SessionId, writes stub comment).

---

## 2026-06-18 11:13 — PAUSED mid-task: Rule 1 correction edits

**Stopped while fixing Rule 1 (MCP Poisoned Tool Description Ingested).** Rule 1 is deployed live in Sentinel with grouping correct (`matchingMethod: Selected` + `groupByCustomDetails: [SessionId]`). Outstanding fixes on Rule 1 before it is clean:

1. Custom detail key `TooName` -> `ToolName` (typo)
2. Custom detail key `ToolDescript_Length` -> `ToolDescLength` (Sentinel custom-detail keys cap at 20 chars; `ToolDescriptionLength` is 21. Key abbreviated; value still maps to the full `ToolDescriptionLength` column.)
3. Severity `Medium` -> `High`
4. `alertDetailsOverride`: remove the literal `alertDisplayNameFormat:` / `alertDescriptionFormat:` prefixes that got pasted into the values; keep only the format string.

**Next steps (dependency order):**
1. Finish Rule 1 fixes above.
2. Create Rules 2-4 (manual wizard, mirror corrected Rule 1). Use `ToolDescLength` consistently. Schedules: R2 15/15 High, R3 30/30 Medium, R4 5/5 High. Add SessionId as a custom detail BEFORE the grouping tab. R2/R3 depend on the `MCPToolNames` / `MCPToolDescriptions` watchlists existing in the workspace.
3. Timestamp probe: replay a small batch, inspect `TimeGenerated` (ingestion-time vs original April/May); apply DCR transform if needed.
4. Full replay: verify rules FIRE and group ONE INCIDENT PER SESSION.
5. On green: begin Sprint 1 (walking skeleton).

**Open doc threads (not blocking):**
- Interface contract doc: reflect `ToolDescLength` abbreviation + note the 20-char custom-detail-key constraint.
- Detection repo `DAILY_LOG.md`: add cross-reference line (commit `deadc95` grouping fix + "rules were never deployed live" finding).
- Copy design spec + interface contract doc + diagrams into new repo `docs/`.

**Key finding standing from earlier today:** the four detection rules were never deployed as live Scheduled analytics rules — only validated as KQL in the Logs blade. Standing them up live is the current Sprint 0 prerequisite (Rule 1 done, 3 to go).

---

## 2026-06-22 (close) — SPRINT 0 COMPLETE: all four rules fired, incidents verified

### Replay executed and verified
Re-ran the forwarder (`_main.py`) after the DCR transform fix. Dry-run confirmed 32 rows from two sources (Claude Desktop + ollmcp captures), 3 distinct description hashes (approved baseline `44c65aee`, V2 drift `730af110`, plus `cb006818`). Live ingestion succeeded.

**Timestamp verification (the DCR fix payoff):** post-replay query confirmed fresh rows landed with `TimeGenerated = 6/22/2026` (now) while `EventTime` preserved the true event time (4/30 and 5/23). The DCR `now()` transform works — replayed historical evidence is now in-window for the scheduled rules.

### All four rules fired and generated incidents
Defender Incidents queue shows **4 incidents — one per rule** — with correct dynamic titles, severities, and categories:

| Incident title | Severity | Category | Active alerts | Detection source |
|----------------|----------|----------|---------------|------------------|
| MCP poisoned tool description: calendar_sync/calendar_sync | High | Defense evasion | 1/1 | Scheduled detection |
| MCP cross-tool reference: calendar_sync references send_email | High | Initial access | 1/1 | Scheduled detection |
| MCP tool description drift: calendar_sync/calendar_sync | Medium | Initial access | 1/1 | Scheduled detection |
| MCP Tool Shadowing executed: send_email redirected to attacker@pwnd.com | High | Exfiltration | 1/1 | Scheduled detection |

### Exit criteria — all met
- Rules deployed live as Scheduled analytics rules (not manual KQL): confirmed by "Scheduled detection" source.
- Rules fire and generate incidents: 4 incidents present.
- One incident per session: every incident shows **1/1 active alerts** — the grouping fix (Selected + SessionId) holds; the two llama send_email events collapsed to a single incident.
- Dynamic alert titles render correctly: the override-field fixes (double-wrap removal, quote stripping, placeholder trimming) all produced clean parameterized titles.
- SessionId present as trigger key: confirmed in the Rule 4 incident custom details (value `75682b09-de40-4138-9a37-358265f95b89`). NOTE: this differs from the pre-replay query's `451b9b40...` — fresh replay produced new session instances; immaterial to verification (the incident carries SessionId as designed).

### Portfolio asset captured
Screenshot of the four-incident queue (Incident name / Severity / Categories / Active alerts / Detection source / Creation time) saved for detection repo `docs/figures/` — shows the rules firing live as scheduled detections, the strongest single piece of evidence in the pack (live incidents, not KQL output).

### From 0 to 4
Session opened with Sentinel showing **0 active rules** (detections existed only as repo YAML + validated KQL). Closed with **four live Scheduled analytics rules firing on real Tool Shadowing attack data, grouped one-incident-per-session**. The detection pack's claim is now "deployed rules generate incidents," not "queries detect."

### Still open (Sprint 1 prerequisites, not blockers)
- Interface contract doc: add `ToolDescLength` abbreviation + the two platform constraints (20-char custom-detail keys; 3-placeholder override cap). The contract is what Sprint 1 builds against — do this before pipeline code.
- Triage repo: commit its DAILY_LOG/README updates if not already done.
- Schema doc: note `TimeGenerated` is now ingestion-time; `EventTime` is event-occurrence time.
- Copy design spec + interface contract + diagrams into triage repo `docs/`.

### Next: Sprint 1 — walking skeleton
Automation Rule → Logic App playbook → Azure Function (Python, managed identity) that reads SessionId off the incident and writes a stub comment back. Prove the auth / RBAC / write-back seam before any enrichment or scoring logic.
