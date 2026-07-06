# MCP Alert Triage Automation

Automated investigation and response for Microsoft Sentinel incidents raised by the
[MCP Tool Shadowing Detection Pack](https://github.com/raymondgonsalves/mcp-tool-shadowing-detections).

When a detection fires, this pipeline performs the repetitive first-pass triage a SOC
analyst would otherwise do by hand — reconstruct the session, enrich it, score severity,
and either auto-close with an explanation or escalate with the evidence assembled. A
bounded LLM writes a plain-English incident summary; all decisions are made by
deterministic code, never the model.

>> **Status:** Sprint 1 complete — walking skeleton proven. The full autonomous chain runs end to end: a detection incident triggers an automation rule → Logic App playbook → Azure Function that writes a triage comment back to the incident as its managed identity, with zero human intervention. Sprints 2–4 (enrichment, scoring, bounded LLM) fill in the Function's logic on this proven plumbing. See `docs/DAILY_LOG.md` for the build record.

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
architectural principle: the model is a bounded component, not the orchestrator.

## Documentation

- `docs/` — design spec, interface contract, architecture diagram, daily log

## Build status by sprint

| Sprint | Scope | Status |
|--------|-------|--------|
| 0 | Detection foundation (four analytics rules live, grouped per session) | Complete |
| 1 | Walking skeleton (automation rule → playbook → Function → managed-identity write-back) | Complete & verified |
| 2 | Deterministic session reconstruction (query MCPProtocolLogs_CL on SessionId) | Complete |
| 3 | Deterministic scoring + response actions | Next |
| 4 | Bounded LLM narrative summary | Planned |
| 5 | Docs, figures, demo video | Planned |

## Open gates (must close before the noted milestone)

> **⚠ Gate — before any public GitHub publish of the playbook definition:**
> The playbook currently calls the Function using a **function key** (a stored secret).
> This must be swapped to **managed-identity-to-Function auth** (Azure AD / Easy Auth) and
> the key removed **before** the playbook's ARM/Logic App definition is exported to this repo.
> A committed playbook definition must never contain the key. The playbook stays cloud-only
> until this swap is done.

  Real extraction from the incident's alert custom details lands in Sprint 2 (enrichment). This
  was a deliberate chain-first choice: prove the plumbing, then wire the real data.

## Verifying the pipeline

Note: the Defender/Azure portal incident **Comments** panel does not display comments written
via the API. Verify write-back through the REST API instead:

```bash
az rest --method get \
  --url "https://management.azure.com/<incident-arm-id>/comments?api-version=2023-11-01"
```

The auto-written comment's `author` will be the Function's managed identity
(not a user), which is the proof of credential-free write-back.
