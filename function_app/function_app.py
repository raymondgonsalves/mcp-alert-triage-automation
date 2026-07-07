import json
import logging
import uuid

import requests
from azure.identity import DefaultAzureCredential
from azure.monitor.query import LogsQueryClient, LogsQueryStatus

import azure.functions as func

app = func.FunctionApp()

# --- Azure Resource Manager (management plane) — used to write the comment back ---
ARM_SCOPE = "https://management.azure.com/.default"
ARM_BASE = "https://management.azure.com"
API_VERSION = "2023-11-01"

# --- Log Analytics workspace (data plane) — used to reconstruct + score the session ---
WORKSPACE_ID = "d0f3187b-ec35-4281-9cb6-52a34418236a"

# The legitimate recipient(s). A send to anything NOT on this allowlist is treated
# as a redirect. Denylist (== attacker) works for the lab, but an allowlist is the
# stronger posture: it catches UNKNOWN-bad recipients, not just the one known-bad.
LEGIT_RECIPIENTS = ("alice@mail.com",)

_credential = DefaultAzureCredential()
_logs_client = LogsQueryClient(_credential)


def _incident_guid_from_arm_id(incident_arm_id: str) -> str:
    """The incident's GUID is the final segment of its ARM resource ID."""
    return incident_arm_id.rstrip("/").rsplit("/", 1)[-1]


def _reconstruct_session_id(incident_guid: str) -> str | None:
    """Derive the real SessionId for an incident via a single data-plane query."""
    query = f"""
        let targetIncident = "{incident_guid}";
        SecurityIncident
        | where IncidentName == targetIncident
        | summarize arg_max(TimeGenerated, *) by IncidentName
        | mv-expand AlertId = todynamic(AlertIds) to typeof(string)
        | join kind=inner (
            SecurityAlert
            | where TimeGenerated > ago(30d)
            | project SystemAlertId,
                      SessionId = tostring(parse_json(tostring(
                          parse_json(ExtendedProperties)["Custom Details"]))["SessionId"][0])
          ) on $left.AlertId == $right.SystemAlertId
        | project SessionId
        | take 1
    """
    try:
        response = _logs_client.query_workspace(
            workspace_id=WORKSPACE_ID, query=query, timespan=None
        )
    except Exception:  # noqa: BLE001
        logging.exception("Session reconstruction query failed")
        return None

    if response.status != LogsQueryStatus.SUCCESS or not response.tables:
        logging.warning("Session reconstruction returned no successful result")
        return None
    table = response.tables[0]
    if not table.rows:
        logging.warning("No SessionId found for incident %s", incident_guid)
        return None
    session_id = table.rows[0][0]
    return str(session_id) if session_id else None


def _as_list(value) -> list:
    """Normalize a make_set() column to a real Python list.

    The Azure Monitor SDK may return a dynamic array either as a JSON string
    (e.g. '["a","b"]') or as an already-parsed list. Calling list() on the
    string form would iterate it character-by-character (a bug); json.loads
    parses it correctly. This helper handles both shapes safely.
    """
    if value is None:
        return []
    if isinstance(value, list):
        return value
    if isinstance(value, str):
        try:
            parsed = json.loads(value)
            return parsed if isinstance(parsed, list) else [parsed]
        except (ValueError, TypeError):
            return [value]
    return [value]


