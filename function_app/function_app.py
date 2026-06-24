import azure.functions as func
import json
import logging
import uuid

import requests
from azure.identity import DefaultAzureCredential

app = func.FunctionApp()

# Azure Resource Manager scope + base URL for the Sentinel REST API.
ARM_SCOPE = "https://management.azure.com/.default"
ARM_BASE = "https://management.azure.com"
# Incident comments API version (stable).
API_VERSION = "2023-11-01"

# One credential per process. DefaultAzureCredential resolves to the developer's
# az-login identity locally and to the Function App's managed identity once
# deployed -- the same code path works in both environments.
_credential = DefaultAzureCredential()


@app.route(route="triage", auth_level=func.AuthLevel.FUNCTION)
def triage(req: func.HttpRequest) -> func.HttpResponse:
    """Sprint 1 walking skeleton.

    Receives an incident ARM resource ID and a SessionId, then writes a stub
    comment back to that Microsoft Sentinel incident. No enrichment, no scoring,
    no LLM -- this exists only to prove the auth / RBAC / write-back seam.
    """
    try:
        body = req.get_json()
    except ValueError:
        return func.HttpResponse(
            "Request body must be JSON.", status_code=400
        )

    incident_arm_id = body.get("incidentArmId")
    session_id = body.get("sessionId")

    if not incident_arm_id or not session_id:
        return func.HttpResponse(
            "Missing required fields: 'incidentArmId' and 'sessionId'.",
            status_code=400,
        )

    logging.info("Triage stub invoked for SessionId=%s", session_id)

    # Acquire an ARM token (developer identity locally, managed identity in Azure).
    try:
        token = _credential.get_token(ARM_SCOPE).token
    except Exception as exc:  # noqa: BLE001 - surface auth failures plainly
        logging.exception("Failed to acquire ARM token")
        return func.HttpResponse(
            f"Auth failed: {exc}", status_code=500
        )

    # The incident comments collection lives under the incident's ARM path.
    # A comment needs a unique name segment; use the SessionId for traceability.
    comment_url = (
        f"{ARM_BASE}{incident_arm_id}/comments/skeleton-{uuid.uuid4().hex}"
        f"?api-version={API_VERSION}"
    )

    comment_message = (
        "[Triage pipeline - Sprint 1 walking skeleton] "
        "Pipeline reached this incident and authenticated via managed identity. "
        f"SessionId: {session_id}. "
        "No enrichment, scoring, or LLM performed -- this is a write-back seam test."
    )

    payload = {"properties": {"message": comment_message}}
    headers = {
        "Authorization": f"Bearer {token}",
        "Content-Type": "application/json",
    }

    resp = requests.put(comment_url, headers=headers, json=payload, timeout=30)

    if resp.status_code in (200, 201):
        logging.info("Comment written to incident for SessionId=%s", session_id)
        return func.HttpResponse(
            json.dumps(
                {
                    "status": "ok",
                    "sessionId": session_id,
                    "httpStatus": resp.status_code,
                }
            ),
            status_code=200,
            mimetype="application/json",
        )

    logging.error(
        "Comment write failed (%s): %s", resp.status_code, resp.text
    )
    return func.HttpResponse(
        json.dumps(
            {
                "status": "error",
                "httpStatus": resp.status_code,
                "detail": resp.text,
            }
        ),
        status_code=502,
        mimetype="application/json",
    )
