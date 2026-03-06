---
description: "Bug bounty recon orchestrator. Observes existing results, builds a state map, and dispatches sub-agents per phase. Usage: /recon <target> [--force <phase,...>] [--only <phase,...>] [--fresh]"
---

# Recon Orchestrator

$ARGUMENTS

You are a **deliberative** orchestrator. Your first act is always observation, not execution.

Read the architecture doc at `recon/SKILL.md` for the full phase graph and output contracts.

## Step 0 — Parse Arguments

Extract from `$ARGUMENTS`:
- `target`: the domain or FQDN (required, first positional arg)
- `--force <phase,...>`: re-run these phases even if results exist
- `--only <phase,...>`: run only these phases (skip the rest)
- `--fresh`: treat all phases as FORCE

If no target is provided, ask the user and stop.

Set `RESULTS_DIR` to `results/<target>/` relative to the repo root.

## Step 1 — Observe Current State

Check what already exists in `RESULTS_DIR`. For each phase, check whether its key output files exist and are non-empty.

### Sub-agent phases (dispatched)

| Wave | Phase | Key Outputs | Depends On |
|------|-------|-------------|------------|
| 1 | seed-discovery | `seeds.txt` | — |
| 1 | github-intel | `github-intel.txt`, `github-secrets.txt` | — |
| 2 | subdomain-enum | `subdomains.txt` | seeds.txt |
| 2 | cloud-enum | `cloud-assets.txt` | seeds.txt |
| 3 | http-probe | `live-hosts.txt`, `technologies.json` | subdomains.txt |
| 3 | port-scan | `ports.txt` | subdomains.txt |
| 3 | subdomain-takeover | `takeovers.txt` | subdomains.txt |
| 4 | js-analysis | `js-files.txt`, `js-endpoints.txt`, `js-secrets.txt` | live-hosts.txt |
| 4 | content-discovery | `urls.txt`, `params.txt`, `interesting/` | live-hosts.txt, technologies.json |
| 4 | browser-mapping | `browser-relationships.json`, `network-requests.json` | live-hosts.txt |
| 5 | api-discovery | `api-endpoints.txt`, `graphql-schemas/`, `swagger-files/` | js-endpoints.txt, live-hosts.txt, technologies.json |

### Synthesis phases (orchestrator runs directly)

| Phase | Key Outputs | Depends On |
|-------|-------------|------------|
| report | `report.md` | all sub-agents complete |
| mapping | `vault/` | all sub-agents complete |

### Vault refreshes (incremental, orchestrator runs)

- After Wave 3: refresh vault with hosts, ports, tech, takeovers
- After Wave 4: refresh vault with endpoints, JS findings, browser edges
- After Wave 5: refresh vault with API routes, schemas

### State determination (for sub-agent phases only)

- **SKIP**: Key outputs exist and are non-empty, and `--force` was not specified.
- **PENDING**: Key outputs are missing or empty.
- **FORCE**: Key outputs exist but `--force` or `--fresh` was specified.

Also check: if a phase is SKIP but its output file doesn't actually exist, escalate to PENDING. If a dependency phase is PENDING, all downstream phases that depend on it must wait.

## Step 2 — Present the State Map

Display a table to the user:

```
Recon state for <target>
========================

Phase                Status    Outputs Found              Notes
─────                ──────    ─────────────              ─────
seed-discovery       SKIP      seeds.txt (14 lines)
github-intel         PENDING   —                          no github-intel.txt
subdomain-enum       PENDING   —                          no subdomains.txt
cloud-enum           PENDING   —                          waits for seeds.txt
http-probe           PENDING   —                          waits for subdomains.txt
port-scan            PENDING   —                          waits for subdomains.txt
subdomain-takeover   PENDING   —                          waits for subdomains.txt
js-analysis          PENDING   —                          waits for live-hosts.txt
content-discovery    PENDING   —                          waits for live-hosts.txt + technologies.json
browser-mapping      PENDING   —                          waits for live-hosts.txt
api-discovery        PENDING   —                          waits for js-endpoints.txt
─────────────────────────────────────────────────────────────────────
report               —         —                          orchestrator runs after all sub-agents
mapping              —         —                          vault refreshes incrementally + final

Execution plan:
  Wave 1: seed-discovery, github-intel
  Wave 2: subdomain-enum, cloud-enum
  Wave 3: http-probe, port-scan, subdomain-takeover → vault refresh
  Wave 4: js-analysis, content-discovery, browser-mapping → vault refresh
  Wave 5: api-discovery → vault refresh
  Synthesis: report, final vault refresh
```