def _gather_session_facts(session_id: str) -> dict | None:
    """Gather the complete per-session scoring input (layer-presence + realized-impact).

    Runs the verified combined query: layer-presence facts from SecurityAlert joined
    (leftouter) to realized-impact facts from MCPProtocolLogs_CL, one row per session.
    Returns a plain dict of facts (no Azure types), or None if the session isn't found.
    """
    query = f"""
        let targetSession = "{session_id}";
        let recipientFacts =
            MCPProtocolLogs_CL
            | where TimeGenerated > ago(30d)
            | where EventType == "ToolCallInvoked" and ToolName == "send_email"
            | where SessionId == targetSession
            | extend Recipient = tostring(parse_json(CallParameters)["recipient"])
            | summarize
                SentToAttacker = countif(Recipient != "alice@mail.com"),
                TotalSends     = count(),
                Recipients     = make_set(Recipient)
                by SessionId
            | extend RealizedBreach = SentToAttacker > 0;
        SecurityAlert
        | where TimeGenerated > ago(30d)
        | extend SessionId = tostring(parse_json(tostring(
              parse_json(ExtendedProperties)["Custom Details"]))["SessionId"][0])
        | where SessionId == targetSession
        | summarize
            R1 = countif(AlertName has "poisoned tool description"),
            R2 = countif(AlertName has "cross-tool reference"),
            R3 = countif(AlertName has "tool description drift"),
            R4 = countif(AlertName has "redirected to attacker"),
            AllRulesFired = make_set(AlertName)
            by SessionId
        | extend
            IngestionSignals = toint(R1 > 0) + toint(R2 > 0) + toint(R3 > 0),
            ExecutionFired   = R4 > 0
        | join kind=leftouter (recipientFacts) on SessionId
        | extend
            RealizedBreach = coalesce(RealizedBreach, false),
            SentToAttacker = coalesce(SentToAttacker, 0),
            TotalSends     = coalesce(TotalSends, 0)
        | project SessionId, IngestionSignals, ExecutionFired, RealizedBreach,
                  SentToAttacker, TotalSends, AllRulesFired, Recipients
        | take 1
    """
    try:
        response = _logs_client.query_workspace(
            workspace_id=WORKSPACE_ID, query=query, timespan=None
        )
    except Exception:  # noqa: BLE001
        logging.exception("Session facts query failed")
        return None

    if response.status != LogsQueryStatus.SUCCESS or not response.tables:
        logging.warning("Session facts query returned no successful result")
        return None
    table = response.tables[0]
    if not table.rows:
        logging.warning("No facts found for session %s", session_id)
        return None

    # Map the single result row (by column name) into a plain dict.
    cols = [c for c in table.columns]
    row = table.rows[0]
    record = dict(zip(cols, row))
    return {
        "session_id": session_id,
        "ingestion_signals": int(record.get("IngestionSignals") or 0),
        "execution_fired": bool(record.get("ExecutionFired")),
        "realized_breach": bool(record.get("RealizedBreach")),
        "sent_to_attacker": int(record.get("SentToAttacker") or 0),
        "total_sends": int(record.get("TotalSends") or 0),
        "rules_fired": _as_list(record.get("AllRulesFired")),
        "recipients": _as_list(record.get("Recipients")),
    }


def score_session(facts: dict) -> tuple[str, str]:
    """Deterministic severity scoring — a PURE function (no I/O, fully unit-testable).

    Decision table (RealizedBreach dominates; then execution; then corroboration):
      RealizedBreach          -> CRITICAL  (redirect executed to a non-legitimate recipient)
      ExecutionFired (no breach)-> HIGH     (redirect detected, recipient legitimate: attempted/defended)
      IngestionSignals >= 2    -> MEDIUM    (corroborated ingestion, not executed)
      IngestionSignals == 1    -> LOW       (single ingestion signal)
      otherwise                -> INFORMATIONAL

    Returns (severity, human-readable reasoning).
    """
    ingestion = facts["ingestion_signals"]
    execution = facts["execution_fired"]
    breach = facts["realized_breach"]

    if breach:
        return (
            "Critical",
            f"Realized breach: {facts['sent_to_attacker']} of {facts['total_sends']} "
            f"send_email calls went to a non-legitimate recipient "
            f"({', '.join(facts['recipients'])}). The redirect executed — data left to an attacker.",
        )
    if execution:
        return (
            "High",
            "Redirect detected (execution-layer rule fired) but all sends went to the "
            "legitimate recipient — attack attempted but defended (no realized impact).",
        )
    if ingestion >= 2:
        return (
            "Medium",
            f"Corroborated ingestion: {ingestion} independent ingestion-layer signals agree "
            f"({'; '.join(facts['rules_fired'])}). Tool description poisoned; no execution observed.",
        )
    if ingestion == 1:
        return (
            "Low",
            f"Single ingestion signal ({'; '.join(facts['rules_fired'])}). "
            "Possible poisoning, low corroboration; no execution observed.",
        )
    return (
        "Informational",
        "No ingestion or execution signals scored for this session.",
    )


