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
- **Tenant context confusion (side-quest).** The subscription's real home tenant is `<home-tenant-id>`, NOT `gonsalvesraygmail.onmicrosoft.com` (the latter is a directory I'm a guest in). The guest-account split is the same root cause as the earlier Defender-portal "wrong tenant" redirect. For explicit `az login --tenant`, use the GUID `<home-tenant-id>…`.
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
- Subscription `5faad216-...`, real home tenant `<home-tenant-id>...` (NOT the onmicrosoft.com guest dir — use the GUID for az login --tenant)
- Verify comment writes via `az rest` GET on .../comments — the Defender portal Comments panel does NOT show API-written comments.

**Other open doc threads (not blocking):** interface contract `ToolDescLength` note already in repo; project plan committed; triage-repo README status line + earlier 0622 log entry still minor-stale.

---

## 2026-07-01 — MILESTONE: Sprint 1 walking skeleton COMPLETE (autonomous detect-to-respond chain proven)

**Work span:** This milestone was built across multiple sessions with non-work days between them:
- **2026-06-24** — Sprint 1 core: Azure Function deployed, managed-identity write-back proven (logged separately; commit `87c2b20`).
- *[gap days — no work on project]*
- **2026-07-01** — Playbook + Automation Rule wired; full autonomous chain proven end to end (this entry).

*(Verify/adjust the middle dates: 6/24 is anchored by the prior commit; 7/01 is anchored by Azure resource timestamps on the incidents, automation rule, and playbook runs. Any additional work sessions between should be added here.)*

### What shipped — the walking skeleton is complete
The full SOAR loop now runs with zero human intervention. Replaying the forwarder generated fresh incidents; ~seconds after each incident was created, a triage comment appeared on it, written by the Function's managed identity — no curl, no manual trigger.

Proven chain:
`Forwarder -> data in MCPProtocolLogs_CL -> detection rule fires -> incident created -> automation rule routes it -> playbook triggers -> HTTP -> Function -> comment written (as managed identity)`

Timing observed: incident `8df5db76` created 17:42:09, comment written 17:42:16 — **7 seconds**. All latency is in the scheduled-detection step (the "patrol interval"); once the incident exists, the automation-rule -> playbook -> Function -> write-back response is effectively instant (event-driven).

### The five-stage SOAR pattern, now concrete
- **detect** — scheduled analytics rule (Rule 2 Cross-Tool, among the four)
- **incident** — grouped per session
- **route** — Standard automation rule, "When incident is created" trigger
- **act** — playbook (thin) -> HTTP -> Azure Function (the logic)
- **outcome** — comment write-back by managed identity (credential-free)

### The three identity hops (the load-bearing lesson: every SOAR hop is a scoped role on an identity)
| Identity | Role | Purpose | Credential? |
|---|---|---|---|
| Function's managed identity | Microsoft Sentinel Responder | Write incident comments | None (managed identity) |
| Sentinel automation SP ("Azure Security Insights", app `98785600-...`, object `cad754b8-...`) | Microsoft Sentinel Automation Contributor (`f4c81013-...`) | Run the playbook | N/A |
| Playbook -> Function hop | **Function key (stored secret)** | Playbook calls Function | **KEY — still to eliminate (see gates)** |

When a SOAR chain "doesn't fire," a missing permission on one of these hops is the first suspect, before logic. Lived this three times.

### Artifacts captured (docs/figures/)
- `figure_11_automation_rule_active_incident_trigger.png` — rule Active, incident trigger, scoped (routing armed)
- `figure_12_playbook_run_history_201_success.png` — run Succeeded; HTTP body shows real incident ARM ID in, `201` + `status:ok` out (full round-trip)
- `figure_13_managed_identity_comment_autowritten.png` — comment authored by managed identity ("Comment created from external application - func-mcp-triage-lab-rg"), not a user (credential-free outcome)

Together these narrate: routed -> executed successfully -> outcome written autonomously by a credential-free identity.

