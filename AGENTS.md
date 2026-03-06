# AGENTS.md

This repository contains recon skills for Claude Code. Start here, then follow pointers.

## How This Repo Works

Skills use a **deliberative orchestrator** pattern. The agent observes existing state,
builds a plan, confirms with the user, then dispatches sub-agents per phase.

- Architecture and phase graph: [`recon/SKILL.md`](recon/SKILL.md)
- Orchestrator entrypoint: [`.claude/commands/recon.md`](.claude/commands/recon.md)
- Tool installer: [`.claude/commands/recon-setup.md`](.claude/commands/recon-setup.md)

## Core Beliefs

1. **Observe before acting.** Never assume clean state. Inspect `results/<target>/` first.
2. **Confirm before executing.** Present a state map (SKIP/PENDING/FORCE) and wait for the user.
3. **Each sub-agent gets one job.** One phase guide, one results contract, one concern.
4. **The vault is a living map.** Refresh incrementally after each wave, not just at the end.
5. **Tech fingerprints route decisions.** Downstream phases consume `technologies.json` to select tools, wordlists, and templates.
6. **Fallbacks over failures.** Missing tools are warnings. Every phase has fallback approaches documented in its reference file.

## Phase Reference Files

Each sub-agent reads exactly one of these:

| Phase | Reference | Key Outputs |
|-------|-----------|-------------|
| seed-discovery | [`recon/references/seed-discovery.md`](recon/references/seed-discovery.md) | `seeds.txt` |
| github-intel | [`recon/references/github-intel.md`](recon/references/github-intel.md) | `github-intel.txt`, `github-secrets.txt` |
| subdomain-enum | [`recon/references/subdomain-enum.md`](recon/references/subdomain-enum.md) | `subdomains.txt` |
| cloud-enum | [`recon/references/cloud-enum.md`](recon/references/cloud-enum.md) | `cloud-assets.txt` |
| http-probe | [`recon/references/http-probe.md`](recon/references/http-probe.md) | `live-hosts.txt`, `technologies.json` |
| port-scan | [`recon/references/port-scan.md`](recon/references/port-scan.md) | `ports.txt` |
| subdomain-takeover | [`recon/references/subdomain-takeover.md`](recon/references/subdomain-takeover.md) | `takeovers.txt` |
| js-analysis | [`recon/references/js-analysis.md`](recon/references/js-analysis.md) | `js-files.txt`, `js-endpoints.txt`, `js-secrets.txt` |
| content-discovery | [`recon/references/content-discovery.md`](recon/references/content-discovery.md) | `urls.txt`, `params.txt`, `interesting/` |
| browser-mapping | [`recon/references/browser-mapping.md`](recon/references/browser-mapping.md) | `browser-relationships.json`, `network-requests.json` |
| api-discovery | [`recon/references/api-discovery.md`](recon/references/api-discovery.md) | `api-endpoints.txt`, `graphql-schemas/`, `swagger-files/` |
| mapping | [`recon/references/mapping.md`](recon/references/mapping.md) | `vault/` |

## Helper Scripts

- `recon/scripts/browser_relationships.py` — browser target selection and capture normalization
- `recon/scripts/build_vault.py` — generates Obsidian-style vault from recon outputs

## Adding a New Phase

1. Write `recon/references/<phase>.md` — self-contained guide a sub-agent can follow alone.
2. Update `recon/SKILL.md` — add to phase table, dependency graph, and output contract.
3. Update `.claude/commands/recon.md` — add to state observation, wave dispatch, and vault refresh.
4. Update this file's phase table.
