# MCP Alert Triage Automation

Automated investigation and response for Microsoft Sentinel incidents raised by the
[MCP Tool Shadowing Detection Pack](https://github.com/raymondgonsalves/mcp-tool-shadowing-detections).

When a detection fires, this pipeline performs the repetitive first-pass triage a SOC
analyst would otherwise do by hand — reconstruct the session, enrich it, score severity,
and either auto-close with an explanation or escalate with the evidence assembled. A
bounded LLM writes a plain-English incident summary; all decisions are made by
deterministic code, never the model.

> **Status:** Sprint 0 (design complete; detection rules being stood up as live analytics rules). Build not yet started.

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

## Repository status

Skeleton. Pipeline code lands in Sprint 1.
