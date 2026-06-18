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
