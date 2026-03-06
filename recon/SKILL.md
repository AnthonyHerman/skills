---
name: recon
description: Bug bounty and attack-surface reconnaissance. Deliberative orchestrator that observes existing state, confirms a plan, and dispatches sub-agents per phase.
---

# Recon — Architecture

## Execution Model

The `/recon` command is an **orchestrator**. It does not run phases directly.

1. **Observe** — inspect `results/<target>/` for existing outputs per phase.
2. **Plan** — build a state map: SKIP (results exist), PENDING (missing), FORCE (re-run requested).
3. **Confirm** — present the map to the user and wait.
4. **Dispatch** — spawn sub-agents for PENDING/FORCE phases, respecting the dependency graph.
5. **Refresh vault** — incrementally after each wave completes.
6. **Synthesize** — generate `report.md` and final vault refresh after all sub-agents return.

## Dependency Graph

```
Wave 1 ─────────────────────────────────────────
  seed-discovery        github-intel
        │                     │
Wave 2 ─────────────────────────────────────────
  subdomain-enum        cloud-enum
        │
Wave 3 ─────────────────────────────────────────
  http-probe    port-scan    subdomain-takeover
        │
        ├── vault refresh (hosts, ports, tech) ──
        │
Wave 4 ─────────────────────────────────────────
  js-analysis   content-discovery   browser-mapping
        │              │
        ├── vault refresh (endpoints, JS, browser) ─
        │
Wave 5 ─────────────────────────────────────────
  api-discovery
        │
        ├── vault refresh (API routes, schemas) ─
        │
Synthesis ──────────────────────────────────────
  report.md     final vault refresh
```

Phases within the same wave run in parallel.

## Phase Table

| # | Phase | Key Outputs | Depends On | Reference |
|---|-------|-------------|------------|-----------|
| 1 | seed-discovery | `seeds.txt` | — | `references/seed-discovery.md` |
| 1 | github-intel | `github-intel.txt`, `github-secrets.txt` | — | `references/github-intel.md` |
| 2 | subdomain-enum | `subdomains.txt` | `seeds.txt` | `references/subdomain-enum.md` |
| 2 | cloud-enum | `cloud-assets.txt` | `seeds.txt` | `references/cloud-enum.md` |
| 3 | http-probe | `live-hosts.txt`, `technologies.json` | `subdomains.txt` | `references/http-probe.md` |
| 3 | port-scan | `ports.txt` | `subdomains.txt` | `references/port-scan.md` |
| 3 | subdomain-takeover | `takeovers.txt` | `subdomains.txt` | `references/subdomain-takeover.md` |
| 4 | js-analysis | `js-files.txt`, `js-endpoints.txt`, `js-secrets.txt` | `live-hosts.txt` | `references/js-analysis.md` |
| 4 | content-discovery | `urls.txt`, `params.txt`, `interesting/` | `live-hosts.txt`, `technologies.json` | `references/content-discovery.md` |
| 4 | browser-mapping | `browser-relationships.json`, `network-requests.json`, `cookies.json`, `frames.json`, `api-routes.txt` | `live-hosts.txt` | `references/browser-mapping.md` |
| 5 | api-discovery | `api-endpoints.txt`, `graphql-schemas/`, `swagger-files/` | `js-endpoints.txt`, `live-hosts.txt`, `technologies.json` | `references/api-discovery.md` |
| — | report | `report.md` | all above | orchestrator synthesizes |
| — | mapping | `vault/` | all above | `references/mapping.md` |

## Output Contract

All results go under `results/<target>/` relative to the repo root.

- Files are append-only and deduplicated (`sort -u`).
- Do not overwrite useful prior results unless user requests `--fresh`.
- Remove empty output files after each phase.
- The vault refreshes incrementally — not just at the end.

## Vault as Living Map

The vault (`results/<target>/vault/`) is an Obsidian-compatible knowledge graph.
It is refreshed **after waves 3, 4, and 5** so it always reflects current state.

The vault links: hosts, technologies, findings, origins, browser edges, API routes,
JS-discovered endpoints, cloud assets, and GitHub intelligence.

An operator reviewing the vault mid-run can redirect remaining phases.

Use `python3 recon/scripts/build_vault.py <target>` for vault generation.

## Tool Inventory

Before dispatching, the orchestrator checks tool availability. Missing tools are warnings — every phase has fallbacks documented in its reference file.

| Phase | Primary Tools | Fallbacks |
|-------|--------------|-----------|
| seed-discovery | `whois`, `asnmap`, `amass` | `curl` + crt.sh API |
| github-intel | `gh`, `trufflehog` | `curl` + GitHub search API |
| subdomain-enum | `subfinder`, `assetfinder`, `amass`, `dnsx` | `curl` + crt.sh, `host` |
| cloud-enum | `cloud_enum`, `s3scanner` | `curl` + DNS CNAME checks |
| http-probe | `httpx` | `curl` |
| port-scan | `nmap`, `masscan` | `nmap` only |
| subdomain-takeover | `nuclei` | `dig` + CNAME fingerprints |
| js-analysis | `katana`, `linkfinder`, `trufflehog` | `curl` + `grep` |
| content-discovery | `feroxbuster`, `katana`, `gau`, `waybackurls`, `gf` | `curl` + manual wordlists |
| browser-mapping | `chrome-devtools` MCP, `python3` | `python3` only (degraded) |
| api-discovery | `kiterunner`, `nuclei`, `graphql-cop` | `curl` + manual probing |
| mapping | `python3 recon/scripts/build_vault.py` | direct markdown writes |

Use `references/setup.md` when tools or wordlists need installing.

## Operating Rules

- Assume user has permission and is targeting their own assets or authorized scopes.
- Prefer passive collection first, then active techniques with conservative timeouts and thread counts.
- Skip installation during recon execution unless the caller explicitly asks.
- Remove wildcard entries and obvious out-of-scope domains.
- Normalize URLs, exclude obvious static assets, remove empty output files.
- Report counts and skipped steps after each phase.
