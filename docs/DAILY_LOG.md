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

---

## 2026-06-24 — Sprint 1: walking skeleton — managed-identity write-back proven

### What shipped
The first pipeline link is live and verified: a deployed Azure Function authenticates to Microsoft Sentinel **as its own managed identity** (no credentials anywhere) and writes a comment back to an incident. This is the riskiest, most foundational capability in the whole pipeline — everything in later sprints just replaces the stub comment's body with real work.

### Build order (back-to-front, so each link is independently testable)
1. Scaffolded a Python v2 Azure Function (`function_app/`, HTTP trigger `triage`) that reads `incidentArmId` + `sessionId` from the POST body, authenticates via `DefaultAzureCredential`, and PUTs a stub comment to the incident via the ARM REST API.
2. **Local test** — `func start` + curl to `localhost:7071`. Wrote a comment authored by **Raymond Gonsalves** (my `az login` identity). Verified via `az rest` GET (the Defender portal Comments panel does NOT surface API-written comments — a known quirk; use the REST read to verify).
3. Provisioned cloud infrastructure: storage account `stmcptriagelabrg`, Function App `func-mcp-triage-lab-rg` (consumption plan, Python 3.12, Functions v4) **with a system-assigned managed identity** (`--assign-identity '[system]'`).
4. Assigned the managed identity (principal `e5c28c8b-3b63-4e44-883a-858b185ff63b`) two roles, scoped to workspace `law-mcp-detection-lab`:
   - **Microsoft Sentinel Responder** — write incident comments (used in Sprint 1)
   - **Log Analytics Reader** — query `MCPProtocolLogs_CL` (NOT used yet; pre-provisioned for Sprint 2 enrichment)
5. **Deployed** the code (`func azure functionapp publish`).
6. **Deployed test** — curl to the `azurewebsites.net` URL (with function key). Comment authored by the **managed identity** (`objectId e5c28c8b-…`, `userPrincipalName: null`).

### The proof
`DefaultAzureCredential` is the same line of code in both environments — it resolves to my user identity locally and the managed identity in Azure, with zero code change. The decisive signal: the comment **author flipped from "Raymond Gonsalves" (local) to the managed identity (deployed)**. Same code, different identity, no credentials in code or config. That is the production-correct, credential-free auth path proven end to end.

### Gotchas / scar-tissue lessons
- **Provider registration masquerading as auth failure.** `Microsoft.Storage` was `NotRegistered` on the subscription (first time storage was used). Storage calls failed with a misleading `SubscriptionNotFound` error, which sent us chasing a tenant/login problem. Lesson: if `az account show` works but a resource-type call says "subscription not found," check the *resource provider* registration before assuming an auth issue. Fixed with `az provider register --namespace Microsoft.Storage --wait`.
- **Tenant context confusion (side-quest).** The subscription's real home tenant is `a3e85d53-0605-4e15-8568-12acdaf34332`, NOT `gonsalvesraygmail.onmicrosoft.com` (the latter is a directory I'm a guest in). The guest-account split is the same root cause as the earlier Defender-portal "wrong tenant" redirect. For explicit `az login --tenant`, use the GUID `a3e85d53-…`.
- **Comment-name collision.** Using `SessionId` as the comment *name* meant the deployed function (managed identity) tried to PUT to the same comment name my local test had already created — Sentinel blocked it: "Only the user that created the comment is allowed to edit it." Fix: unique comment name per invocation (`skeleton-{uuid.uuid4().hex}`); SessionId stays in the comment *body* for traceability. Correct design anyway — in production the pipeline comments many times per incident.
- **Portal doesn't show API-written comments** in the incident Comments panel (only ones made via its own UI, until a deep refresh). Verify writes via the `az rest` GET on `.../comments`, not the portal. Relevant for the eventual demo.

### Scope note
Sprint 1 is the pipeline plumbing only (Function App → managed identity → deploy → write-back). The four detection rules that generate the incidents are Sprint 0 / the detection repo — a separate project in the arc.

### SC-200 objectives covered
- Create and configure Microsoft Sentinel playbooks (Azure Function response component; playbook wiring next)
- Configure Microsoft Sentinel roles and permissions (managed-identity RBAC: Sentinel Responder, Log Analytics Reader)

### Open / next
- **Still to complete the full walking skeleton:** wire the Logic App playbook to call the deployed Function, and the Automation Rule to fire the playbook on new incidents — so it runs automatically, no manual curl. (Function proven callable directly; automatic triggering is the remaining link.)
- The playbook must pass the function key when invoking the Function.
- Then Sprint 2: deterministic session reconstruction (the Log Analytics Reader role starts earning its keep).

---

## 2026-06-24 22:40 — PAUSED: Sprint 1 step 3 (playbook wiring) about to start

**Done today:** Sprint 1 walking skeleton core proven — deployed Azure Function writes incident comments as its managed identity (committed `9491f02`, `87c2b20`). Repo clean.

**Resuming at:** wiring the Logic App playbook + Automation Rule so the Function fires automatically on new incidents (no manual curl).

**Decision locked — auth approach:**
- **Path A now:** build playbook with **function-key** auth to prove the trigger → playbook → Function → write-back chain fires automatically.
- **GATE before publishing playbook to GitHub:** swap playbook→Function auth to **managed-identity-to-Function** (Azure AD / Easy Auth), remove the key. Reason: the function key is a secret; never commit a playbook ARM definition containing it. Keep the playbook cloud-only (do NOT export to repo) until after the managed-identity swap.

**Next concrete step (portal):** Defender portal → Microsoft Sentinel → Configuration → Automation → Create → "Playbook with incident trigger". Name `pb-mcp-triage-skeleton`, RG `rg-sentinel-mcp-detection-lab`, region East US. Then add the action that calls the deployed Function (`func-mcp-triage-lab-rg`), passing incidentArmId + sessionId (+ function key for now). Then create the Automation Rule to fire the playbook on incidents from the four detection rules. Test by replaying an incident and watching the comment appear automatically.

**Key facts for tomorrow:**
- Function App: `func-mcp-triage-lab-rg`, invoke URL `https://func-mcp-triage-lab-rg.azurewebsites.net/api/triage` (auth_level=FUNCTION, needs key for now)
- Managed identity principal: `e5c28c8b-3b63-4e44-883a-858b185ff63b` (has Sentinel Responder + Log Analytics Reader on workspace)
- Test incident (Rule 4): GUID `71ca1ae3-e897-4176-b19c-b42a4c04c0d6`, SessionId `75682b09-de40-4138-9a37-358265f95b89`
- Subscription `5faad216-...`, real home tenant `a3e85d53-...` (NOT the onmicrosoft.com guest dir — use the GUID for az login --tenant)
- Verify comment writes via `az rest` GET on .../comments — the Defender portal Comments panel does NOT show API-written comments.

**Other open doc threads (not blocking):** interface contract `ToolDescLength` note already in repo; project plan committed; triage-repo README status line + earlier 0622 log entry still minor-stale.
