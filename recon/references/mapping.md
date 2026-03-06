# Recon Mapping

Use this phase after recon output exists and the caller wants a graph-oriented note vault.

## Inputs

- `live-hosts.txt`
- optional `technologies.json`
- optional `urls.txt`
- optional `js-files.txt`
- optional `subdomains.txt`
- optional `ports.txt`
- optional `interesting/*.txt`
- optional `browser-relationships.json`
- optional `network-requests.json`
- optional `cookies.json`
- optional `frames.json`
- optional `origins.txt`

## Goal

Create a note vault where hosts, technologies, and findings are linked as entities so the graph shows architecture, relationships, and finding clusters.

When browser mapping output exists, extend the vault with runtime trust and dependency edges so the graph also shows cross-origin, iframe, cookie-scope, redirect, and API relationships.

## Vault Shape

```text
vault/
  hosts/
  tech/
  findings/
  origins/
  browser/
  _index.md
```

Use `notesmd-cli` when available. Otherwise write Markdown files directly.

Preferred implementation in this repo:

```bash
python3 recon/scripts/build_vault.py <target>
python3 recon/scripts/build_vault.py <target> --vault-name <notesmd-vault-name>
```

This writes a repo-local vault to `results/<target>/vault/` and, when `--vault-name` is provided, also creates matching notes through `notesmd-cli`.

Refresh the vault after browser mapping and after content discovery when those phases add or change:

- `browser-relationships.json`
- `network-requests.json`
- `api-routes.txt`
- `forms.txt`
- `origins.txt`

## Host Notes

Create one note per live host and include:

- status and interest metadata when known
- links to technologies
- top endpoints for that host
- linked findings
- open ports
- connections to other hosts inferred from JS, redirects, or cross-origin references
- browser/runtime edges such as `calls-api`, `loads-from`, `embeds`, `posts-form-to`, and `shares-session-scope-with`
- runtime API routes observed in `network-requests.json` and `api-routes.txt`

Sanitize note names by replacing `:` with `-`.

## Technology Notes

Create one note per unique technology and link every host that uses it.

## Origin Notes

When browser mapping output exists, create one note per observed origin and include:

- incoming edges such as `allows-origin`, `embedded-by`, and `calls-api`
- outgoing edges such as `redirects-to`
- link back to the owning host note when the origin hostname matches a live host

## Browser Notes

Always write:

- `browser/relationships.md`: collector status, edge counts, and captured pages
- `browser/captures.md`: one-line capture summaries per page

These notes should help the Obsidian graph expose runtime relationships even before opening individual host notes.

## Finding Notes

Create one note per non-empty file in `interesting/` and link affected hosts.

Severity defaults:

- high: `xss`, `sqli`, `ssrf`, `lfi`
- medium: `idor`, `redirect`
- low: `debug`

## Index Note

Create `_index.md` with:

- generation timestamp
- counts for hosts, technologies, findings, and URLs
- links to all host, technology, finding, and origin notes

## Connection Detection

Prioritize:

1. cross-origin URLs extracted from JavaScript
2. redirect chains
3. API or frontend naming patterns such as `api`, `gateway`, `app`, `dashboard`
4. shared infrastructure signals like common IPs, headers, or stacks

If the caller cares about browser trust boundaries or application-to-application relationships, extend the mapping with:

- CORS headers such as `Access-Control-Allow-Origin` and `Access-Control-Allow-Credentials`
- framing controls such as `Content-Security-Policy: frame-ancestors` and `X-Frame-Options`
- redirect targets across hostnames
- JavaScript references to external origins and `/api/` endpoints

These are relationship signals, not findings by themselves.

## Rules

- Remove empty sections from notes.
- For very large targets, summarize low-interest hosts in a bulk note.
- Limit endpoint lists per host to keep notes readable.
