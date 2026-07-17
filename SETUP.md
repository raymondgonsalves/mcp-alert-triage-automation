# Setup & Reproducibility

This guide describes how to stand up the `mcp-alert-triage-automation` pipeline in your own
Azure environment. It is written to be followed end-to-end — but read
[What's lab-specific vs. portable](#whats-lab-specific-vs-portable) first, because parts of
the detection layer are specific to this lab and you will substitute your own.

The pipeline is: **detection fires → Sentinel incident → Automation Rule → Logic App
playbook → Azure Function (managed identity) → write-back to the incident.** See the
[architecture diagrams](README.md#architecture) for the full picture.

---

## Prerequisites

| Requirement | Version / detail | Why |
|---|---|---|
| Python | **3.12** | The Function App targets the Azure Functions **v4** runtime, Python **v2** programming model. |
| Azure Functions Core Tools | v4 | Local run + `func azure functionapp publish`. |
| Azure CLI | current | Provisioning, RBAC grants, verification (`az rest`, `az logic`, `az monitor`). |
| An Azure subscription | Contributor on a resource group | To create the resources below. |
| Anthropic API key | — | The bounded LLM narrator. Absent, the deterministic pipeline still runs; only the narration is skipped (see [graceful degradation](#configuration-app-settings)). |

Azure resources you will provision:

- A **Log Analytics workspace** with **Microsoft Sentinel** enabled on it.
- A custom log table (this lab uses **`MCPProtocolLogs_CL`**) plus its **DCR/DCE** and a forwarder to populate it — *lab-specific; see below.*
- An **Azure Function App** (Linux, Python 3.12, Functions v4) with its **storage account** and **Application Insights** (referenced by `host.json`).
- A **Logic App** (Consumption) for the playbook.

---

## What's lab-specific vs. portable

Being explicit here is the point — a reproducibility guide that hides its assumptions fails
the moment someone tries to follow it.

**Portable (transplants with configuration):**

- The **Azure Function** (`function_app/`) — the entire triage brain: session reconstruction, deterministic scoring, the bounded LLM narrator, and the managed-identity write-back.
- The **playbook** (`playbooks/pb-mcp-triage-skeleton.definition.json`) — with connection/identity substitutions (see [Deploy the playbook](#5-deploy-the-playbook)).
- The **managed-identity auth model** (Gate 2) — playbook → Function via Entra token, Function → Sentinel via its own managed identity. No stored secrets.

**Lab-specific (you substitute your own):**

- The **four detection analytics rules** and their grouping. The pipeline assumes incidents that carry a **SessionId** your detections emit. You would substitute your own detections that produce a correlatable session identifier.
- The **`MCPProtocolLogs_CL` table, its DCR/DCE, and the forwarder** that lands MCP protocol logs. Your reconstruction source will differ.
- The **reconstruction KQL** inside the Function (incident → alert → SessionId → session facts) is written against this lab's schema. You will adapt the queries to your table shape. See `docs/INTERFACE_CONTRACT.md` for the contract the Function expects.
- Two **hardcoded, lab-specific values in `function_app.py`** you must edit (see [Code you must edit](#code-you-must-edit)): the workspace ID and the legitimate-recipient allowlist.
- All **resource names, workspace IDs, and tenant/subscription identifiers** — these are placeholders throughout (`<...>`).

The honest summary: the **response half** (score → narrate → write back, all under managed
identity) is fully portable. The **detection + reconstruction half** assumes this lab's data
model and is where you'll do real adaptation work.

---

## Code you must edit

The committed `function_app.py` carries lab-specific constants as **placeholders or lab
values** — it is a template, not drop-in-runnable. Set these before deploying:

| Location | Constant | Set to |
|---|---|---|
| `function_app.py:22` | `WORKSPACE_ID` | Your Log Analytics workspace **GUID** (currently a `<placeholder>` — redacted). |
| `function_app.py:27` | `LEGIT_RECIPIENTS` | Your legitimate recipient allowlist. A send to anything **not** on this list is treated as a redirect. This lab uses `("alice@mail.com",)`. |
| `function_app.py:36` | `_LLM_MODEL` | The Anthropic model string (e.g. `claude-sonnet-4-6`). Hardcoded here — **not** an app setting. |

---

## Deploy steps

Placeholders used below: `<resource-group>`, `<location>`, `<workspace-name>`,
`<workspace-id>`, `<function-app-name>`, `<function-app-client-id>`, `<subscription-id>`.

### 1. Provision the workspace and Sentinel

Create the Log Analytics workspace and enable Microsoft Sentinel on it. Create the custom
table and its data-collection pipeline (**lab-specific** — substitute your own detection
source if you are not reproducing the MCP forwarder).

### 2. Deploy the detection layer (lab-specific)

Deploy your analytics rules so that firing produces a Sentinel **incident** carrying a
**SessionId** your reconstruction step can key on. This lab uses four rules grouped per
session; yours will differ. The rest of the pipeline only requires that an incident exist and
that a SessionId be recoverable from it — that is the contract in `docs/INTERFACE_CONTRACT.md`.

### 3. Deploy the Azure Function

```bash
cd function_app

# Create YOUR OWN virtualenv (do not reuse a committed one)
python3 -m venv .venv
source .venv/bin/activate            # Windows/WSL: source .venv/bin/activate
pip install -r requirements.txt

# Edit the lab-specific constants first (see "Code you must edit" above):
#   function_app.py:22  WORKSPACE_ID
#   function_app.py:27  LEGIT_RECIPIENTS
#   function_app.py:36  _LLM_MODEL   (only if changing the model)

# Run the scorer test (zero-dependency; no Azure creds needed) — see Verification
python3 test_scorer.py

# Publish to the Function App (Functions Core Tools v4)
func azure functionapp publish <function-app-name>
```

The Function is the **Python v2 model** (`function_app.py` is the single entry point). The
HTTP trigger exposes the endpoint the playbook calls: `/api/triage`.

### 4. Grant the Function's managed identity its roles

The Function authenticates outward with `DefaultAzureCredential` — locally your dev identity,
in Azure the Function App's **system-assigned managed identity**. Enable that identity, then
grant it the two roles it needs. **These grants are load-bearing:** without them the Function
publishes cleanly but fails at runtime (KQL reads return 403, or the write-back PUT is
rejected).

```bash
# Enable system-assigned managed identity on the Function App
az functionapp identity assign -g <resource-group> -n <function-app-name>

# Capture its principalId
FUNC_MI=$(az functionapp identity show -g <resource-group> -n <function-app-name> --query principalId -o tsv)

# (a) Read session data from Log Analytics (azure-monitor-query)
az role assignment create --assignee "$FUNC_MI" \
  --role "Log Analytics Reader" \
  --scope "/subscriptions/<subscription-id>/resourceGroups/<resource-group>/providers/Microsoft.OperationalInsights/workspaces/<workspace-name>"

# (b) Write incident comments back to Sentinel (requests -> Sentinel REST API)
az role assignment create --assignee "$FUNC_MI" \
  --role "Microsoft Sentinel Responder" \
  --scope "/subscriptions/<subscription-id>/resourceGroups/<resource-group>"
```

| Role | Scope | Enables |
|---|---|---|
| **Log Analytics Reader** | the workspace | `azure-monitor-query` runs the reconstruction KQL |
| **Microsoft Sentinel Responder** | the workspace / RG | `requests` PUTs the narrated comment to the incident |

Responder is the least-privilege role that can write incident comments; Contributor also
works but grants more than needed.

### 5. Deploy the playbook

The committed definition is `playbooks/pb-mcp-triage-skeleton.definition.json`. Import it into
a Consumption Logic App. **Two things do not transplant and must be set for your tenant:**

- **API connections / `$connections`** — a bare definition does not carry live connections. Re-create the Microsoft Sentinel connection (and any others) in your tenant after import.
- **The Easy Auth audience** — the playbook's HTTP action presents a managed-identity token for audience `api://<function-app-client-id>`. This value in the committed file is a **placeholder** (redacted); replace it with *your* Function App's app-registration client ID.

After import, enable the Logic App's managed identity and add it to the Function's **Easy Auth
allow-list** (this is the Gate 2 model — the Function validates the token and rejects
everything else with 401). See `docs/GATE2_managed_identity_swap.md` for the exact auth wiring.

### 6. Wire the Automation Rule

In Sentinel, create an **Automation Rule** that runs the imported playbook when a qualifying
incident is created. This is what makes the pipeline autonomous — no human invocation.

> **Note the built-in delay.** The playbook contains a ~120s delay before it calls the
> Function. This is deliberate: it absorbs a measured commit-latency race between incident
> creation and the `SecurityIncident` record being queryable. See
> `docs/FINDING_alert_commit_race.md`. Do not remove it.

---

## Configuration (app settings)

Set on the Function App via `az functionapp config appsettings set -g <resource-group> -n <function-app-name> --settings KEY=value`:

| Setting | Value | Notes |
|---|---|---|
| `FUNCTIONS_WORKER_RUNTIME` | `python` | From `local.settings.json.example`. |
| `FUNCTIONS_EXTENSION_VERSION` | `~4` | Functions v4 runtime. |
| `AzureWebJobsStorage` | storage connection | The Function App's storage account (not the emulator sentinel used locally). |
| `APPLICATIONINSIGHTS_CONNECTION_STRING` | telemetry | `host.json` enables App Insights logging. |
| `ANTHROPIC_API_KEY` | your Anthropic key | The **only** environment variable the Function reads (`function_app.py:355`). See graceful degradation below. |

Everything else the Function needs is a **code constant**, not an app setting — the workspace
ID, recipient allowlist, and model are edited in `function_app.py` (see
[Code you must edit](#code-you-must-edit)). `ANTHROPIC_API_KEY` is the sole runtime env var.

**Graceful degradation (no key = no crash).** The Anthropic call lives inside
`narrate_assessment`, whose Layer-5 fail-safe returns `None` on *any* failure. So an unset or
invalid `ANTHROPIC_API_KEY` raises inside the LLM call, is caught by that fail-safe, and the
pipeline proceeds with the **deterministic-only** comment — the authoritative verdict still
writes; only the narration is skipped. The key is recommended, not strictly required.

**Local development** uses `function_app/local.settings.json` (git-ignored; copy from
`local.settings.json.example` and add `ANTHROPIC_API_KEY`). Never commit the populated file —
that is what the `.gitignore` entry protects.

---

## Verification — "how do you know it worked"

**Unit level (no Azure, no pytest, no key):**

```bash
cd function_app
python3 test_scorer.py        # exit 0 = all pass; prints PASS/FAIL per severity tier
```

Confirms the deterministic scorer — the authoritative severity logic — across all tiers
(Critical / High / Medium / Low / Informational) before any deployment. Zero-dependency: it
imports `score_session` directly and needs only the packages in `requirements.txt`.

**End-to-end (the autonomous chain):**

1. Trigger a qualifying detection (or replay session data into the source table).
2. Confirm the incident was created and the **playbook ran on its own** — check the Logic App **run history** (autonomous invocation, not a manual run). Cf. `docs/figures/figure_23_sprint4_playbook_run_history_autonomous_invocation.png`.
3. Confirm the **narrated comment** was written by the Function's **managed identity** (not a user), primary-source via the REST API:

```bash
az rest --method get \
  --url "https://management.azure.com/<incident-arm-id>/comments?api-version=2023-11-01"
```

The comment's `author` will be the managed identity — the proof of credential-free
write-back. (The Defender Activity pane's `Trigger` field reads `Manual` for API-written
comments; that reflects *external application*, not manual invocation — autonomy is evidenced
by run history. See the README's *Verifying the pipeline* section.)

---

## Troubleshooting

| Symptom | Likely cause | Fix |
|---|---|---|
| Function publishes but KQL reads 403 | MI missing Log Analytics Reader | Step 4(a). |
| Write-back PUT rejected (403) | MI missing Sentinel Responder | Step 4(b). |
| KQL runs but returns nothing / wrong workspace | `WORKSPACE_ID` still the placeholder | Set `function_app.py:22`. |
| Playbook -> Function returns **401** | Logic App MI not on the Function's Easy Auth allow-list, or wrong audience | Step 5 + `docs/GATE2_managed_identity_swap.md`. |
| Reconstruction returns no SessionId on first run | Commit-latency race (incident not yet queryable) | The 120s playbook delay handles this — don't remove it. `docs/FINDING_alert_commit_race.md`. |
| Narration missing, everything else fine | `ANTHROPIC_API_KEY` unset or invalid | Expected graceful degradation — deterministic verdict still writes; set the key to restore narration. |

---

## A note on identifiers

All tenant, subscription, workspace, and object identifiers in this repo are placeholders.
None are credentials — the pipeline uses managed-identity auth with no stored secrets. See the
README's *Security* section for the full rationale.
