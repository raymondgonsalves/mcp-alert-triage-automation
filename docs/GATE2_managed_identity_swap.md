# Gate 2: playbook → Function auth — function key → managed identity

**Date:** 2026-07-15
**Status:** CLOSED and verified. The playbook→Function hop no longer uses a shared secret;
authentication is managed-identity / Microsoft Entra (Easy Auth). The previously-used
function key has been rotated and confirmed dead (returns 401).

## Why this gate existed

The Logic App playbook (`pb-mcp-triage-skeleton`) called the Azure Function
(`func-mcp-triage-lab-rg`) with a **function key** embedded in the request URI
(`?code=<key>`). That key lives in the playbook's ARM/Logic App definition — so exporting
that definition to a public repo would publish the secret. The gate: swap the hop to
identity-based auth and remove the key **before** any public publish.

## End state (what "closed" means)

- The playbook's HTTP action URI is the bare endpoint — `.../api/triage`, no `?code=`.
- The playbook authenticates with its **system-assigned managed identity**, presenting an
  Entra token for audience `api://<function-app-registration-client-id>`.
- The Function App has **App Service Authentication (Easy Auth)** enabled with a Microsoft
  identity provider; it validates the token and rejects everything else with 401.
- The Function's own `authLevel` is **ANONYMOUS** — required, because with Easy Auth in
  front, a function-key check would cause a BadRequest. Easy Auth is the gatekeeper now, not
  the key. "Anonymous" here means "don't *also* require a function key on top of the token,"
  not "open" — unauthenticated calls still get 401 from Easy Auth.
- The old function key has been rotated; calling with it (or any key) returns 401.

## The swap sequence (order matters)

1. **Playbook managed identity** — already enabled (system-assigned). Confirmed via
   `az rest ... /workflows/pb-mcp-triage-skeleton` → `identity.principalId`.
2. **Easy Auth on the Function** — Authentication → Add identity provider → Microsoft.
   Created a new app registration for the Function. Set: Require authentication;
   Unauthenticated requests → **HTTP 401** (it's an API, not a website); tenant-restricted to
   the home tenant.
3. **Function `authLevel` FUNCTION → ANONYMOUS** — code change (the `@app.route` decorator),
   redeployed. Required for the managed-identity flow per Microsoft's docs.
4. **Playbook HTTP action → managed identity** — stripped `?code=` from the URI; added
   Authentication = Managed Identity, System-assigned, Audience =
   `api://<function-client-id>`. Published (draft ≠ live).
5. **Allowed client applications** — on the Function's Easy Auth, allow the playbook's
   identity (see the ID gotcha below).
6. **Verify** — re-ran the pipeline; a new autonomous incident produced a scored, narrated
   comment written by the managed identity, key-free.
7. **Rotate the key** — killed the old value; confirmed the old key now returns 401.

## Gotchas (the parts that cost time — worth remembering)

### 1. Principal/object ID vs application/client ID
The Easy Auth "Allowed client applications" field matches against the **`appid` claim** in
the incoming token, which is the managed identity's **Application (client) ID** — NOT its
principal/object ID. The playbook's `identity.principalId` (`60ba3d22-...`) is the object ID;
its allow-list value is a *different* GUID (`3101340b-...`), retrieved via:
```bash
az ad sp show --id <principalId> --query "{appId:appId, objectId:id, displayName:displayName}"
```
Putting the principal ID in the allow-list would have caused a silent 401. Two IDs for one
identity — use the `appId` for the allow-list, the `principalId` for role assignments.

### 2. The `api://` audience prefix
The Function's `allowedAudiences` is `api://<client-id>` (with the `api://` prefix), so the
playbook's HTTP-action Audience must match exactly — `api://46439dbd-...`, not the bare GUID.
A mismatch is a 401.

### 3. `az webapp auth show` gives a misleading v1 projection of a v2 config
The Function's auth is **configVersion v2**, but `az webapp auth show` reported v1-style
fields: it showed `unauthenticatedClientAction: "RedirectToLoginPage"` and null
`globalValidation`/`identityProviders`, even though the portal (which reads v2 natively)
showed "Return HTTP 401." The CLI projection was the artifact, not the truth.

Resolved by **testing actual behavior** rather than trusting either report:
```bash
curl -s -o /dev/null -w "%{http_code}\n" "https://func-mcp-triage-lab-rg.azurewebsites.net/api/triage"
# → 401  (unauthenticated request is rejected — the setting IS in effect)
```
The HTTP response code is ground truth; the management-plane reports disagreed and one was
internally inconsistent. When reports conflict, measure the behavior.

Related: `az webapp auth update --action` is a **v1-only** command (its allowed values are
`AllowAnonymous` / `LoginWith...`, with no `Return401` option) and running it against a v2
config risks clobbering the v2 provider settings. For v2 auth fields, use the portal (it
writes v2 natively) — matching the tool to the task.

## Lessons

- **Two IDs, two purposes:** application/client ID for token-audience/allow-list matching;
  principal/object ID for RBAC role assignments. Confusing them is a silent 401.
- **Behavior over reports:** when the portal and CLI disagree (and here they did, repeatedly),
  the running system's actual HTTP response settles it. A `curl` status code beat two
  conflicting dashboards.
- **Match the tool to the task:** a v1-era CLI command can't express (and can damage) a v2
  auth config; the portal was the correct instrument for the v2 fields.
- **"Anonymous" ≠ "open":** with Easy Auth in front, the function-level anonymous setting is
  correct and *more* secure — the identity check simply moved to a different layer.

## Evidence

- figure_24 — old (rotated) function key → 401 (key auth retired)
- figure_25 — Logic App run history: HTTP action green via managed identity (incident #22 run)
- figure_26 — playbook HTTP action inputs: keyless URI + `ManagedServiceIdentity` auth,
  audience `api://46439dbd-...`

## Remaining (Sprint 5 packaging)

- The unused `MICROSOFT_PROVIDER_AUTHENTICATION_SECRET` app-setting was auto-created by the
  Easy Auth wizard. It is not used by the managed-identity flow. Leave it; never export its
  value. (Its *name* in config is harmless; its *value* must never be committed.)
- Exporting the playbook definition to the repo is now safe (no key in the URI), but the
  export must still be scanned to confirm no `?code=` remnant and no secret *value* is dragged
  in via the provider-secret setting.
