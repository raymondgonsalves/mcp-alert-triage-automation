# MCP Alert Triage Automation — Recruiter Brief

A 3-minute overview of what was built and why it matters. For the full technical detail, see [`README.md`](https://github.com/raymondgonsalves/mcp-alert-triage-automation/blob/main/README.md).

---

## What this project is

An autonomous incident-response pipeline for Microsoft Sentinel that triages a **Tool Shadowing** attack the moment it's detected — with no analyst in the loop. When a detection fires, the pipeline reconstructs the attack session, scores its severity with deterministic code, and writes a plain-English pre-assessment back to the incident.

Its defining design choice: a language model is used only to *explain* the verdict, never to decide it. Deterministic code sets the severity and routes around the model entirely, so even a fully compromised model cannot change the outcome or trigger an action.

---

## Why this matters

Detection is only half of a SOC's job. A rule that raises an incident still leaves an analyst to do the repetitive first-pass work: figure out what happened, how bad it is, and write it up. That triage is exactly the manual load teams are trying to reduce.

This project automates that first pass for Tool Shadowing incidents — the attack class from the detection pack earlier in my portfolio arc. It closes the loop from *detecting* the attack to *responding* to it, and it does so in a way that treats the AI component as untrusted: the model helps a human read the incident faster, but it has no authority to act.

That boundary is the point. As teams rush to put LLMs into security workflows, the safe pattern isn't "let the AI decide" — it's "let deterministic code decide, and let the AI explain." This project is a working demonstration of that pattern.

---

## What I built

- **An end-to-end autonomous pipeline** — a Sentinel Automation Rule triggers a Logic App playbook, which invokes a Python Azure Function that does the triage and writes back to the incident, with zero human intervention
- **A deterministic severity scorer** — plain code that reconstructs the attack session from MCP protocol logs and assigns severity from the evidence (a send to any non-approved recipient is treated as a redirect and escalated)
- **A bounded LLM narrator** — the model writes the human-readable explanation only, hardened with a five-layer defense that degrades gracefully to a code-only comment if the model fails, errors, or is unavailable
- **Credential-free authentication** — the entire pipeline authenticates with Microsoft Entra managed identities and Easy Auth; there are no stored secrets or API keys anywhere in it
- **Least-privilege access** — the Function's identity holds exactly two scoped roles (Log Analytics Reader and Microsoft Sentinel Responder), chosen as the minimum needed to read evidence and write the assessment

---

## What it demonstrates

- **SOC automation / SOAR** — Sentinel Automation Rules, Logic App playbooks, and event-driven Azure Functions wired into one autonomous workflow (this project aligns directly with the Microsoft SC-200 Security Operations Analyst certification)
- **Secure AI integration** — a strict architectural boundary between AI-generated explanation and rule-based decision, so the model can never take an action; the enterprise-ready pattern for putting LLMs into security operations
- **Cloud security architecture** — credential-free managed-identity authentication, least-privilege RBAC, and an attributable audit trail (every automated action is written back under the managed identity's own name, not an anonymous key)
- **Resilience engineering** — graceful degradation when the LLM is unavailable, and a diagnosed-and-fixed timing race between incident creation and data availability, resolved with a bounded delay and documented with measured evidence
- **Detection-to-response translation** — turning the alerts from a detection pack into an operational response capability, an underrepresented skill in most security portfolios

The frameworks the work aligns to: OWASP Agentic Top 10, MITRE ATT&CK, MITRE ATLAS. The technical stack: Microsoft Sentinel, Logic Apps, Azure Functions (Python), Azure Entra ID, KQL.

---

## How it fits in the broader portfolio

This is the fifth and final project in a five-project arc on AI agent security:

| Phase       | Project                                                                                                                                               | Focus                                                        |
| ----------- | ----------------------------------------------------------------------------------------------------------------------------------------------------- | ------------------------------------------------------------ |
| Use         | [Mastering SOC Agentic AI](https://modern-character-425.notion.site/Ray-Gonsalves-2394b1f7c9ba8043a797f55386422214)                                   | Using AI agents in production SOC workflows                  |
| Defend      | [Defending Agentic AI](https://github.com/raymondgonsalves/Defending_Agentic_AI)                                                                      | Policy-gated AI agent triage with human approval gates       |
| Analyze     | [Tool Shadowing Threat Model](https://modern-character-425.notion.site/Tool-Shadowing-Attack-MCP-Connected-AI-Agent-3584b1f7c9ba804483d1e1aa5fb148f6) | Written threat model report on the attack class              |
| Detect      | [MCP Tool Shadowing Detection Pack](https://github.com/raymondgonsalves/mcp-tool-shadowing-detections)                                                | Operational detection rules for the attack                   |
| **Respond** | **MCP Alert Triage Automation (this project)**                                                                                                        | **Autonomous triage and response to the detected incidents** |

Together they show the full lifecycle: how to use these systems, how to defend them, how to analyze new attacks against them, how to detect those attacks in operational telemetry, and how to respond to them autonomously.

---

## Architecture at a glance

[![Architecture Diagram](https://github.com/raymondgonsalves/mcp-alert-triage-automation/raw/main/docs/figures/architecture_overview.svg)](https://github.com/raymondgonsalves/mcp-alert-triage-automation/blob/main/docs/figures/architecture_overview.svg)

*The response pipeline, end to end: a Sentinel detection fires, an Automation Rule triggers the Logic App playbook, the playbook invokes the Python Azure Function under managed-identity authentication, and the Function reconstructs the session, scores it, narrates the verdict, and writes the pre-assessment back to the incident.*

---

## Where to look

- [`README.md`](https://github.com/raymondgonsalves/mcp-alert-triage-automation/blob/main/README.md) — full technical overview including the architecture, the bounded-LLM design, and the security model
- [`SETUP.md`](https://github.com/raymondgonsalves/mcp-alert-triage-automation/blob/main/SETUP.md) — reproducibility guide: prerequisites, deploy steps, RBAC grants, and what's lab-specific vs. portable
- [`function_app/`](https://github.com/raymondgonsalves/mcp-alert-triage-automation/tree/main/function_app) — the Python Azure Function: session reconstruction, the deterministic scorer, and the bounded LLM narrator
- [`playbooks/`](https://github.com/raymondgonsalves/mcp-alert-triage-automation/tree/main/playbooks) — the Logic App playbook definition

---

## Contact

Ray Gonsalves &nbsp;|&nbsp; [LinkedIn](https://www.linkedin.com/in/raymond-gonsalves) &nbsp;|&nbsp; [Portfolio on Notion](https://modern-character-425.notion.site/Ray-Gonsalves-2394b1f7c9ba8043a797f55386422214)