### Scar-tissue lessons (all real, all cost time)
- **Portal split #1 — incident trigger only in Standard rules.** The Defender portal's *Enhanced* automation rules exposed only "When alert is created." Incident-level triggers live in **Standard rules**. Concept: alert-level vs incident-level automation are different surfaces post-unification. Exam-relevant (unified platform).
- **Portal split #2 — Azure portal Automation redirects to Defender.** Workspace is fully onboarded to the unified platform; the classic Azure Sentinel automation page redirects. Concept: after Defender onboarding, some config moves; "it's on the other portal."
- **Portal split #3 — "Manage playbook permissions" opens docs, not a panel.** The Defender portal stubs the RBAC-granting UI. Worked around it via CLI role assignment (which is what the button does underneath). Concept: every "grant permissions" GUI = an `az role assignment create`.
- **Tenant gremlin (recurring).** "Limited or No Access / not a member of this tenant" in the portal — same guest-account (`#EXT#`) root cause as the CLI's `SubscriptionNotFound` earlier. Fix: force tenant `<home-tenant-id>...` via `https://portal.azure.com/#@<home-tenant-id>...` (NOT the onmicrosoft.com guest dir). Do NOT click "I acknowledge" (that drops you in as a no-access passthrough user) — click "Sign out" and re-enter on the right tenant.
- **Service principal empty `id` on table query.** `az ad sp show ... -o table` returned name but blank id (guest-tenant resolution flakiness); `--query id -o tsv` resolved it cleanly (`cad754b8-...`). Reference SPs by stable app ID (`98785600-...`, global constant) when name/object resolution is unreliable.
- **Status codes told the debugging story.** 401 "only the author can edit" (4xx = my request's fault; comment-name collision -> fixed with uuid) progressed to 201 Created (2xx success, new resource). 4xx = caller's fault, 5xx = server's fault — the fastest triage of an API failure.

### Design notes / refinements to revisit (not blocking)
- **"For each" loop wraps the HTTP action.** Referencing alert-level data pulled the Function call inside a per-alert "For each" loop (ran "1 of 1" — one alert per incident, fine now). Risk: if an incident ever held multiple alerts, the Function would be called once per alert (duplicate comments). When wiring real SessionId, consider restructuring to call the Function once per incident.
- **Scoping is broader than intended.** The automation rule fired on ALL FOUR MCP incidents, not just Cross-Tool (four playbook runs observed, one per incident). The condition is likely "Analytics rule name Contains MCP," not the single Cross-Tool rule. This is arguably the BETTER design for a triage pipeline (triage every tool-shadowing incident), but verify the condition and confirm it's intentional. Lesson: verify automation-rule conditions rather than assuming scope from a truncated view.

### OPEN GATES (must close before certain milestones)
1. **SessionId is a placeholder.** Body currently sends `sessionId: "PLACEHOLDER-chain-test"`. Real extraction from nested alert custom details is deferred (enrichment work, Sprint 2). Chain-first was deliberate — prove plumbing, then wire real data.
2. **Function key must be eliminated before GitHub publish.** The playbook -> Function hop uses a function key (a stored secret). GATE: swap to managed-identity-to-Function (Azure AD / Easy Auth) and remove the key BEFORE exporting the playbook definition to the repo. Keep the playbook cloud-only until then — a committed playbook ARM definition must not contain the key.

### SC-200 objectives covered
- Configure SOAR in Microsoft Sentinel (automation rules + playbooks; the complete pattern, built and verified)
- Configure Microsoft Sentinel roles and permissions (three scoped role assignments across identities)
- Manage Microsoft Sentinel analytics rules (scheduled rules as the automation trigger source)
- (Unified platform) Navigate Sentinel in the Defender portal; alert-vs-incident automation surfaces

### Next
- Sprint 2 — deterministic session reconstruction (Function queries MCPProtocolLogs_CL on SessionId; the Log Analytics Reader role starts being used). This is also where real SessionId extraction replaces the placeholder.
- Before any GitHub publish of the playbook: close Gate 2 (managed-identity-to-Function swap).

---

## 2026-07-06 — MILESTONE: Sprint 2 COMPLETE (deterministic SessionId reconstruction; Gate 1 closed)

**Work span:** Built across sessions 2026-07-03 (design + KQL verification) through 2026-07-06 (Function port, deploy, deployed proof). Non-work days between.

### What shipped
The Function no longer sends a placeholder SessionId — it **derives the real SessionId from the log data**. The `PLACEHOLDER-chain-test` is gone from the live pipeline. Proven twice:
- **Locally** (DefaultAzureCredential -> dev identity): proved the *code and query logic*. Returned `reconstructed: true, sessionId: c7df4d04-...`.
- **Deployed** (DefaultAzureCredential -> managed identity): proved the *authorization*. Same result, but the query ran as the managed identity using its **Log Analytics Reader** role — that role's first real exercise since it was pre-assigned in Sprint 1.

### The design (verified before coding, every step)
Single **KQL join** bridges incident -> its alert -> SessionId, entirely server-side (correlation + nested-JSON extraction both in KQL; Python receives one clean string):
```
SecurityIncident (by IncidentName) -> arg_max latest -> mv-expand AlertIds
  -> join kind=inner SecurityAlert on AlertId == SystemAlertId
  -> extract SessionId = tostring(parse_json(tostring(parse_json(ExtendedProperties)["Custom Details"]))["SessionId"][0])
```
Two different keys, two different jobs (an important distinction, easy to conflate):
- **SystemAlertId** = the *bridge* key that joins incident -> alert (incident's `AlertIds` array matches `SecurityAlert.SystemAlertId`).
- **SessionId** = the *correlation payload* extracted FROM the alert's custom details. Its job is correlating session events (used later in reconstruction), NOT bridging incident->alert.

Data structure verified against real data: `ExtendedProperties` is a JSON string whose `Custom Details` value is ITSELF a JSON string (double-nesting -> two parse_json calls), and every custom detail is an ARRAY (CallId had two values, proving why `[0]` is always required).

### Architecture decisions
- **Function extracts SessionId itself** (playbook stays thin, passes only incidentArmId). Chosen over playbook-side extraction: keeps logic in testable Python, avoids fiddly designer expressions.
- **Single data-plane query** over two-step (management API + query). The alerts management API does NOT return custom details — they live only in the `SecurityAlert` log table's `ExtendedProperties`. So one KQL query does both correlation and extraction. One new mechanism (azure-monitor-query / LogsQueryClient), one plane for this step.
- **30-day time window** on the SecurityAlert filter — performance guard (partitions by time); fresh incidents always well within it.
- **Graceful degradation** — if reconstruction finds no match, the Function still writes a flagged comment (no silent failure; the analyst learns the incident was processed).

### Two planes, one identity — both now proven in the cloud
- **Data plane** — LogsQueryClient query, **Log Analytics Reader** (proven THIS sprint, first exercise)
- **Management plane** — comment write, **Sentinel Responder** (proven Sprint 1)
Same DefaultAzureCredential resolves to dev identity locally / managed identity deployed.

### Audit-grade proof (the deployed managed-identity path)
`az rest` on the incident's comments, sorted by time via jq, shows the LATEST comment authored by:
- name: "Comment created from external application - func-mcp-triage-lab-rg"
- **objectId: e5c28c8b-3b63-4e44-883a-858b185ff63b** (the Function App's managed identity principal)
- message: the Sprint 2 text with the real reconstructed SessionId c7df4d04-...
Validated against a CONTROL: an earlier comment correctly attributed to "Raymond Gonsalves" (objectId 9ed673f4-...). Two distinct objectIds = attribution system distinguishes actors correctly = the managed-identity attribution is real, not a default label. (Note: `grep -A3` initially hid this by stripping timestamps — used jq to sort structured data properly. Right tool for structured data = jq, not grep.)

### Debugging notes worth keeping
- Local `func start` shows `AzureWebJobsStorage: Unhealthy` warning — BENIGN for an HTTP function (that storage is for internal bookkeeping / timer/durable features, not simple HTTP triggers). Severity triage: not on the critical path; the curl worked despite it. (Fix if a clean console is wanted: run Azurite emulator.)
- `curl (7) Failed to connect` = nothing listening = server not running (connection-level failure, below HTTP). Distinct from a 401/403 (server up, rejected). The error TYPE points to the layer. Cause: had Ctrl+C'd func start before curling; need host + curl running concurrently in two terminals.

### OPEN GATES
1. ~~SessionId placeholder~~ — **CLOSED this sprint.**
2. **Function key -> managed-identity swap** — STILL OPEN. The playbook->Function hop still uses a function key (a stored shared secret in the URL `?code=`). Must swap to managed-identity/Easy-Auth (Bearer token) and remove the key BEFORE exporting the playbook definition to GitHub.

### SC-200 / concept coverage this sprint
- KQL: parse_json / nested (double) parsing, dynamic-field navigation, arrays + `[0]`, `join kind=inner`, `mv-expand ... to typeof(string)`, `arg_max(TimeGenerated,*)`, `let`, time-filter-early performance.
- Data sources: custom details live in `SecurityAlert.ExtendedProperties` (log table), NOT the management API. Same logical alert has multiple representations; know which holds which field.
- Identity: DefaultAzureCredential credential chain (managed identity vs az CLI); authN (token) vs authZ (roles); managed identity = no stored secret + attributable actions (objectId in audit record).
- Planes: data-plane read (Log Analytics Reader) vs management-plane write (Sentinel Responder); a role assigned but never exercised is unproven until invoked.
- Serverless: module-load vs request-time execution (cold start); `@app.route` decorator registers + wires the HTTP trigger; Function App (container) vs function (item); route name vs function name; deploy = management-plane promotion using dev identity; "deployed" != "working" (runtime authorization is a separate test).
- Evidence: consistent-with vs inferred vs audit-grade proof; control cases; structure-aware tools (jq) vs line tools (grep).

### Next
- Sprint 3 — deterministic scoring + response actions (the SessionId now feeds real session reconstruction / enrichment).
- Before any GitHub publish of the playbook: close Gate 2 (function-key -> managed identity).


---

## 2026-07-06 — FINDING: Safety-trained model refused a tool-shadowing attack that an ungoverned local model executed

**Context:** While gathering inputs for the Sprint 3 deterministic scoring model, an investigation into why no single SessionId showed all four detection rules firing together surfaced a genuine security finding about model behavior under a tool-shadowing (MCP prompt-injection) attack.

### The finding (four points)

1. **No single SessionId exhibited all four detection layers firing together.** Sessions showed subsets: some ingestion-only, some execution-only.

2. **The two log sources emit structurally different event sets — and this is by design, not chance.**
   - **Claude Desktop** (ModelName `claude-opus`): emits `SessionStart`, `ToolDescriptionLoaded`, `ToolCallInvoked`, `SessionEnd` — the full arc.
   - **ollmcp** (ModelName `llama3.2`): the `PARSER_OLLMCP.py` parser is **structurally limited to `ToolCallInvoked` only** (confirmed in source). It therefore **cannot emit `ToolDescriptionLoaded`**, so ollmcp sessions can **never** trigger the ingestion-layer rules (R1/R2/R3), which key off tool-description events.
   - Additionally, the two sources assign SessionId by different rules (confirmed in NORMALIZER.py comments): ollmcp = one SessionId per transcript; Claude Desktop = a new SessionId at each SessionStart (fragments one logical attack across multiple IDs).

3. **Ground-truth outcome — the models behaved oppositely on the same attack:**
   - **Claude Desktop (claude-opus): REFUSED the redirect.** Every `send_email` call went to the legitimate recipient (`alice@mail.com`). The poisoned tool description was loaded, but the model did not act on the malicious redirect.
   - **ollmcp (llama3.2): EXECUTED the redirect.** Multiple `send_email` calls went to `attacker@pwnd.com`, including the signature payload `body: "Original recipient: alice@mail.com\n..."` with `recipient: attacker@pwnd.com` — the tool-shadowing attack working exactly as designed.
   - **Interpretation:** the model's safety training was the deciding factor between a defended attempt and a realized breach.

4. **The `CallParameters.recipient` field is the realized-impact signal — NOT evidence that Rule 4 fired for Claude.**
   - Rule 4 ("Original Recipient Tell") fires on the *presence of a redirect* (send to attacker with the original-recipient tell). Claude's sends went to the **legitimate** recipient, so **Rule 4's condition is NOT met for Claude — Rule 4 should stay silent for Claude.**
   - The recipient field lets us distinguish **realized breach** (recipient = attacker@pwnd.com, ollmcp) from **defended/refused attempt** (recipient = legitimate, Claude). It is a finer, ground-truth *impact* signal than "did a detection rule fire."
   - Correction of an earlier mis-inference: the recipient field is *exculpatory* for Claude (proves the send was clean), not evidence the redirect detection fired.

### Why this matters for the scoring model (Sprint 3)

The original execution dimension ("did Rule 4 fire?") is too coarse. The data supports a finer, evidence-based kill-chain gradient:

| Stage | Evidence | Severity |
|---|---|---|
| Ingestion only | ToolDescriptionLoaded events, poisoned description; no malicious send | Lower |
| Attempted execution, defended | send_email present but recipient = legitimate (model refused redirect) | Medium |
| Realized execution (breach) | send_email with recipient = attacker@pwnd.com | Highest |

The severity signal lives in the **payload (`CallParameters.recipient`)**, not merely in event metadata or which rule fired. Scoring the *realized impact* (who actually got the email) rather than the *attempt* (a send occurred) avoids false-high severity on blocked attacks — a detection-fidelity / alert-fatigue concern.

### Security significance (portfolio-relevant, AI-security theme)

This is a demonstrable result about **AI safety training functioning as a security control**: a safety-aligned frontier model (Claude/claude-opus) resisted a tool-shadowing / MCP prompt-injection attack that an ungoverned local model (llama3.2 via ollmcp) executed. Maps to AI-security threat frameworks (MITRE ATLAS, agentic-AI attack surface). The comparison (same attack, different model, opposite outcome) isolates the model's governance as the deciding variable.

### Data-quality / test-coverage implications
- No current test session produces "all four layers + realized attacker-redirect" on ONE SessionId, because: ollmcp (which redirects) cannot emit ingestion events; Claude (which emits the full arc) refused the redirect. Neither source alone produces the fully-corroborated realized-breach case.
- Consequence for build: the "fully corroborated critical breach" scoring branch has no ground-truth test case yet. Options: (a) craft/inject a synthetic full-arc realized-breach transcript for test coverage; (b) fix Claude Desktop SessionId fragmentation AND accept it models a *defended* attack; (c) build/verify the branches that DO have data and treat the fully-corroborated-breach branch as verified-later. To be decided in Sprint 3 build.

### Investigative method used (for the record)
Symptom (layers don't share a SessionId) -> hypothesis (the model generates different events) -> confirmed mechanism at source (read PARSER_OLLMCP.py, NORMALIZER.py, queried raw MCPProtocolLogs_CL and CallParameters recipients) -> root cause (structural parser capability + SessionId assignment rules + model refusal behavior). Validated telemetry against ground truth rather than assuming event-type == outcome.

---

## 2026-07-07 — MILESTONE: Sprint 3 COMPLETE (deterministic recipient-aware scoring; the pipeline now decides)

**Work span:** 2026-07-06 to 2026-07-08 (UTC). Design -> investigation (which produced a documented AI-security finding) -> query verification -> Python scorer -> local + deployed test -> two real bugs and a duplicate-incident discovery caught by verifying actual behavior.

### What shipped
The pipeline now **makes a decision**: it scores each session's severity deterministically and writes that severity, with reasoning and evidence, back to the incident as a human-in-the-loop pre-assessment. Still no LLM (that is Sprint 4). Flow: incident -> SessionId (Sprint 2) -> gather per-session facts -> deterministic score -> comment.

### The scoring model (recipient-aware, evidence-backed)
Two evidence dimensions combined into a deterministic decision table:
- **Layer presence** (from SecurityAlert): which detection rules fired -> ingestion corroboration (count of R1/R2/R3) and execution (R4).
- **Realized impact** (from MCPProtocolLogs_CL CallParameters): the actual send recipient -> did harm land.

Decision table (RealizedBreach dominates, then execution, then corroboration):
```
RealizedBreach            -> CRITICAL   (redirect executed to non-legitimate recipient)
ExecutionFired (no breach)-> HIGH       (redirect detected, recipient legit: attempted/defended)
IngestionSignals >= 2     -> MEDIUM     (corroborated ingestion, not executed)
IngestionSignals == 1     -> LOW        (single ingestion signal)
else                      -> INFORMATIONAL
```
Verified tier mapping vs. real data: ollmcp c7df4d04/75682b09 -> Critical (realized breach, 4-of-8 sends to attacker); Claude 885f51f0/d85ebe36 -> Medium (2 ingestion signals); Claude 9dc4131a/06a74586 -> Low (1 ingestion signal).

### Key design decisions
- **Score observed behavior, not static tags.** Input is which detection layers co-occurred on the reconstructed session, NOT the static MITRE technique tag (constant per rule -> circular). MITRE is the rubric (informs weighting: execution above ingestion), not a runtime input.
- **Recipient as realized-impact signal (allowlist).** The severity distinction between a defended attempt (send to legitimate recipient) and a realized breach (send to attacker) lives in the CallParameters payload, not in which rule fired. Used an allowlist check (recipient != legitimate) rather than a denylist (== known-attacker): the allowlist catches UNKNOWN-bad recipients, the stronger posture.
- **Two independent severity axes:** confidence/corroboration (how many independent ingestion signals agree) is separate from impact (did harm land).
- **Rule 4 proposes, recipient confirms.** R4 detects the redirect shape; the recipient confirms whether it landed -- escalating a confirmed breach to Critical and downgrading a defended attempt (avoids false-high severity on blocked attacks).

### Engineering: pure function + full branch coverage
- `score_session(facts) -> (severity, reasoning)` is a **pure function** (no I/O), unit-testable in isolation. `test_scorer.py` exercises ALL branches -- including "corroborated ingestion + realized breach" which NO real session can produce (ollmcp can't emit ingestion events; Claude won't execute). That branch is verified synthetically. Logic proven synthetically; behavior proven on real data (c7df4d04 -> Critical).
- Querying (`_gather_session_facts`), scoring (`score_session`), presentation (`_build_comment`) are separate single-responsibility functions.

### THREE real problems caught -- each by verifying actual output/behavior, not trusting a signal

**1. Malformed comment (JSON-string / list() bug).**
First deployed comment exploded the evidence arrays into single characters (recipients showed as ['[','"','a','l','i','c','e',...]).
- Root cause: make_set() dynamic arrays came back from the Azure Monitor SDK as a JSON *string* ('["a","b"]'), not a Python list. list() on a string iterates it CHARACTER BY CHARACTER -- a serialization-boundary bug.
- Fix: parse with json.loads via a defensive `_as_list()` helper handling both JSON-string and already-a-list shapes.
- Lesson: list() iterates, it does not "convert"; data crossing a system boundary is serialized and must be deserialized; a 201/"success" does NOT mean correct output -- caught only by INSPECTING the comment content.

**2. Stale deployment (deployed function running OLD code).**
After a redeploy, the deployed function was still writing **Sprint 2** comments ("reconstruction only, no scoring"). The repo file was correctly Sprint 3 (grep confirmed score_session present), but the deployed code was Sprint 2 -- the earlier deploy had not actually pushed the new code to Azure.
- Caught by: reading what the deployed function ACTUALLY WROTE (the jq comment content said "Sprint 2"), not trusting that "I ran a publish" meant Sprint 3 was live.
- Fix: explicit redeploy (func azure functionapp publish ...), watched for "Remote build succeeded" + triage registered, then re-verified behaviorally. New comment then correctly read "Sprint 3 ... CRITICAL".
- Lesson: "deployed" (the command ran) != "the new version is live and serving" (verified behavior). Confirm a deploy by the deployed system's ACTUAL behavior, not the deploy command's exit. This is post-deploy behavioral verification / release validation.

**3. Duplicate incidents (same title, different GUIDs).**
The portal would not show incident "number 7" (f03904b2) and instead showed "number 1" whose activities stopped at June 24 -- contradicting the jq proof of a July-8 comment. Root cause: TWO incidents share the title "MCP Tool Shadowing executed: send_email redirected to attacker@pwnd.com" with DIFFERENT GUIDs (f03904b2 = number 7, created Jul 1; 71ca1ae3 = number 1, created Jun 22). Lab detection re-runs create NEW incidents (new GUIDs), not updates to old ones. The Function correctly targets f03904b2 by GUID; the portal navigation (by title/number) landed on the other one.
- Caught by: refusing to accept a date that didn't add up (a July-8 comment can't be absent from the incident that has it -> the viewed incident must be a different record), then resolving via the ARM API (listed all "Tool Shadowing" incidents with their GUIDs).
- Lesson: entity resolution -- same label, different entity is a real trap. Resolve to the STABLE unique identifier (GUID), never the human label (title/number). Incident numbers are unstable (reassigned on rebuild). The ARM API is ground truth; the portal is a fallible, cached, sometimes-diverging view (Defender vs. Azure portals differ). When the UI confuses you, query the API.

### Two planes still both exercised (as managed identity, deployed)
Scoring queries TWO tables (SecurityAlert + MCPProtocolLogs_CL) via data-plane Log Analytics Reader; comment write via management-plane Sentinel Responder. Deployed run (proof: figure_15) confirmed the managed identity reads both tables for scoring and writes the scored comment. Audit-grade proof: jq on incident f03904b2 comments shows latest authored by objectId of func-mcp-triage-lab-rg with the Sprint 3 CRITICAL message.

### OPEN GATES
1. ~~SessionId placeholder~~ -- closed Sprint 2.
2. **Function key -> managed-identity swap** -- STILL OPEN. Playbook->Function hop still uses a function key (shared secret in URL). Swap to managed-identity/Easy-Auth before any GitHub publish of the playbook definition.

### Test-coverage note (honest)
The "fully corroborated realized breach" tier (ingestion>0 AND RealizedBreach) has NO real-data example -- verified synthetically only, because ollmcp can't emit ingestion events and Claude won't execute. Documented so the gap is explicit.

### SC-200 / concept coverage this sprint
- KQL: countif conditional aggregation, make_set/make_list, has vs contains (term-indexed vs substring), toint() explicit type conversion (KQL strict -- no implicit bool->int), let for tabular subqueries, join kind=leftouter vs inner (data preservation), coalesce for outer-join nulls, row-count sanity after joins, booleans-summed-to-a-count idiom, getschema for schema discovery.
- Detection: attempt vs realized impact (detection fidelity, alert fatigue); payload inspection over metadata; corroboration needs INDEPENDENT signals; confidence vs impact as separate axes; a rule fires on a CONDITION (Claude's clean recipient means R4's condition unmet).
- Epistemics: independent corroboration vs derived consistency (alerts derived FROM telemetry -- agreement checks the pipeline, not independent reality); data provenance/lineage.
- Software: pure functions & unit-testability; separation of concerns; serialization/deserialization at boundaries; list() iterates not converts; success-signal != correct-output.
- Deployment: "deployed" != "live/serving"; post-deploy behavioral verification; a deploy can silently not-take.
- Sentinel/identity: incident (case) vs alert (detection); SystemAlertId as incident<->alert join key; IncidentName column holds the GUID; incident numbers are UNSTABLE (reassigned on rebuild); GUID is the stable identity; entity resolution (same title != same incident); Defender portal vs Azure portal are different views over the same data; portal is a cached/filtered view, ARM API is ground truth.
- Investigation: root-cause vs symptom; confirm mechanism at source before acting; one symptom can have multiple causes -- gather evidence to distinguish; refuse to accept a contradiction, investigate it.

### Next
- Sprint 4 -- the bounded LLM: it NARRATES the deterministic score (natural-language explanation for the analyst) but does NOT make the severity decision. Determinism stays load-bearing; the model only adds readable explanation. Every prior sprint built the trustworthy deterministic core precisely so the LLM can be added safely -- as narrator, not decider.
- Before any GitHub publish of the playbook: close Gate 2 (function key -> managed identity).

---

## 2026-07-14 — MILESTONE: Sprint 4 COMPLETE (bounded LLM narrator; the pipeline now explains — safely — and runs fully autonomously)

**Work span:** 2026-07-08 to 2026-07-14 (UTC). Design → bounded narrator build (5 layers) → local + deployed proof of BOTH LLM paths (real narration + fail-safe against a real API error) → first fully-autonomous end-to-end run → a real commit-latency race discovered, mis-diagnosed, MEASURED, corrected, and the corrected fix verified.

### What shipped
The pipeline now **explains its decision** — a bounded LLM narrates the already-decided deterministic severity in natural language, additive and clearly labeled, and it does so with no authority to change the verdict. And the full chain now runs **autonomously end-to-end**: detection → incident → automation rule → playbook (with a commit-latency delay) → Function → reconstruct → score → narrate → managed-identity comment, no human in the loop. Flow: incident → SessionId (Sprint 2) → gather facts (Sprint 3) → deterministic score (Sprint 3, authoritative) → **bounded LLM narration (Sprint 4, explanatory)** → comment with both blocks.

### The bounded narrator (5 layers) — hardening around ONE principle
`narrate_assessment(severity, facts) -> str | None`. Severity is an INPUT (from `score_session`); the function returns only a narration string or None. Five layers:
- **L1 sanitize** — aggressively strip the attacker-controlled evidence (recipients, rule names) to a whitelisted char set; removes STRUCTURAL injection vectors (newlines, brackets, tags, control chars). Replaces stripped chars with a space (keeps legit multi-part data readable, not fused).
- **L2 isolate** — the sanitized evidence goes in a delimited `<untrusted_evidence>` block the model is told to describe, never obey.
- **L3 narrow task** — explain the GIVEN severity in 2–3 sentences; never assign, never recommend actions.
- **L4 validate** — output must be a non-empty string, hard length cap (600 chars).
- **L5 fail-safe** — ANY exception → return None → caller proceeds with the deterministic-only comment.

### The architectural guarantee (the thesis, stated) — the correction that mattered
Char-stripping does NOT neutralize word-based injection ("IGNORE PREVIOUS INSTRUCTIONS" is letters + spaces; it survives). Proven empirically. So L1 is **hardening, not the guarantee**. The GUARANTEE is architectural: severity flows `score_session` → `_build_comment` DIRECTLY; it is never in the LLM's output path. Even a fully-compromised model can only produce a labeled, subordinate wrong sentence beside a correct authoritative verdict — it cannot change the severity, cannot trigger an action. **Prompt injection is unsolvable by filtering (malicious input is natural language, indistinguishable from valid data at the character level); the robust defense is constrained capability, not perfect input sanitization.** Hardening reduces the LIKELIHOOD of a bad narration; architecture eliminates the POSSIBILITY of a bad verdict.

### Trust labeling as a security control
`_build_comment` writes two explicitly-labeled blocks: `[Rule-based - Non AI generated] Severity: …` (authoritative, always first) and `[AI-generated explanation -- narration only, does not affect the severity above] …` (additive, only if narration present). Labeling both sides means an analyst never has to INFER which half is authoritative — the label itself is the control. If the LLM fails, the comment is exactly the deterministic pre-assessment; the authoritative content never degrades.

### BOTH LLM paths proven against REAL conditions (branch coverage)
- **Fail-safe path** (2026-07-10): the Anthropic API returned a REAL `400 - credit balance too low` error. L5 caught it, logged the traceback, and the pipeline wrote the deterministic-only comment and succeeded (`Executed 'triage' (Succeeded)`). Real fault-injection, not a mock — stronger than the earlier stubbed test. (figure_16)
- **Happy path** (2026-07-10 → 07-14): deployed, managed identity, real Claude narration appended and correctly labeled. (figures 16, 17 manual-invoked; figures 20, 21 fully autonomous.)

### THE MAIN FINDING — a commit-latency race: discovered, MIS-DIAGNOSED, measured, corrected, verified
**Discovery (07-10):** first fully-autonomous run wrote a DEGRADED comment ("no SessionId could be reconstructed") — managed identity fired ~12s after incident creation, before reconstruction's inputs were queryable. Real race, surfaced only under autonomous full-speed execution (manual curl tests always passed because the human introduces natural delay).

**Wrong fix (07-13):** hypothesized `SecurityAlert` commit latency; added a bounded in-Function retry (45s wait, max 2 attempts). Deployed and re-ran → STILL degraded (comment now ~58s out, so the retry demonstrably FIRED — it just didn't help). The hypothesis fit the symptom but was never measured.

**Measurement (07-13):** `ingestion_time()` on both tables the reconstruction join depends on:
```
SecurityAlert       commit lag = 32s
SecurityIncident    commit lag = 77s   <- the binding constraint
```
The query STARTS from `SecurityIncident` (inner join); its Log Analytics table copy lagged the ARM incident resource by 77s. The 45s retry fired at ~T+57s — 18s too early. `AlertIds` WAS populated, so empty-linkage was ruled out. Root cause was the incident-table commit latency, not the alert's.

**Conceptual error caught:** "the incident exists in ARM" (queried at T+0) != "the incident is queryable in KQL" (T+77s). Different systems, different latencies; the reconstruction depends on the slower one.

**Corrected fix (07-14):** a 120s `Delay` action in the playbook, BEFORE the HTTP call to the Function (right layer: the orchestrator shouldn't invoke the responder before the responder's input exists; and a playbook delay avoids the Logic App's ~120s synchronous-HTTP timeout that an in-Function sleep would risk). The 45s in-Function retry is retained as a variance backstop. **Verified:** incident #18, autonomous run, comment landed ~139s after creation (120s delay + 8s measured chain latency + Function work), and — the key signal — it was a scored `CRITICAL` + narrated comment, NOT the degraded message. The degraded→scored flip is the fix, confirmed.

### TWO more corrections caught by verification this sprint
**1. `Trigger: Manual` in the Defender activity pane is NOT evidence of manual invocation.** Initially read it as "the Function was curl-invoked." Falsified: incident #18's comment shows `Trigger: Manual` yet was written by a run we KNOW was autonomous. The field describes HOW the comment was added (external app via ARM comments API) — every Function-written comment reads Manual regardless of what invoked the Function. **Autonomy is evidenced by the Logic App run history, not this field** (figure_23: Sentinel-incident trigger → Delay 2m → For each → HTTP, all green, run started off the incident event).
**2. Chain-startup latency measured at 8s, not the ~2s assumed** (incident #18 created 14:28:08 → playbook run started 14:28:16). Small, but the delay-margin math should use the measured value.

### Progression (the engineering story, three data points)
```
Jul 10   no delay        comment @ +12s    DEGRADED (race discovered)
Jul 13   45s retry       comment @ +58s    DEGRADED (retry fired; wrong table targeted)
Jul 14   120s delay+retry comment @ +139s  CRITICAL scored + narrated  ✓
```

### Engineering notes
- `_reconstruct_session_id` refactored into a retry wrapper + `_attempt_reconstruct_session_id` (single-shot). Separates "how to retry" from "what to try"; retry policy lives in one place; the query stays a plain testable function.
- `narrate_assessment` bounding was tested adversarially (stubbed compromise, outage, garbage, overflow) AND against the real API. Worst-case verified: a fully-injected LLM only corrupts the labeled narration, never the verdict.
- API key: `os.environ["ANTHROPIC_API_KEY"]`, from gitignored `local.settings.json` locally / Function App app setting when deployed. Never in code, never committed. `anthropic` added to requirements.txt (commented: bounded narrator; explains, never decides).

### Artifacts produced
- Sprint 4 `function_app.py` (496 lines: narrator + retry) + requirements.txt (`anthropic`)
- figure_16 — fail-safe graceful degradation vs. a REAL zero-credits API error (terminal png + full-log txt)
- figure_17/18 — deployed narrated assessment, CLI + Defender UI (manual-invoked; incident #7)
- figure_19 — autonomous run degraded comment (the race; incident #9, "no SessionId" jq)
- figure_20 — autonomous race gap: incident creation time vs. degraded-comment time (~12s, incident #9)
- figure_21/22 — fully-autonomous narrated assessment, CLI + Defender UI (incident #18)
- figure_23 — Logic App run history: autonomous invocation + the 120s Delay executing
- `FINDING_alert_commit_race.md` — the two-stage race diagnosis (wrong hypothesis retained + measured correction)
- Updated function_app flow diagram (draw.io + docx) reflecting the narrator, retry, and architectural bound

### SC-200 / concept coverage this sprint
- AI security: prompt injection (OWASP LLM01) unsolvable by filtering; structural injection vectors (newlines/brackets/tags/control chars) forge the code/data boundary; hardening (probabilistic) vs architectural guarantee (eliminates possibility); constrain capability, don't just filter input; provenance/trust labeling as a control; second-order injection (attacker data flowing into the defender's own analysis LLM).
- Resilience: transient-fault handling & the Retry pattern; bounded retries (never unbounded); retry-then-degrade; graceful degradation / enhancement-not-dependency; adversarial/negative testing; real fault-injection > mocks; branch coverage of BOTH paths of an external dependency.
- Distributed systems: race conditions surface under autonomous timing, pass manual tests; ingestion/commit latency (`ingestion_time()` vs `TimeGenerated`); ARM resource vs Log Analytics table copy are different systems with different latencies; an inner join needs BOTH sides committed; schedule the response at the right layer (orchestrator, not responder).
- Investigation/epistemics: a hypothesis that explains a symptom is not a verified cause; MEASURE latency, don't infer it; falsify with data (`Trigger: Manual`; the wrong-table fix); the run history — not a UI field — evidences autonomy.
- Software: separation of concerns enables extension without disturbing (the narrator slotted into a seam); pure functions; secret management (env var / app setting, never in code/committed).
- Deployment: "Remote build succeeded" != live (confirm by behavior); autosaved Draft != Published (Logic App); copied file != right file (verify line count + grep, not the `cp` exit).

### OPEN GATES
1. ~~SessionId placeholder~~ — closed Sprint 2.
2. **Function key → managed-identity swap** — STILL OPEN. Playbook→Function hop uses a function key (shared secret in URL). Close before any public GitHub publish of the playbook definition. (Repo is currently private / not yet published, so no live exposure.)

### Next
- Arc COMPLETE (use → defend → analyze → detect → **respond**). Sprint 5 = hardening/packaging for publication: close Gate 2, then public GitHub repo with the arc narrative.
- Optional future work (noted in the finding): read incident→alert linkage from the ARM API (immediately consistent) instead of the `SecurityIncident` table, removing the 77s lag from the critical path entirely.

---

## 2026-07-15 — GATE 2 CLOSED: playbook→Function auth swapped from function key to managed identity (the pipeline is now credential-free and publish-ready)

**Work span:** 2026-07-15 (~1h50m focused block). Swapped the last shared secret in the
autonomous chain — the function key the playbook used to call the Function — for
managed-identity / Microsoft Entra (Easy Auth) authentication, then rotated the exposed key.
This was the final engineering blocker before the repo can be published.

### Why it mattered
The playbook (`pb-mcp-triage-skeleton`) called the Function (`func-mcp-triage-lab-rg`) with a
**function key in the request URI** (`?code=<key>`). That key lives in the playbook's
ARM/Logic App definition — so exporting that definition to a public repo would publish the
secret. Gate 2: swap the hop to identity-based auth and remove the key before any publish.

### What shipped (end state)
- Playbook HTTP-action URI is the bare endpoint — `.../api/triage`, **no `?code=`**.
- Playbook authenticates with its **system-assigned managed identity**, presenting an Entra
  token for audience `api://<function-app-client-id>...` (the Function's app-registration client ID).
- Function App has **Easy Auth** (Microsoft identity provider) enabled: require
  authentication, unauthenticated → **HTTP 401**, tenant-restricted to home tenant.
- Function `authLevel` **FUNCTION → ANONYMOUS** (line 412) — required with Easy Auth in
  front; the identity check moved to the Easy Auth layer, so "anonymous" is correct and *more*
  secure, not "open" (unauthenticated calls still 401).
- Old function key **rotated**; the exposed value (pasted mid-session, so treated as
  compromised) now returns 401, as does any key.

### Verified against a real autonomous run
- Incident #22, GUID `61cfe118-b9e0-4740-b267-309a018ab50e`, created 17:57:42Z.
- Comment written 18:00:01Z (~139s: 120s delay + chain + work), scored **CRITICAL** + real
  narration, authored by the managed identity — **no key in any hop**.
- The comment landing at all is proof the token was accepted; a failed auth would have 401'd
  the HTTP action with no comment written.
- Old key → 401 confirms key auth is fully retired.

### Gotchas caught (each cost time; each worth remembering)
**1. Principal/object ID vs application/client ID.** Easy Auth "Allowed client applications"
matches the token's `appid` claim = the identity's **Application (client) ID**, NOT its
principal/object ID. The playbook's `principalId` is `<playbook-principal-id>...`; the value the allow-list
needs is its `appId` `<playbook-app-id>...` (via `az ad sp show --id <principalId> --query appId`).
Using the principal ID would have been a silent 401. (principalId = RBAC; appId = token
audience/allow-list.)

**2. The `api://` audience prefix.** The Function's `allowedAudiences` is
`api://<function-app-client-id>...`; the playbook's HTTP-action Audience must match exactly (with the
`api://`), not the bare GUID.

**3. `az webapp auth show` gave a misleading v1 projection of a v2 config.** It reported
`unauthenticatedClientAction: RedirectToLoginPage` and null `globalValidation`, while the
portal (v2-native) showed "Return HTTP 401." Resolved by testing ACTUAL BEHAVIOR:
`curl` the endpoint unauthenticated → **401** = the setting IS in effect; the CLI report was
the artifact. Also: `az webapp auth update --action` is v1-only (no `Return401` value) and
would risk clobbering the v2 provider config — used the portal for v2 auth fields instead.

### Lessons (recurring themes, reinforced)
- Two IDs, two purposes: application/client ID for token audience + allow-list; principal ID
  for RBAC. Confusing them = silent 401.
- Behavior over reports: portal and CLI disagreed (and one was internally inconsistent); the
  running system's HTTP response settled it. When dashboards conflict, measure behavior.
- Match the tool to the task: a v1-era CLI command can't express (and can damage) a v2 auth
  config; the portal writes v2 natively.
- Credential hygiene: rotate anything that leaks (the key was pasted, so it was rotated);
  Azure redacted the new key in CLI output (`value: null`) — good default.
- "Deployed/saved ≠ live": the authLevel redeploy and the playbook auth change both needed
  explicit confirmation (publish the Logic App draft; verify behavior, not the build message).

### Artifacts
- figure_24 — old (rotated) function key → 401 (key auth retired)
- figure_25 — Logic App run history: HTTP action green via managed identity (incident #22)
- figure_26 — playbook HTTP action inputs: keyless URI + `ManagedServiceIdentity` auth,
  audience `api://<function-app-client-id>...`
- `docs/GATE2_managed_identity_swap.md` — full swap writeup (sequence, gotchas, lessons)

### SC-200 / concept coverage
- Identity & auth: managed identity = credential-free M2M auth; Microsoft Entra / Easy Auth
  (App Service Authentication) as a token-validation layer in front of a Function;
  authentication vs authorization; the `api://` audience; app-registration client ID vs
  managed-identity principal ID; the token `appid` claim.
- Azure ops: Easy Auth v2 vs v1 CLI surface mismatch; portal-vs-CLI ground-truth
  reconciliation; key rotation; unauthenticated-action (401 for APIs vs redirect for
  websites).
- Security posture: eliminate shared secrets from exportable definitions; least-privilege
  (unused Graph `User.Read` and provider secret left untouched, not expanded); rotate leaked
  credentials.

### OPEN GATES
1. ~~Gate 1 (SessionId placeholder)~~ — closed Sprint 2.
2. ~~Gate 2 (function key → managed identity)~~ — **CLOSED 2026-07-15 (this entry).**

### Next (Sprint 5 — packaging for publication)
- Export the playbook ARM/Logic App definition to the repo — now safe (no key in URI), but
  scan the export: no `?code=` remnant, and never commit the
  `MICROSOFT_PROVIDER_AUTHENTICATION_SECRET` *value* (the auto-created, unused provider
  secret).
- Docs pass, figures, demo video; then public GitHub publish of the full arc
  (use → defend → analyze → detect → respond).
- Optional (from the race finding): read incident→alert linkage from the ARM API
  (immediately consistent) to drop the `SecurityIncident` 77s lag from the critical path.

### In-flight (resume 2026-07-17+): demo video, then publish
- Next: record demo video — continuous take, autonomy as the hero beat, compress the labeled 120s delay (approach decided). Then publish: flip repo public, update LinkedIn/Notion/résumé links, capstone arc-complete post.
- Phase B (README + diagrams + SETUP.md) is complete. Sprint 5 remaining is video + publish only.

#### Closed 2026-07-17: SETUP.md + three issues it surfaced
- Wrote `SETUP.md` (standalone reproducibility guide, linked from README on-ramp): prerequisites, provisioning, deploy steps, RBAC grants (Log Analytics Reader + Microsoft Sentinel Responder on the Function's managed identity), a "Code you must edit" section (WORKSPACE_ID / LEGIT_RECIPIENTS / _LLM_MODEL are code constants, not app settings), lab-specific vs. portable split, verification, troubleshooting.
- Confirmed the only runtime env var is `ANTHROPIC_API_KEY` (`function_app.py:355`); everything else is a code constant. Graceful degradation verified: an unset key raises inside the Anthropic call, is caught by the Layer-5 fail-safe in `narrate_assessment`, deterministic verdict still writes.
- Writing the guide flushed out three real issues, all fixed:
  - **Hardcoded workspace GUID** at `function_app.py:22` — missed by the earlier redaction pass, which scoped its greps to `.md`/`.txt`/`.json` and never scanned source. Redacted to `<placeholder>` (commit `4042587`). Source-wide GUID/subscription/hostname scan otherwise clean. History left intact per the documented scrub-forward stance (workspace ID = non-credential identifier, same category as the tenant/client IDs).
  - **`test_scorer.py` broken as committed** — it string-extracted `score_session` from `function_app_sprint3.py` (renamed to `function_app.py` during consolidation → FileNotFoundError), and the extraction boundaries (`def score_session` … `def _build_comment`) were also stale after the file reorg (narration code now sits between them).
  - **`function_app.py` not import-safe** — `DefaultAzureCredential()` and `LogsQueryClient()` were instantiated at module import (lines 29–30), so a plain `import function_app` required Azure creds. This is why the original test used the fragile extract-and-exec workaround.
- Fixes (committed together as `test(scorer): import score_session directly; make data-plane client lazy for import-safety`):
  - Made the data-plane client **lazy-init** via `_get_logs_client()`; both `query_workspace` call sites updated. Module now imports with no Azure creds (verified: client/credential both `None` at import).
  - **Rewrote `test_scorer.py`** to import `score_session` directly (durable against future reorg) as a **zero-dependency** plain-assert runner — no pytest (requirements.txt has none), runs `python3 test_scorer.py`, exit-coded, all 6 cases across every severity tier pass.
- Lesson banked: **a redaction pass is only as complete as its file-type scope.** "Redacted" was claimed after scanning md/txt/json, but `.py` source held an un-scrubbed identifier. The claim was broader than the scan; the gap was in the file type we skipped.

#### Closed 2026-07-16 (this block's predecessor: playbook PLACEHOLDER cleanup + Sprint 5 gating)
- Placeholder `sessionId` removed from live playbook, published, and verified gone from the live ARM definition via `az logic workflow show ... | grep -i sessionid` (empty). Draft/Active badge persisted cosmetically — grep against ARM was the authoritative check.
- Playbook definition first-committed as the single file `playbooks/pb-mcp-triage-skeleton.definition.json` (1819 bytes; earlier stray `playbook/` dir and duplicate `.json` removed). Acceptance-tested: valid JSON, `incidentArmId` present, no `sessionId`.
- Secret gates passed: working-tree grep triaged clean; full-history `gitleaks` = "no leaks found" after two `generic-api-key` false positives (x-ms-client-request-id correlation GUIDs in figure_16) were suppressed via fingerprint-scoped `.gitleaksignore`. Rotated function key confirmed never committed to history.
- `.gitignore` verified (local.settings.json, .venv/, __pycache__/, *.env all covered); `local.settings.json.example` template content-verified as placeholder-only.
- Identifiers redacted-forward (tenant/client/principal IDs → placeholders); history left intact by decision (non-secret object IDs); rationale documented in README Security section. Post-scrub gitleaks re-run clean.
- Architecture diagrams (hero `architecture_overview.svg` + detailed `function_app_triage_flow.svg`) color-matched and placed in docs/figures/.
- README consolidated (diagrams wired in, "Open gates" removed, Gate 2 collapsed, Security + identifier note added, on-ramp expanded). Both pre-commit checks passed: internal docs/*.md links resolve; detection-pack cross-link confirmed Public + clean URL via Edge InPrivate.