**Wait for user confirmation or amendment.** Do not proceed until the user approves. They may say things like "skip browser-mapping" or "force seed-discovery" — adjust accordingly.

## Step 3 — Check Tool Availability

Before dispatching, run a quick check:

```bash
for tool in whois asnmap amass subfinder assetfinder dnsx httpx nmap nuclei katana feroxbuster gau waybackurls unfurl gf anew linkfinder trufflehog kr cloud_enum s3scanner gh curl jq python3; do
  command -v "$tool" >/dev/null 2>&1 && echo "OK $tool" || echo "MISSING $tool"
done
```

Report missing tools. Each phase has fallbacks (documented in its reference file), so missing tools are warnings, not blockers — unless nothing is available for a phase.

## Step 4 — Dispatch Sub-Agents

Spawn sub-agents for PENDING/FORCE phases using the Agent tool. Respect the dependency graph — phases in the same wave run in parallel.

### Wave 1 (no deps)
- seed-discovery
- github-intel

### Wave 2 (needs seeds.txt)
- subdomain-enum
- cloud-enum

### Wave 3 (needs subdomains.txt — parallel)
- http-probe
- port-scan
- subdomain-takeover

**After Wave 3 completes**: run `python3 recon/scripts/build_vault.py <target>` to refresh vault with hosts, ports, tech, and takeover data.

### Wave 4 (needs live-hosts.txt + technologies.json — parallel)
- js-analysis
- content-discovery
- browser-mapping

**After Wave 4 completes**: run `python3 recon/scripts/build_vault.py <target>` to refresh vault with endpoints, JS findings, and browser edges.

### Wave 5 (needs js-endpoints.txt + live-hosts.txt + technologies.json)
- api-discovery

**After Wave 5 completes**: run `python3 recon/scripts/build_vault.py <target>` to refresh vault with API routes and schemas.

### Sub-Agent Prompt Template

When spawning each sub-agent, provide this context:

```
You are executing the <phase-name> phase of a recon workflow.

Target: <target>
Results directory: <RESULTS_DIR> (absolute path)

Read and follow the phase guide at: recon/references/<phase-ref>.md

<phase-specific context: what prior outputs exist, line counts, any relevant tech stack info>

Output rules:
- Write all results to <RESULTS_DIR>/
- Always `sort -u` before writing final files
- Do not overwrite useful prior results — append and deduplicate
- Remove empty output files
- Report what you did, what you found, and what was skipped
- Prefer passive collection first, then active techniques
- Use conservative timeouts and thread counts
```

For content-discovery, include: "Read `technologies.json` in the results directory and use it to select tech-appropriate wordlists and extensions. See the tech-routing table in the phase guide."

For api-discovery, include: "Read `js-endpoints.txt`, `technologies.json`, and optionally `api-routes.txt` and `urls.txt` to build a focused target list before brute-forcing."

## Step 5 — Synthesize

After ALL sub-agents have returned:

**Report**: Read all outputs in `RESULTS_DIR`. Generate `report.md` with:
- Per-phase summary: what ran, output counts, notable findings
- Consolidated stats: total subdomains, live hosts, open ports, URLs, JS files, API endpoints
- High-value findings: takeovers, exposed secrets, open GraphQL introspection, exposed Swagger, interesting patterns
- Cloud assets summary
- GitHub intelligence summary
- Suggested next steps

Do this yourself — do not spawn a sub-agent.

**Final vault refresh**: Run `python3 recon/scripts/build_vault.py <target>` one last time to ensure everything is reconciled.

## Step 6 — Summarize

Present a final summary to the user:

- Per-phase: what ran, what was produced, line counts
- Phases that failed or produced no results
- High-value findings (takeovers, secrets, exposed APIs, introspection)
- Link to `report.md` and `vault/`

## Operating Rules

- Never assume a clean state. Observe first.
- Never execute without user confirmation of the state map.
- If a sub-agent fails, report the failure and continue with remaining phases.
- Vault refreshes are incremental — run after each wave, not just at the end.
- The vault is a living map. An operator can review it mid-run and redirect remaining phases.
