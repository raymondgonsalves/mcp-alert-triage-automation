# MCP Alert Triage Automation

Automated investigation and response for Microsoft Sentinel incidents raised by the
[MCP Tool Shadowing Detection Pack](https://github.com/raymondgonsalves/mcp-tool-shadowing-detections).

When a detection fires, this pipeline performs the repetitive first-pass triage a SOC
analyst would otherwise do by hand — reconstruct the session, enrich it, score severity,
and either auto-close with an explanation or escalate with the evidence assembled. A
bounded LLM writes a plain-English incident summary; all decisions are made by
deterministic code, never the model.

>> **Status:** Sprints 1–4 complete — the arc is closed. A detection incident triggers an automation rule → Logic App playbook → Azure Function (managed identity) that reconstructs the SessionId, gathers per-session facts, applies a deterministic recipient-aware severity model, has a **bounded LLM narrate** that verdict in plain English, and writes the labeled pre-assessment back to the incident — fully autonomously, zero human intervention. Both LLM paths are proven against real conditions (real narration, and graceful degradation against a real API failure), and a real commit-latency race discovered during the first autonomous run was measured and fixed. See `docs/DAILY_LOG.md` for the build record and `docs/FINDING_alert_commit_race.md` for the race analysis.

## The portfolio arc

This is the fifth and final artifact in a connected body of work on agentic-AI security:
**use → defend → analyze → detect → respond.** This project is *respond* — the
operational follow-through to the detection pack.

## Architecture (overview)

```
Detection rule fires → Sentinel incident
  → Automation Rule → Logic App playbook → Azure Function (Python, managed identity)
    → read SessionId (trigger key) → reconstruct session from MCPProtocolLogs_CL
    → deterministic enrichment → deterministic risk scoring
    → sanitize evidence → bounded LLM summary → schema-validate
    → auto-close | escalate | HITL-gated containment → write back to incident
```

The LLM never scores, decides escalation, or contains. That boundary is the core
architectural principle: the model is a bounded component, not the orchestrator. The
guarantee is architectural, not filter-based — severity is decided by `score_session` and
passed to the comment builder directly, never through the LLM's output path. Adversarial
testing confirmed the bound holds: even a fully-compromised model can only produce a
labeled, subordinate explanation beside a correct, authoritative verdict — it cannot change
the severity or trigger an action.

## Documentation

- `docs/` — design spec, interface contract, architecture diagram, daily log

## Build status by sprint

| Sprint | Scope | Status |
|--------|-------|--------|
| 0 | Detection foundation (four analytics rules live, grouped per session) | Complete |
| 1 | Walking skeleton (automation rule → playbook → Function → managed-identity write-back) | Complete & verified |
| 2 | Deterministic session reconstruction (incident → alert → SessionId, server-side KQL) | Complete & verified |
| 3 | Deterministic recipient-aware scoring (RealizedBreach → Critical) | Complete & verified |
| 4 | Bounded LLM narrator (explains the deterministic verdict; never decides) + commit-latency race fix | Complete & verified |
| 5 | Docs, figures, demo video; close Gate 2; public publish | Next |

## Open gates (must close before the noted milestone)

> **⚠ Gate — before any public GitHub publish of the playbook definition:**
> The playbook currently calls the Function using a **function key** (a stored secret).
> This must be swapped to **managed-identity-to-Function auth** (Azure AD / Easy Auth) and
> the key removed **before** the playbook's ARM/Logic App definition is exported to this repo.
> A committed playbook definition must never contain the key. The playbook stays cloud-only
> until this swap is done.


## Verifying the pipeline

The auto-written comment renders in the Defender incident **Activities** pane (authored by
the Function's managed identity) and can also be read primary-source via the REST API:

```bash
az rest --method get \
  --url "https://management.azure.com/<incident-arm-id>/comments?api-version=2023-11-01"
```

The comment's `author` will be the Function's managed identity (not a user), which is the
proof of credential-free write-back. Note: the Defender Activity pane's `Trigger` field reads
`Manual` for these comments — this reflects that they are written by an external application
via the ARM comments API, **not** that the Function was manually invoked. Autonomous
invocation is evidenced by the Logic App run history, not that field.
