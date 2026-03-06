# Browser Relationship Mapping

Use this phase after HTTP probing when you want real runtime relationships from live hosts.

## Goal

Capture browser/runtime trust and dependency edges that passive HTTP data misses:

- CORS policy exposure
- iframe and embed relationships
- cookie scope and session-sharing signals
- redirect relationships
- frontend to backend/API calls from actual browser traffic
- form actions and third-party resource origins

## Output Location

Keep all artifacts under `results/<target>/`.

Derived outputs written by this phase:

- `browser-targets.txt`
- `browser-relationships.json`
- `network-requests.json`
- `cookies.json`
- `frames.json`
- `api-routes.txt`
- optional `forms.txt`
- optional `origins.txt`
- optional `cors-results.json`

Recommended raw capture location:

```text
results/<target>/browser/raw/
```

Store one JSON file per visited page there.

## Runtime Requirement

Preferred collector: the `chrome-devtools` MCP server in a fresh Codex session.

Do a direct collector sanity check before declaring it unavailable. A successful `chrome-devtools` action such as listing pages is sufficient. Do not treat failure of generic MCP resource-listing methods as evidence that the DevTools collector is unavailable.

If the MCP server is unavailable, the phase should still:

- write `browser-targets.txt`
- write structured JSON outputs with collector status `skipped` or `unavailable`
- add a browser section to `results/<target>/report.md`

This phase should degrade cleanly instead of failing the whole recon flow.

## Target Selection

Default to collecting from all live hosts when the host count is small or moderate and the pages are reachable without authentication.

Use a prioritized subset only when:

- the live-host set is large enough that full browser coverage is not practical in the current run
- the pages require authentication or human interaction that will dominate the budget
- the caller explicitly wants a narrow browser pass

When prioritization is necessary, prefer:

- login or app surfaces
- admin, dashboard, portal, auth, gateway, graphql, and API-adjacent hosts
- hosts returning `200`, `401`, or `403`
- canonical redirects and browser-visible block pages such as `403` or WAF denies, because they still reveal trust boundaries and routing behavior

Use the helper script:

```bash
python3 recon/scripts/browser_relationships.py <target> --collector-status unavailable --collector-reason "Chrome DevTools MCP not available in this session"
```

That writes `browser-targets.txt` even when no raw captures exist yet.

## Raw Capture Shape

The normalizer accepts flexible per-page JSON, but this structure is the intended contract:

```json
{
  "target_url": "https://app.example.com/",
  "final_url": "https://app.example.com/dashboard",
  "page": {
    "url": "https://app.example.com/dashboard",
    "title": "Dashboard",
    "forms": [
      {"action": "https://api.example.com/session", "method": "POST"}
    ],
    "frames": [
      {
        "url": "https://widgets.example.net/embed",
        "parent_url": "https://app.example.com/dashboard"
      }
    ],
    "resources": [
      {"url": "https://cdn.example.net/app.js", "type": "script"}
    ]
  },
  "network_requests": [
    {
      "url": "https://api.example.com/graphql",
      "method": "POST",
      "resource_type": "fetch",
      "status": 200,
      "request_headers": {"content-type": "application/json"},
      "response_headers": {
        "access-control-allow-origin": "https://app.example.com",
        "access-control-allow-credentials": "true"
      }
    }
  ],
  "cookies": [
    {
      "name": "sid",
      "domain": ".example.com",
      "path": "/",
      "secure": true,
      "httpOnly": true,
      "sameSite": "Lax"
    }
  ]
}
```

## MCP Collection Guidance

In a fresh session where `chrome-devtools` works:

1. Open each URL from `browser-targets.txt` or the full `live-hosts.txt` set when the scope is manageable.
2. Let the page settle after login redirects or SPA bootstrapping.
3. Collect:
   - network requests
   - cookies
   - visible forms
   - frame URLs
   - major script/image/font/frame origins
4. Save one JSON capture per page under `results/<target>/browser/raw/`.
5. Run the normalizer again without the unavailable override.
6. Refresh the mapping vault with `python3 recon/scripts/build_vault.py <target>` so API routes, origins, and browser edges appear in Obsidian notes.

## Vulnerability-Oriented Uses

Use the DevTools collector for more than relationship mapping. It is also useful for discovering candidate vulnerabilities and validation paths, including:

- hidden or JS-only API routes and unauthenticated endpoints
- CORS behavior and credentialed cross-origin requests
- iframe/embed relationships and clickjacking-relevant surfaces
- form actions, CSRF-relevant endpoints, and anti-CSRF tokens
- redirect chains, cross-origin login handoffs, and SSO routing
- third-party origins that receive sensitive identifiers or tokens
- client-side errors, debug behavior, and blocked-but-exposed endpoints
- service workers, local/session storage, and other client-side state carriers when present
- DOM-exposed secrets, config blobs, and feature flags loaded at runtime
- postMessage flows and cross-frame communication when present

## Normalization

Run:

```bash
python3 recon/scripts/browser_relationships.py <target>
```

Useful options:

- `--max-hosts 15`
- `--raw-dir results/<target>/browser/raw`
- `--collector-status partial`
- `--collector-reason "Authenticated pages were not exercised"`

## Relationship Edges

The normalizer emits edges such as:

- `allows-origin`
- `allows-credentials-for`
- `embeds`
- `embedded-by`
- `loads-from`
- `redirects-to`
- `calls-api`
- `posts-form-to`
- `sets-cookie-for`
- `shares-session-scope-with`

These are relationship signals for mapping, not automatically findings.
