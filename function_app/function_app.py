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

# --- Log Analytics workspace (data plane) — used to reconstruct the session ---
# The workspace GUID that holds the incidents and MCPProtocolLogs_CL.
WORKSPACE_ID = "d0f3187b-ec35-4281-9cb6-52a34418236a"

# One credential per process. DefaultAzureCredential resolves to the developer's
# az-login identity locally and to the Function App's managed identity once
# deployed -- the same code path works in both environments, for BOTH the
# management-plane call (comment write, via the token below) and the data-plane
# call (log query, via LogsQueryClient below).
_credential = DefaultAzureCredential()
_logs_client = LogsQueryClient(_credential)


def _incident_guid_from_arm_id(incident_arm_id: str) -> str:
    """The incident's GUID is the final segment of its ARM resource ID."""
    return incident_arm_id.rstrip("/").rsplit("/", 1)[-1]


def _reconstruct_session_id(incident_guid: str) -> str | None:
    """Derive the real SessionId for an incident via a single data-plane query.

    Bridges incident -> its alert -> the SessionId in the alert's custom details,
    entirely server-side (correlation + nested-JSON extraction both in KQL).
    Returns the SessionId string, or None if it cannot be reconstructed.
    """
    # NOTE: incident_guid is injected via a KQL `let` bound to a string literal.
    # It originates from the incident ARM ID (an Azure-issued GUID), not free-form
    # user input; still, it is only ever used as a GUID equality filter.
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
            workspace_id=WORKSPACE_ID,
            query=query,
            timespan=None,  # the query bounds time itself (ago(30d))
        )
    except Exception:  # noqa: BLE001 - surface query failures in logs, degrade gracefully
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


@app.route(route="triage", auth_level=func.AuthLevel.FUNCTION)
def triage(req: func.HttpRequest) -> func.HttpResponse:
    """Sprint 2 — deterministic SessionId reconstruction.

    Receives an incident ARM resource ID, derives the real SessionId from the
    log data (incident -> alert -> custom details), and writes a triage comment
    back to the incident. Still no scoring and no LLM -- this sprint proves the
    Function can faithfully reconstruct the session key from the raw data.
    """
    try:
        body = req.get_json()
    except ValueError:
        return func.HttpResponse("Request body must be JSON.", status_code=400)

    incident_arm_id = body.get("incidentArmId")
    if not incident_arm_id:
        return func.HttpResponse(
            "Missing required field: 'incidentArmId'.", status_code=400
        )

    incident_guid = _incident_guid_from_arm_id(incident_arm_id)
    logging.info("Triage invoked for incident %s", incident_guid)

    # --- Data plane: reconstruct the real SessionId (Log Analytics Reader role) ---
    session_id = _reconstruct_session_id(incident_guid)

    # Graceful degradation: still comment even if reconstruction found nothing,
    # so the analyst learns the incident was processed and what was/wasn't found.
    if session_id:
        comment_message = (
            "[Triage pipeline - Sprint 2 session reconstruction] "
            "Session reconstructed from log data via managed identity. "
            f"SessionId: {session_id}. "
            "Deterministic reconstruction only -- no scoring or LLM yet."
        )
        logging.info("Reconstructed SessionId=%s for incident %s", session_id, incident_guid)
    else:
        comment_message = (
            "[Triage pipeline - Sprint 2 session reconstruction] "
            "Pipeline reached this incident, but no SessionId could be reconstructed "
            "from the log data (no matching alert within the lookback window). "
            "Manual review suggested."
        )

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
            json.dumps(
                {
                    "status": "ok",
                    "incidentGuid": incident_guid,
                    "sessionId": session_id,  # null if reconstruction failed
                    "reconstructed": session_id is not None,
                    "httpStatus": resp.status_code,
                }
            ),
            status_code=200,
            mimetype="application/json",
        )

    logging.error("Comment write failed (%s): %s", resp.status_code, resp.text)
    return func.HttpResponse(
        json.dumps(
            {"status": "error", "httpStatus": resp.status_code, "detail": resp.text}
        ),
        status_code=502,
        mimetype="application/json",
    )