def _build_comment(session_id: str, severity: str, reasoning: str, facts: dict) -> str:
    """Human-in-the-loop presentation: severity WITH its reasoning and evidence anchor."""
    return (
        f"[Triage pipeline - Sprint 3 deterministic pre-assessment] "
        f"Severity: {severity.upper()}. "
        f"{reasoning} "
        f"Session: {session_id}. "
        f"Evidence — rules fired: {facts.get('rules_fired')}; recipients: {facts.get('recipients')}. "
        f"This is a deterministic, rule-based pre-assessment to aid triage; "
        f"final disposition requires analyst review."
    )


@app.route(route="triage", auth_level=func.AuthLevel.FUNCTION)
def triage(req: func.HttpRequest) -> func.HttpResponse:
    """Sprint 3 — deterministic recipient-aware scoring.

    incident -> SessionId (Sprint 2) -> gather per-session facts -> deterministic score
    -> write severity + reasoning back to the incident. Still no LLM (that is Sprint 4).
    """
    try:
        body = req.get_json()
    except ValueError:
        return func.HttpResponse("Request body must be JSON.", status_code=400)

    incident_arm_id = body.get("incidentArmId")
    if not incident_arm_id:
        return func.HttpResponse("Missing required field: 'incidentArmId'.", status_code=400)

    incident_guid = _incident_guid_from_arm_id(incident_arm_id)
    logging.info("Triage invoked for incident %s", incident_guid)

    # --- Data plane: reconstruct SessionId, then gather facts, then score ---
    session_id = _reconstruct_session_id(incident_guid)

    if not session_id:
        comment_message = (
            "[Triage pipeline - Sprint 3] Pipeline reached this incident, but no SessionId "
            "could be reconstructed (no matching alert in the lookback window). Manual review suggested."
        )
        severity = None
    else:
        facts = _gather_session_facts(session_id)
        if facts is None:
            comment_message = (
                f"[Triage pipeline - Sprint 3] Session {session_id} reconstructed, but no "
                "scoring facts could be gathered. Manual review suggested."
            )
            severity = None
        else:
            severity, reasoning = score_session(facts)
            comment_message = _build_comment(session_id, severity, reasoning, facts)
            logging.info("Scored session %s as %s", session_id, severity)

    # --- Management plane: write the comment back (Sentinel Responder role) ---
    try:
        token = _credential.get_token(ARM_SCOPE).token
    except Exception as exc:  # noqa: BLE001
        logging.exception("Failed to acquire ARM token")
        return func.HttpResponse(f"Auth failed: {exc}", status_code=500)

    comment_url = (
        f"{ARM_BASE}{incident_arm_id}/comments/triage-{uuid.uuid4().hex}"
        f"?api-version={API_VERSION}"
    )
    payload = {"properties": {"message": comment_message}}
    headers = {"Authorization": f"Bearer {token}", "Content-Type": "application/json"}
    resp = requests.put(comment_url, headers=headers, json=payload, timeout=30)

    if resp.status_code in (200, 201):
        logging.info("Comment written for incident %s", incident_guid)
        return func.HttpResponse(
            json.dumps({
                "status": "ok",
                "incidentGuid": incident_guid,
                "sessionId": session_id,
                "severity": severity,
                "httpStatus": resp.status_code,
            }),
            status_code=200,
            mimetype="application/json",
        )

    logging.error("Comment write failed (%s): %s", resp.status_code, resp.text)
    return func.HttpResponse(
        json.dumps({"status": "error", "httpStatus": resp.status_code, "detail": resp.text}),
        status_code=502,
        mimetype="application/json",
    )
